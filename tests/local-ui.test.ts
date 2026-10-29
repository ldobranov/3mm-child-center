import { afterEach, beforeAll, describe, expect, it, vi } from 'vitest'
import { nextTick, ref } from 'vue'
import { mount, flushPromises } from '@vue/test-utils'
import Status from '../source/frontend/local/Status.vue'
import { UI_DEBUG_MODE } from '../source/frontend/local/use-local'
import { applicationHostKey } from '@3mm/application-ui/v1'
import Desk from '../source/frontend/local/Desk.vue'
import Registration from '../source/frontend/local/Registration.vue'
import ClientForm from '../source/frontend/local/ClientForm.vue'
import Visits from '../source/frontend/local/Visits.vue'
import Privacy from '../source/frontend/local/Privacy.vue'
import Administration from '../source/frontend/local/Administration.vue'
import Barsy from '../source/frontend/local/Barsy.vue'
import Readers from '../source/frontend/local/Readers.vue'
import Commerce from '../source/frontend/local/Commerce.vue'
import Cashier from '../source/frontend/local/Cashier.vue'
import CommerceSetup from '../source/frontend/local/CommerceSetup.vue'
import { catalogs } from '../source/frontend/local/i18n'
import { translate } from '../source/frontend/local/locale'
import { formatTimestamp } from '../source/frontend/local/time'

afterEach(() => { sessionStorage.clear(); vi.restoreAllMocks() })
// jsdom lacks native dialog presentation; browser review covers focus/top layer.
beforeAll(() => Object.defineProperties(HTMLDialogElement.prototype, {
  showModal: {configurable:true,value:function(this:HTMLDialogElement){this.open=true}},
  close: {configurable:true,value:function(this:HTMLDialogElement){this.open=false}},
}))
const keys = (names: string[]) => names.map(operation_id => ({ operation_id, kind: 'command', idempotency: 'required' }))
function host(names: string[]) {
  let locale = 'en'
  const listeners = new Set<(info: {locale: string}) => void>()
  const unsubscribe = vi.fn((listener: (info: {locale: string}) => void) => listeners.delete(listener))
  return { getInfo: vi.fn().mockResolvedValue({ operations: keys(names) }), invoke: vi.fn(),
    presentation: { version: 1, getInfo: () => ({locale}), subscribe: (listener: (info: {locale: string}) => void) => {
      listeners.add(listener); return () => unsubscribe(listener)
    } },
    setLocale(value: string) { locale = value; listeners.forEach(listener => listener({locale})) }, unsubscribe,
  }
}
function mountWith(component: any, h: any, props = {}, appearance = ref({ button: 'solid', card: 'bordered' })) {
  return mount(component, { props, global: { provide: { [applicationHostKey as symbol]: h, [Symbol.for('3mm.extension-ui.v1')]: appearance } } })
}
async function fill(form: any) {
  const inputs = form.findAll('input')
  await inputs[0].setValue('Test Parent')
  await inputs[1].setValue('00000000')
  await inputs[3].setValue('Test Child')
  await inputs[4].setValue(true)
}

describe('Local application host consumers', () => {
  it.each(['new','prepared','uncertain','zero','lost','refused','validation-lost','validation-refused'])('charges stay time with visible feedback and no duplicate send: %s',async(mode)=>{
    const id='visit_'+'1'.repeat(32),cmd='commercial_'+'2'.repeat(32),child='child_'+'3'.repeat(32)
    const h=host(['cashier_list','cashier_detail','commerce_prepare','commerce_validate','commerce_execute','commerce_check'])
    let confirmed=false
    const existing=['prepared','uncertain'].includes(mode)
    h.invoke.mockImplementation((name:string)=>{
      if(name==='cashier_list')return Promise.resolve({items:[{visit_id:id,child_name:'Child',guardian_name:'Parent',account_state:'open'}],has_more:false})
      if(name==='cashier_detail')return Promise.resolve({visit_id:id,child_id:child,child_name:'Child',guardian_name:'Parent',visit_state:'closed',parent_linked:true,
        account:{state:'open',account_id:201,time_confirmed:confirmed?1:0,quantity:confirmed?(mode==='zero'?'0':'2'):null,unit:'minutes'},choices:[],allowed_articles:[],
        members:[{visit_id:id,child_id:child,child_name:'Child',phase:'closed',duration_seconds:mode==='zero'?0:61,allowed_articles:[]}],commands:[],
        attention:existing&&!confirmed?[{command_id:cmd,kind:'time',state:mode,parameters:{minutes:2,unit:'minutes'},acknowledged:1}]:[],has_more:false})
      if(name==='commerce_prepare')return Promise.resolve(existing?{status:'rejected',data:null,message:'commerce_pending'}:{status:'applied',message:null,data:{command_id:cmd,state:'prepared'}})
      if(name==='commerce_validate'){
        if(mode==='validation-lost')return Promise.reject(new Error('lost validation'))
        if(mode==='validation-refused')return Promise.resolve({status:'rejected',data:null,message:'commerce_article_unavailable'})
        return Promise.resolve({status:'applied',message:null,data:{command_id:cmd,state:'prepared'}})
      }
      if(name==='commerce_execute'){
        if(mode==='lost')return Promise.reject(new Error('lost'))
        if(mode==='refused')return Promise.resolve({status:'rejected',data:null,message:'commerce_article_unavailable'})
        if(mode==='zero')confirmed=true
        return Promise.resolve({status:'applied',message:null,data:{state:mode==='zero'?'confirmed':'uncertain'}})
      }
      if(name==='commerce_check'){confirmed=true;return Promise.resolve({status:'applied',message:null,data:{state:'confirmed'}})}
      throw new Error('Unexpected operation '+name)
    })
    const page=mountWith(Cashier,h);await flushPromises()
    await page.findAll('button').find(b=>b.text()==='Account details')!.trigger('click');await flushPromises()
    for(const tab of ['Consumption','Payment','Commercial journal']){
      await page.get('dialog').findAll('button').find(b=>b.text()===tab)!.trigger('click')
      expect(page.get('.cc-time-charge').isVisible()).toBe(true)
    }
    const label=mode==='uncertain'?catalogs.en.commerce_check_result:catalogs.en.commerce_prepare_time
    await page.get('dialog').findAll('button').find(b=>b.text()===label)!.trigger('click');await flushPromises()
    expect(h.invoke.mock.calls.filter(c=>c[0]==='commerce_prepare')).toHaveLength(existing?0:1)
    expect(h.invoke.mock.calls.filter(c=>c[0]==='commerce_execute')).toHaveLength(mode==='uncertain'||mode.startsWith('validation-')?0:1)
    if(existing)expect(h.invoke.mock.calls.find(c=>c[0]===(mode==='prepared'?'commerce_execute':'commerce_check'))![1]).toMatchObject({command_id:cmd})
    expect(h.invoke.mock.calls.filter(c=>c[0]==='commerce_validate')).toHaveLength(mode==='uncertain'?0:1)
    if(mode==='refused'||mode==='validation-refused')expect(page.get('.cc-time-charge').text()).toContain(catalogs.en.commerce_article_unavailable)
    else if(mode==='lost'||mode==='validation-lost'){
      expect(page.get('.cc-time-charge').text()).toContain(catalogs.en.outcome_needs_review)
      expect(h.invoke.mock.calls.filter(c=>c[0]==='commerce_check')).toHaveLength(0)
    }else{
      expect(page.get('.cc-time-charge').text()).toContain(mode==='zero'?catalogs.en.commerce_time_zero:catalogs.en.commerce_time_confirmed)
      expect(h.invoke.mock.calls.filter(c=>c[0]==='commerce_check')).toHaveLength(mode==='zero'?0:1)
    }
    page.unmount()
  })

  it.each(['primary','journal','mismatch'])('uses the explicit review for a lost stay-charge acknowledgement without replay: %s',async(mode)=>{
    const prefix=mode==='journal'?'commerce':'cashier',id='visit_'+'1'.repeat(32),cmd='commercial_'+'2'.repeat(32),child='child_'+'3'.repeat(32)
    const h=host([prefix+'_list',prefix+'_detail','commerce_prepare','commerce_validate','commerce_execute','commerce_check'])
    let confirmed=false
    h.invoke.mockImplementation((name:string,payload:any)=>{
      if(name===prefix+'_list')return Promise.resolve({items:[{visit_id:id,child_name:'Child',guardian_name:'Parent',account_state:'open'}],has_more:false})
      if(name===prefix+'_detail')return Promise.resolve({visit_id:id,child_id:child,child_name:'Child',guardian_name:'Parent',visit_state:'closed',parent_linked:true,
        account:{state:'open',account_id:42,time_confirmed:confirmed?1:0,quantity:confirmed?'51.000':null,unit:'minutes'},choices:[],allowed_articles:[],commands:[],
        attention:confirmed?[]:[{command_id:cmd,kind:'time',state:'uncertain',parameters:{minutes:51,quantity:'51.000',unit:'minutes'},acknowledged:0}],has_more:false})
      if(name==='commerce_check'){
        expect(payload).toEqual({command_id:cmd,account_id:null,reviewed:true})
        if(mode==='mismatch')return Promise.resolve({status:'rejected',data:null,message:'commerce_check_required'})
        confirmed=true;return Promise.resolve({status:'applied',data:{state:'confirmed'},message:null})
      }
      throw new Error('Unexpected operation '+name)
    })
    const page=mountWith(mode==='journal'?Commerce:Cashier,h);await flushPromises()
    await page.findAll('button').find(b=>b.text()==='Account details')!.trigger('click');await flushPromises()
    await page.get('dialog').findAll('button').find(b=>b.text()==='Consumption')!.trigger('click')
    const check=()=>page.get('.cc-time-charge').findAll('button').find(b=>b.text()===catalogs.en.commerce_check_result)!
    expect(page.get('.cc-time-charge').isVisible()).toBe(true)
    expect(check().attributes('disabled')).toBeDefined()
    expect(h.invoke.mock.calls.filter(c=>c[0]==='commerce_check')).toHaveLength(0)
    const checkbox=mode==='journal'?page.get('dialog details.ui-stack input[type=checkbox]'):page.get('.cc-time-charge input[type=checkbox]')
    await checkbox.setValue(true)
    expect(check().attributes('disabled')).toBeUndefined()
    await check().trigger('click');await flushPromises()
    expect(h.invoke.mock.calls.filter(c=>c[0]==='commerce_check')).toHaveLength(1)
    expect(h.invoke.mock.calls.filter(c=>['commerce_prepare','commerce_validate','commerce_execute'].includes(c[0]))).toHaveLength(0)
    if(mode==='mismatch'){
      expect(page.get('.cc-time-charge').text()).toContain(catalogs.en.commerce_check_required)
      expect(page.get('.cc-time-charge').text()).not.toContain(catalogs.en.commerce_time_confirmed)
      expect(check().attributes('disabled')).toBeDefined()
    }else expect(page.get('.cc-time-charge').text()).toContain(catalogs.en.commerce_time_confirmed+': 51.000 Minutes')
    page.unmount()
  })

  it('shows the exact parent mismatch in the pending opening without exposing remote contacts',async()=>{
    const id='visit_'+'1'.repeat(32),h=host(['cashier_list','cashier_detail','commerce_execute'])
    h.invoke.mockImplementation((name:string)=>Promise.resolve(name==='cashier_list'
      ?{items:[{visit_id:id,child_name:'Child',guardian_name:'Parent'}],has_more:false}
      :{visit_id:id,child_id:'child_1',child_name:'Child',guardian_name:'Parent',visit_state:'closed',parent_linked:true,
        account:{state:'prepared',account_id:null},choices:[],allowed_articles:[],opening_available:true,opening_state:'review',
        opening_error:'commerce_opening_review',commands:[],attention:[{command_id:'commercial_'+'2'.repeat(32),kind:'open',state:'prepared',parameters:{place_id:6},error_code:'commerce_parent_phone_mismatch'}],has_more:false}))
    const page=mountWith(Cashier,h);await flushPromises()
    await page.findAll('button').find(b=>b.text()==='Account details')!.trigger('click');await flushPromises()
    expect(page.get('dialog').text()).toContain(catalogs.en.commerce_parent_phone_mismatch)
    h.setLocale('bg');await nextTick()
    expect(page.get('dialog').text()).toContain(catalogs.bg.commerce_parent_phone_mismatch)
    expect(h.invoke.mock.calls.some(c=>c[0]==='commerce_execute')).toBe(false)
    page.unmount()
  })

  it('offers categories in the detailed directory, reads only explicitly and paginates by twenty',async()=>{
    const h=host(['barsy_categories'])
    h.invoke.mockResolvedValue({status:'ready',items:[{category_id:1,label:'Бар'},{category_id:2,label:'КУХНЯ'}],has_more:true})
    const page=mountWith(Barsy,h);await flushPromises()
    expect(h.invoke).not.toHaveBeenCalled()
    await page.findAll('button').find(b=>b.text()==='Categories')!.trigger('click');await flushPromises()
    expect(h.invoke).not.toHaveBeenCalled()
    await page.get('form').trigger('submit');await flushPromises()
    expect(h.invoke.mock.calls[0].slice(0,2)).toEqual(['barsy_categories',{offset:0}])
    expect(page.get('table').text()).toContain('Бар')
    expect(page.get('table').text()).toContain('КУХНЯ')
    expect(page.get('table').text()).not.toContain('ID')
    await page.findAll('button').find(b=>b.text()==='Next')!.trigger('click');await flushPromises()
    expect(h.invoke.mock.calls.at(-1)!.slice(0,2)).toEqual(['barsy_categories',{offset:20}])
    page.unmount()
  })
  it('distinguishes category format failures from connection failures and clears an old error on success',async()=>{
    const h=host(['commerce_settings','barsy_categories'])
    let status='invalid_response'
    h.invoke.mockImplementation((name:string)=>Promise.resolve(name==='commerce_settings'
      ?{revision:1,time_article_id:null,unit:'minutes',places:[],articles:[]}
      :{status,items:status==='ready'?[{category_id:5,label:'Cafe'}]:[],has_more:false}))
    const page=mountWith(CommerceSetup,h);await flushPromises()
    await page.get('#commerce-catalog-type').setValue('categories')
    const search=async()=>{await page.findAll('form')[1].trigger('submit');await flushPromises()}
    await search()
    expect(page.text()).toContain(catalogs.en.barsy_invalid_response)
    expect(page.text()).not.toContain(catalogs.en.barsy_unavailable)
    status='unavailable';await search()
    expect(page.text()).toContain(catalogs.en.barsy_unavailable)
    status='ready';await search()
    expect(page.text()).toContain('Cafe')
    expect(page.text()).not.toContain(catalogs.en.barsy_unavailable)
    expect(page.text()).not.toContain(catalogs.en.barsy_invalid_response)
    page.unmount()
  })
  it.each([[Desk,'list_registrations','get_registration'],[Administration,'admin_list_clients','admin_get_client']])('keeps the selected client visible alongside readable status',async(component,listOp,detailOp)=>{
    const one='reg_'+'1'.repeat(32),two='reg_'+'2'.repeat(32)
    const h=host([listOp as string,detailOp as string])
    h.invoke.mockImplementation((name:string,payload:any)=>name===listOp?Promise.resolve({items:[{registration_id:one,guardian_name:'First Parent',status:'approved'},{registration_id:two,guardian_name:'Second Parent',status:'submitted'}],total:2}):Promise.resolve({registration_id:payload.registration_id,status:'approved',guardian:{display_name:payload.registration_id===one?'First Parent':'Second Parent',phone:'',email:''},children:[],revision:1,consent_version:'v1',consented_at:'2026-10-28'}))
    const page=mountWith(component,h);await flushPromises()
    let buttons=page.findAll('.cc-client-row')
    expect(buttons.map(b=>b.text())).toEqual(['First ParentApproved','Second ParentPending'])
    await buttons[0].trigger('click');await flushPromises()
    buttons=page.findAll('.cc-client-row')
    expect(buttons[0].attributes('aria-pressed')).toBe('true')
    if(component===Administration)expect((page.get('#admin-guardian').element as HTMLInputElement).value).toBe('First Parent')
    else expect(page.find('.cc-client-detail').text()).toContain('First Parent')
    await buttons[1].trigger('click');await flushPromises()
    expect(page.findAll('.cc-client-row').map(b=>b.attributes('aria-pressed'))).toEqual(['false','true'])
    if(component===Administration)expect((page.get('#admin-guardian').element as HTMLInputElement).value).toBe('Second Parent')
    else expect(page.find('.cc-client-detail').text()).toContain('Second Parent')
    page.unmount()
  })
  it.each(['confirmed','lost'])('sends a cashier consumption once and stops on a %s result',async(mode)=>{
    const id='visit_'+'1'.repeat(32),cmd='commercial_'+'2'.repeat(32)
    const h=host(['cashier_list','cashier_detail','commerce_prepare','commerce_validate','commerce_execute','commerce_check'])
    h.invoke.mockImplementation((name:string)=>{
      if(name==='cashier_list')return Promise.resolve({items:[{visit_id:id,child_name:'Child',guardian_name:'Parent'}],has_more:false})
      if(name==='cashier_detail')return Promise.resolve({visit_id:id,child_id:'child_1',child_name:'Child',guardian_name:'Parent',visit_state:'active',parent_linked:true,account:{state:'open',account_id:201,remote_state:'open'},choices:[{article_id:20,label:'Juice'}],allowed_articles:[20],commands:[],has_more:false})
      if(name==='commerce_prepare')return Promise.resolve({status:'applied',message:null,data:{command_id:cmd,state:'prepared'}})
      if(name==='commerce_validate')return Promise.resolve({status:'applied',message:null,data:{command_id:cmd,state:'prepared'}})
      if(name==='commerce_execute'&&mode==='lost')return Promise.reject(new Error('lost'))
      return Promise.resolve({status:'applied',message:null,data:{state:name==='commerce_check'?'confirmed':'uncertain'}})
    })
    const page=mountWith(Cashier,h);await flushPromises()
    await page.findAll('button').find(b=>b.text()==='Account details')!.trigger('click');await flushPromises()
    await page.get('dialog').findAll('button').find(b=>b.text()==='Consumption')!.trigger('click')
    await page.get('#sale-article').setValue('20')
    await page.get('#sale-article').element.closest('form')!.dispatchEvent(new Event('submit',{bubbles:true,cancelable:true}));await flushPromises()
    expect(h.invoke.mock.calls.filter(c=>c[0]==='commerce_execute')).toHaveLength(1)
    expect(h.invoke.mock.calls.filter(c=>c[0]==='commerce_check')).toHaveLength(mode==='lost'?0:1)
    expect(page.get('.cc-consumption-feedback').text()).toContain(mode==='confirmed'?'Consumption added to the family bill.':catalogs.en.outcome_needs_review)
    if(mode==='lost'){
      await page.get('#sale-article').element.closest('form')!.dispatchEvent(new Event('submit',{bubbles:true,cancelable:true}));await flushPromises()
      expect(h.invoke.mock.calls.filter(c=>c[0]==='commerce_execute')).toHaveLength(1)
    }
    page.unmount()
  })
  it('saves a default place and parent category without adding a place button to article rows',async()=>{
    const h=host(['commerce_settings','commerce_save_settings','barsy_places','barsy_categories'])
    h.invoke.mockImplementation((name:string)=>{
      if(name==='commerce_settings')return Promise.resolve({revision:1,time_article_id:10,unit:'minutes',places:[7],articles:[],default_place_id:null,guardian_category_id:null})
      if(name==='barsy_places')return Promise.resolve({status:'ready',items:[{place_id:7,label:'Play room'}],has_more:false})
      if(name==='barsy_categories')return Promise.resolve({status:'ready',items:[{category_id:5,label:'Cafe'}],has_more:false})
      return Promise.resolve({status:'applied',message:null,data:{state:'saved'}})
    })
    const page=mountWith(CommerceSetup,h)
    await flushPromises();await page.get('#commerce-default-place').setValue('7')
    await page.get('#commerce-catalog-type').setValue('categories')
    await page.findAll('form')[1].trigger('submit');await flushPromises()
    await page.findAll('button').find(b=>b.text()==='Use for parents')!.trigger('click')
    expect(page.text()).not.toContain('Use place')
    await page.findAll('button').find(b=>b.text()==='Save changes')!.trigger('click');await flushPromises()
    expect(h.invoke.mock.calls.find(c=>c[0]==='commerce_save_settings')![1]).toMatchObject({default_place_id:7,guardian_category_id:5})
    page.unmount()
  })
  it('manages the family stays and parent catalogue from the existing cashier route',async()=>{
    const id='visit_'+'1'.repeat(32),second='visit_'+'2'.repeat(32),cid='child_'+'3'.repeat(32),other='child_'+'4'.repeat(32)
    const h=host(['cashier_list','cashier_detail','commerce_prepare','commerce_catalog','commerce_validate','commerce_execute','commerce_check','family_finish','family_transition'])
    const family=[{visit_id:id,child_id:cid,child_name:'First child',phase:'paused',last_transition_at:'2026-10-28T10:00:00Z',duration_seconds:60,allowed_articles:[20]},
      {visit_id:second,child_id:other,child_name:'Second child',phase:'inside',last_transition_at:'2026-10-28T10:01:00Z',duration_seconds:120,allowed_articles:[]}]
    h.invoke.mockImplementation((name:string)=>{
      if(name==='cashier_list')return Promise.resolve({items:[{visit_id:id,child_name:'First child, Second child',guardian_name:'Parent',account_state:'open'}],has_more:false})
      if(name==='cashier_detail')return Promise.resolve({visit_id:id,child_id:cid,child_name:'First child',guardian_name:'Parent',visit_state:'active',parent_linked:true,account:{state:'open',account_id:201,remote_state:'open'},choices:[{article_id:20,label:'Juice'}],allowed_articles:[20],commands:[],members:family,has_more:false})
      if(name==='commerce_catalog')return Promise.resolve({items:[{article_id:21,label:'Parent coffee'}],has_more:false})
      if(name==='commerce_prepare')return Promise.resolve({status:'applied',message:null,data:{command_id:'commercial_'+'5'.repeat(32),state:'prepared'}})
      if(name==='commerce_validate')return Promise.resolve({status:'applied',message:null,data:{command_id:'commercial_'+'5'.repeat(32),state:'prepared'}})
      if(name==='commerce_execute'||name==='commerce_check')return Promise.resolve({status:'applied',message:null,data:{state:name==='commerce_execute'?'uncertain':'confirmed'}})
      return Promise.resolve({status:'applied',message:null,data:{state:'saved'}})
    })
    const page=mountWith(Cashier,h);await flushPromises()
    await page.findAll('button').find(b=>b.text()==='Account details')!.trigger('click');await flushPromises()
    expect(page.get('dialog').text()).toContain('Second child')
    await page.get('dialog').findAll('button').find(b=>b.text()==='Resume')!.trigger('click');await flushPromises()
    expect(h.invoke.mock.calls.find(c=>c[0]==='family_transition')![1]).toEqual({visit_id:id,expected_transition_at:family[0].last_transition_at,action:'resume'})
    await page.get('dialog').findAll('button').find(b=>b.text()==='Consumption')!.trigger('click')
    await page.get('#sale-child').setValue(other)
    expect(page.get('#sale-article').findAll('option').map(o=>o.text())).not.toContain('Juice')
    await page.get('#sale-consumer').setValue('guardian')
    await flushPromises()
    expect(h.invoke.mock.calls.filter(c=>c[0]==='commerce_catalog')).toHaveLength(1)
    expect(h.invoke.mock.calls.find(c=>c[0]==='commerce_catalog')![1]).toEqual({visit_id:id,query:'',offset:0})
    expect(page.get('#sale-article').findAll('option').map(o=>o.text())).toContain('Parent coffee')
    await page.get('#sale-article').setValue('21')
    await page.get('#sale-quantity').setValue('2')
    await page.get('#sale-article').element.closest('form')!.dispatchEvent(new Event('submit',{bubbles:true,cancelable:true}));await flushPromises()
    expect(h.invoke.mock.calls.find(c=>c[0]==='commerce_prepare')![1]).toMatchObject({visit_id:id,consumer:'guardian',article_id:21,consumer_child_id:other,quantity:'2'})
    expect(h.invoke.mock.calls.filter(c=>c[0]==='commerce_execute')).toHaveLength(1)
    expect(h.invoke.mock.calls.filter(c=>c[0]==='commerce_check')).toHaveLength(1)
    const finish=()=>page.get('dialog').findAll('button').find(b=>b.text()==='Finish all family stays')!
    await page.get('dialog').findAll('button').find(b=>b.text()==='Overview')!.trigger('click')
    expect(finish().attributes('disabled')).toBeDefined()
    await page.get('dialog').findAll('input[type=checkbox]')[0].setValue(true)
    await finish().trigger('click');await flushPromises()
    expect(h.invoke.mock.calls.find(c=>c[0]==='family_finish')![1]).toEqual({visit_id:id,members:family.map(m=>({visit_id:m.visit_id,expected_transition_at:m.last_transition_at,expected_phase:m.phase}))})
    page.unmount()
  })
  it.each(['opened','read_failure','closed'])('watches an opening bill through read-only status and stops when %s',async(mode)=>{
    vi.useFakeTimers({toFake:['setTimeout','clearTimeout']})
    const id='visit_'+'1'.repeat(32),h=host(['cashier_list','cashier_detail','family_retry_open','commerce_places','commerce_prepare'])
    let state='review'
    h.invoke.mockImplementation((name:string)=>{
      if(name==='cashier_list')return Promise.resolve({items:[{visit_id:id,child_name:'Child',guardian_name:'Parent'}],has_more:false})
      if(name==='family_retry_open'){state='opening';return Promise.resolve({status:'applied',message:null,data:{state:'prepared'}})}
      if(name==='cashier_detail'){
        if(state==='read_failure')return Promise.reject({code:'unavailable'})
        return Promise.resolve({visit_id:id,child_id:'child_1',child_name:'Child',guardian_name:'Parent',visit_state:'active',parent_linked:true,
          opening_state:state,opening_available:true,opening_error:state==='review'?'commerce_opening_review':null,
          account:state==='open'?{state:'open',account_id:201}:null,choices:[],allowed_articles:[],commands:[],attention:[],has_more:false})
      }
      throw new Error('Unexpected operation '+name)
    })
    const page=mountWith(Cashier,h)
    try{
      await flushPromises();await page.findAll('button').find(b=>b.text()==='Account details')!.trigger('click');await flushPromises()
      expect(page.get('dialog').text()).not.toContain('Load configured places')
      await page.get('dialog').findAll('button').find(b=>b.text()==='Continue account opening')!.trigger('click');await flushPromises()
      expect(page.get('dialog').text()).toContain(catalogs.en.commerce_opening_opening)
      expect(h.invoke.mock.calls.filter(c=>c[0]==='family_retry_open')).toHaveLength(1)
      if(mode==='closed')await page.get('dialog').trigger('cancel')
      else state=mode==='opened'?'open':'read_failure'
      await vi.advanceTimersByTimeAsync(2000);await flushPromises()
      if(mode==='opened')expect(page.get('dialog').text()).not.toContain(catalogs.en.commerce_opening_opening)
      if(mode==='read_failure')expect(page.get('dialog').text()).toContain(catalogs.en.read_unavailable)
      const reads=h.invoke.mock.calls.filter(c=>c[0]==='cashier_detail').length
      await vi.advanceTimersByTimeAsync(20000);await flushPromises()
      expect(h.invoke.mock.calls.filter(c=>c[0]==='cashier_detail')).toHaveLength(reads)
      expect(h.invoke.mock.calls.some(c=>['commerce_places','commerce_prepare'].includes(c[0]))).toBe(false)
    }finally{page.unmount();vi.useRealTimers()}
  })
  it('ignores a late parent catalogue after switching back to the child',async()=>{
    const id='visit_'+'1'.repeat(32),h=host(['cashier_list','cashier_detail','commerce_prepare','commerce_catalog'])
    let reply:(result:unknown)=>void=()=>{}
    h.invoke.mockImplementation((name:string)=>name==='cashier_list'
      ?Promise.resolve({items:[{visit_id:id,child_name:'Child',guardian_name:'Parent'}],has_more:false})
      :name==='commerce_catalog'?new Promise(resolve=>reply=resolve)
      :Promise.resolve({visit_id:id,child_id:'child_1',child_name:'Child',guardian_name:'Parent',visit_state:'active',parent_linked:true,
        account:{state:'open',account_id:201},choices:[],allowed_articles:[],commands:[],has_more:false}))
    const page=mountWith(Cashier,h);await flushPromises()
    await page.findAll('button').find(b=>b.text()==='Account details')!.trigger('click');await flushPromises()
    await page.get('dialog').findAll('button').find(b=>b.text()==='Consumption')!.trigger('click')
    await page.get('#sale-consumer').setValue('guardian');await page.get('#sale-consumer').setValue('child')
    reply({items:[{article_id:21,label:'Parent coffee'}],has_more:false});await flushPromises()
    expect(page.get('#sale-article').text()).not.toContain('Parent coffee')
    expect(page.get('#sale-article').element.closest('form')!.querySelector('button[type=submit]')!.hasAttribute('disabled')).toBe(true)
    expect(h.invoke.mock.calls.some(c=>c[0]==='commerce_prepare')).toBe(false)
    page.unmount()
  })
  it('advances only inside stays locally, resynchronizes on refresh and stops the timer on unmount',async()=>{
    let monotonic=1000, tick:()=>void=()=>{}
    vi.spyOn(performance,'now').mockImplementation(()=>monotonic)
    vi.spyOn(window,'setInterval').mockImplementation((handler:TimerHandler)=>{tick=handler as ()=>void;return 73})
    const clear=vi.spyOn(window,'clearInterval').mockImplementation(()=>{})
    const rows=[{visit_id:'visit_'+'1'.repeat(32),child_name:'Inside child',phase:'inside',duration_seconds:59,rounded_minutes:1,last_transition_at:'2026-10-27T10:00:00Z',entered_at:'2026-10-27T10:00:00Z',exited_at:null},
      {visit_id:'visit_'+'2'.repeat(32),child_name:'Paused child',phase:'paused',duration_seconds:20,rounded_minutes:1,last_transition_at:'2026-10-27T10:00:00Z',entered_at:'2026-10-27T10:00:00Z',exited_at:null},
      {visit_id:'visit_'+'3'.repeat(32),child_name:'Closed child',phase:'closed',duration_seconds:30,rounded_minutes:1,last_transition_at:'2026-10-27T10:00:00Z',entered_at:'2026-10-27T10:00:00Z',exited_at:'2026-10-27T10:01:00Z'}]
    const h=host(['list_visits']);h.invoke.mockImplementation(()=>Promise.resolve({items:rows.map(row=>({...row})),total:3}))
    const page=mountWith(Visits,h);await flushPromises()
    const times=()=>page.findAll('tbody tr').map(row=>row.findAll('td')[4].text())
    expect(times()).toEqual(['0m 59s','0m 20s','0m 30s'])
    monotonic+=2500;tick();await nextTick()
    expect(times()).toEqual(['1m 1s','0m 20s','0m 30s'])
    expect(h.invoke).toHaveBeenCalledTimes(1)
    rows[0].phase='paused';rows[0].duration_seconds=62
    await page.findAll('button').find(b=>b.text()==='Refresh')!.trigger('click');await flushPromises()
    monotonic+=5000;tick();await nextTick()
    expect(times()).toEqual(['1m 2s','0m 20s','0m 30s'])
    expect(h.invoke).toHaveBeenCalledTimes(2)
    page.unmount();expect(clear).toHaveBeenCalledWith(73)
  })
  it('keeps per-child consumption consent independent and empty by default',async()=>{
    const submitted=vi.fn()
    const form=mount(ClientForm,{props:{disabled:false,choices:[{article_id:20,label:'Juice'}],onSubmit:submitted}})
    await form.get('#client-parent').setValue('Parent');await form.get('input[type="tel"]').setValue('000')
    await form.get('#client-child-0').setValue('First')
    await form.findAll('button').find(b=>b.text()==='+ Child')!.trigger('click')
    await form.get('#client-child-1').setValue('Second')
    const checks=form.findAll('input[type="checkbox"]')
    await checks[0].setValue(true);await checks.at(-1)!.setValue(true)
    await form.get('form').trigger('submit')
    expect(submitted.mock.calls[0][0].children).toEqual([{display_name:'First',allowed_article_ids:[20]},{display_name:'Second',allowed_article_ids:[]}])
    form.unmount()
  })
  it('requires explicit send, preserves a lost commerce reply and resolves through the commercial receipt without replay',async()=>{
    const id='visit_'+'1'.repeat(32),cmd='commercial_'+'2'.repeat(32)
    const h=host(['commerce_list','commerce_detail','commerce_validate','commerce_execute','commerce_cancel','commerce_request_outcome','request_outcome'])
    h.invoke.mockImplementation((name:string)=>{
      if(name==='commerce_list')return Promise.resolve({items:[{visit_id:id,child_name:'Child',guardian_name:'Parent',visit_state:'active',account_state:'open'}],has_more:false})
      if(name==='commerce_detail')return Promise.resolve({visit_id:id,child_id:'child_1',child_name:'Child',guardian_name:'Parent',visit_state:'active',parent_linked:true,account:{state:'open',account_id:201,remote_state:'open'},choices:[],allowed_articles:[],has_more:false,
        commands:[{command_id:cmd,kind:'consumption',state:'prepared',parameters:{article_id:20,quantity:'1',consumer:'guardian'},acknowledged:0}]})
      if(name==='commerce_validate')return Promise.resolve({status:'applied',message:null,data:{command_id:cmd,state:'prepared'}})
      if(name==='commerce_execute')return Promise.reject(new Error('lost reply'))
      if(name==='commerce_request_outcome')return Promise.resolve({status:'unknown',result_json:null})
      throw new Error(name)
    })
    const page=mountWith(Commerce,h);await flushPromises()
    await page.findAll('button').find(b=>b.text()==='Account details')!.trigger('click');await flushPromises()
    const send=()=>page.get('dialog').findAll('button').find(b=>b.text()==='Send once')!
    await page.get('dialog').findAll('button').find(b=>b.text()==='Consumption')!.trigger('click')
    expect(send().isVisible()).toBe(true)
    await page.get('dialog').findAll('button').find(b=>b.text()==='Commercial journal')!.trigger('click')
    expect(page.get('dialog').findAll('details').filter(d=>d.classes().includes('ui-stack'))).toHaveLength(1)
    expect(send().attributes('disabled')).toBeDefined()
    await page.get('dialog input[type="checkbox"]').setValue(true);await send().trigger('click');await flushPromises()
    expect(h.invoke.mock.calls.filter(c=>c[0]==='commerce_execute')).toHaveLength(1)
    expect(page.text()).toContain('Outcome')
    await page.get('dialog').findAll('button').find(b=>b.text()==='Check saved outcome')!.trigger('click');await flushPromises()
    expect(h.invoke.mock.calls.filter(c=>c[0]==='commerce_request_outcome')).toHaveLength(1)
    expect(h.invoke.mock.calls.filter(c=>c[0]==='request_outcome')).toHaveLength(0)
    expect(h.invoke.mock.calls.filter(c=>c[0]==='commerce_execute')).toHaveLength(1)
    expect(page.findAll('button').filter(b=>b.text()==='Send once').every(b=>b.attributes('disabled')!==undefined)).toBe(true)
    page.unmount()
  })
  it.each(['cashier/confirmed','cashier/lost','cashier/refused','accounts/confirmed','accounts/lost','accounts/refused'])('shows payment feedback at the action and updates the active list: %s',async(scenario)=>{
    const [route,mode]=scenario.split('/'),prefix=route==='accounts'?'commerce':'cashier'
    const id='visit_'+'1'.repeat(32),cmd='commercial_'+'2'.repeat(32)
    const h=host([prefix+'_list',prefix+'_detail','cashier_preview','cashier_prepare','cashier_execute','cashier_check'])
    let closed=false
    h.invoke.mockImplementation((name:string)=>{
      if(name===prefix+'_list')return Promise.resolve({items:[{visit_id:id,child_name:'Child',guardian_name:'Parent',account_state:'open',account_id:201}],has_more:false})
      if(name===prefix+'_detail')return Promise.resolve({visit_id:id,child_id:'child_1',child_name:'Child',guardian_name:'Parent',visit_state:'closed',parent_linked:true,
        account:{state:closed?'closed':'open',remote_state:closed?'closed':'open',account_id:201,time_confirmed:1,unit:'minutes',quantity:'2'},choices:[],allowed_articles:[],commands:[],has_more:false})
      if(name==='cashier_preview')return Promise.resolve({status:'applied',message:null,data:{quote_id:'quote_'+'3'.repeat(32),amount:'12.50',currency_code:'EUR',expires_at:'2026-10-29T10:02:00Z',methods:[{paymethod_id:3,label:'Cash'}]}})
      if(name==='cashier_prepare')return Promise.resolve({status:'applied',message:null,data:{command_id:cmd,state:'prepared'}})
      if(name==='cashier_execute'){
        if(mode==='lost')return Promise.reject(new Error('lost payment'))
        if(mode==='refused')return Promise.resolve({status:'rejected',message:'commerce_quote_expired',data:null})
        return Promise.resolve({status:'applied',message:null,data:{state:'uncertain'}})
      }
      if(name==='cashier_check'){closed=true;return Promise.resolve({status:'applied',message:null,data:{state:'confirmed'}})}
      throw new Error(name)
    })
    const page=mountWith(route==='accounts'?Commerce:Cashier,h);await flushPromises()
    await page.findAll('button').find(b=>b.text()==='Account details')!.trigger('click');await flushPromises()
    if(route==='accounts')await page.get('.cc-checkout-entry button').trigger('click')
    else{
      await page.get('dialog').findAll('button').find(b=>b.text()==='Payment')!.trigger('click')
      await page.get('dialog').findAll('button').find(b=>b.text()===catalogs.en.commerce_payment_preview)!.trigger('click')
    }
    await flushPromises()
    await page.get('#pay-method').setValue('3')
    const form=page.get('#pay-method').element.closest('form')!
    await page.get('dialog').findAll('input[type=checkbox]').at(-1)!.setValue(true)
    form.dispatchEvent(new Event('submit',{bubbles:true,cancelable:true}));await flushPromises()
    expect(h.invoke.mock.calls.filter(c=>c[0]==='cashier_execute')).toHaveLength(1)
    expect(h.invoke.mock.calls.filter(c=>c[0]==='cashier_check')).toHaveLength(mode==='confirmed'?1:0)
    expect(page.get('.cc-payment-feedback').isVisible()).toBe(true)
    expect(page.get('.cc-payment-feedback').text()).toContain(mode==='confirmed'?'Payment confirmed. The family bill is closed.':mode==='lost'?catalogs.en.outcome_needs_review:catalogs.en.commerce_quote_expired)
    expect(page.findAll('tbody tr')).toHaveLength(mode==='confirmed'?0:1)
    page.unmount()
  })
  it.each(['prepared','uncertain','mismatch'])('continues the exact payment from Accounts without another quote or payment preparation: %s',async(mode)=>{
    const id='visit_'+'1'.repeat(32),cmd='commercial_'+'2'.repeat(32)
    const h=host(['commerce_list','commerce_detail','cashier_preview','cashier_prepare','cashier_execute','cashier_check','cashier_cancel'])
    let closed=false
    h.invoke.mockImplementation((name:string,payload:any)=>{
      if(name==='commerce_list')return Promise.resolve({items:[{visit_id:id,child_name:'Child',guardian_name:'Parent',account_id:42,account_state:'open'}],has_more:false})
      if(name==='commerce_detail')return Promise.resolve({visit_id:id,child_id:'child_1',child_name:'Child',guardian_name:'Parent',visit_state:'closed',parent_linked:true,
        account:{state:closed?'closed':'open',account_id:42,time_confirmed:1,unit:'minutes',quantity:'51'},choices:[],allowed_articles:[],commands:[],
        attention:closed?[]:[{command_id:cmd,kind:'payment',state:mode==='prepared'?'prepared':'uncertain',acknowledged:0,parameters:{amount:'25.50',currency_code:'EUR',method_label:'Cash'}}],has_more:false})
      if(name==='cashier_execute')return Promise.resolve({status:'applied',message:null,data:{state:'uncertain'}})
      if(name==='cashier_check'){
        expect(payload).toEqual({command_id:cmd,account_id:null,reviewed:mode!=='prepared'})
        if(mode==='mismatch')return Promise.resolve({status:'rejected',message:'commerce_check_required',data:null})
        closed=true;return Promise.resolve({status:'applied',message:null,data:{state:'confirmed'}})
      }
      throw new Error('Unexpected '+name)
    })
    const page=mountWith(Commerce,h);await flushPromises()
    await page.findAll('button').find(b=>b.text()==='Account details')!.trigger('click');await flushPromises()
    await page.get('.cc-checkout-entry button').trigger('click');await flushPromises()
    expect(page.get('.cc-checkout').text()).toContain('25.50 EUR')
    const action=()=>page.get('.cc-checkout').findAll('button').find(b=>b.text()===(mode==='prepared'?catalogs.en.commerce_prepare_payment:catalogs.en.commerce_check_result))!
    expect(action().attributes('disabled')).toBeDefined()
    await page.get('.cc-checkout input[type=checkbox]').setValue(true)
    expect(action().attributes('disabled')).toBeUndefined()
    await action().trigger('click');await flushPromises()
    expect(h.invoke.mock.calls.filter(c=>['cashier_preview','cashier_prepare'].includes(c[0]))).toHaveLength(0)
    expect(h.invoke.mock.calls.filter(c=>c[0]==='cashier_execute')).toHaveLength(mode==='prepared'?1:0)
    expect(h.invoke.mock.calls.filter(c=>c[0]==='cashier_check')).toHaveLength(1)
    if(mode==='mismatch'){
      expect(page.get('.cc-payment-feedback').text()).toContain(catalogs.en.commerce_check_required)
      expect(page.get('.cc-checkout').exists()).toBe(true)
    }else{
      expect(page.get('.cc-payment-feedback').text()).toContain(catalogs.en.commerce_payment_confirmed)
      expect(page.findAll('tbody tr')).toHaveLength(0)
    }
    page.unmount()
  })

  it.each(['active','time','pending'])('explains and blocks premature checkout from Accounts: %s',async(mode)=>{
    const id='visit_'+'1'.repeat(32),h=host(['commerce_list','commerce_detail','cashier_preview'])
    h.invoke.mockImplementation((name:string)=>Promise.resolve(name==='commerce_list'?{items:[{visit_id:id,child_name:'Child',guardian_name:'Parent',account_state:'open'}],has_more:false}:
      {visit_id:id,child_id:'child_1',child_name:'Child',guardian_name:'Parent',visit_state:mode==='active'?'active':'closed',parent_linked:true,
        account:{state:'open',account_id:42,time_confirmed:mode==='time'?0:1,unit:'minutes',quantity:'51'},choices:[],allowed_articles:[],commands:[],
        attention:mode==='pending'?[{command_id:'commercial_'+'2'.repeat(32),kind:'consumption',state:'uncertain',parameters:{},acknowledged:0}]:[],has_more:false}))
    const page=mountWith(Commerce,h);await flushPromises()
    await page.findAll('button').find(b=>b.text()==='Account details')!.trigger('click');await flushPromises()
    expect(page.get('.cc-checkout-entry button').attributes('disabled')).toBeDefined()
    expect(page.get('.cc-checkout-entry').text()).toContain(mode==='pending'?catalogs.en.commerce_pending:catalogs.en.commerce_finish_first)
    expect(h.invoke.mock.calls.filter(c=>c[0]==='cashier_preview')).toHaveLength(0)
    page.unmount()
  })

  it('keeps payment unavailable in Accounts without cashier access',async()=>{
    const id='visit_'+'1'.repeat(32),h=host(['commerce_list','commerce_detail'])
    h.invoke.mockImplementation((name:string)=>Promise.resolve(name==='commerce_list'?{items:[{visit_id:id,child_name:'Child',guardian_name:'Parent'}],has_more:false}:
      {visit_id:id,child_id:'child_1',child_name:'Child',guardian_name:'Parent',visit_state:'closed',parent_linked:true,account:{state:'open',account_id:42,time_confirmed:1},choices:[],allowed_articles:[],commands:[],has_more:false}))
    const page=mountWith(Commerce,h);await flushPromises()
    await page.findAll('button').find(b=>b.text()==='Account details')!.trigger('click');await flushPromises()
    expect(page.find('.cc-checkout-entry').exists()).toBe(false)
    expect(page.get('dialog').findAll('button').some(b=>b.text()==='Payment')).toBe(false)
    page.unmount()
  })

  it('cancels an expired unsent payment before reading a new amount without another send',async()=>{
    const id='visit_'+'1'.repeat(32),cmd='commercial_'+'2'.repeat(32)
    const h=host(['commerce_list','commerce_detail','cashier_preview','cashier_prepare','cashier_execute','cashier_check','cashier_cancel'])
    let prepared=true
    h.invoke.mockImplementation((name:string)=>{
      if(name==='commerce_list')return Promise.resolve({items:[{visit_id:id,child_name:'Child',guardian_name:'Parent'}],has_more:false})
      if(name==='commerce_detail')return Promise.resolve({visit_id:id,child_id:'child_1',child_name:'Child',guardian_name:'Parent',visit_state:'closed',parent_linked:true,account:{state:'open',account_id:42,time_confirmed:1},choices:[],allowed_articles:[],commands:[],has_more:false,
        attention:prepared?[{command_id:cmd,kind:'payment',state:'prepared',parameters:{amount:'25.50',currency_code:'EUR',method_label:'Cash'},acknowledged:0}]:[]})
      if(name==='cashier_execute')return Promise.resolve({status:'rejected',data:null,message:'commerce_quote_expired'})
      if(name==='cashier_cancel'){prepared=false;return Promise.resolve({status:'applied',message:null,data:{state:'cancelled'}})}
      if(name==='cashier_preview')return Promise.resolve({status:'applied',message:null,data:{quote_id:'quote_'+'3'.repeat(32),amount:'25.50',currency_code:'EUR',expires_at:'2026-10-29T10:02:00Z',methods:[{paymethod_id:1,label:'Cash'}]}})
      throw new Error(name)
    })
    const page=mountWith(Commerce,h);await flushPromises()
    await page.findAll('button').find(b=>b.text()==='Account details')!.trigger('click');await flushPromises()
    await page.get('.cc-checkout-entry button').trigger('click')
    await page.get('.cc-checkout input[type=checkbox]').setValue(true)
    await page.get('.cc-checkout').findAll('button').find(b=>b.text()===catalogs.en.commerce_prepare_payment)!.trigger('click');await flushPromises()
    expect(page.get('.cc-payment-feedback').text()).toContain(catalogs.en.commerce_quote_expired)
    await page.get('.cc-checkout').findAll('button').find(b=>b.text()==='Cancel')!.trigger('click');await flushPromises()
    await page.get('.cc-checkout').findAll('button').find(b=>b.text()===catalogs.en.commerce_payment_preview)!.trigger('click');await flushPromises()
    expect(page.get('#pay-method').exists()).toBe(true)
    expect(h.invoke.mock.calls.filter(c=>c[0]==='cashier_execute')).toHaveLength(1)
    expect(h.invoke.mock.calls.filter(c=>c[0]==='cashier_cancel')).toHaveLength(1)
    expect(h.invoke.mock.calls.filter(c=>c[0]==='cashier_preview')).toHaveLength(1)
    page.unmount()
  })

  it('keeps external-payment verification separate from child-consumption consent',async()=>{
    const id='visit_'+'1'.repeat(32),h=host(['cashier_list','cashier_detail','commerce_allow_child','cashier_external_close'])
    h.invoke.mockImplementation((name:string)=>Promise.resolve(name==='cashier_list'?{items:[{visit_id:id,child_name:'Child',guardian_name:'Parent'}],has_more:false}:
      {visit_id:id,child_id:'child_1',child_name:'Child',guardian_name:'Parent',visit_state:'closed',parent_linked:true,account:{state:'open',account_id:42,time_confirmed:1},choices:[],allowed_articles:[],commands:[],has_more:false}))
    const page=mountWith(Cashier,h);await flushPromises()
    await page.findAll('button').find(b=>b.text()==='Account details')!.trigger('click');await flushPromises()
    await page.get('dialog').findAll('button').find(b=>b.text()==='Consumption')!.trigger('click')
    await page.get('dialog form input[type=checkbox]').setValue(true)
    await page.get('dialog').findAll('button').find(b=>b.text()==='Commercial journal')!.trigger('click')
    const review=page.get('dialog details')
    await review.get('summary').trigger('click')
    expect(review.get('button').attributes('disabled')).toBeDefined()
    await review.get('input[type=checkbox]').setValue(true)
    expect(review.get('button').attributes('disabled')).toBeUndefined()
    expect(h.invoke.mock.calls.some(c=>c[0]==='cashier_external_close')).toBe(false)
    page.unmount()
  })

  it.each(['applied','rejected','lost'])('releases a closed empty test bill locally with explicit admin review and a scoped receipt: %s',async(mode)=>{
    const id='visit_'+'1'.repeat(32),cmd='commercial_'+'2'.repeat(32)
    const h=host(['commerce_list','commerce_detail','commerce_release_empty','commerce_recovery_outcome'])
    let released=false
    h.invoke.mockImplementation((name:string)=>{
      if(name==='commerce_list')return Promise.resolve({items:released?[]:[{visit_id:id,child_name:'Child',guardian_name:'Parent',account_id:41,account_state:'open'}],has_more:false})
      if(name==='commerce_detail')return Promise.resolve({visit_id:id,child_id:'child_1',child_name:'Child',guardian_name:'Parent',visit_state:'closed',parent_linked:true,
        account:{state:released?'closed':'open',remote_state:'closed',account_id:41,time_confirmed:0,quantity:null},choices:[],allowed_articles:[],commands:released?[{command_id:cmd,kind:'time',state:'waived',parameters:{quantity:'2.000',article_id:28,_recovery:{reason:'Empty test bill'}},acknowledged:0}]:[],has_more:false})
      if(name==='commerce_release_empty'){
        if(mode==='rejected')return Promise.resolve({status:'rejected',data:null,message:'commerce_empty_release_denied'})
        released=true
        if(mode==='lost')return Promise.reject(new Error('lost local release reply'))
        return Promise.resolve({status:'applied',message:null,data:{state:'closed'}})
      }
      if(name==='commerce_recovery_outcome')return Promise.resolve({status:'confirmed',result_json:JSON.stringify({status:'applied',message:null,data:{state:'closed'}})})
      throw new Error(name)
    })
    const page=mountWith(Commerce,h);await flushPromises()
    await page.findAll('button').find(b=>b.text()==='Account details')!.trigger('click');await flushPromises()
    await page.get('dialog').findAll('button').find(b=>b.text()==='Commercial journal')!.trigger('click')
    const release=page.get('.cc-empty-release');await release.get('summary').trigger('click')
    const button=()=>release.get('button')
    expect(button().attributes('disabled')).toBeDefined()
    await release.get('#empty-release-reason').setValue('Empty test bill')
    expect(button().attributes('disabled')).toBeDefined()
    await release.get('input[type=checkbox]').setValue(true)
    expect(button().attributes('disabled')).toBeUndefined()
    await release.get('form').trigger('submit');await flushPromises()
    expect(h.invoke.mock.calls.find(c=>c[0]==='commerce_release_empty')![1]).toEqual({visit_id:id,expected_account_id:41,reviewed:true,accepted_missing_time:true,reason:'Empty test bill'})
    expect(h.invoke.mock.calls.filter(c=>c[0]==='commerce_release_empty')).toHaveLength(1)
    if(mode==='lost'){
      expect(page.get('.cc-empty-release').text()).toContain(catalogs.en.outcome_needs_review)
      await page.get('dialog').findAll('button').find(b=>b.text()==='Check saved outcome')!.trigger('click');await flushPromises()
      expect(h.invoke.mock.calls.filter(c=>c[0]==='commerce_recovery_outcome')).toHaveLength(1)
      expect(h.invoke.mock.calls.filter(c=>c[0]==='commerce_release_empty')).toHaveLength(1)
    }else if(mode==='rejected')expect(page.get('.cc-empty-release').text()).toContain(catalogs.en.commerce_empty_release_denied)
    else{
      expect(page.get('dialog').text()).toContain(catalogs.en.commerce_empty_released)
      expect(page.get('dialog').text()).toContain(catalogs.en.commerce_state_waived)
      expect(page.findAll('tbody tr')).toHaveLength(0)
    }
    expect(h.invoke.mock.calls.some(c=>['commerce_execute','cashier_execute'].includes(c[0]))).toBe(false)
    page.unmount()
  })

  it.each(['no_access','active','already_closed'])('hides empty-account release when not applicable: %s',async(mode)=>{
    const id='visit_'+'1'.repeat(32),h=host(['commerce_list','commerce_detail',...(mode==='no_access'?[]:['commerce_release_empty'])])
    h.invoke.mockImplementation((name:string)=>Promise.resolve(name==='commerce_list'?{items:[{visit_id:id,child_name:'Child',guardian_name:'Parent'}],has_more:false}:
      {visit_id:id,child_id:'child_1',child_name:'Child',guardian_name:'Parent',visit_state:mode==='active'?'active':'closed',parent_linked:true,
        account:{state:mode==='already_closed'?'closed':'open',account_id:41,time_confirmed:0},choices:[],allowed_articles:[],commands:[],has_more:false}))
    const page=mountWith(Commerce,h);await flushPromises()
    await page.findAll('button').find(b=>b.text()==='Account details')!.trigger('click');await flushPromises()
    await page.get('dialog').findAll('button').find(b=>b.text()==='Commercial journal')!.trigger('click')
    expect(page.find('.cc-empty-release').exists()).toBe(false)
    page.unmount()
  })

  it.each(['accounts/applied','cashier/applied','accounts/rejected','accounts/lost'])('archives an unlinked failed parent request without retrying client creation: %s',async(scenario)=>{
    const [route,mode]=scenario.split('/'),prefix=route==='cashier'?'cashier':'commerce'
    const id='visit_'+'1'.repeat(32),cmd='commercial_'+'2'.repeat(32)
    const h=host([prefix+'_list',prefix+'_detail','commerce_prepare','commerce_execute','commerce_release_unlinked','commerce_recovery_outcome'])
    let archived=false
    h.invoke.mockImplementation((name:string)=>{
      if(name===prefix+'_list')return Promise.resolve({items:archived?[]:[{visit_id:id,child_name:'Child',guardian_name:'Parent',account_id:null,account_state:null}],has_more:false})
      if(name===prefix+'_detail')return Promise.resolve({visit_id:id,child_id:'child_1',child_name:'Child',guardian_name:'Parent',visit_state:'closed',parent_linked:false,account:null,
        opening_state:archived?'archived':'setup_required',opening_available:false,choices:[],allowed_articles:[],
        commands:archived?[{command_id:cmd,kind:'parent',state:'abandoned',parameters:{},acknowledged:0}]:[],
        attention:archived?[]:[{command_id:cmd,kind:'parent',state:'uncertain',parameters:{},acknowledged:0}],has_more:false})
      if(name==='commerce_release_unlinked'){
        if(mode==='rejected')return Promise.resolve({status:'rejected',data:null,message:'commerce_unlinked_release_denied'})
        archived=true
        if(mode==='lost')return Promise.reject(new Error('lost archive reply'))
        return Promise.resolve({status:'applied',message:null,data:{state:'archived'}})
      }
      if(name==='commerce_recovery_outcome')return Promise.resolve({status:'confirmed',result_json:JSON.stringify({status:'applied',message:null,data:{state:'archived'}})})
      throw new Error(name)
    })
    const page=mountWith(route==='cashier'?Cashier:Commerce,h);await flushPromises()
    await page.findAll('button').find(b=>b.text()==='Account details')!.trigger('click');await flushPromises()
    await page.get('dialog').findAll('button').find(b=>b.text()==='Commercial journal')!.trigger('click')
    const form=page.get('.cc-unlinked-release');await form.get('summary').trigger('click')
    expect(form.get('button').attributes('disabled')).toBeDefined()
    await form.get('#empty-release-reason').setValue('Abandon the old test request')
    expect(form.get('button').attributes('disabled')).toBeDefined()
    await form.get('input[type=checkbox]').setValue(true)
    await form.get('form').trigger('submit');await flushPromises()
    expect(h.invoke.mock.calls.find(c=>c[0]==='commerce_release_unlinked')![1]).toEqual({visit_id:id,reviewed:true,accepted_orphaned_parent:true,reason:'Abandon the old test request'})
    expect(h.invoke.mock.calls.filter(c=>['commerce_prepare','commerce_execute'].includes(c[0]))).toHaveLength(0)
    if(mode==='lost'){
      expect(page.get('.cc-unlinked-release').text()).toContain(catalogs.en.outcome_needs_review)
      await page.get('dialog').findAll('button').find(b=>b.text()==='Check saved outcome')!.trigger('click');await flushPromises()
      expect(h.invoke.mock.calls.filter(c=>c[0]==='commerce_recovery_outcome')).toHaveLength(1)
    }else if(mode==='rejected')expect(page.get('.cc-unlinked-release').text()).toContain(catalogs.en.commerce_unlinked_release_denied)
    else{
      expect(page.get('dialog').text()).toContain(catalogs.en.commerce_unlinked_archived)
      expect(page.get('dialog').text()).toContain(catalogs.en.commerce_state_abandoned)
      expect(page.get('dialog').text()).not.toContain(catalogs.en.commerce_auto_opening_setup)
      expect(page.get('dialog').findAll('button').some(b=>b.text()===catalogs.en.commerce_prepare_parent)).toBe(false)
      expect(page.findAll('tbody tr')).toHaveLength(0)
    }
    expect(h.invoke.mock.calls.filter(c=>c[0]==='commerce_release_unlinked')).toHaveLength(1)
    page.unmount()
  })

  it.each(['no_access','active'])('does not offer unlinked archive outside its scope: %s',async(mode)=>{
    const id='visit_'+'1'.repeat(32),h=host(['commerce_list','commerce_detail',...(mode==='no_access'?[]:['commerce_release_unlinked'])])
    h.invoke.mockImplementation((name:string)=>Promise.resolve(name==='commerce_list'?{items:[{visit_id:id,child_name:'Child',guardian_name:'Parent'}],has_more:false}:
      {visit_id:id,child_id:'child_1',child_name:'Child',guardian_name:'Parent',visit_state:mode==='active'?'active':'closed',parent_linked:false,account:null,choices:[],allowed_articles:[],commands:[],has_more:false}))
    const page=mountWith(Commerce,h);await flushPromises()
    await page.findAll('button').find(b=>b.text()==='Account details')!.trigger('click');await flushPromises()
    await page.get('dialog').findAll('button').find(b=>b.text()==='Commercial journal')!.trigger('click')
    expect(page.find('.cc-unlinked-release').exists()).toBe(false)
    page.unmount()
  })

  it('cashier receives the Barsy quote and cannot prepare a payment without method and received confirmation',async()=>{
    const id='visit_'+'1'.repeat(32)
    const h=host(['cashier_list','cashier_detail','cashier_preview','cashier_prepare','cashier_execute','cashier_request_outcome'])
    h.invoke.mockImplementation((name:string)=>{
      if(name==='cashier_list')return Promise.resolve({items:[{visit_id:id,child_name:'Child',guardian_name:'Parent',account_state:'open'}],has_more:false})
      if(name==='cashier_detail')return Promise.resolve({visit_id:id,child_id:'child_1',child_name:'Child',guardian_name:'Parent',visit_state:'closed',parent_linked:true,account:{state:'open',account_id:201,remote_state:'open',time_confirmed:1},choices:[],allowed_articles:[],commands:[],has_more:false})
      if(name==='cashier_preview')return Promise.resolve({status:'applied',message:null,data:{quote_id:'quote_'+'3'.repeat(32),amount:'12.50',currency_code:'EUR',expires_at:'2026-10-28T11:00:00Z',methods:[{paymethod_id:3,label:'Cash'}]}})
      if(name==='cashier_prepare')return Promise.resolve({status:'applied',message:null,data:{state:'prepared'}})
      throw new Error(name)
    })
    const page=mountWith(Cashier,h);await flushPromises()
    await page.findAll('button').find(b=>b.text()==='Account details')!.trigger('click');await flushPromises()
    expect(page.text()).not.toContain('Prepare parent synchronization')
    await page.get('dialog').findAll('button').find(b=>b.text()==='Payment')!.trigger('click')
    await page.get('dialog').findAll('button').find(b=>b.text()==='Read current payment amount')!.trigger('click');await flushPromises()
    expect(page.get('dialog').text()).toContain('12.50 EUR')
    const prepare=()=>page.get('dialog').findAll('button').find(b=>b.text()==='Pay and close bill')!
    expect(prepare().attributes('disabled')).toBeDefined()
    await page.get('#pay-method').setValue('3')
    await page.get('dialog').findAll('button').find(b=>b.text()==='Overview')!.trigger('click')
    await page.get('dialog').findAll('button').find(b=>b.text()==='Payment')!.trigger('click')
    expect((page.get('#pay-method').element as HTMLSelectElement).value).toBe('3')
    expect(prepare().attributes('disabled')).toBeDefined()
    await page.get('dialog form input[type="checkbox"]').setValue(true)
    await page.get('dialog form').trigger('submit');await flushPromises()
    const payload=h.invoke.mock.calls.find(c=>c[0]==='cashier_prepare')![1]
    expect(payload).toEqual({visit_id:id,quote_id:'quote_'+'3'.repeat(32),paymethod_id:3,confirmed:true})
    expect(h.invoke.mock.calls.some(c=>c[0]==='cashier_execute')).toBe(false)
    page.unmount()
  })
  it('shows cashier an unresolved operator action and identifies that another role must handle it',async()=>{
    const id='visit_'+'1'.repeat(32),cmd='commercial_'+'2'.repeat(32)
    const h=host(['cashier_list','cashier_detail'])
    const urgent={command_id:cmd,kind:'consumption',state:'uncertain',error_code:'commerce_check_required',parameters:{article_id:20,quantity:'1'},acknowledged:0}
    h.invoke.mockImplementation((name:string)=>Promise.resolve(name==='cashier_list'?{items:[{visit_id:id,child_name:'Child',guardian_name:'Parent'}],has_more:false}:{visit_id:id,child_id:'child_1',child_name:'Child',guardian_name:'Parent',visit_state:'closed',parent_linked:true,account:null,choices:[{article_id:20,label:'Juice'}],allowed_articles:[],commands:[],attention:[urgent],has_more:false}))
    const page=mountWith(Cashier,h);await flushPromises()
    await page.findAll('button').find(b=>b.text()==='Account details')!.trigger('click');await flushPromises()
    expect(page.get('dialog').text()).toContain('A staff member with the appropriate permission must handle this action')
    expect(page.get('dialog').findAll('button').some(b=>b.text()==='Check result without resending')).toBe(false)
    await page.get('dialog').findAll('button').find(b=>b.text()==='Commercial journal')!.trigger('click')
    expect(page.get('dialog').text()).toContain('Juice · 1')
    page.unmount()
  })
  it('commercial dialog discards late private data and closes on real access denial',async()=>{
    const id='visit_'+'1'.repeat(32);let reply:(value:any)=>void=()=>{}
    const h=host(['commerce_list','commerce_detail'])
    h.invoke.mockImplementation((name:string)=>name==='commerce_list'?Promise.resolve({items:[{visit_id:id,child_name:'Child',guardian_name:'Parent'}],has_more:false}):new Promise(resolve=>reply=resolve))
    const page=mountWith(Commerce,h);await flushPromises()
    await page.findAll('button').find(b=>b.text()==='Account details')!.trigger('click');await flushPromises()
    expect(page.get('dialog').text()).toContain('Loading')
    await page.get('dialog').trigger('cancel');reply({guardian_name:'Late private data'});await flushPromises()
    expect(page.find('dialog').exists()).toBe(false);expect(page.text()).not.toContain('Late private data')
    h.invoke.mockImplementation((name:string)=>name==='commerce_detail'?Promise.reject({code:'access_denied'}):Promise.resolve({items:[],has_more:false}))
    await page.findAll('button').find(b=>b.text()==='Account details')!.trigger('click');await flushPromises()
    expect(page.find('dialog').exists()).toBe(false)
    page.unmount()
  })
  it('configures commerce from bounded directory choices and saves a compare-and-set revision',async()=>{
    const h=host(['commerce_settings','commerce_save_settings','commerce_settings_outcome','barsy_articles','barsy_places'])
    let saved:any={revision:2,time_article_id:null,unit:'hours',places:[],articles:[]}
    h.invoke.mockImplementation((name:string,payload:any)=>{
      if(name==='commerce_settings')return Promise.resolve(JSON.parse(JSON.stringify(saved)))
      if(name==='barsy_articles')return Promise.resolve({status:'ready',items:[{article_id:10,label:'Time'},{article_id:20,label:'Juice'}],has_more:false})
      if(name==='commerce_save_settings'){const {expected_revision,...value}=payload;saved={revision:expected_revision+1,...value};return Promise.resolve({status:'applied',message:null,data:{state:'saved'}})}
      throw new Error(name)
    })
    const page=mountWith(CommerceSetup,h);await flushPromises()
    await page.findAll('form')[1].trigger('submit');await flushPromises()
    await page.findAll('button').find(b=>b.text()==='Use for stay time')!.trigger('click')
    expect(page.findAll('button').find(b=>b.text()==='Selected for stay time')!.attributes('aria-pressed')).toBe('true')
    expect(page.findAll('button').find(b=>b.text()==='Selected for stay time')!.classes()).toContain('ui-button--secondary')
    const add=page.findAll('.cc-catalog-list li')[1].findAll('button').find(b=>b.text()==='Allow consumption article')!
    expect(add.classes()).toContain('ui-button--primary')
    await add.trigger('click')
    expect(page.get('aside').text()).toContain('Selection changed')
    expect(h.invoke.mock.calls.some(c=>c[0]==='commerce_save_settings')).toBe(false)
    await page.get('aside button').trigger('click');await flushPromises()
    expect(h.invoke.mock.calls.find(c=>c[0]==='commerce_save_settings')![1]).toEqual({expected_revision:2,time_article_id:10,unit:'hours',places:[],articles:[{article_id:20,label:'Juice'}]})
    expect(page.get('aside').text()).toContain('Commercial settings saved')
    expect(page.text()).toContain('Juice')
    page.unmount()
  })
  it('saves child consumption before account opening only after explicit parent attestation and reloads the saved choices',async()=>{
    const id='visit_'+'1'.repeat(32),childId='child_'+'2'.repeat(32)
    const h=host(['commerce_list','commerce_detail','commerce_allow_child'])
    let saved:number[]=[]
    h.invoke.mockImplementation((name:string,payload:any)=>{
      if(name==='commerce_list')return Promise.resolve({items:[{visit_id:id,child_name:'Child',guardian_name:'Parent'}],has_more:false})
      if(name==='commerce_detail')return Promise.resolve({visit_id:id,child_id:childId,child_name:'Child',guardian_name:'Parent',visit_state:'active',parent_linked:true,account:null,allowed_articles:[...saved],choices:[{article_id:20,label:'Juice'}],commands:[],has_more:false})
      if(name==='commerce_allow_child'){saved=[...payload.article_ids];return Promise.resolve({status:'applied',message:null,data:{state:'saved'}})}
      throw new Error(name)
    })
    const page=mountWith(Commerce,h);await flushPromises()
    await page.findAll('button').find(b=>b.text()==='Account details')!.trigger('click');await flushPromises()
    await page.get('dialog').findAll('button').find(b=>b.text()==='Consumption')!.trigger('click')
    const form=()=>page.get('dialog form')
    await form().findAll('input[type="checkbox"]')[0].setValue(true)
    await page.get('dialog').findAll('button').find(b=>b.text()==='Overview')!.trigger('click')
    await page.get('dialog').findAll('button').find(b=>b.text()==='Consumption')!.trigger('click')
    expect((form().findAll('input')[0].element as HTMLInputElement).checked).toBe(true)
    expect(form().get('button').attributes('disabled')).toBeDefined()
    expect(form().text()).toContain('confirm the parent permission')
    await form().trigger('submit');expect(h.invoke.mock.calls.some(c=>c[0]==='commerce_allow_child')).toBe(false)
    await form().findAll('input[type="checkbox"]')[1].setValue(true)
    await form().trigger('submit');await flushPromises()
    expect(h.invoke.mock.calls.find(c=>c[0]==='commerce_allow_child')![1]).toEqual({child_id:childId,expected_articles:[],article_ids:[20],reviewed:true})
    expect(form().text()).toContain('Child consumption permissions saved')
    expect((form().findAll('input')[0].element as HTMLInputElement).checked).toBe(true)
    await form().findAll('input[type="checkbox"]')[0].setValue(false)
    expect(form().text()).not.toContain('Child consumption permissions saved')
    expect(form().text()).toContain('confirm the parent permission')
    page.unmount()
  })
  it('shows configured place names on initial load and removes only the chosen ID through an explicit settings save',async()=>{
    const h=host(['commerce_settings','commerce_save_settings','barsy_places'])
    let saved:any={revision:2,time_article_id:10,unit:'minutes',places:[6,7,8],articles:[]}
    h.invoke.mockImplementation((name:string,payload:any)=>{
      if(name==='commerce_settings')return Promise.resolve(JSON.parse(JSON.stringify(saved)))
      if(name==='barsy_places')return Promise.resolve({status:'ready',items:[{place_id:6,label:'Игрална зала 1'},{place_id:7,label:'Игрална зала 2'},{place_id:8,label:'Игрална зала 3'}].filter(p=>payload.place_ids.includes(p.place_id)),has_more:false})
      if(name==='commerce_save_settings'){const {expected_revision,...value}=payload;saved={revision:expected_revision+1,...value};return Promise.resolve({status:'applied',message:null,data:{state:'saved'}})}
      throw new Error(name)
    })
    const page=mountWith(CommerceSetup,h);await flushPromises()
    expect(h.invoke.mock.calls.find(c=>c[0]==='barsy_places')![1]).toEqual({offset:0,place_ids:[6,7,8]})
    expect(page.get('.cc-place-list').text()).toContain('Игрална зала 1')
    const remove=page.get('button[aria-label="Remove Игрална зала 1"]')
    expect(remove.classes()).toContain('ui-button--danger')
    expect(remove.text()).toBe('Игрална зала 1')
    await remove.trigger('click')
    expect(page.get('.cc-place-list').text()).not.toContain('Игрална зала 1')
    expect(page.get('.cc-place-list').text()).toContain('Игрална зала 2')
    expect(h.invoke.mock.calls.some(c=>c[0]==='commerce_save_settings')).toBe(false)
    await page.get('aside button').trigger('click');await flushPromises()
    expect(h.invoke.mock.calls.find(c=>c[0]==='commerce_save_settings')![1].places).toEqual([7,8])
    expect(page.get('.cc-place-list').text()).toContain('Игрална зала 3')
    page.unmount()
  })
  it('resolves the selected stay article by ID and renders only names in the settings catalogue',async()=>{
    const h=host(['commerce_settings','barsy_articles'])
    h.invoke.mockImplementation((name:string,payload:any)=>{
      if(name==='commerce_settings')return Promise.resolve({revision:1,time_article_id:28,unit:'minutes',places:[],articles:[]})
      if(name==='barsy_articles')return Promise.resolve({status:'ready',items:payload.article_id?[{article_id:28,label:'Play room minutes'}]:[{article_id:28,label:'Play room minutes'},{article_id:32,label:'Juice'}],has_more:false})
      throw new Error(name)
    })
    const page=mountWith(CommerceSetup,h);await flushPromises()
    expect(page.text()).toContain('Stay article: Play room minutes')
    expect(h.invoke.mock.calls.find(c=>c[0]==='barsy_articles')![1]).toEqual({query:'',offset:0,article_id:28})
    await page.findAll('form')[1].trigger('submit');await flushPromises()
    expect(page.get('.cc-catalog-list').text()).toContain('Juice')
    expect(page.get('.cc-catalog-list').text()).not.toMatch(/\b(28|32)\b/)
    expect(page.findAll('.cc-catalog-list li')).toHaveLength(2)
    page.unmount()
  })
  it('opens stay details immediately, paginates the selected stay, and discards a reply after Escape', async () => {
    let reply:(value:any)=>void=()=>{}
    const visit={visit_id:'visit_'+'1'.repeat(32),child_name:'Selected child',phase:'inside',duration_seconds:30,rounded_minutes:1,last_transition_at:'2026-10-27T10:00:00Z',entered_at:'2026-10-27T10:00:00Z',exited_at:null}
    const h=host(['list_visits','get_visit'])
    h.invoke.mockImplementation((name:string)=>name==='list_visits' ? Promise.resolve({items:[visit],total:1}) : new Promise(resolve=>{reply=resolve}))
    const page=mountWith(Visits,h);await flushPromises()
    await page.findAll('button').find(b=>b.text()==='Stay details')!.trigger('click');await flushPromises()
    expect(page.find('dialog').element.open).toBe(true)
    expect(page.find('dialog').text()).toContain('Loading')
    expect(h.invoke.mock.calls.at(-1)![1]).toEqual({visit_id:visit.visit_id,offset:0,limit:20})
    reply({...visit,guardian_name:'Selected parent',timeline_complete:true,event_total:21,events:[{event_id:'event_1',kind:'start',occurred_at:visit.entered_at,duration_seconds:0,phase:'inside'}]});await flushPromises()
    expect(page.find('dialog').text()).toContain('Selected parent')
    expect(page.find('dialog li').text()).toContain('Entry')
    await page.find('dialog').findAll('button').find(b=>b.text()==='Next')!.trigger('click');await flushPromises()
    expect(h.invoke.mock.calls.at(-1)![1]).toEqual({visit_id:visit.visit_id,offset:20,limit:20})
    await page.find('dialog').trigger('cancel');await flushPromises()
    reply({...visit,guardian_name:'Late private reply',timeline_complete:true,event_total:21,events:[]});await flushPromises()
    expect(page.find('dialog').exists()).toBe(false)
    expect(page.text()).not.toContain('Late private reply')
    page.unmount()
  })
  it('shows a detail error in the open dialog, recovers on explicit refresh and closes after access denial', async () => {
    const visit={visit_id:'visit_'+'1'.repeat(32),child_name:'Selected child',phase:'closed',duration_seconds:30,rounded_minutes:1,last_transition_at:'2026-10-27T10:00:00Z',entered_at:'2026-10-27T10:00:00Z',exited_at:'2026-10-27T10:00:30Z'}
    const h=host(['list_visits','get_visit'])
    let failure:Error|null=new Error('unavailable')
    h.invoke.mockImplementation((name:string)=>name==='list_visits' ? Promise.resolve({items:[visit],total:1}) : failure ? Promise.reject(failure) : Promise.resolve({...visit,guardian_name:'Recovered parent',timeline_complete:true,event_total:0,events:[]}))
    const page=mountWith(Visits,h);await flushPromises()
    await page.findAll('button').find(b=>b.text()==='Stay details')!.trigger('click');await flushPromises()
    expect(page.find('dialog [role="alert"]').text()).toContain('Read unavailable')
    const attempts=h.invoke.mock.calls.length
    await flushPromises();expect(h.invoke).toHaveBeenCalledTimes(attempts)
    failure=null
    await page.find('dialog').findAll('button').find(b=>b.text()==='Refresh')!.trigger('click');await flushPromises()
    expect(page.find('dialog').text()).toContain('Recovered parent')
    await page.find('dialog').findAll('button').find(b=>b.text()==='Close')!.trigger('click');await flushPromises()
    failure=Object.assign(new Error('revoked'),{code:'access_denied'})
    await page.findAll('button').find(b=>b.text()==='Stay details')!.trigger('click');await flushPromises()
    expect(page.find('dialog').exists()).toBe(false)
    expect(page.text()).not.toContain('Recovered parent')
    expect(page.text()).toContain('Access is unavailable')
    page.unmount()
  })
  it.each([
    {name:'desk',component:Desk,operations:['list_registrations']},
    {name:'administration',component:Administration,operations:['admin_list_clients']},
    {name:'readers',component:Readers,operations:['get_reader_settings','list_reader_activity']},
  ])('keeps $name query failure separate from revoked access and clears it after explicit refresh', async ({component,operations}) => {
    const h=host(operations)
    let failure: Error | null=null
    h.invoke.mockImplementation((operation:string)=> {
      if(failure)return Promise.reject(failure)
      return Promise.resolve(operation==='get_reader_settings'
        ? {revision:1,mode:'disabled',effective_from:'2026-10-27T10:00:00Z',toggle_ids:[],entry_ids:[],exit_ids:[],device_ids:[]}
        : {items:[{registration_id:'reg_1',guardian_name:'Fresh record',status:'approved',event_id:'evt_1',reader_id:'in',occurred_at:'2026-10-27T10:00:00Z',outcome:'started',child_name:'Fresh record'}],total:1})
    })
    const page=mountWith(component,h);await flushPromises()
    expect(page.text()).toContain('Fresh record')
    const refresh=()=>page.findAll('button').find(b=>b.text()==='Refresh')!.trigger('click')
    failure=Object.assign(new Error('query response unavailable'),{code:'unconfirmed'})
    await refresh();await flushPromises()
    expect(page.text()).toContain('Read unavailable.')
    expect(page.text()).not.toContain('Access is unavailable')
    expect(page.text()).not.toContain('Fresh record')
    const attempts=h.invoke.mock.calls.length
    await flushPromises();expect(h.invoke).toHaveBeenCalledTimes(attempts)
    failure=null;await refresh();await flushPromises()
    expect(page.text()).toContain('Fresh record')
    expect(page.text()).not.toContain('Read unavailable.')
    failure=Object.assign(new Error('revoked'),{code:'access_denied'})
    await refresh();await flushPromises()
    expect(page.text()).toContain('Access is unavailable')
    expect(page.text()).not.toContain('Fresh record')
    page.unmount()
  })
  it('loads disabled reader policy without mutation and keeps a stale revision refusal editable', async () => {
    const h = host(['get_reader_settings','list_reader_activity','set_reader_settings','reader_request_outcome'])
    h.invoke.mockImplementation((operation: string) => Promise.resolve(operation === 'get_reader_settings'
      ? {revision:4,mode:'disabled',effective_from:'2026-10-27T10:00:00Z',toggle_ids:[],entry_ids:[],exit_ids:[],device_ids:['dev_'+'9'.repeat(32)]}
      : operation === 'list_reader_activity' ? {items:[],total:0}
      : {status:'rejected',data:null,message:'Reader settings changed; refresh before saving'}))
    const page = mountWith(Readers,h); await flushPromises()
    expect(h.invoke.mock.calls.some(c=>c[0]==='set_reader_settings')).toBe(false)
    expect(page.find('select').element.value).toBe('disabled')
    expect(page.text()).toContain('dev_'+'9'.repeat(32))
    await page.find('select').setValue('directional')
    await page.findAll('textarea')[0].setValue('entry-1\nentry-2')
    await page.findAll('textarea')[1].setValue('exit-1')
    await page.find('form').trigger('submit'); await flushPromises()
    expect(h.invoke.mock.calls.find(c=>c[0]==='set_reader_settings')![1]).toEqual({expected_revision:4,mode:'directional',toggle_ids:[],entry_ids:['entry-1','entry-2'],exit_ids:['exit-1']})
    expect(page.text()).toContain('Reader settings changed')
    expect(page.findAll('textarea')[0].element.value).toBe('entry-1\nentry-2')
    expect(page.find('fieldset').attributes('disabled')).toBeUndefined()
    page.unmount()
  })
  it('reviews a lost reader save by its original identity without replaying it', async () => {
    const h = host(['get_reader_settings','list_reader_activity','set_reader_settings','reader_request_outcome'])
    h.invoke.mockImplementation((operation: string) => {
      if(operation==='get_reader_settings')return Promise.resolve({revision:1,mode:'disabled',effective_from:'2026-10-27T10:00:00Z',toggle_ids:[],entry_ids:[],exit_ids:[],device_ids:[]})
      if(operation==='list_reader_activity')return Promise.resolve({items:[],total:0})
      if(operation==='set_reader_settings')return Promise.reject(new Error('lost reply'))
      return Promise.resolve({status:'confirmed',result_json:JSON.stringify({status:'applied',data:{revision:2,status:'updated'},message:null})})
    })
    const page = mountWith(Readers,h); await flushPromises()
    await page.find('form').trigger('submit'); await flushPromises()
    const original = JSON.parse(sessionStorage.getItem('child-center-local-pending-v1')!)
    expect(page.find('fieldset').attributes('disabled')).toBeDefined()
    await page.findAll('button').find(b=>b.text()==='Check saved outcome')!.trigger('click'); await flushPromises()
    expect(h.invoke.mock.calls.filter(c=>c[0]==='set_reader_settings')).toHaveLength(1)
    expect(h.invoke.mock.calls.find(c=>c[0]==='reader_request_outcome')![1]).toEqual(original)
    expect(sessionStorage.getItem('child-center-local-pending-v1')).toBeNull()
    page.unmount()
  })
  it('clears reader history and configuration after access is revoked', async () => {
    const h = host(['get_reader_settings','list_reader_activity'])
    h.invoke.mockImplementation((operation: string) => Promise.resolve(operation === 'get_reader_settings'
      ? {revision:1,mode:'disabled',effective_from:'2026-10-27T10:00:00Z',toggle_ids:[],entry_ids:[],exit_ids:[],device_ids:[]}
      : {items:[{event_id:'evt_1',reader_id:'door-1',occurred_at:'2026-10-27T10:00:00Z',outcome:'started',child_name:'Private reader child'}],total:1}))
    const page = mountWith(Readers,h); await flushPromises()
    expect(page.text()).toContain('Private reader child')
    h.getInfo.mockRejectedValueOnce(new Error('revoked'))
    await page.findAll('button').find(b=>b.text()==='Refresh')!.trigger('click'); await flushPromises()
    expect(page.text()).not.toContain('Private reader child')
    expect(page.find('form').exists()).toBe(false)
    page.unmount()
  })
  it('previews a named USB scan before confirming its exact snapshot', async () => {
    const h = host(['list_visits','preview_scan','confirm_scan','visit_request_outcome'])
    h.invoke.mockImplementation((operation: string) => {
      if (operation === 'list_visits') return Promise.resolve({items:[],total:0})
      if (operation === 'preview_scan') return Promise.resolve({child_name:'Named child',phase:'absent',action:'start',preview_token:'a'.repeat(64),visit_id:null})
      return Promise.resolve({status:'applied',data:{status:'inside',visit_id:'visit_1'},message:null})
    })
    const page = mountWith(Visits,h); await flushPromises()
    await page.find('fieldset input').setValue('usb-code')
    await page.find('fieldset').element.closest('form')!.dispatchEvent(new Event('submit',{bubbles:true,cancelable:true}))
    await flushPromises()
    expect(page.text()).toContain('Named child')
    expect(h.invoke.mock.calls.filter(c=>c[0] === 'confirm_scan')).toHaveLength(0)
    await page.findAll('button').find(b=>b.text()==='Confirm entry')!.trigger('click'); await flushPromises()
    expect(h.invoke.mock.calls.filter(c=>c[0] === 'confirm_scan')).toHaveLength(1)
    expect(h.invoke.mock.calls.find(c=>c[0] === 'confirm_scan')![1]).toEqual({code:'usb-code',preview_token:'a'.repeat(64)})
    page.unmount()
  })
  it('drops a delayed bracelet preview when another code is entered', async () => {
    let reply: (value:any)=>void = ()=>{}
    const h = host(['list_visits','preview_scan','confirm_scan'])
    h.invoke.mockImplementation((operation:string) => operation === 'list_visits' ? Promise.resolve({items:[],total:0}) : new Promise(resolve=>{reply=resolve}))
    const page = mountWith(Visits,h); await flushPromises()
    await page.find('fieldset input').setValue('first')
    await page.find('fieldset').element.closest('form')!.dispatchEvent(new Event('submit',{bubbles:true,cancelable:true}))
    await page.find('fieldset input').setValue('second')
    reply({child_name:'Old child',phase:'absent',action:'start',preview_token:'a'.repeat(64),visit_id:null}); await flushPromises()
    expect(page.text()).not.toContain('Old child')
    expect(h.invoke.mock.calls.some(c=>c[0] === 'confirm_scan')).toBe(false)
    page.unmount()
  })
  it('sends Sofia calendar-day filters and distinguishes the repeated DST hour', async () => {
    const h = host(['list_visits'])
    h.invoke.mockResolvedValue({items:[],total:0})
    const page = mountWith(Visits,h); await flushPromises()
    const dates = page.findAll('input[type=date]')
    await dates[0].setValue('2026-10-25'); await dates[1].setValue('2026-10-25')
    await dates[0].element.closest('form')!.dispatchEvent(new Event('submit',{bubbles:true,cancelable:true})); await flushPromises()
    expect(h.invoke.mock.calls.at(-1)![1]).toMatchObject({started_from:'2026-10-25',started_to:'2026-10-25'})
    expect(formatTimestamp('2026-10-25T00:30:00Z','en-GB')).toContain('(+03:00)')
    expect(formatTimestamp('2026-10-25T01:30:00Z','bg-BG')).toContain('(+02:00)')
    expect(formatTimestamp('2026-10-28T11:08:28Z','bg-BG')).not.toMatch(/GMT|Гринуич|\+02:00/)
    page.unmount()
  })
  it('keeps staff browser registration usable after fullscreen denial and uses staff permission', async () => {
    const h = host(['register_client','request_outcome'])
    h.invoke.mockResolvedValue({status:'applied',data:{registration_id:'reg_1',status:'approved'},message:null})
    const page = mountWith(Registration,h); await flushPromises()
    Object.defineProperty(page.find('main').element,'requestFullscreen',{value:vi.fn().mockRejectedValue(new Error('Denied')),configurable:true})
    await page.findAll('button').find(b=>b.text()==='Fullscreen')!.trigger('click'); await flushPromises()
    expect(page.text()).toContain('Registration remains available')
    await fill(page.findComponent(ClientForm)); await page.find('form').trigger('submit'); await flushPromises()
    expect(h.invoke.mock.calls[0][0]).toBe('register_client')
    expect(page.text()).toContain('Registration saved and approved')
    page.unmount()
  })
  it('takes initial/live locale from Core and unsubscribes without losing form state', async () => {
    const h = host(['submit_registration'])
    h.setLocale('bg')
    const page = mountWith(Registration,h); await flushPromises()
    expect(page.text()).toContain('Регистрация')
    await fill(page.findComponent(ClientForm))
    h.setLocale('en'); await flushPromises()
    expect(page.text()).toContain('Registration')
    expect((page.find('input').element as HTMLInputElement).value).toBe('Test Parent')
    h.setLocale('zz'); await flushPromises()
    expect(page.text()).toContain('Registration')
    page.unmount()
    expect(h.unsubscribe).toHaveBeenCalledTimes(1)
  })
  it('performs no Barsy reads until requested and preserves a search during a Core language switch', async () => {
    const h = host(['barsy_check','barsy_articles'])
    const page = mountWith(Barsy,h); await flushPromises()
    expect(h.invoke).not.toHaveBeenCalled()
    expect(page.text()).toContain('settings gear')
    expect(page.find('input[type=password]').exists()).toBe(false)
    await page.find('#barsy-search').setValue('Juice')
    h.setLocale('bg'); await flushPromises()
    expect((page.find('#barsy-search').element as HTMLInputElement).value).toBe('Juice')
    expect(page.get('summary').text()).toContain('Връзка и подробен справочник')
    h.invoke.mockResolvedValue({status:'ready',items:[{article_id:12,label:'Synthetic Juice'}],has_more:false})
    await page.find('form').trigger('submit'); await flushPromises()
    expect(h.invoke.mock.calls).toEqual([['barsy_articles',{query:'Juice',offset:0}]])
    expect(page.text()).toContain('Synthetic Juice')
    page.unmount()
  })
  it('clears Barsy results on denied refresh and ignores a pending external reply', async () => {
    let reply: (value: any) => void = () => {}
    const h = host(['barsy_check','barsy_articles'])
    h.invoke.mockImplementation(() => new Promise(resolve => { reply = resolve }))
    const page = mountWith(Barsy,h); await flushPromises()
    await page.find('form').trigger('submit')
    h.getInfo.mockRejectedValueOnce(new Error('Revoked'))
    await page.findAll('button').find(b => b.text() === 'Refresh')!.trigger('click'); await flushPromises()
    reply({status:'ready',items:[{article_id:12,label:'Stale directory'}],has_more:false}); await flushPromises()
    expect(page.text()).not.toContain('Stale directory')
    expect(page.text()).toContain('Access is unavailable')
    expect(h.invoke).toHaveBeenCalledTimes(1)
    page.unmount()
  })
  it('shows a failed Barsy check without retry and keeps local controls credential-free', async () => {
    const h = host(['barsy_check'])
    h.invoke.mockResolvedValue({status:'unavailable',pos_id:null})
    const page = mountWith(Barsy,h); await flushPromises()
    await page.findAll('button').find(b => b.text() === 'Check connection')!.trigger('click'); await flushPromises()
    expect(page.text()).toContain('Barsy is unavailable')
    expect(h.invoke).toHaveBeenCalledTimes(1)
    expect(page.find('input').exists()).toBe(false)
    page.unmount()
  })
  it('exports and erases the selected client without entering an internal identifier', async () => {
    const id = 'reg_'+'1'.repeat(32)
    const h = host(['admin_list_clients','admin_get_client','export_personal_data','erase_personal_data'])
    h.invoke.mockImplementation((operation: string) => {
      if (operation === 'admin_list_clients') return Promise.resolve({items:[{registration_id:id,guardian_name:'Selected Parent',status:'approved'}],total:1})
      if (operation === 'admin_get_client') return Promise.resolve({registration_id:id,revision:1,status:'approved',guardian:{display_name:'Selected Parent',phone:'123',email:''},children:[],consent_version:'v1',consented_at:'2026-10-27'})
      return Promise.resolve({status:'applied',data:operation === 'export_personal_data' ? {document_json:'{"synthetic":true}'} : {status:'erased'},message:null})
    })
    const page = mountWith(Administration,h); await flushPromises()
    await page.find('.cc-row').trigger('click'); await flushPromises()
    expect(page.find('input[pattern]').exists()).toBe(false)
    await page.findAll('button').find(b => b.text() === 'Export')!.trigger('click'); await flushPromises()
    expect(page.find('pre').text()).toContain('synthetic')
    expect(h.invoke.mock.calls.find(c => c[0] === 'export_personal_data')![1]).toEqual({registration_id:id})
    expect(page.findAll('button').find(b => b.text() === 'Erase')!.attributes('disabled')).toBeDefined()
    await page.find('input[type=checkbox]').setValue(true)
    await page.findAll('button').find(b => b.text() === 'Erase')!.trigger('click'); await flushPromises()
    expect(h.invoke.mock.calls.find(c => c[0] === 'erase_personal_data')![1]).toEqual({registration_id:id,confirmed:true})
    expect(page.find('fieldset').exists()).toBe(false)
    expect(page.find('pre').exists()).toBe(false)
    page.unmount()
  })
  it('retains stale administration edits and submits the observed revision once', async () => {
    const h = host(['admin_list_clients', 'admin_get_client', 'admin_update_client', 'admin_request_outcome'])
    h.invoke.mockImplementation((operation: string) => {
      if (operation === 'admin_list_clients') return Promise.resolve({items:[{registration_id:'reg_'+'1'.repeat(32),guardian_name:'Parent',status:'approved'}],total:1})
      if (operation === 'admin_get_client') return Promise.resolve({registration_id:'reg_'+'1'.repeat(32),revision:3,status:'approved',
        guardian:{display_name:'Parent',phone:'123',email:''},children:[{child_id:'child_'+'2'.repeat(32),display_name:'Child'}],consent_version:'v1',consented_at:'2026-10-27'})
      return Promise.resolve({status:'rejected',data:null,message:'Client changed; refresh before saving'})
    })
    const page = mountWith(Administration,h); await flushPromises()
    await page.find('.cc-row').trigger('click'); await flushPromises()
    await page.find('fieldset input').setValue('My correction')
    await page.findAll('form')[1].trigger('submit'); await flushPromises()
    expect(h.invoke.mock.calls.filter(c => c[0] === 'admin_update_client')).toHaveLength(1)
    expect(h.invoke.mock.calls.find(c => c[0] === 'admin_update_client')![1]).toMatchObject({expected_revision:3,guardian:{display_name:'My correction'}})
    expect((page.find('fieldset input').element as HTMLInputElement).value).toBe('My correction')
    expect(page.text()).toContain('Client changed; refresh before saving')
    expect(page.text()).not.toContain('Changes saved')
    page.unmount()
  })
  it('resolves a lost administration response without resending the correction', async () => {
    const h = host(['admin_list_clients','admin_get_client','admin_update_client','admin_request_outcome'])
    h.invoke.mockImplementation((operation: string) => {
      if (operation === 'admin_list_clients') return Promise.resolve({items:[{registration_id:'reg_'+'1'.repeat(32),guardian_name:'Parent',status:'approved'}],total:1})
      if (operation === 'admin_get_client') return Promise.resolve({registration_id:'reg_'+'1'.repeat(32),revision:1,status:'approved',guardian:{display_name:'Parent',phone:'123',email:''},children:[],consent_version:'v1',consented_at:'2026-10-27'})
      if (operation === 'admin_request_outcome') return Promise.resolve({status:'confirmed',result_json:JSON.stringify({status:'applied',data:{status:'updated',revision:2},message:null})})
      return Promise.reject(new Error('Lost reply'))
    })
    const page = mountWith(Administration,h); await flushPromises()
    await page.find('.cc-row').trigger('click'); await flushPromises()
    await page.findAll('form')[1].trigger('submit'); await flushPromises()
    expect(page.find('fieldset').attributes('disabled')).toBeDefined()
    await page.findAll('button').find(b => b.text() === 'Check saved outcome')!.trigger('click'); await flushPromises()
    expect(h.invoke.mock.calls.filter(c => c[0] === 'admin_update_client')).toHaveLength(1)
    expect(h.invoke.mock.calls.some(c => c[0] === 'admin_request_outcome')).toBe(true)
    expect(sessionStorage.getItem('child-center-local-pending-v1')).toBeNull()
    page.unmount()
  })
  it('clears administration personal data on revoked access and ignores delayed details', async () => {
    let reply: (value: any) => void = () => {}
    const h = host(['admin_list_clients','admin_get_client'])
    h.invoke.mockImplementation((operation: string) => operation === 'admin_list_clients'
      ? Promise.resolve({items:[{registration_id:'reg_1',guardian_name:'Private Parent',status:'approved'}],total:1})
      : new Promise(resolve => { reply = resolve }))
    const page = mountWith(Administration,h); await flushPromises()
    await page.find('.cc-row').trigger('click')
    h.getInfo.mockRejectedValueOnce(new Error('Revoked'))
    // Invoke a submit on the search form to supersede the detail read.
    await page.find('form').trigger('submit'); await flushPromises()
    reply({registration_id:'reg_1',revision:1,status:'approved',guardian:{display_name:'Stale private data',phone:'123',email:''},children:[],consent_version:'v1',consented_at:'2026-10-27'})
    await flushPromises()
    expect(page.text()).not.toContain('Private Parent')
    expect(page.text()).not.toContain('Stale private data')
    page.unmount()
  })
  it('requires consent and a contact before emitting registration', async () => {
    const submitted = vi.fn()
    const form = mount(ClientForm, { props: { disabled: false, onSubmit: submitted } })
    await form.find('form').trigger('submit')
    expect(submitted).not.toHaveBeenCalled()
    await fill(form)
    await form.find('form').trigger('submit')
    expect(submitted).toHaveBeenCalledTimes(1)
    const payload = submitted.mock.calls[0][0]
    expect(payload.guardian.display_name).toBe('Test Parent')
    expect(payload.guardian.consent_version).toBe('local-registration-v2')
    expect(payload.children).toEqual([{ display_name: 'Test Child',allowed_article_ids:[] }])
    form.unmount()
  })
  it('does not expose registration actions without live host access', async () => {
    const h = host([])
    const page = mountWith(Desk, h)
    await flushPromises()
    expect(page.findComponent(ClientForm).exists()).toBe(false)
    expect(h.invoke).not.toHaveBeenCalled()
    page.unmount()
  })
  it('submits exactly once, blocks after lost response, and resolves without replay', async () => {
    const h = host(['submit_registration', 'kiosk_request_outcome'])
    h.invoke.mockRejectedValueOnce(new Error('synthetic lost reply')).mockResolvedValueOnce({ status: 'confirmed',
      result_json: JSON.stringify({ status: 'applied', data: { registration_id: 'reg_' + '1'.repeat(32), status: 'submitted' }, message: null }) })
    const page = mountWith(Registration, h)
    await flushPromises()
    await fill(page.findComponent(ClientForm))
    await page.find('form').trigger('submit')
    await flushPromises()
    expect(h.invoke).toHaveBeenCalledTimes(1)
    const options = h.invoke.mock.calls[0][2]
    expect(options.idempotencyKey).toMatch(/^[0-9a-f]{32}$/)
    expect(page.find('fieldset').attributes('disabled')).toBeDefined()
    const button = page.findAll('button').find(b => b.text().includes('Check saved outcome'))!
    await button.trigger('click'); await flushPromises()
    expect(h.invoke.mock.calls[1]).toEqual(['kiosk_request_outcome', { request_id: options.idempotencyKey, operation_id: 'submit_registration' }])
    expect(page.findComponent(ClientForm).exists()).toBe(false)
    expect(page.text()).toContain('Submitted for staff approval')
    expect(sessionStorage.getItem('child-center-local-pending-v1')).toBeNull()
    page.unmount()
  })
  it('shows a durable domain refusal and permits a corrected logical request', async () => {
    const h = host(['submit_registration'])
    h.invoke.mockResolvedValue({ status: 'rejected', data: null, message: 'Names and at least one contact are required' })
    const page = mountWith(Registration, h); await flushPromises()
    await fill(page.findComponent(ClientForm)); await page.find('form').trigger('submit'); await flushPromises()
    expect(page.text()).toContain('Names and at least one contact are required')
    expect(page.find('fieldset').attributes('disabled')).toBeUndefined()
    expect(h.invoke).toHaveBeenCalledTimes(1)
    page.unmount()
  })
  it('clears personal listings when a refreshed read is denied', async () => {
    const h = host(['list_registrations'])
    h.invoke.mockResolvedValueOnce({ items: [{ registration_id: 'reg_' + '1'.repeat(32), guardian_name: 'Sensitive Parent', status: 'approved' }], total: 1 })
    const page = mountWith(Desk, h); await flushPromises()
    expect(page.text()).toContain('Sensitive Parent')
    h.getInfo.mockRejectedValueOnce(new Error('revoked'))
    await page.findAll('button').find(b => b.text().includes('Refresh'))!.trigger('click'); await flushPromises()
    expect(page.text()).not.toContain('Sensitive Parent')
    page.unmount()
  })
  it('keeps an invalid mutation response pending instead of allowing a replacement', async () => {
    const h = host(['submit_registration', 'kiosk_request_outcome'])
    h.invoke.mockResolvedValueOnce({ status: 'unexpected' }).mockResolvedValueOnce({ status: 'confirmed', result_json: '{}' })
    const page = mountWith(Registration, h); await flushPromises()
    await fill(page.findComponent(ClientForm)); await page.find('form').trigger('submit'); await flushPromises()
    const saved = sessionStorage.getItem('child-center-local-pending-v1')
    expect(saved).not.toBeNull()
    await page.findAll('button').find(b => b.text() === 'Check saved outcome')!.trigger('click'); await flushPromises()
    expect(sessionStorage.getItem('child-center-local-pending-v1')).toBe(saved)
    expect(page.find('fieldset').attributes('disabled')).toBeDefined()
    page.unmount()
  })
  it('ignores an old client detail after another client is selected', async () => {
    let first: (value: any) => void = () => {}
    const h = host(['list_registrations', 'get_registration'])
    h.invoke.mockImplementation((operation: string, payload: any) => {
      if (operation === 'list_registrations') return Promise.resolve({ items: [
        { registration_id:'reg_1', guardian_name:'First', status:'approved' },
        { registration_id:'reg_2', guardian_name:'Second', status:'approved' }], total:2 })
      if (payload.registration_id === 'reg_1') return new Promise(resolve => { first = resolve })
      return Promise.resolve({ registration_id:'reg_2', status:'approved', guardian:{display_name:'Current guardian',phone:'222',email:''},children:[] })
    })
    const page = mountWith(Desk,h); await flushPromises()
    await page.findAll('.cc-row')[0].trigger('click')
    await page.findAll('.cc-row')[1].trigger('click'); await flushPromises()
    first({ registration_id:'reg_1',status:'approved',guardian:{display_name:'Stale guardian',phone:'111',email:''},children:[] })
    await flushPromises()
    expect(page.text()).toContain('Current guardian')
    expect(page.text()).not.toContain('Stale guardian')
    page.unmount()
  })
  it('drops a detail reply after a refresh has revoked access', async () => {
    let reply: (value: any) => void = () => {}
    const h = host(['list_registrations','get_registration'])
    h.invoke.mockImplementation((operation: string) => operation === 'list_registrations'
      ? Promise.resolve({items:[{registration_id:'reg_1',guardian_name:'First',status:'approved'}],total:1})
      : new Promise(resolve => { reply = resolve }))
    const page = mountWith(Desk,h); await flushPromises()
    await page.find('.cc-row').trigger('click')
    h.getInfo.mockRejectedValueOnce(new Error('revoked'))
    await page.findAll('button').find(b => b.text() === 'Refresh')!.trigger('click'); await flushPromises()
    reply({registration_id:'reg_1',status:'approved',guardian:{display_name:'Stale private data',phone:'111',email:''},children:[]})
    await flushPromises()
    expect(page.text()).not.toContain('Stale private data')
    page.unmount()
  })
  it('offers visits-only staff a named finish confirmation and its exact snapshot', async () => {
    const visit = {visit_id:'visit_'+'1'.repeat(32),child_name:'Selected child',phase:'inside',duration_seconds:30,rounded_minutes:1,last_transition_at:'2026-10-27T10:00:00+00:00'}
    const h = host(['list_visits','finish_visit','visit_request_outcome'])
    h.invoke.mockResolvedValueOnce({items:[visit],total:1}).mockResolvedValueOnce({status:'applied',data:{status:'closed',duration_seconds:30,rounded_minutes:1},message:null}).mockResolvedValueOnce({items:[],total:0})
    const page = mountWith(Visits,h); await flushPromises()
    expect(page.findAll('button').some(b => b.text() === 'Clients')).toBe(false)
    await page.findAll('button').find(b => b.text() === 'Finish stay')!.trigger('click'); await flushPromises()
    expect(h.invoke).toHaveBeenCalledTimes(1)
    expect(page.find('[aria-label="Finish stay confirmation"]').text()).toContain('Selected child')
    await page.findAll('button').find(b => b.text() === 'Cancel')!.trigger('click')
    expect(h.invoke).toHaveBeenCalledTimes(1)
    await page.findAll('button').find(b => b.text() === 'Finish stay')!.trigger('click')
    await page.findAll('button').find(b => b.text() === 'Confirm finish')!.trigger('click'); await flushPromises()
    expect(h.invoke.mock.calls[1][1]).toEqual({visit_id:visit.visit_id,expected_transition_at:visit.last_transition_at,expected_phase:'inside'})
    expect(h.invoke.mock.calls.some(([name]) => name === 'list_registrations')).toBe(false)
    page.unmount()
  })
  it('uses the incoming locale without a local selector and preserves the entered form', async () => {
    const h = host(['submit_registration'])
    const page = mountWith(Registration,h); await flushPromises()
    await fill(page.findComponent(ClientForm))
    await page.setProps({ locale: 'bg-BG' })
    expect(page.text()).toContain('Детски център')
    expect(page.text()).toContain('Регистрирай')
    expect(page.text()).not.toContain('Parent /')
    expect((page.findAll('input')[0].element as HTMLInputElement).value).toBe('Test Parent')
    expect(page.find('[aria-label="Change language"]').exists()).toBe(false)
    expect(localStorage.getItem('preferredLanguage')).toBeNull()
    page.unmount()
  })
  it('falls back to English per language and per key; Bulgarian is optional', () => {
    expect(translate(catalogs, 'es-MX', 'child_center')).toBe('Child Center')
    expect(translate({ en: { save: 'Save', close: 'Close' }, fr: { save: 'Enregistrer' } }, 'fr-FR', 'save')).toBe('Enregistrer')
    expect(translate({ en: { save: 'Save', close: 'Close' }, fr: { save: 'Enregistrer' } }, 'fr-FR', 'close')).toBe('Close')
    expect(translate({ en: { save: 'Save' } }, 'bg', 'save')).toBe('Save')
  })
  it('inherits live Core button/card appearance through the real public UiSurface', async () => {
    const appearance = ref({ button: 'outline', card: 'raised' })
    const page = mountWith(Registration, host(['submit_registration']), {}, appearance); await flushPromises()
    expect(page.find('.ui-v2').attributes('data-button')).toBe('outline')
    expect(page.find('.ui-v2').attributes('data-card')).toBe('raised')
    expect(page.find('main.ui-section').exists()).toBe(true)
    expect(page.find('button.ui-button--primary').exists()).toBe(true)
    appearance.value = { button: 'solid', card: 'bordered' }; await flushPromises()
    expect(page.find('.ui-v2').attributes('data-button')).toBe('solid')
    expect(page.find('.ui-v2').attributes('data-card')).toBe('bordered')
    page.unmount()
  })
  it('retranslates a displayed domain refusal when the incoming locale changes', async () => {
    const h = host(['submit_registration'])
    h.invoke.mockResolvedValue({status:'rejected',data:null,message:'Names and at least one contact are required'})
    const page = mountWith(Registration,h); await flushPromises()
    await fill(page.findComponent(ClientForm)); await page.find('form').trigger('submit'); await flushPromises()
    expect(page.text()).toContain('Names and at least one contact are required')
    await page.setProps({locale:'bg'})
    expect(page.text()).toContain('Попълнете имената и поне един контакт.')
    page.unmount()
  })
  it('does not display a delayed export after switching subjects', async () => {
    let reply: (value: any) => void = () => {}
    const h = host(['export_personal_data','privacy_request_outcome'])
    h.invoke.mockImplementation(() => new Promise(resolve => { reply = resolve }))
    const page = mountWith(Privacy,h); await flushPromises()
    const subject = page.find('input')
    await subject.setValue('reg_'+'1'.repeat(32))
    await page.findAll('button').find(b => b.text() === 'Export')!.trigger('click')
    expect(subject.attributes('disabled')).toBeDefined()
    // A queued input event can still arrive after dispatch.
    ;(subject.element as HTMLInputElement).value = 'reg_'+'2'.repeat(32)
    subject.element.dispatchEvent(new Event('input', { bubbles: true }))
    await flushPromises()
    reply({status:'applied',data:{document_json:'Private original subject'},message:null}); await flushPromises()
    expect(page.text()).not.toContain('Private original subject')
    page.unmount()
  })
  it('uses the latest search when an older list response arrives last', async () => {
    let old: (value: any) => void = () => {}
    const h = host(['list_registrations'])
    h.invoke.mockImplementation((_operation: string, payload: any) => payload.query === ''
      ? new Promise(resolve => { old = resolve })
      : Promise.resolve({items:[{registration_id:'reg_new',guardian_name:'Latest search',status:'approved'}],total:1}))
    const page = mountWith(Desk,h); await flushPromises()
    await page.find('input').setValue('new query')
    await page.find('.cc-toolbar').trigger('submit'); await flushPromises()
    old({items:[{registration_id:'reg_old',guardian_name:'Outdated search',status:'approved'}],total:1}); await flushPromises()
    expect(page.text()).toContain('Latest search')
    expect(page.text()).not.toContain('Outdated search')
    page.unmount()
  })
})


describe('Core-configured normal/debug presentation',()=>{
  const visit='visit_'+'1'.repeat(32),cmd='commercial_'+'2'.repeat(32),child='child_'+'3'.repeat(32)
  const baseDetail=()=>({visit_id:visit,child_id:child,child_name:'Child',guardian_name:'Parent',visit_state:'closed',parent_linked:true,
    account:{state:'open',remote_state:'open',account_id:44,time_confirmed:0,unit:'minutes',quantity:null},choices:[],allowed_articles:[],
    commands:[],attention:[{command_id:cmd,kind:'time',state:'uncertain',parameters:{quantity:'7.000',unit:'minutes'},acknowledged:0}],has_more:false})
  async function open(debug:boolean,preferenceFailure=false){
    const h=host(['ui_preferences_payments_manage','cashier_list','cashier_detail','commerce_prepare','commerce_validate','commerce_check','commerce_execute'])
    h.invoke.mockImplementation((name:string)=>{
      if(name==='ui_preferences_payments_manage')return preferenceFailure?Promise.reject(new Error('optional preference read failed')):Promise.resolve({debug_mode:debug})
      if(name==='cashier_list')return Promise.resolve({items:[{visit_id:visit,child_name:'Child',guardian_name:'Parent',account_state:'open'}],has_more:false})
      if(name==='cashier_detail')return Promise.resolve(baseDetail())
      if(name==='commerce_check')return Promise.resolve({status:'rejected',data:null,message:'commerce_check_required'})
      throw new Error('Unexpected operation '+name)
    })
    const page=mountWith(Cashier,h);await flushPromises()
    await page.findAll('button').find(b=>b.text()==='Account details')!.trigger('click');await flushPromises()
    return {page,h}
  }
  it('normal mode keeps one visible failure and the actual uncertainty review without diagnostic duplicates',async()=>{
    const {page,h}=await open(false)
    expect(page.text()).not.toContain(catalogs.en.commerce_interactive_notice)
    expect(page.get('dialog').text()).not.toContain(catalogs.en.commerce_observation)
    expect(page.get('dialog').text()).toContain(catalogs.en.commerce_history)
    expect(page.find('.cc-command-meta').exists()).toBe(false)
    const time=page.get('.cc-time-charge')
    expect(time.find('input[type=checkbox]').exists()).toBe(true)
    expect(time.get('button').attributes('disabled')).toBeDefined()
    await time.get('input[type=checkbox]').setValue(true)
    await time.get('button').trigger('click');await flushPromises()
    expect(page.findAll('.cc-error').filter(e=>e.isVisible())).toHaveLength(1)
    expect(h.invoke.mock.calls.filter(c=>c[0]==='commerce_check')).toHaveLength(1)
    expect(h.invoke.mock.calls.some(c=>c[0]==='commerce_execute')).toBe(false)
    page.unmount()
  })
  it.each([false,true])('debug=%s retains explicit review gates; technical metadata is visible only in debug',async(debug)=>{
    const {page}=await open(debug)
    await page.get('dialog').findAll('button').find(b=>b.text()===(debug?'Commercial journal':'History'))!.trigger('click')
    expect(page.find('.cc-command-meta').exists()).toBe(debug)
    expect(page.get('.cc-time-charge').get('button').attributes('disabled')).toBeDefined()
    page.unmount()
  })
  it('a failed preference read falls back to the detailed interface without revoking permitted business actions',async()=>{
    const {page}=await open(false,true)
    expect(page.text()).toContain(catalogs.en.commerce_interactive_notice)
    expect(page.get('dialog').text()).toContain(catalogs.en.commerce_observation)
    expect(page.text()).not.toContain(catalogs.en.access_unavailable)
    page.unmount()
  })
  it('normal mode keeps a lost-result check and manual acknowledgement without exposing opaque identifiers',async()=>{
    const {page,h}=await open(false)
    const original=h.invoke.getMockImplementation()!
    h.invoke.mockImplementation((name:string,...args:any[])=>name==='commerce_check'?Promise.reject(new Error('lost check reply')):original(name,...args))
    await page.get('.cc-time-charge input[type=checkbox]').setValue(true)
    await page.get('.cc-time-charge button').trigger('click');await flushPromises()
    const saved=JSON.parse(sessionStorage.getItem('child-center-local-pending-v1')!)
    const review=page.get('dialog .cc-review')
    expect(review.text()).toContain(catalogs.en.unconfirmed_operation)
    expect(review.text()).not.toContain(saved.request_id)
    expect(review.text()).not.toContain('commerce_validate')
    expect(review.get('.cc-manual-review').attributes('open')).toBeUndefined()
    expect(review.findAll('button').find(b=>b.text()===catalogs.en.finish_manual_review)!.attributes('disabled')).toBeDefined()
    expect(h.invoke.mock.calls.some(c=>c[0]==='commerce_execute')).toBe(false)
    page.unmount()
  })
})


describe('Explicit confirmation buttons in normal mode',()=>{
  const id='visit_'+'1'.repeat(32),cmd='commercial_'+'2'.repeat(32),child='child_'+'3'.repeat(32)
  it.each(['confirmed','lost','prepared','uncertain'])('confirms a payment only on the named button and never resends a lost result: %s',async(mode)=>{
    const h=host(['ui_preferences_payments_manage','cashier_list','cashier_detail','cashier_preview','cashier_prepare','cashier_execute','cashier_check'])
    let closed=false
    const params={amount:'10.14',currency_code:'EUR',method_label:'Cash',expires_at:'2099-10-29T12:00:00Z'}
    h.invoke.mockImplementation((name:string)=>{
      if(name==='ui_preferences_payments_manage')return Promise.resolve({debug_mode:false})
      if(name==='cashier_list')return Promise.resolve({items:closed?[]:[{visit_id:id,child_name:'Child',guardian_name:'Parent',account_state:'open'}],has_more:false})
      if(name==='cashier_detail')return Promise.resolve({visit_id:id,child_id:child,child_name:'Child',guardian_name:'Parent',visit_state:'closed',parent_linked:true,
        account:{state:closed?'closed':'open',remote_state:closed?'closed':'open',account_id:44,time_confirmed:1,quantity:'7.000',unit:'minutes'},choices:[],allowed_articles:[],commands:[],
        attention:!closed&&['prepared','uncertain'].includes(mode)?[{command_id:cmd,kind:'payment',state:mode,parameters:params,acknowledged:0}]:[],has_more:false})
      if(name==='cashier_preview')return Promise.resolve({status:'applied',message:null,data:{quote_id:'quote_'+'4'.repeat(32),amount:'10.14',currency_code:'EUR',expires_at:params.expires_at,methods:[{paymethod_id:1,label:'Cash'}]}})
      if(name==='cashier_prepare')return Promise.resolve({status:'applied',message:null,data:{command_id:cmd,state:'prepared'}})
      if(name==='cashier_execute')return mode==='lost'?Promise.reject(new Error('lost payment reply')):Promise.resolve({status:'applied',message:null,data:{state:'uncertain'}})
      if(name==='cashier_check'){closed=true;return Promise.resolve({status:'applied',message:null,data:{state:'confirmed'}})}
      throw new Error('Unexpected operation '+name)
    })
    const page=mountWith(Cashier,h);await flushPromises()
    await page.findAll('button').find(b=>b.text()==='Account details')!.trigger('click');await flushPromises()
    expect(h.invoke.mock.calls.some(c=>c[0]==='cashier_execute'||c[0]==='cashier_prepare')).toBe(false)
    await page.get('.cc-checkout-entry button').trigger('click');await flushPromises()
    const checkout=page.get('.cc-checkout')
    if(['prepared','uncertain'].includes(mode)){
      expect(h.invoke.mock.calls.some(c=>c[0]==='cashier_preview'||c[0]==='cashier_prepare')).toBe(false)
      if(mode==='uncertain'){
        expect(checkout.find('input[type=checkbox]').exists()).toBe(true)
        expect(checkout.findAll('button').find(b=>b.text()===catalogs.en.commerce_check_result)!.attributes('disabled')).toBeDefined()
        await checkout.get('input[type=checkbox]').setValue(true)
        await checkout.findAll('button').find(b=>b.text()===catalogs.en.commerce_check_result)!.trigger('click')
      }else{
        expect(checkout.find('input[type=checkbox]').exists()).toBe(false)
        await checkout.findAll('button').find(b=>b.text().includes(catalogs.en.commerce_received_close))!.trigger('click')
      }
    }else{
      expect(checkout.find('input[type=checkbox]').exists()).toBe(false)
      const form=checkout.get('form')
      expect(form.get('button[type=submit]').attributes('disabled')).toBeDefined()
      await form.get('select').setValue('1')
      expect(form.get('button[type=submit]').text()).toContain('10.14 EUR')
      expect(h.invoke.mock.calls.some(c=>c[0]==='cashier_execute')).toBe(false)
      await form.trigger('submit')
    }
    await flushPromises()
    expect(h.invoke.mock.calls.filter(c=>c[0]==='cashier_execute')).toHaveLength(mode==='uncertain'?0:1)
    if(mode==='lost'){
      expect(page.get('dialog .cc-review').isVisible()).toBe(true)
      expect(h.invoke.mock.calls.some(c=>c[0]==='cashier_check')).toBe(false)
      expect(page.findAll('.cc-review').filter(e=>e.isVisible())).toHaveLength(1)
    }else{
      expect(page.get('dialog').text()).toContain(catalogs.en.commerce_payment_confirmed)
      expect(page.findAll('tbody tr')).toHaveLength(0)
      expect(h.invoke.mock.calls.filter(c=>c[0]==='cashier_check')).toHaveLength(1)
    }
    if(mode==='confirmed'||mode==='lost')expect(h.invoke.mock.calls.find(c=>c[0]==='cashier_prepare')![1]).toMatchObject({confirmed:true,paymethod_id:1})
    page.unmount()
  })
  it('records parental permission through its explicitly named submit action, retaining the article choices',async()=>{
    const h=host(['ui_preferences_children_manage','commerce_list','commerce_detail','commerce_allow_child'])
    let saved=false
    h.invoke.mockImplementation((name:string)=>{
      if(name==='ui_preferences_children_manage')return Promise.resolve({debug_mode:false})
      if(name==='commerce_list')return Promise.resolve({items:[{visit_id:id,child_name:'Child',guardian_name:'Parent'}],has_more:false})
      if(name==='commerce_detail')return Promise.resolve({visit_id:id,child_id:child,child_name:'Child',guardian_name:'Parent',visit_state:'closed',parent_linked:true,account:null,allowed_articles:saved?[20]:[],choices:[{article_id:20,label:'Juice'}],commands:[],attention:[],has_more:false})
      if(name==='commerce_allow_child'){saved=true;return Promise.resolve({status:'applied',message:null,data:{state:'saved'}})}
      throw new Error('Unexpected operation '+name)
    })
    const page=mountWith(Commerce,h);await flushPromises()
    await page.findAll('button').find(b=>b.text()==='Account details')!.trigger('click');await flushPromises()
    await page.get('dialog').findAll('button').find(b=>b.text()==='Consumption')!.trigger('click')
    const form=page.get('dialog form')
    expect(form.findAll('input[type=checkbox]')).toHaveLength(1)
    expect(form.get('button[type=submit]').text()).toBe(catalogs.en.commerce_save_permission)
    await form.get('input[type=checkbox]').setValue(true)
    expect(h.invoke.mock.calls.some(c=>c[0]==='commerce_allow_child')).toBe(false)
    await form.trigger('submit');await flushPromises()
    expect(h.invoke.mock.calls.find(c=>c[0]==='commerce_allow_child')![1]).toMatchObject({reviewed:true,expected_articles:[],article_ids:[20]})
    page.unmount()
  })
})


describe('Visible application settings and quiet progress',()=>{
  it.each(['applied','lost','rejected'])('saves the visible Debug mode through an admin operation and preserves lost-reply recovery: %s',async(mode)=>{
    let enabled=false,revision=1
    const h=host(['admin_get_settings','admin_save_settings','admin_request_outcome','ui_preferences_administration_manage'])
    h.invoke.mockImplementation((name:string,payload:any)=>{
      if(name==='ui_preferences_administration_manage')return Promise.resolve({debug_mode:enabled})
      if(name==='admin_get_settings')return Promise.resolve({revision,debug_mode:enabled})
      if(name==='admin_save_settings'){
        if(mode==='rejected')return Promise.resolve({status:'rejected',data:null,message:'Application settings changed; refresh before saving'})
        enabled=payload.debug_mode;revision++
        return mode==='lost'?Promise.reject(new Error('lost settings reply')):Promise.resolve({status:'applied',message:null,data:{revision,debug_mode:enabled}})
      }
      if(name==='admin_request_outcome')return Promise.resolve({status:'confirmed',result_json:JSON.stringify({status:'applied',message:null,data:{revision,debug_mode:enabled}})})
      throw new Error('Unexpected operation '+name)
    })
    let page=mountWith(Administration,h);await flushPromises()
    expect(page.get('.cc-app-settings h2').text()).toBe(catalogs.en.app_settings)
    expect((page.get('#app-debug-mode').element as HTMLInputElement).checked).toBe(false)
    expect(page.get('.cc-app-settings button[type=submit]').attributes('disabled')).toBeDefined()
    await page.get('#app-debug-mode').setValue(true)
    expect(h.invoke.mock.calls.some(c=>c[0]==='admin_save_settings')).toBe(false)
    await page.get('.cc-app-settings form').trigger('submit');await flushPromises()
    expect(h.invoke.mock.calls.find(c=>c[0]==='admin_save_settings')![1]).toEqual({expected_revision:1,debug_mode:true})
    if(mode==='lost'){
      await page.findAll('button').find(b=>b.text()===catalogs.en.check_saved_outcome)!.trigger('click');await flushPromises()
      expect(h.invoke.mock.calls.filter(c=>c[0]==='admin_save_settings')).toHaveLength(1)
      expect(h.invoke.mock.calls.some(c=>c[0]==='admin_request_outcome')).toBe(true)
    }else if(mode==='rejected')expect(page.text()).toContain(catalogs.en.app_settings_stale)
    if(mode!=='rejected'){
      page.unmount();page=mountWith(Administration,h);await flushPromises()
      expect((page.get('#app-debug-mode').element as HTMLInputElement).checked).toBe(true)
    }
    page.unmount()
  })
  it('does not offer the setting without its existing admin permission',async()=>{
    const h=host(['admin_list_clients']);h.invoke.mockResolvedValue({items:[],total:0})
    const page=mountWith(Administration,h);await flushPromises()
    expect(page.find('.cc-app-settings').exists()).toBe(false)
    expect(h.invoke.mock.calls.some(c=>c[0]==='admin_save_settings')).toBe(false)
    page.unmount()
  })
  it('shows only a spinner while working normally, full pending details in debug, and actionable failure after a lost reply',async()=>{
    const debug=ref(false),pending={request_id:'a'.repeat(32),operation_id:'cashier_execute'}
    const page=mount(Status,{props:{busy:true,pending,error:''},global:{provide:{[UI_DEBUG_MODE as symbol]:debug,[Symbol.for('3mm.extension-ui.v1')]:ref({button:'solid',card:'bordered'})}}})
    expect(page.get('.cc-working').attributes('aria-label')).toBe(catalogs.en.loading)
    expect(page.find('.cc-review').exists()).toBe(false)
    expect(page.text()).not.toContain(catalogs.en.pending_review)
    await page.setProps({busy:false,error:'outcome_needs_review'})
    expect(page.find('.cc-working').exists()).toBe(false)
    expect(page.get('.cc-review').text()).toContain(catalogs.en.unconfirmed_operation)
    expect(page.text()).not.toContain(catalogs.en.pending_review)
    expect(page.get('.cc-review button').attributes('disabled')).toBeUndefined()
    debug.value=true;await nextTick();await page.setProps({busy:true})
    expect(page.get('.cc-review').text()).toContain(catalogs.en.pending_review)
    expect(page.get('.cc-review').text()).toContain(pending.request_id)
    page.unmount()
  })
})
