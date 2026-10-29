<script setup lang="ts">
import {computed,onMounted,onUnmounted,ref,watch} from 'vue'
import {UiButton,UiDialog,UiField,UiSurface} from '@3mm/ui/v1'
import type {ApplicationPayload} from '@3mm/application-ui/v1'
import {provideApplicationLocale} from './i18n'
import {useLocal} from './use-local'
import {formatTimestamp} from './time'
import Status from './Status.vue'
import './local.css'
type Choice={article_id:number;label:string}
type Member={visit_id:string;child_id:string;child_name:string;phase:'inside'|'paused'|'closed';last_transition_at:string;duration_seconds:number;allowed_articles:number[]}
type Account={account_id:number|null;place_id:number;state:string;remote_state:string;identity:string;time_confirmed:number;quantity:string|null;unit:string}
type Row={visit_id:string;child_name:string;guardian_name:string;visit_state:string;account_id:number|null;account_state:string|null;place_id:number|null}
type Command={command_id:string;kind:string;state:string;error_code:string|null;acknowledged:number;parameters:Record<string,any>}
type Detail={visit_id:string;child_id:string;child_name:string;guardian_name:string;visit_state:string;parent_linked:boolean;account:Account|null;choices:Choice[];allowed_articles:number[];commands:Command[];attention:Command[];has_more:boolean;members?:Member[];opening_error?:string|null;opening_available?:boolean;opening_state?:'setup_required'|'synchronizing'|'opening'|'review'|'open'|'archived'}
type Quote={quote_id:string;amount:string;currency_code:string;expires_at:string;methods:{paymethod_id:number;label:string}[]}
const props=defineProps<{locale?:string;cashier?:boolean}>()
const strings=provideApplicationLocale(computed(()=>props.locale)),{t}=strings
const {allowed,busy,pending,error,debugMode,can,access,read,readFailure,command,resolve,reviewed}=useLocal(strings)
const workflowBusy=ref(false),actionConfirmed=ref<'consumption'|'payment'|''>('')
const prefix=computed(()=>props.cashier?'cashier':'commerce'),locked=computed(()=>busy.value||!!pending.value||loading.value||workflowBusy.value)
const rows=ref<Row[]>([]),detail=ref<Detail|null>(null),offset=ref(0),more=ref(false),filter=ref('open'),loading=ref(false)
const detailOpen=ref(false),detailLoading=ref(false),quote=ref<Quote|null>(null),paymethod=ref(''),received=ref(false)
const place=ref(''),article=ref(''),quantity=ref('1'),consumer=ref('child'),sendConfirmed=ref<Record<string,boolean>>({}),reviewedRemote=ref<Record<string,boolean>>({}),accountIds=ref<Record<string,string>>({})
const childArticles=ref<number[]>([]),parentReviewed=ref(false),externalCloseReviewed=ref(false),emptyReleaseReviewed=ref(false),emptyReleaseReason=ref(''),eventOffset=ref(0),places=ref<{place_id:number;label:string}[]>([])
const target=ref('')
const selectedChild=ref(''),guardianChoices=ref<Choice[]>([]),catalogQuery=ref(''),catalogOffset=ref(0),catalogMore=ref(false),catalogLoading=ref(false),finishConfirmed=ref(false)
const members=computed(()=>detail.value?.members??[])
const activeMembers=computed(()=>members.value.filter(m=>m.phase!=='closed'))
const consumerChild=computed(()=>members.value.find(m=>m.child_id===selectedChild.value))
const allowedConsumption=computed(()=>consumerChild.value?.allowed_articles??detail.value?.allowed_articles??[])
const saleChoices=computed(()=>consumer.value==='guardian'?guardianChoices.value:detail.value?.choices.filter(c=>allowedConsumption.value.includes(c.article_id))??[])
const section=ref<'overview'|'consumption'|'journal'|'payment'>('overview')
const archivedBilling=computed(()=>detail.value?.opening_state==='archived')
const releaseUnlinked=computed(()=>!!detail.value&&!detail.value.account)
const attention=computed(()=>detail.value?.attention??detail.value?.commands.filter(item=>['prepared','uncertain'].includes(item.state))??[])
const timeCommand=computed(()=>attention.value.find(item=>item.kind==='time'))
const paymentCommand=computed(()=>attention.value.find(item=>item.kind==='payment'))
const paymentAvailable=computed(()=>props.cashier||can('cashier_preview')||can('cashier_execute')||can('cashier_check'))
const checkoutBlock=computed(()=>!detail.value||detail.value.visit_state!=='closed'||!detail.value.account?.time_confirmed?'commerce_finish_first':attention.value.some(item=>item.kind!=='payment')?'commerce_pending':'')
const paymentReviewed=computed(()=>!!paymentCommand.value&&(paymentCommand.value.state==='prepared'?!!sendConfirmed.value[paymentCommand.value.command_id]:!!paymentCommand.value.acknowledged||!!reviewedRemote.value[paymentCommand.value.command_id]))
const timeReviewRequired=computed(()=>timeCommand.value?.state==='uncertain'&&!timeCommand.value.acknowledged)
const timeReviewConfirmed=computed(()=>!!timeCommand.value&&!!reviewedRemote.value[timeCommand.value.command_id])
const visibleCommands=computed(()=>{
  const urgent=attention.value
  if(section.value!=='journal')return debugMode.value?urgent:urgent.filter(item=>!['time','payment'].includes(item.kind))
  const ids=new Set(urgent.map(item=>item.command_id))
  return [...urgent,...(detail.value?.commands??[]).filter(item=>!ids.has(item.command_id))]
})
const consentSaved=ref(false)
const consentDirty=computed(()=>!!detail.value&&JSON.stringify(childArticles.value)!==JSON.stringify(allowedConsumption.value))
watch(selectedChild,()=>{childArticles.value=[...allowedConsumption.value];parentReviewed.value=false;consentSaved.value=false})
let serial=0,detailSerial=0,catalogSerial=0,disposed=false,openingReads=0
let openingTimer:ReturnType<typeof setTimeout>|undefined
function stopOpeningWatch(){if(openingTimer!==undefined)clearTimeout(openingTimer);openingTimer=undefined}
onUnmounted(()=>{disposed=true;serial++;detailSerial++;catalogSerial++;stopOpeningWatch()})
function close(){actionConfirmed.value='';detailSerial++;catalogSerial++;stopOpeningWatch();detail.value=null;detailOpen.value=false;quote.value=null;received.value=false;externalCloseReviewed.value=false;emptyReleaseReviewed.value=false;emptyReleaseReason.value='';detailLoading.value=false}
function updateRow(result:Detail){
  const row=rows.value.find(row=>row.visit_id===result.visit_id)
  if(row){row.account_id=result.account?.account_id??null;row.account_state=result.opening_state==='archived'?'archived':result.account?.state??null;row.visit_state=result.visit_state}
  if(filter.value==='open'&&(result.account?.state==='closed'||result.opening_state==='archived'))rows.value=rows.value.filter(row=>row.visit_id!==result.visit_id)
}
function watchOpening(current:number){
  if(disposed||current!==detailSerial||!detailOpen.value||!detail.value||pending.value||openingReads>=15||!['synchronizing','opening'].includes(detail.value.opening_state||''))return
  openingTimer=setTimeout(async()=>{
    openingTimer=undefined
    if(disposed||current!==detailSerial||locked.value||!detail.value)return
    const id=detail.value.visit_id;openingReads++
    try{
      const result=await read<Detail>(prefix.value+'_detail',{visit_id:id,offset:eventOffset.value})
      if(disposed||current!==detailSerial||pending.value)return
      detail.value=result
      updateRow(result)
      watchOpening(current)
    }catch(failure){if(!disposed&&current===detailSerial)readFailure(failure)}
  },2000)
}
async function refresh(){
  const current=++serial;close();rows.value=[];more.value=false;loading.value=true
  await access()
  try {
    if(disposed||current!==serial||!can(prefix.value+'_list'))return
    const result=await read<{items:Row[];has_more:boolean}>(prefix.value+'_list',{offset:offset.value,limit:20,filter:filter.value})
    if(!disposed&&current===serial){rows.value=result.items;more.value=result.has_more}
  }catch(failure){if(!disposed&&current===serial)readFailure(failure)}
  finally{if(!disposed&&current===serial)loading.value=false}
}
async function select(id:string,start=0){
  stopOpeningWatch();openingReads=0;catalogSerial++;catalogLoading.value=false;guardianChoices.value=[];catalogMore.value=false;article.value=''
  if(!detailOpen.value||id!==target.value){section.value='overview';consumer.value='child';actionConfirmed.value=''}
  target.value=id
  consentSaved.value=false
  if(error.value==='read_unavailable')error.value=''
  const current=++detailSerial;detail.value=null;detailOpen.value=true;detailLoading.value=true;eventOffset.value=start;quote.value=null;received.value=false;parentReviewed.value=false;externalCloseReviewed.value=false;emptyReleaseReviewed.value=false;emptyReleaseReason.value=''
  sendConfirmed.value={};reviewedRemote.value={};accountIds.value={}
  try {
    const result=await read<Detail>(prefix.value+'_detail',{visit_id:id,offset:start})
    if(!disposed&&current===detailSerial){detail.value=result;updateRow(result);childArticles.value=[...result.allowed_articles];finishConfirmed.value=false
      if(!result.members?.some(m=>m.child_id===selectedChild.value))selectedChild.value=result.child_id
      watchOpening(current)
      if(consumer.value==='guardian'&&section.value==='consumption'&&result.account?.state==='open'&&can('commerce_catalog'))void loadCatalog(catalogOffset.value)}
  }catch(failure){if(!disposed&&current===detailSerial){readFailure(failure);if(!can(prefix.value+'_detail'))close()}}
  finally{if(!disposed&&current===detailSerial)detailLoading.value=false}
}
async function act(operation:string,payload:ApplicationPayload){
  const current=detailSerial,id=detail.value?.visit_id
  const kind=[...(detail.value?.commands??[]),...attention.value].find(item=>item.command_id===payload.command_id)?.kind
  const result=await command<{state?:string}>(operation,payload)
  if(!disposed&&current===detailSerial&&result&&id){
    if(operation.endsWith('_check')&&result.state==='confirmed'&&(kind==='consumption'||kind==='payment'))actionConfirmed.value=kind
    await select(id,eventOffset.value);return !disposed&&detail.value?.visit_id===id
  }
}
async function confirmConsent(){
  if(locked.value||!detail.value)return
  parentReviewed.value=true
  await saveConsent()
}
async function confirmFinish(){
  if(locked.value||!detail.value)return
  finishConfirmed.value=true
  await finishFamily()
}
async function confirmStep(item:Command){
  if(locked.value||!detail.value||item.state!=='prepared')return
  sendConfirmed.value[item.command_id]=true
  await executeStep(item)
}
async function confirmPayment(){
  if(locked.value||!detail.value||!quote.value||!paymethod.value)return
  received.value=true
  await pay()
}
async function confirmPreparedPayment(){
  const step=paymentCommand.value
  if(locked.value||!detail.value||step?.state!=='prepared')return
  sendConfirmed.value[step.command_id]=true
  await continuePayment(step)
}
const confirmLabel=(item:Command)=>t('commerce_confirm_'+item.kind)
async function saveConsent(){
  if(!detail.value||!parentReviewed.value||locked.value)return
  const result=await act('commerce_allow_child',{child_id:selectedChild.value||detail.value.child_id,expected_articles:allowedConsumption.value,article_ids:childArticles.value,reviewed:true})
  if(result)consentSaved.value=true
}
async function prepare(kind:string){
  if(!detail.value)return
  const payload={visit_id:detail.value.visit_id,kind,place_id:place.value?Number(place.value):null,
    article_id:article.value?Number(article.value):null,quantity:quantity.value,consumer:consumer.value,
    ...(kind==='consumption'?{consumer_child_id:selectedChild.value||detail.value.child_id}:{})}
  if(kind==='consumption'||kind==='time')await submitCommercial('commerce_prepare',payload,'commerce')
  else await act('commerce_prepare',payload)
}
async function sendCommercial(commandId:string,dispatch:string,current:number){
  if(!can(dispatch+'_execute')){error.value='access_denied';return}
  if(dispatch==='commerce'){
    if(!can('commerce_validate')){error.value='access_denied';return}
    const validated=await command<{command_id?:string;state:string}>('commerce_validate',{command_id:commandId})
    if(disposed||current!==detailSerial||!validated)return
    if(validated.command_id!==commandId||validated.state!=='prepared'){error.value='commerce_stale';return}
  }
  const sent=await command<{state:string}>(dispatch+'_execute',{command_id:commandId})
  if(disposed||current!==detailSerial||!sent)return
  if(sent.state==='confirmed')return sent
  if(sent.state!=='uncertain'){error.value='commerce_stale';return}
  if(!can(dispatch+'_check')){error.value='commerce_check_required';return}
  const checked=await command<{state:string}>(dispatch+'_check',{command_id:commandId,account_id:null,reviewed:false})
  if(!disposed&&current===detailSerial)return checked
}
async function executeStep(item:Command){
  if(item.kind==='payment'){await continuePayment(item);return}
  if(!['time','consumption'].includes(item.kind)){await act(commandPrefix(item)+'_execute',{command_id:item.command_id});return}
  if(locked.value||!detail.value||!sendConfirmed.value[item.command_id])return
  const current=detailSerial,id=detail.value.visit_id
  workflowBusy.value=true
  actionConfirmed.value=''
  try{
    const checked=await sendCommercial(item.command_id,'commerce',current)
    if(checked?.state==='confirmed'&&item.kind==='consumption')actionConfirmed.value='consumption'
  }
  finally{
    workflowBusy.value=false
    if(!disposed&&current===detailSerial&&!pending.value)await select(id,eventOffset.value)
  }
}
async function chargeTime(){
  if(locked.value||!detail.value||detail.value.account?.time_confirmed)return
  const step=timeCommand.value
  if(!step){await prepare('time');return}
  const current=detailSerial,id=detail.value.visit_id
  workflowBusy.value=true
  try{
    if(step.state==='uncertain'){
      if(!can('commerce_check')){error.value='access_denied';return}
      if(!step.acknowledged&&!reviewedRemote.value[step.command_id]){error.value='commerce_manual_review_required';return}
      await command('commerce_check',{command_id:step.command_id,account_id:null,reviewed:!!reviewedRemote.value[step.command_id]})
    }else await sendCommercial(step.command_id,'commerce',current)
  }finally{
    workflowBusy.value=false
    if(!disposed&&current===detailSerial&&!pending.value)await select(id,eventOffset.value)
  }
}
async function submitCommercial(operation:string,payload:ApplicationPayload,dispatch:string){
  if(locked.value||!detail.value)return
  actionConfirmed.value=''
  const current=detailSerial,id=detail.value.visit_id
  workflowBusy.value=true
  try{
    const prepared=await command<{command_id?:string;state:string}>(operation,payload)
    if(disposed||current!==detailSerial||!prepared)return
    if(!prepared.command_id||prepared.state!=='prepared'){error.value='commerce_stale';return}
    const checked=await sendCommercial(prepared.command_id,dispatch,current)
    if(checked?.state==='confirmed'){
      if(dispatch==='cashier')actionConfirmed.value='payment'
      else if(payload.kind==='consumption')actionConfirmed.value='consumption'
    }
  }finally{
    workflowBusy.value=false
    if(!disposed&&current===detailSerial&&!pending.value)await select(id,eventOffset.value)
  }
}
async function loadCatalog(start=0){
  if(!detail.value||locked.value||catalogLoading.value)return
  const current=detailSerial,catalogRequest=++catalogSerial;catalogLoading.value=true
  try{const result=await read<{items:Choice[];has_more:boolean}>('commerce_catalog',{visit_id:detail.value.visit_id,query:catalogQuery.value,offset:start})
    if(!disposed&&current===detailSerial&&catalogRequest===catalogSerial&&consumer.value==='guardian'){guardianChoices.value=result.items;catalogOffset.value=start;catalogMore.value=result.has_more;article.value=''}}
  catch(failure){if(!disposed&&current===detailSerial&&catalogRequest===catalogSerial)readFailure(failure)}finally{if(catalogRequest===catalogSerial)catalogLoading.value=false}
}
function changeConsumer(){
  catalogSerial++;catalogLoading.value=false;guardianChoices.value=[];catalogMore.value=false;catalogOffset.value=0;catalogQuery.value='';article.value=''
  if(consumer.value==='guardian')void loadCatalog()
}
async function finishFamily(){
  if(!detail.value||!finishConfirmed.value)return
  await act('family_finish',{visit_id:detail.value.visit_id,members:activeMembers.value.map(m=>({visit_id:m.visit_id,expected_transition_at:m.last_transition_at,expected_phase:m.phase}))})
}
async function loadPlaces(){
  if(!can('commerce_places')||locked.value)return
  const current=detailSerial
  try{const result=await read<{items:{place_id:number;label:string}[]}>('commerce_places',{});if(!disposed&&current===detailSerial)places.value=result.items}
  catch(failure){if(!disposed&&current===detailSerial)readFailure(failure)}
}
async function releaseEmpty(){
  if(locked.value||!detail.value||!emptyReleaseReviewed.value||!emptyReleaseReason.value.trim())return
  const common={visit_id:detail.value.visit_id,reviewed:true,reason:emptyReleaseReason.value.trim()}
  if(releaseUnlinked.value)await act('commerce_release_unlinked',{...common,accepted_orphaned_parent:true})
  else if(detail.value.account?.account_id)await act('commerce_release_empty',{...common,expected_account_id:detail.value.account.account_id,accepted_missing_time:true})
}
async function beginCheckout(){
  if(locked.value||!detail.value)return
  section.value='payment'
  if(!paymentCommand.value)await preview()
}
async function continuePayment(step=paymentCommand.value){
  if(locked.value||!detail.value||!step||step.kind!=='payment')return
  const current=detailSerial,id=detail.value.visit_id
  workflowBusy.value=true;actionConfirmed.value=''
  try{
    let result:{state:string}|undefined
    if(step.state==='prepared'){
      if(!sendConfirmed.value[step.command_id])return
      result=await sendCommercial(step.command_id,'cashier',current)
    }else if(step.state==='uncertain'){
      if(!step.acknowledged&&!reviewedRemote.value[step.command_id])return
      result=await command<{state:string}>('cashier_check',{command_id:step.command_id,account_id:null,reviewed:!!reviewedRemote.value[step.command_id]})
    }
    if(!disposed&&current===detailSerial&&result?.state==='confirmed')actionConfirmed.value='payment'
  }finally{
    workflowBusy.value=false
    if(!disposed&&current===detailSerial&&!pending.value)await select(id,eventOffset.value)
  }
}
async function preview(){
  if(!detail.value||locked.value||paymentCommand.value||checkoutBlock.value)return
  const current=detailSerial
  quote.value=null;received.value=false
  const result=await command<Quote>('cashier_preview',{visit_id:detail.value.visit_id})
  if(!disposed&&current===detailSerial&&result){quote.value=result;paymethod.value=''}
}
async function pay(){
  if(!detail.value||!quote.value||!received.value||!paymethod.value)return
  await submitCommercial('cashier_prepare',{visit_id:detail.value.visit_id,quote_id:quote.value.quote_id,paymethod_id:Number(paymethod.value),confirmed:true},'cashier')
}
async function review(){
  const id=detail.value?.visit_id
  await resolve()
  if(!debugMode.value&&id&&detailOpen.value){
    if(!pending.value)await select(id,eventOffset.value)
  }else await refresh()
}
const state=(value:string|null)=>t('commerce_state_'+(value||'unlinked'))
const commandPrefix=(item:Command)=>item.kind==='payment'?'cashier':'commerce'
const journalAction=(item:Command)=>debugMode.value||!['time','payment'].includes(item.kind)
const applicable=(item:Command)=>!archivedBilling.value&&can(commandPrefix(item)+'_execute')&&(!['time','consumption'].includes(item.kind)||can('commerce_validate'))
onMounted(refresh)
</script>
<template>
  <UiSurface><main class="ui-section ui-stack cc-local">
    <header><h1>{{t(cashier?'commerce_cashier':'commerce_accounts')}}</h1><UiButton :disabled="locked" @click="refresh">{{t('refresh')}}</UiButton></header>
    <Status v-if="!detailOpen" :busy="busy" :pending="pending" :error="error" @resolve="review" @reviewed="reviewed();refresh()"/>
    <p v-if="!allowed.length">{{t('access_is_unavailable')}}</p><p v-if="debugMode">{{t('commerce_interactive_notice')}}</p>
    <UiField id="accounts-filter" v-model="filter" type="select" :label="t('show')" :options="[{value:'open',label:t('active')},{value:'all',label:t('all')}]" :disabled="locked" @update:model-value="offset=0;refresh()"/>
    <p v-if="loading" role="status">{{t('loading')}}</p><p v-else-if="!rows.length">{{t('no_records')}}</p>
    <div class="cc-table ui-table"><table v-if="rows.length"><thead><tr><th>{{t('child')}}</th><th>{{t('parent')}}</th><th>{{t('state')}}</th><th>{{t('action')}}</th></tr></thead>
      <tbody><tr v-for="row in rows" :key="row.visit_id"><td>{{row.child_name}}</td><td>{{row.guardian_name}}</td><td>{{state(row.account_state)}} · {{row.account_id||'—'}}</td><td><UiButton :disabled="locked" @click="select(row.visit_id)">{{t('commerce_open_details')}}</UiButton></td></tr></tbody>
    </table></div>
    <div class="cc-toolbar"><UiButton :disabled="locked||offset===0" @click="offset-=20;refresh()">{{t('previous')}}</UiButton><UiButton :disabled="locked||!more" @click="offset+=20;refresh()">{{t('next')}}</UiButton></div>
    <UiDialog v-if="detailOpen" :open="detailOpen" :title="t(cashier?'commerce_cashier':'commerce_accounts')" :close-label="t('close')" @update:open="!$event&&close()">
      <div class="ui-stack">
        <Status :busy="busy" :pending="pending" :error="error" @resolve="review" @reviewed="reviewed();refresh()"/>
        <p v-if="detailLoading" role="status">{{t('loading')}}</p>
        <UiButton v-if="!detail&&!detailLoading&&target&&can(prefix+'_detail')" @click="select(target,eventOffset)">{{t('refresh')}}</UiButton>
        <template v-if="detail">
          <header><h3>{{members.length?detail.guardian_name:detail.child_name+' · '+detail.guardian_name}}</h3><UiButton :disabled="locked||detailLoading" @click="select(detail.visit_id,eventOffset)">{{t('refresh')}}</UiButton></header>
          <p>{{t('commerce_local_stay')}}: {{detail.visit_state==='closed'?t('closed'):t('active')}}</p>
          <p>{{t('commerce_remote_account')}}: {{detail.account?.account_id||'—'}} · {{state(detail.account?.state||null)}}</p>
          <p v-if="debugMode&&detail.account">{{t('commerce_observation')}}: {{state(detail.account.remote_state)}}</p>
          <p v-if="detail.account?.state==='closed'&&!detail.account.time_confirmed" role="status">{{t('commerce_empty_released')}}</p>
          <p v-if="detail.opening_error" class="cc-error" role="status">{{t(detail.opening_error)}}</p>
          <p v-else-if="detail.opening_state==='synchronizing'||detail.opening_state==='opening'" role="status">{{t('commerce_opening_'+detail.opening_state)}}</p>
          <p v-if="archivedBilling" role="status">{{t('commerce_unlinked_archived')}}</p>
          <p v-if="!archivedBilling&&!detail.account&&!detail.opening_available">{{t('commerce_auto_opening_setup')}}</p>
          <UiButton v-if="!detail.account?.account_id&&detail.opening_available&&detail.opening_state!=='synchronizing'&&detail.opening_state!=='opening'&&can('family_retry_open')" :disabled="locked" @click="act('family_retry_open',{visit_id:detail.visit_id})">{{t('commerce_continue_opening')}}</UiButton>
          <nav class="cc-detail-tabs" :aria-label="t('sections')">
            <UiButton :aria-pressed="section==='overview'" @click="section='overview'">{{t('commerce_overview')}}</UiButton>
            <UiButton v-if="!archivedBilling&&(can('commerce_prepare')||can('commerce_allow_child')||can('commerce_execute'))" :aria-pressed="section==='consumption'" @click="section='consumption'">{{t('commerce_consumption')}}</UiButton>
            <UiButton v-if="paymentAvailable&&!archivedBilling" :aria-pressed="section==='payment'" @click="section='payment'">{{t('commerce_payment')}}</UiButton>
            <UiButton :aria-pressed="section==='journal'" @click="section='journal'">{{t(debugMode?'commerce_journal':'commerce_history')}}</UiButton>
          </nav>
          <section v-if="members.length" v-show="section==='overview'" class="ui-stack">
            <h3>{{t('commerce_family_stays')}}</h3>
            <div v-for="member in members" :key="member.visit_id" class="cc-family-member">
              <strong>{{member.child_name}}</strong><span>{{t(member.phase==='inside'?'inside':member.phase==='paused'?'paused':'closed')}} · {{Math.floor(member.duration_seconds/60)}} {{t('commerce_minutes')}}</span>
              <UiButton v-if="member.phase!=='closed'&&can('family_transition')" :disabled="locked" @click="act('family_transition',{visit_id:member.visit_id,expected_transition_at:member.last_transition_at,action:member.phase==='inside'?'pause':'resume'})">{{t(member.phase==='inside'?'pause':'resume')}}</UiButton>
            </div>
            <template v-if="activeMembers.length&&can('family_finish')">
              <label v-if="debugMode" class="cc-check ui-check"><input v-model="finishConfirmed" type="checkbox" :disabled="locked"/>{{t('commerce_finish_family_confirmation')}}</label>
              <UiButton :disabled="locked||(debugMode&&!finishConfirmed)" @click="debugMode?finishFamily():confirmFinish()">{{t('commerce_finish_family')}}</UiButton>
            </template>
          </section>
          <section v-if="detail.visit_state==='closed'&&detail.account?.state==='open'&&(can('commerce_prepare')||detail.account.time_confirmed)" class="ui-stack cc-time-charge">
            <p v-if="detail.account.time_confirmed" role="status">{{t(detail.account.quantity==='0'?'commerce_time_zero':'commerce_time_confirmed')}}<span v-if="detail.account.quantity!=null&&detail.account.quantity!=='0'">: {{detail.account.quantity}} {{t('commerce_'+detail.account.unit)}}</span></p>
            <template v-else>
              <p v-if="timeCommand">{{t('commerce_kind_time')}} · {{state(timeCommand.state)}}</p>
              <p v-if="timeCommand?.state==='uncertain'">{{t('commerce_check_required')}}</p>
              <label v-if="timeReviewRequired&&timeCommand" class="cc-check ui-check"><input v-model="reviewedRemote[timeCommand.command_id]" type="checkbox" :disabled="locked"/>{{t('commerce_external_attestation')}}</label>
              <UiButton variant="primary" :disabled="locked||(timeReviewRequired&&!timeReviewConfirmed)" :loading="workflowBusy" @click="chargeTime">{{t(timeCommand?.state==='uncertain'?'commerce_check_result':'commerce_prepare_time')}}</UiButton>
            </template>
            <p v-if="debugMode&&error" role="alert" class="cc-error">{{t(error)}}</p>
          </section>
          <section v-if="paymentAvailable&&detail.account?.state==='open'" v-show="section!=='payment'" class="ui-stack cc-checkout-entry">
            <UiButton variant="primary" :disabled="locked||(!paymentCommand&&(!!checkoutBlock||!can('cashier_preview')))" @click="beginCheckout">{{t(paymentCommand?.state==='uncertain'?'commerce_review_payment':paymentCommand?'commerce_continue_payment':'commerce_close_bill')}}</UiButton>
            <p v-if="!paymentCommand&&checkoutBlock">{{t(checkoutBlock)}}</p>
          </section>
          <h3 v-if="visibleCommands.length||section==='journal'">{{t(section==='journal'?(debugMode?'commerce_journal':'commerce_history'):'commerce_pending_actions')}}</h3>
          <p v-if="section==='journal'&&!visibleCommands.length">{{t('no_records')}}</p>
          <details v-for="item in visibleCommands" :key="item.command_id" :open="['prepared','uncertain'].includes(item.state)" class="ui-stack">
            <summary>{{t('commerce_kind_'+item.kind)}} · {{state(item.state)}}</summary>
            <p v-if="item.parameters.article_id">{{item.kind==='time'?t('commerce_kind_time'):(item.parameters.label||detail.choices.find(choice=>choice.article_id===item.parameters.article_id)?.label||t('commerce_article_name_unavailable'))}} · {{item.parameters.quantity??item.parameters.minutes}} {{item.kind==='time'?t('commerce_'+(item.parameters.quantity===undefined?'minutes':item.parameters.unit)):''}}</p>
            <p v-if="item.parameters.amount">{{item.parameters.amount}} {{item.parameters.currency_code}}</p>
            <p v-if="item.parameters.method_label">{{t('commerce_payment_method')}}: {{item.parameters.method_label}}</p>
            <p v-if="item.parameters.place_id">{{t('commerce_place')}}: {{item.parameters.place_id}}</p>
            <p v-if="item.kind==='release'&&item.parameters.reason">{{t('commerce_release_reason')}}: {{item.parameters.reason}}</p>
            <p v-if="item.state==='waived'&&item.parameters._recovery?.reason">{{t('commerce_release_reason')}}: {{item.parameters._recovery.reason}}</p>
            <p v-if="item.parameters.consumer">{{t('commerce_consumer')}}: {{t(item.parameters.consumer==='child'?'child':'parent')}}</p>
            <details v-if="debugMode" class="cc-command-meta"><summary>{{t('commerce_technical_details')}}</summary><code>{{item.command_id}}</code></details>
            <p v-if="item.error_code&&applicable(item)&&journalAction(item)">{{t(item.error_code)}}</p>
            <p v-if="!applicable(item)&&['prepared','uncertain'].includes(item.state)">{{t('commerce_other_role_action')}}</p>
            <template v-if="applicable(item)&&journalAction(item)&&item.state==='prepared'">
              <label v-if="debugMode" class="cc-check ui-check"><input v-model="sendConfirmed[item.command_id]" type="checkbox" :disabled="locked"/>{{t(item.kind==='payment'?'commerce_received_confirmation':'commerce_send_confirmation')}}</label>
              <UiButton :disabled="locked||(debugMode&&!sendConfirmed[item.command_id])" @click="debugMode?executeStep(item):confirmStep(item)">{{debugMode?t('commerce_send_once'):confirmLabel(item)}}</UiButton>
              <UiButton :disabled="locked" @click="act(commandPrefix(item)+'_cancel',{command_id:item.command_id})">{{t('cancel')}}</UiButton>
            </template>
            <template v-if="applicable(item)&&journalAction(item)&&item.state==='uncertain'">
              <p v-if="item.kind==='open'">{{t('commerce_account_marker')}}: <code>3mm {{detail.account?.identity}}</code></p>
              <UiField v-if="item.kind==='open'" :id="'account-'+item.command_id" v-model="accountIds[item.command_id]" :label="t('commerce_reconcile_account_id')" :maxlength="16" :disabled="locked"/>
              <label v-if="!item.acknowledged&&item.kind!=='parent'&&item.kind!=='open'" class="cc-check ui-check"><input v-model="reviewedRemote[item.command_id]" type="checkbox" :disabled="locked"/>{{t('commerce_external_attestation')}}</label>
              <UiButton :disabled="locked" @click="act(commandPrefix(item)+'_check',{command_id:item.command_id,account_id:accountIds[item.command_id]?Number(accountIds[item.command_id]):null,reviewed:!!reviewedRemote[item.command_id]})">{{t('commerce_check_result')}}</UiButton>
            </template>
          </details>
          <div v-if="section==='journal'" class="cc-toolbar"><UiButton :disabled="locked||eventOffset===0" @click="select(detail.visit_id,eventOffset-50)">{{t('previous')}}</UiButton><UiButton :disabled="locked||!detail.has_more" @click="select(detail.visit_id,eventOffset+50)">{{t('next')}}</UiButton></div>
          <div v-if="!archivedBilling&&(!cashier||can('commerce_prepare')||can('commerce_allow_child'))" class="ui-stack">
            <div v-show="section==='overview'" class="ui-stack">
            <UiButton v-if="!detail.parent_linked&&!detail.opening_available" :disabled="locked" @click="prepare('parent')">{{t('commerce_prepare_parent')}}</UiButton>
            <section v-if="detail.parent_linked&&!detail.account&&!detail.opening_available">
              <UiButton :disabled="locked" @click="loadPlaces">{{t('commerce_load_places')}}</UiButton>
              <UiField id="account-place" v-model="place" type="select" :label="t('commerce_place')" :disabled="locked" :options="[{value:'',label:'—'},...places.map(p=>({value:String(p.place_id),label:p.label}))]"/>
              <UiButton :disabled="locked||!place" @click="prepare('open')">{{t('commerce_prepare_open')}}</UiButton>
            </section>
            <template v-if="detail.account?.state==='open'">
              <UiButton v-if="debugMode||detail.account.remote_state==='unknown'" :disabled="locked" @click="act('commerce_observe',{visit_id:detail.visit_id})">{{t('commerce_check_account')}}</UiButton>
            </template>
            </div>
            <div v-show="section==='consumption'" class="ui-stack">
            <template v-if="detail.account?.state==='open'&&can('commerce_prepare')">
              <form @submit.prevent="prepare('consumption')"><fieldset :disabled="locked"><legend>{{t('commerce_add_consumption')}}</legend>
                <UiField id="sale-consumer" v-model="consumer" type="select" :label="t('commerce_consumer')" :options="[{value:'child',label:t('child')},{value:'guardian',label:t('parent')}]" @update:model-value="changeConsumer"/>
                <UiField v-if="consumer==='child'&&members.length" id="sale-child" v-model="selectedChild" type="select" :label="t('child')" :options="members.map(m=>({value:m.child_id,label:m.child_name}))" @update:model-value="article=''"/>
                <template v-if="consumer==='guardian'">
                  <p>{{t('commerce_guardian_catalog_hint')}}</p>
                  <UiField id="guardian-catalog-search" v-model="catalogQuery" :label="t('search')" :maxlength="120"/>
                  <UiButton type="button" :disabled="catalogLoading" @click="loadCatalog()">{{t('barsy_load')}}</UiButton>
                  <div class="cc-toolbar"><UiButton type="button" :disabled="catalogLoading||catalogOffset===0" @click="loadCatalog(catalogOffset-20)">{{t('previous')}}</UiButton><UiButton type="button" :disabled="catalogLoading||!catalogMore" @click="loadCatalog(catalogOffset+20)">{{t('next')}}</UiButton></div>
                  <p v-if="catalogLoading" role="status">{{t('loading')}}</p>
                  <p v-else-if="!guardianChoices.length">{{t('no_records')}}</p>
                </template>
                <UiField id="sale-article" v-model="article" type="select" :label="t('commerce_article')" :options="[{value:'',label:'—'},...saleChoices.map(c=>({value:String(c.article_id),label:c.label}))]"/>
                <UiField id="sale-quantity" v-model="quantity" :label="t('commerce_quantity')" required :maxlength="20"/>
                <p v-if="consumer==='child'&&!saleChoices.length">{{t('commerce_parent_permission')}}</p>
                <UiButton type="submit" variant="primary" :disabled="!article||catalogLoading||(consumer==='child'&&!allowedConsumption.includes(Number(article)))">{{t('commerce_prepare')}}</UiButton>
              </fieldset></form>
            </template>
            <div class="cc-consumption-feedback" aria-live="polite">
              <p v-if="workflowBusy" role="status">{{t('loading')}}</p>
              <p v-else-if="actionConfirmed==='consumption'" role="status">{{t('commerce_consumption_confirmed')}}</p>
              <p v-if="debugMode&&error" role="alert" class="cc-error">{{t(error)}}</p>
            </div>
            <form v-if="can('commerce_allow_child')" @submit.prevent="debugMode?saveConsent():confirmConsent()">
              <fieldset :disabled="locked"><legend>{{t('commerce_parent_choices')}} · {{consumerChild?.child_name||detail.child_name}}</legend>
                <label v-for="choice in detail.choices" :key="choice.article_id" class="cc-check ui-check"><input v-model="childArticles" type="checkbox" :value="choice.article_id"/>{{choice.label}}</label>
                <label v-if="debugMode" class="cc-check ui-check"><input v-model="parentReviewed" type="checkbox" required/>{{t('commerce_parent_attestation')}}</label>
                <p v-if="debugMode&&!parentReviewed&&(!consentSaved||consentDirty)">{{t('commerce_consent_save_hint')}}</p>
                <UiButton type="submit" :disabled="debugMode&&!parentReviewed">{{t(debugMode?'save_changes':'commerce_save_permission')}}</UiButton>
                <p v-if="consentSaved&&!consentDirty" role="status">{{t('commerce_consent_saved')}}</p>
              </fieldset>
            </form>
            </div>
          </div>
          <section v-if="paymentAvailable&&detail.account?.state==='open'" v-show="section==='payment'" class="ui-stack cc-checkout">
            <p v-if="debugMode">{{t('commerce_payment_notice')}}</p>
            <template v-if="paymentCommand">
              <p>{{t('commerce_kind_payment')}} · {{state(paymentCommand.state)}}</p>
              <p><strong>{{paymentCommand.parameters.amount}} {{paymentCommand.parameters.currency_code}}</strong><span v-if="paymentCommand.parameters.method_label"> · {{paymentCommand.parameters.method_label}}</span></p>
              <p v-if="debugMode&&paymentCommand.parameters.expires_at">{{formatTimestamp(paymentCommand.parameters.expires_at,strings.locale.value)}}</p>
              <label v-if="paymentCommand.state==='prepared'&&debugMode" class="cc-check ui-check"><input v-model="sendConfirmed[paymentCommand.command_id]" type="checkbox" :disabled="locked"/>{{t('commerce_received_confirmation')}}</label>
              <template v-if="paymentCommand.state==='uncertain'">
                <p>{{t('commerce_check_required')}}</p>
                <label v-if="!paymentCommand.acknowledged" class="cc-check ui-check"><input v-model="reviewedRemote[paymentCommand.command_id]" type="checkbox" :disabled="locked"/>{{t('commerce_external_attestation')}}</label>
              </template>
              <div class="cc-toolbar">
                <UiButton variant="primary" :disabled="locked||((debugMode||paymentCommand.state==='uncertain')&&!paymentReviewed)" :loading="workflowBusy" @click="!debugMode&&paymentCommand.state==='prepared'?confirmPreparedPayment():continuePayment()">{{paymentCommand.state==='prepared'?debugMode?t('commerce_prepare_payment'):t('commerce_received_close')+' · '+paymentCommand.parameters.amount+' '+paymentCommand.parameters.currency_code:t('commerce_check_result')}}</UiButton>
                <UiButton v-if="paymentCommand.state==='prepared'&&can('cashier_cancel')" :disabled="locked" @click="act('cashier_cancel',{command_id:paymentCommand.command_id})">{{t('cancel')}}</UiButton>
              </div>
            </template>
            <template v-else>
            <p v-if="checkoutBlock">{{t(checkoutBlock)}}</p>
            <UiButton v-if="debugMode||!quote" :disabled="locked||!!checkoutBlock||!can('cashier_preview')" @click="preview">{{t('commerce_payment_preview')}}</UiButton>
            <form v-if="quote" @submit.prevent="debugMode?pay():confirmPayment()"><fieldset :disabled="locked"><legend>{{t(debugMode?'commerce_payment_preview':'commerce_payment')}}</legend>
              <p><strong>{{quote.amount}} {{quote.currency_code}}</strong><span v-if="debugMode"> · {{formatTimestamp(quote.expires_at,strings.locale.value)}}</span></p>
              <UiField id="pay-method" v-model="paymethod" type="select" :label="t('commerce_payment_method')" :options="[{value:'',label:'—'},...quote.methods.map(m=>({value:String(m.paymethod_id),label:m.label}))]"/>
              <label v-if="debugMode" class="cc-check ui-check"><input v-model="received" type="checkbox" required/>{{t('commerce_received_confirmation')}}</label>
              <UiButton type="submit" variant="primary" :loading="workflowBusy" :disabled="(debugMode&&!received)||!paymethod||!can('cashier_prepare')||!can('cashier_execute')">{{debugMode?t('commerce_prepare_payment'):t('commerce_received_close')+' · '+quote.amount+' '+quote.currency_code}}</UiButton>
            </fieldset></form>
            </template>
          </section>
          <div v-if="paymentAvailable" v-show="section==='payment'" class="cc-payment-feedback" aria-live="polite">
            <p v-if="workflowBusy" role="status">{{t('loading')}}</p>
            <p v-else-if="actionConfirmed==='payment'" role="status">{{t('commerce_payment_confirmed')}}</p>
            <p v-if="debugMode&&error" role="alert" class="cc-error">{{t(error)}}</p>
          </div>
          <details v-if="!archivedBilling&&detail.visit_state==='closed'&&section==='journal'&&((can('commerce_release_empty')&&detail.account?.state==='open')||(can('commerce_release_unlinked')&&!detail.account))" class="ui-stack cc-empty-release" :class="{'cc-unlinked-release':releaseUnlinked}">
            <summary>{{t(releaseUnlinked?'commerce_release_unlinked':'commerce_release_empty')}}</summary>
            <p>{{t(releaseUnlinked?'commerce_release_unlinked_hint':'commerce_release_empty_hint')}}</p>
            <form @submit.prevent="releaseEmpty"><fieldset :disabled="locked">
              <UiField id="empty-release-reason" v-model="emptyReleaseReason" :label="t('commerce_release_reason')" required :maxlength="240"/>
              <label class="cc-check ui-check"><input v-model="emptyReleaseReviewed" type="checkbox" required/>{{t(releaseUnlinked?'commerce_release_unlinked_attestation':'commerce_release_empty_attestation')}}</label>
              <UiButton type="submit" variant="danger" :disabled="locked||!emptyReleaseReviewed||!emptyReleaseReason.trim()">{{t(releaseUnlinked?'commerce_release_unlinked':'commerce_release_empty')}}</UiButton>
            </fieldset></form>
            <p v-if="debugMode&&error" class="cc-error" role="alert">{{t(error)}}</p>
          </details>
          <details v-if="paymentAvailable&&can('cashier_external_close')&&detail.account?.state==='open'&&section==='journal'" class="ui-stack">
            <summary>{{t('commerce_external_close')}}</summary>
            <label class="cc-check ui-check"><input v-model="externalCloseReviewed" type="checkbox" :disabled="locked"/>{{t('commerce_external_attestation')}}</label>
            <UiButton :disabled="locked||!externalCloseReviewed||!can('cashier_external_close')" @click="act('cashier_external_close',{visit_id:detail.visit_id,reviewed:true})">{{t('commerce_external_close')}}</UiButton>
          </details>

        </template>
      </div>
      <template #actions><UiButton @click="close">{{t('close')}}</UiButton></template>
    </UiDialog>
  </main></UiSurface>
</template>
