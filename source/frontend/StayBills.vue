<template>
  <section v-if="items.length || error" class="stay-bills" aria-labelledby="stay-bills-title">
    <header><h2 id="stay-bills-title">{{ t('Изпращане към Barsy', 'Barsy delivery') }}</h2><button :disabled="loading" @click="load">{{ t('Обнови', 'Refresh') }}</button></header>
    <p>{{ t('Приключването поставя отчета на опашка. Не е необходимо второ изпращане. Тестовите записи не се изпращат.', 'Finishing queues the bill. No second send is needed. Test records are not sent.') }}</p>
    <p v-if="error" class="error" role="alert">{{ error }}</p>
    <div class="scroll"><table v-if="items.length">
      <thead><tr><th>{{ t('Дете', 'Child') }}</th><th>{{ t('Минути', 'Minutes') }}</th><th>{{ t('Количество', 'Quantity') }}</th><th>{{ t('Barsy сметка', 'Barsy account') }}</th><th>{{ t('Състояние', 'Status') }}</th></tr></thead>
      <tbody><tr v-for="item in items" :key="item.bill_id"><td>{{ item.child_display_name }}<small>{{ item.visit_id.slice(-8).toUpperCase() }}</small></td><td>{{ item.rounded_minutes }}</td><td>{{ item.quantity }} {{ item.billing_unit === 'minutes' ? t('мин', 'min') : t('ч', 'h') }}</td><td>{{ item.remote_account_id || '—' }}</td><td>{{ status(item) }}<button v-if="item.state === 'retryable'" :disabled="loading" @click="retry(item)">{{ t('Изпрати след корекция', 'Send after correction') }}</button></td></tr></tbody>
    </table></div>
    <p v-if="!loading && !items.length && !error">{{ t('Няма приключени престои.', 'No completed stays.') }}</p>
    <footer><button :disabled="loading || offset === 0" @click="offset -= 50; load()">{{ t('Назад', 'Previous') }}</button><button :disabled="loading || !more" @click="offset += 50; load()">{{ t('Напред', 'Next') }}</button></footer>
  </section>
</template>
<script setup lang="ts">
import { onMounted, onUnmounted, ref } from 'vue'
import { createRequestId, invokeApplicationOperation } from './application-api'
import { useChildCenterLanguage } from './language'
const { t } = useChildCenterLanguage()
type Bill = { bill_id: string; visit_id: string; child_display_name: string; rounded_minutes: number; quantity: string; billing_unit: 'hours' | 'minutes'; state: string; remote_account_id: number | null; error_code: string | null }
const items = ref<Bill[]>([]), offset = ref(0), more = ref(false), loading = ref(false), error = ref('')
let timer: number | undefined
let disposed = false, lastPoll = 0
async function load() {
  if (loading.value) return
  loading.value = true; error.value = ''
  const token = localStorage.getItem('authToken') || ''
  try {
    const result = await invokeApplicationOperation<{ items: Bill[]; has_more: boolean }>('operator', 'list_stay_bills', localStorage.getItem('authToken') || '', { offset: offset.value })
    if (!disposed && token === (localStorage.getItem('authToken') || '')) { items.value = result.items; more.value = result.has_more }
  } catch (reason) { error.value = reason instanceof Error ? reason.message : t('Неуспешно обновяване.', 'Refresh failed.') }
  finally { loading.value = false; lastPoll = Date.now() }
}
function status(bill: Bill) {
  if (bill.error_code === 'zero_duration') return t('Без отчетно време', 'No billable time')
  if (bill.state === 'confirmed') return t('Потвърдено в Barsy', 'Confirmed in Barsy')
  if (bill.state === 'mock_confirmed') return t('Тест — не е изпратено', 'Test — not sent')
  if (bill.state === 'prepared') return t('Чака изпращане', 'Queued for delivery')
  if (bill.state === 'retryable') return bill.error_code === 'parent_sync_required' ? t('Чака синхронизация на родителя', 'Waiting for parent sync') : t('Нужна настройка на артикул без таймер / проверка на касата от администратор', 'Administrator: check non-timed article configuration and POS')
  return t('Нужна проверка от администратор — не изпращайте повторно', 'Administrator review required — do not resend')
}
async function retry(bill: Bill) {
  if (!window.confirm(t('Да се използва текущо настроеният артикул за този неизпратен отчет? Минутите не се променят.', 'Use the currently configured article for this unsent bill? Measured minutes remain unchanged.'))) return
  loading.value = true; error.value = ''
  try {
    await invokeApplicationOperation('operator', 'retry_stay_bill', localStorage.getItem('authToken') || '', { bill_id: bill.bill_id }, createRequestId())
    loading.value = false; await load()
  } catch (reason) { error.value = reason instanceof Error ? reason.message : t('Изпращането не беше подготвено.', 'Delivery could not be prepared.') }
  finally { loading.value = false }
}
onMounted(() => { load(); timer = window.setInterval(() => {
  const delay = items.value.some(item => item.state === 'prepared') ? 2000 : 10000
  if (!disposed && !document.hidden && Date.now() - lastPoll >= delay) void load()
}, 1000) })
onUnmounted(() => { disposed = true; if (timer !== undefined) window.clearInterval(timer) })
</script>
<style scoped>
.stay-bills { margin-top: 1rem; padding: 1rem; border: 1px solid var(--card-border); border-radius: .8rem; color: var(--text-primary); background: var(--card-bg); }
header, footer { display: flex; flex-wrap: wrap; gap: .6rem; align-items: center; justify-content: space-between; } h2 { margin: 0; font-size: 1.2rem; }
p, small { color: var(--text-secondary); } small { display: block; margin-top: .25rem; } .scroll { overflow-x: auto; } table { width: 100%; min-width: 36rem; border-collapse: collapse; }
th, td { padding: .7rem; text-align: left; border-bottom: 1px solid var(--card-border); } th { white-space: nowrap; } footer { margin-top: .8rem; justify-content: flex-start; }
button { min-height: 2.5rem; padding: .5rem .75rem; font: inherit; color: inherit; background: var(--card-bg); border: 1px solid var(--card-border); border-radius: .5rem; cursor: pointer; } button:disabled { opacity: .5; cursor: default; } .error { color: var(--error-color); }
</style>
