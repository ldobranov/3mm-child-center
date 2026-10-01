import { createApp, h, ref, provide } from 'vue'
import AccountDesk from '../../source/frontend/AccountDesk.vue'
import ScanOutcomes from '../../source/frontend/ScanOutcomes.vue'
import BarsyDirectory from '../../source/frontend/BarsyDirectory.vue'
import ConsumptionChoices from '../../source/frontend/ConsumptionChoices.vue'
import ActiveVisits from '../../source/frontend/StaffVisits.vue'
import OperatorDesk from '../../source/frontend/StaffOperator.vue'
import Administration from '../../source/frontend/Administration.vue'
import VisitHistory from '../../source/frontend/StaffHistory.vue'
import StaffCashier from '../../source/frontend/StaffCashier.vue'
import StaffAccessSettings from '../../source/frontend/StaffAccessSettings.vue'
const selected = ref<string[]>([])
localStorage.setItem('authToken', 'synthetic-preview-session')
createApp({ setup: () => {
  if (location.search.includes('workflow')) provide('childCenterCan', () => true)
  return () => location.search.includes('workflow') ? h('div', [h(ScanOutcomes), h(AccountDesk)]) : location.search.includes('access') ? h(StaffAccessSettings) : location.search.includes('cashier') ? h(StaffCashier) : location.search.includes('admin') ? h(Administration) : location.search.includes('operator') ? h(OperatorDesk) : location.search.includes('history') ? h(VisitHistory) : location.search.includes('visits') ? h(ActiveVisits) : h('div', [h(BarsyDirectory), h('section', { class: 'preview-choices' }, [
  h('h2', 'Registration preview'),
  h(ConsumptionChoices, { audience: 'operator', modelValue: selected.value, 'onUpdate:modelValue': (value: string[]) => { selected.value = value } }),
])]) } }).mount('#app')
