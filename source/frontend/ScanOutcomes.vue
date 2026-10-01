<template>
  <section class="scan-outcomes" aria-labelledby="scan-outcomes-title">
    <header><h2 id="scan-outcomes-title">{{ t('Последни сканирания', 'Recent scans') }}</h2><button :disabled="loading" @click="refresh">{{ t('Обнови', 'Refresh') }}</button></header>
    <p v-if="error" role="alert">{{ error }}</p>
    <p v-if="items.some(item => item.error_code)" role="status">{{ t('Отказаният вход няма да се изпълни по-късно. След корекция сканирайте отново.', 'A denied entry will not run later. After correcting the problem, scan again.') }}</p>
    <p v-if="!items.length && !loading">{{ t('Няма сканирания.', 'No scans yet.') }}</p>
    <ul><li v-for="item in items" :key="item.event_id" :class="{ failed: item.error_code || item.status === 'unknown_identifier' }">
      <time>{{ new Date(item.occurred_at).toLocaleTimeString() }}</time>
      <span>{{ item.child_name || (item.status === 'unknown_identifier' ? t('Непозната гривна', 'Unknown bracelet') : '—') }}</span>
      <strong>{{ label(item) }}</strong>
    </li></ul>
  </section>
</template>
<script setup lang="ts">
import { inject, onMounted, onUnmounted, ref } from 'vue'
import { invokeApplicationOperation } from './application-api'
import { useChildCenterLanguage } from './language'
const { t } = useChildCenterLanguage()
const can = inject<(operation: string) => boolean>('childCenterCan', () => false)
type Scan = { event_id: string; occurred_at: string; status: string; error_code: string | null; child_name: string | null }
const items = ref<Scan[]>([]), loading = ref(false), error = ref('')
let timer: number | undefined, disposed = false
async function refresh() {
  if (disposed || loading.value || !can('list_scan_outcomes')) return
  const token = localStorage.getItem('authToken') || ''
  loading.value = true
  try {
    const result = await invokeApplicationOperation<{ items: Scan[] }>('operator', 'list_scan_outcomes', token, {})
    if (!disposed && can('list_scan_outcomes') && token === (localStorage.getItem('authToken') || '')) { items.value = result.items; error.value = '' }
  } catch { if (!disposed) error.value = t('Неуспешно обновяване на сканиранията.', 'Could not refresh scans.') }
  finally { loading.value = false }
}
function label(item: Scan) {
  const labels: Record<string, string> = {
    barsy_credentials_unavailable: t('Входът е отказан — проверете запазените данни за достъп до Barsy', 'Entry denied — check saved Barsy credentials'),
    barsy_unavailable: t('Входът е отказан — връзката с Barsy не е достъпна', 'Entry denied — Barsy connection unavailable'),
    barsy_rejected: t('Входът е отказан — Barsy отказа проверката', 'Entry denied — Barsy rejected the check'),
    barsy_invalid_response: t('Входът е отказан — невалиден отговор от Barsy', 'Entry denied — invalid Barsy response'),
    no_enabled_tables: t('Входът е отказан — администраторът трябва да включи поне една маса в Администрация → Barsy → Маси', 'Entry denied — an administrator must enable at least one table in Administration → Barsy → Tables'),
    no_free_tables: t('Входът е отказан — няма свободна включена маса. Проверете отворените сметки в Barsy', 'Entry denied — no enabled table is free. Check open accounts in Barsy'),
    unknown_identifier: t('Няма закачена гривна с този номер', 'No attached bracelet with this number'),
    started: t('Приемът е създаден', 'Admission created'), resumed: t('Продължен престой', 'Stay resumed'),
    paused: t('Пауза', 'Paused'), closed: t('Приключено', 'Closed'),
    ignored: t('Без промяна — проверете състоянието на приема', 'No change — check admission status'),
    wrong_reader_mode: t('Грешен четец или режим', 'Wrong reader or mode'), late_event: t('Закъсняло събитие', 'Late event'),
    already_active: t('Вече е вътре', 'Already inside'), already_closed: t('Вече е приключено', 'Already closed'),
    already_paused: t('Вече е на пауза', 'Already paused'),
  }
  return labels[item.error_code || item.status] || t('Нужна е проверка', 'Review required')
}
onMounted(() => { void refresh(); timer = window.setInterval(() => { if (!document.hidden) void refresh() }, 3000) })
onUnmounted(() => { disposed = true; window.clearInterval(timer); items.value = [] })
</script>
<style scoped>
.scan-outcomes { padding: 1rem; margin: 1rem 0; border: 1px solid var(--card-border); border-radius: .6rem; color: var(--text-primary); background: var(--card-bg); }
header { display: flex; justify-content: space-between; align-items: center; gap: .7rem; } h2 { font-size: 1.1rem; margin: 0; }
button { padding: .5rem .8rem; color: inherit; background: var(--card-bg); border: 1px solid var(--card-border); border-radius: .4rem; }
ul { list-style: none; padding: 0; margin: .7rem 0 0; } li { display: grid; grid-template-columns: 6rem 1fr 2fr; gap: .6rem; padding: .6rem 0; border-top: 1px solid var(--card-border); overflow-wrap: anywhere; }
time, p { color: var(--text-secondary); } .failed strong { color: var(--error-color); }
@media(max-width: 40rem) { li { grid-template-columns: 1fr; } }
</style>
