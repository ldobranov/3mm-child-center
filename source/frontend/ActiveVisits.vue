<template>
  <section class="cc-page" :class="{ 'cc-page--embedded': embedded }" aria-label="Stays">
    <header v-if="!embedded" class="cc-header">
      <div>
        <p class="cc-eyebrow">{{ t('Оператор', 'Operator') }}</p>
        <h1 id="visits-title">{{ t('Активни посещения', 'Active visits') }}</h1>
      </div>
      <div class="cc-connection" :class="{ 'cc-connection--warning': stale, 'cc-connection--offline': offline }">
        <span class="cc-dot" aria-hidden="true"></span>
        {{ connectionLabel }}
      </div>
    </header>

    <p v-if="error" class="cc-error" role="alert">{{ error }}</p>
    <p v-if="notice" class="cc-notice" role="status">{{ notice }}</p>

    <section v-if="accountFilter !== 'closed'" class="cc-reader" aria-labelledby="reader-title">
      <div>
        <p class="cc-eyebrow">{{ t('Reader режим', 'Reader mode') }}</p>
        <h2 id="reader-title">{{ readerModeLabel }}</h2>
        <p v-if="readerState?.mode === 'dedicated_readers'" class="cc-muted">
          {{ t('Режимът се определя от конфигурирания физически reader.', 'The configured physical reader determines the direction.') }}
        </p>
      </div>
      <div v-if="readerState?.mode === 'operator_selected'" class="cc-purpose" :aria-label="t('Избран режим на reader', 'Selected reader mode')">
        <button
          type="button"
          class="cc-purpose-button"
          :class="{ 'cc-purpose-button--active': readerState.operator_selected_purpose === 'entry' }"
          :disabled="busy"
          @click="setPurpose('entry')"
        >
          {{ t('Вход', 'Entry') }}
        </button>
        <button
          type="button"
          class="cc-purpose-button"
          :class="{ 'cc-purpose-button--active': readerState.operator_selected_purpose === 'exit' }"
          :disabled="busy"
          @click="setPurpose('exit')"
        >
          {{ t('Изход', 'Exit') }}
        </button>
      </div>
      <div class="cc-reader-actions">
        <button type="button" class="cc-button" :disabled="busy" @click="refresh">{{ t('Обнови', 'Refresh') }}</button>
        <button type="button" class="cc-language" :aria-label="t('Смени езика', 'Change language')" @click="toggleLanguage">
          {{ language === 'bg' ? 'EN' : 'BG' }}
        </button>
      </div>
    </section>

    <AccountDesk :refresh-token="billingRefresh" :stays="accountStays" :initial-filter="accountFilter" @accounts-loaded="accountIds = $event">
      <template #finish="{ account, locked }">
        <button v-if="visits.some(v => v.visit_id === account.visit_id)" type="button" class="cc-button cc-button--primary" :disabled="busy || locked || !account.admitted" @click="closeVisit(account.visit_id)">{{ t('Приключи играта', 'Finish playing') }}</button>
      </template>
    </AccountDesk>
    <section v-if="accountFilter !== 'closed' && otherVisits.length" class="cc-panel" aria-labelledby="active-title">
      <div class="cc-panel-header">
        <div>
          <h2 id="active-title">{{ t('Други неприключени престои', 'Other open stays') }}</h2>
          <p>{{ t('Изходът поставя времето на пауза. Само оператор приключва престоя.', 'Exit pauses the timer. Only an operator finishes the stay.') }}</p>
          <p>{{ otherVisits.length }} {{ otherVisits.length === 1 ? t('активно посещение', 'active visit') : t('активни посещения', 'active visits') }}</p>
        </div>
        <time v-if="lastUpdated">{{ t('Последно обновяване:', 'Last updated:') }} {{ formatTime(lastUpdated.toISOString()) }}</time>
      </div>

      <div v-if="visits.length" class="cc-grid">
        <article v-for="visit in otherVisits" :key="visit.visit_id" class="cc-visit">
          <div class="cc-visit-header">
            <div>
              <h3>{{ visit.child_display_name }}</h3>
              <span>{{ shortId(visit.visit_id) }}</span>
            </div>
            <strong>{{ formatDuration(elapsedSeconds(visit)) }}</strong>
          </div>
          <dl>
            <div><dt>{{ t('Състояние', 'Status') }}</dt><dd>{{ visit.phase === 'pending' ? t('Чака сметка — не допускайте още детето', 'Opening account — do not admit yet') : visit.phase === 'paused' ? t('Пауза — извън залата', 'Paused — outside') : visit.phase === 'legacy' ? t('Стар модел — приключете и в Barsy', 'Legacy — also close in Barsy') : t('Игра — в залата', 'Playing — inside') }}</dd></div>
            <div>
              <dt>{{ t('Вход', 'Entry') }}</dt>
              <dd>{{ formatDate(visit.entered_at) }}</dd>
            </div>
            <div>
              <dt>{{ t('Последно събитие', 'Last event') }}</dt>
              <dd>{{ formatTime(visit.last_event_at) }}</dd>
            </div>
            <div v-if="visit.barsy_table">
              <dt>{{ t('Barsy маса', 'Barsy table') }}</dt>
              <dd>{{ visit.barsy_table.display_name }} · ID {{ visit.barsy_table.barsy_place_id }}</dd>
              <dd>{{ barsyStateLabel(visit.barsy_table.timing_state) }}</dd>
            </div>
          </dl>
          <button type="button" class="cc-button cc-button--danger" :disabled="busy || visit.phase === 'pending'" @click="closeVisit(visit.visit_id)">
            {{ visit.phase === 'legacy' ? t('Приключи старото посещение', 'Finish legacy visit') : t('Приключи и изпрати към Barsy', 'Finish and send to Barsy') }}
          </button>
        </article>
      </div>
      <div v-else class="cc-empty">
        <h3>{{ t('Няма активни посещения', 'No active visits') }}</h3>
        <p>{{ t('При сканиране на гривна детето ще се появи тук автоматично.', 'The child will appear here automatically after the bracelet is scanned.') }}</p>
      </div>
    </section>
    <details class="cc-history"><summary>{{ t('Отчети от предишния модел', 'Previous workflow reports') }}</summary><StayBills :key="billingRefresh" /></details>
  </section>
</template>

<script setup lang="ts">
import { computed, inject, onMounted, onUnmounted, ref } from 'vue'

import { createRequestId, invokeApplicationOperation } from './application-api'
import { useChildCenterLanguage } from './language'
import StayBills from './StayBills.vue'
import AccountDesk from './AccountDesk.vue'
defineProps<{ embedded?: boolean; accountFilter?: 'open' | 'closed' }>()
const emit = defineEmits<{ 'playing-finished': [] }>()
const can = inject<(operation: string) => boolean>('childCenterCan', () => false)
const billingRefresh = ref(0)

type ReaderState = {
  mode: 'automatic_toggle' | 'operator_selected' | 'dedicated_readers'
  operator_selected_purpose: 'entry' | 'exit'
  effective_from: string
}

type ActiveVisit = {
  visit_id: string
  child_id: string
  child_display_name: string
  entered_at: string
  elapsed_seconds: number
  phase?: 'inside' | 'paused' | 'legacy' | 'pending'
  last_event_at: string
  barsy_table: null | {
    table_slot_id: string
    barsy_place_id: number
    display_name: string
    timing_state: 'prepared' | 'mock_confirmed' | 'confirmed' | 'retryable' | 'ambiguous' | 'manual_review'
  }
}

const readerState = ref<ReaderState | null>(null)
const { language, locale, t, toggleLanguage } = useChildCenterLanguage()
const visits = ref<ActiveVisit[]>([])
const accountIds = ref<string[]>([])
const otherVisits = computed(() => visits.value.filter(v => !accountIds.value.includes(v.visit_id)))
const accountStays = computed(() => visits.value.map(v => ({ visit_id: v.visit_id, phase: v.phase || 'legacy', duration: formatDuration(elapsedSeconds(v)) })))
const lastUpdated = ref<Date | null>(null)
const clockNow = ref(Date.now())
const busy = ref(false)
const offline = ref(false)
const error = ref('')
const notice = ref('')
let refreshTimer: number | undefined
let clockTimer: number | undefined

const stale = computed(() => !offline.value && (!lastUpdated.value || clockNow.value - lastUpdated.value.getTime() > 30_000))
const connectionLabel = computed(() => {
  if (offline.value) return t('Офлайн — показани са последните данни', 'Offline — showing the latest available data')
  if (stale.value) return t('Данните са остарели', 'Data is stale')
  return t('Локална връзка активна', 'Local connection active')
})
const readerModeLabel = computed(() => {
  if (!readerState.value) return t('Зареждане…', 'Loading…')
  if (readerState.value.mode === 'dedicated_readers') return t('Специализирани вход/изход readers', 'Dedicated entry/exit readers')
  if (readerState.value.mode === 'automatic_toggle') return t('Автоматично: първо сканиране ВХОД, следващо ИЗХОД', 'Automatic: first scan ENTRY, next scan EXIT')
  return readerState.value.operator_selected_purpose === 'entry' ? t('Следващото сканиране е ВХОД', 'Next scan is ENTRY') : t('Следващото сканиране е ИЗХОД', 'Next scan is EXIT')
})

async function invoke<T>(operation: string, payload: Record<string, unknown>, command = false): Promise<T> {
  if (!can(operation)) throw new Error(t('Нямате достъп до това действие.', 'You do not have access to this action.'))
  const token = localStorage.getItem('authToken') || ''
  return await invokeApplicationOperation<T>(
    'operator',
    operation,
    token,
    payload,
    command ? createRequestId() : undefined,
  )
}

async function loadData(showBusy = true) {
  if (showBusy) busy.value = true
  error.value = ''
  try {
    const [reader, active] = await Promise.all([
      invoke<ReaderState>('get_operator_reader_state', {}),
      invoke<{ items: ActiveVisit[] }>('list_active_visits', { cursor: null, limit: 100 }),
    ])
    readerState.value = reader
    visits.value = active.items
    lastUpdated.value = new Date()
    offline.value = false
  } catch (reason) {
    offline.value = true
    error.value = reason instanceof Error ? reason.message : t('Локалните данни не могат да бъдат обновени.', 'Local data could not be refreshed.')
  } finally {
    if (showBusy) busy.value = false
  }
}

async function refresh() {
  notice.value = ''
  await loadData()
}

async function setPurpose(purpose: 'entry' | 'exit') {
  if (!readerState.value || readerState.value.operator_selected_purpose === purpose) return
  busy.value = true
  error.value = ''
  notice.value = ''
  try {
    await invoke('set_operator_reader_purpose', { purpose }, true)
    readerState.value = await invoke<ReaderState>('get_operator_reader_state', {})
    lastUpdated.value = new Date()
    offline.value = false
    notice.value = purpose === 'entry' ? t('Reader режимът е ВХОД.', 'Reader mode is ENTRY.') : t('Reader режимът е ИЗХОД.', 'Reader mode is EXIT.')
  } catch (reason) {
    offline.value = true
    error.value = reason instanceof Error ? reason.message : t('Reader режимът не беше променен.', 'Reader mode was not changed.')
  } finally {
    busy.value = false
  }
}

async function closeVisit(visitId: string) {
  const visit = visits.value.find(v => v.visit_id === visitId)
  if (busy.value || !visit) return
  if (!window.confirm(`${visit.child_display_name} · ${formatDuration(elapsedSeconds(visit))}\n${t('Приключване на играта и освобождаване на гривната? Паузите не се таксуват; общото време се закръгля нагоре до минута. Сметката остава за плащане.', 'Finish playing and release the bracelet? Pauses are excluded; total playing time is rounded up to a minute. The account remains awaiting payment.')}`)) return
  busy.value = true
  error.value = ''
  notice.value = ''
  try {
    const result = await invoke<{ barsy_table: ActiveVisit['barsy_table']; duration_seconds: number; rounded_minutes?: number }>('close_visit', { visit_id: visitId, occurred_at: new Date().toISOString() }, true)
    visits.value = visits.value.filter((item) => item.visit_id !== visitId)
    lastUpdated.value = new Date()
    offline.value = false
    notice.value = t('Играта е приключена. Времето е записано и гривната е освободена. Продължете към плащане.', 'Playing finished. Time recorded and bracelet released. Proceed to payment.')
    if (result.rounded_minutes != null) notice.value += ` ${t('Измерено:', 'Measured:')} ${formatDuration(result.duration_seconds)} · ${t('За отчитане:', 'Billable:')} ${result.rounded_minutes} ${t('мин', 'min')}.`
    billingRefresh.value += 1
    if (accountIds.value.includes(visitId)) emit('playing-finished')
    if (result.barsy_table?.timing_state === 'manual_review') {
      notice.value += t(' Спрете времето и приключете сметката в Barsy. Масата остава заета до проверка от администратор.', ' Stop timing and close the account in Barsy. The place remains allocated until administrator verification.')
    }
  } catch (reason) {
    error.value = reason instanceof Error ? reason.message : t('Посещението не беше приключено.', 'The visit could not be closed.')
  } finally {
    busy.value = false
  }
}

function elapsedSeconds(visit: ActiveVisit) {
  if (visit.phase === 'paused' || visit.phase === 'pending' || offline.value) return visit.elapsed_seconds
  return visit.elapsed_seconds + Math.max(0, Math.floor((clockNow.value - (lastUpdated.value?.getTime() || clockNow.value)) / 1000))
}

function barsyStateLabel(state: string): string {
  if (state === 'mock_confirmed') return t('Тестов запис', 'Test record')
  if (state === 'prepared') return t('Чака отваряне в Barsy', 'Waiting to open in Barsy')
  if (state === 'retryable') return t('Чака готовност на Barsy или синхронизация на родителя', 'Waiting for Barsy readiness or parent sync')
  if (state === 'confirmed') return t('Сметката е отворена в Barsy', 'Account opened in Barsy')
  return t('Barsy изисква проверка от администратор', 'Barsy requires administrator review')
}

function formatDuration(total: number) {
  const hours = Math.floor(total / 3600)
  const minutes = Math.floor((total % 3600) / 60)
  const seconds = total % 60
  return [hours, minutes, seconds].map((value) => String(value).padStart(2, '0')).join(':')
}

function formatDate(value: string) {
  return new Intl.DateTimeFormat(locale.value, { dateStyle: 'short', timeStyle: 'short' }).format(new Date(value))
}

function formatTime(value: string) {
  return new Intl.DateTimeFormat(locale.value, { timeStyle: 'medium' }).format(new Date(value))
}

function shortId(value: string) {
  return value.slice(-8).toUpperCase()
}

onMounted(async () => {
  await loadData()
  refreshTimer = window.setInterval(() => loadData(false), 15_000)
  clockTimer = window.setInterval(() => { clockNow.value = Date.now() }, 1_000)
})

onUnmounted(() => {
  if (refreshTimer !== undefined) window.clearInterval(refreshTimer)
  if (clockTimer !== undefined) window.clearInterval(clockTimer)
})
</script>

<style scoped>
.cc-page {
  --text-color: var(--text-primary, #20242a);
  --muted-text-color: var(--text-secondary, #626b75);
  --surface-color: var(--card-bg, #fff);
  --surface-muted: var(--color-background-soft, var(--panel-bg, #f3f5f7));
  --border-color: var(--card-border, #d8dde3);
  --danger-color: var(--error-color, #b42318);
  max-width: 86rem; margin: 0 auto; padding: clamp(1rem, 3vw, 2.5rem); color: var(--text-color);
}
.cc-header, .cc-reader, .cc-panel-header, .cc-visit-header { display: flex; align-items: center; justify-content: space-between; gap: 1rem; }
.cc-page.cc-page--embedded { padding: 0; margin: 0; max-width: none; }
.cc-header { align-items: flex-start; margin-bottom: 1rem; }
.cc-eyebrow { margin: 0 0 .35rem; color: var(--primary-color, #356ae6); font-size: .75rem; font-weight: 700; letter-spacing: .08em; text-transform: uppercase; }
h1, h2, h3, p { margin-top: 0; } h1 { margin-bottom: 0; font-size: clamp(1.5rem, 4vw, 2.2rem); } h2 { margin-bottom: 0; font-size: 1.2rem; } h3 { margin-bottom: 0; }
.cc-connection { display: flex; align-items: center; gap: .45rem; padding: .4rem .65rem; border: 1px solid var(--border-color, #d8dde3); border-radius: 999px; color: var(--success-color, #067647); font-size: .78rem; }
.cc-dot { width: .5rem; height: .5rem; border-radius: 50%; background: currentColor; }
.cc-connection--warning { color: #b54708; } .cc-connection--offline { color: var(--danger-color, #b42318); }
:global(.dark-mode) .cc-connection--warning { color: #fdb022; }
.cc-reader, .cc-panel { border: 1px solid var(--border-color, #d8dde3); border-radius: .85rem; background: var(--surface-color, #fff); }
.cc-reader { margin-bottom: 1rem; padding: 1rem; }
.cc-reader-actions { display: flex; align-items: center; gap: .5rem; }
.cc-muted, .cc-panel-header p, .cc-panel-header time { margin: .35rem 0 0; color: var(--muted-text-color, #626b75); font-size: .82rem; }
.cc-purpose { display: grid; grid-template-columns: repeat(2, minmax(6rem, 1fr)); padding: .2rem; border: 1px solid var(--border-color, #d8dde3); border-radius: .65rem; background: var(--surface-muted, #f3f5f7); }
.cc-purpose-button { min-height: 2.55rem; padding: .55rem 1rem; border: 0; border-radius: .5rem; color: var(--muted-text-color, #626b75); background: transparent; cursor: pointer; }
.cc-purpose-button--active { color: var(--button-primary-text, #fff); background: var(--primary-color, #356ae6); box-shadow: 0 .15rem .45rem rgb(0 0 0 / 12%); }
.cc-panel { overflow: hidden; margin-top: 1rem; }
.cc-panel-header { padding: 1rem 1.15rem; border-bottom: 1px solid var(--border-color, #d8dde3); }
.cc-grid { display: grid; grid-template-columns: repeat(auto-fit, minmax(min(100%, 18rem), 1fr)); gap: 1rem; padding: 1rem; }
.cc-visit { display: grid; gap: 1rem; padding: 1rem; border: 1px solid var(--border-color, #d8dde3); border-radius: .7rem; background: var(--surface-muted, #f7f8fa); }
.cc-visit-header span { color: var(--muted-text-color, #626b75); font-size: .75rem; } .cc-visit-header strong { font-variant-numeric: tabular-nums; font-size: 1.25rem; }
dl { display: grid; grid-template-columns: repeat(2, 1fr); gap: .8rem; margin: 0; } dl div { display: grid; gap: .2rem; } dt { color: var(--muted-text-color, #626b75); font-size: .75rem; } dd { margin: 0; font-size: .88rem; }
.cc-button { min-height: 2.55rem; padding: .55rem .85rem; border: 1px solid var(--border-color, #cbd1d8); border-radius: .5rem; color: inherit; background: var(--surface-color, #fff); cursor: pointer; }
.cc-language { min-width: 2.7rem; min-height: 2.55rem; padding: .4rem .6rem; border: 1px solid var(--border-color, #cbd1d8); border-radius: 999px; color: inherit; background: var(--surface-color, #fff); font-weight: 700; cursor: pointer; }
.cc-button--danger { color: var(--danger-color, #b42318); } button:disabled { cursor: not-allowed; opacity: .55; }
.cc-button--primary { border-color: var(--primary-color); font-weight: 700; }
.cc-history { margin-top: 1rem; } .cc-history summary { cursor: pointer; color: var(--text-secondary); padding: .7rem 0; }
.cc-error, .cc-notice { margin-bottom: 1rem; padding: .75rem 1rem; border-radius: .55rem; } .cc-error { color: var(--danger-color, #b42318); background: var(--error-surface, rgb(180 35 24 / 8%)); } .cc-notice { color: var(--success-color, #067647); background: var(--success-surface, rgb(6 118 71 / 8%)); }
.cc-empty { min-height: 18rem; display: grid; place-content: center; padding: 2rem; color: var(--muted-text-color, #626b75); text-align: center; } .cc-empty p { margin: .5rem 0 0; }
@media (max-width: 46rem) { .cc-reader { align-items: stretch; flex-direction: column; } .cc-purpose { width: 100%; } .cc-panel-header { align-items: flex-start; flex-direction: column; } }
@media (max-width: 34rem) { .cc-header { align-items: stretch; flex-direction: column; } .cc-connection { align-self: flex-start; } .cc-visit-header { flex-wrap: wrap; } dl { grid-template-columns: 1fr; } }
</style>
