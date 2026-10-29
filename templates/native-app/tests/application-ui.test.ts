import { afterEach, expect, it, vi } from 'vitest'
import { mount, flushPromises } from '@vue/test-utils'
import { applicationHostKey } from '@3mm/application-ui/v1'
import App from '../source/frontend/App.vue'
afterEach(()=>sessionStorage.clear())
function render(invoke=vi.fn().mockResolvedValue({value:0})) {
  return mount(App,{global:{provide:{[applicationHostKey as symbol]:{
    getInfo:async()=>({module_id:'org.example.application',operations:[{operation_id:'read_value'},{operation_id:'add_value'},{operation_id:'request_outcome'}]}),invoke}}}})
}
it('uses public UI controls and switches preview locale without losing state',async()=>{
  const page=render();await flushPromises()
  expect(page.find('.ui-v2').exists()).toBe(true)
  expect(page.find('.ui-button').exists()).toBe(true)
  expect(page.text()).toContain('Value: 0')
  await page.setProps({locale:'bg'})
  expect(page.text()).toContain('Стойност: 0')
  await page.setProps({locale:'de-DE'})
  expect(page.text()).toContain('Value: 0')
  page.unmount()
})
it('retains the original request after a lost reply and resolves without mutation replay',async()=>{
  const invoke=vi.fn().mockResolvedValueOnce({value:0}).mockRejectedValueOnce(new Error('lost'))
    .mockResolvedValueOnce({found:true,result_json:'{"status":"applied","value":1}'})
  const page=render(invoke);await flushPromises()
  await page.findAll('button')[0].trigger('click');await flushPromises()
  expect(page.find('code').exists()).toBe(true)
  expect(page.findAll('button')[0].attributes('disabled')).toBeDefined()
  await page.findAll('button')[1].trigger('click');await flushPromises()
  expect(invoke.mock.calls.map(call=>call[0])).toEqual(['read_value','add_value','request_outcome'])
  expect(page.text()).toContain('Value: 1')
  page.unmount()
})
