<template>
  <main class="cc-page" aria-labelledby="history-title">
    <header class="cc-header">
      <div>
        <p class="cc-eyebrow">{{ t('Оператор', 'Operator') }}</p>
        <h1 id="history-title">{{ t('История на посещенията', 'Visit history') }}</h1>
        <p>{{ t('Приключени посещения и реално измерено време.', 'Closed visits and actual measured time.') }}</p>
      </div>
      <button type="button" class="cc-language" :aria-label="t('Смени езика', 'Change language')" @click="toggleLanguage">
        {{ language === 'bg' ? 'EN' : 'BG' }}
      </button>
    </header>

    <section class="cc-panel" aria-labelledby="filters-title">
      <div class="cc-panel-heading">
        <div>
          <p class="cc-eyebrow">{{ t('Филтри', 'Filters') }}</p>
          <h2 id="filters-title">{{ t('Намери посещение', 'Find a visit') }}</h2>
        </div>
        <div class="cc-periods" :aria-label="t('Бърз избор на период', 'Quick period selection')">
          <button type="button" class="cc-subtle" :disabled="loading" @click="selectPeriod(1)">{{ t('Днес', 'Today') }}</button>
          <button type="button" class="cc-subtle" :disabled="loading" @click="selectPeriod(7)">{{ t('7 дни', '7 days') }}</button>
          <button type="button" class="cc-subtle" :disabled="loading" @click="selectPeriod(30)">{{ t('30 дни', '30 days') }}</button>
          <button type="button" class="cc-subtle" :disabled="loading" @click="clearFilters">{{ t('Всички', 'All') }}</button>
        </div>
      </div>

      <form class="cc-filters" @submit.prevent="applyFilters">
        <label class="cc-search">
          <span>{{ t('Родител или дете', 'Guardian or child') }}</span>
          <input v-model.trim="draft.query" type="search" maxlength="120" :placeholder="t('Търсене по име', 'Search by name')">
        </label>
        <label>
          <span>{{ t('От дата', 'From date') }}</span>
          <input v-model="draft.dateFrom" type="date" :max="draft.dateTo || undefined">
        </label>
        <label>
          <span>{{ t('До дата', 'To date') }}</span>
          <input v-model="draft.dateTo" type="date" :min="draft.dateFrom || undefined">
        </label>
        <button class="cc-primary" type="submit" :disabled="loading">{{ t('Приложи', 'Apply') }}</button>
      </form>
    </section>

    <p v-if="error" class="cc-error" role="alert">{{ error }}</p>

    <section class="cc-panel cc-results" aria-labelledby="results-title">
      <div class="cc-panel-heading">
        <div>
          <h2 id="results-title">{{ t('Резултати', 'Results') }}</h2>
          <p v-if="!loading || items.length">{{ items.length }} {{ t('заредени посещения', 'visits loaded') }}</p>
        </div>
        <button type="button" class="cc-subtle" :disabled="loading" @click="applyFilters">{{ t('Обнови', 'Refresh') }}</button>
      </div>

      <div v-if="items.length" class="cc-table-wrap">
        <table>
          <thead>
            <tr>
              <th>{{ t('Дете / родител', 'Child / guardian') }}</th>
              <th>{{ t('Вход', 'Entry') }}</th>
              <th>{{ t('Изход', 'Exit') }}</th>
              <th>{{ t('Време', 'Duration') }}</th>
              <th>{{ t('Източник', 'Source') }}</th>
              <th>Barsy</th>
            </tr>
          </thead>
          <tbody>
            <tr v-for="item in items" :key="item.visit_id">
              <td data-label="">
                <strong>{{ item.child_display_name }}</strong>
                <span>{{ item.guardian_display_name }}</span>
              </td>
              <td :data-label="t('Вход', 'Entry')">{{ formatDate(item.entered_at) }}</td>
              <td :data-label="t('Изход', 'Exit')">{{ formatDate(item.exited_at) }}</td>
              <td :data-label="t('Време', 'Duration')"><div><strong class="cc-duration">{{ formatDuration(item.duration_seconds) }}</strong><span v-if="item.rounded_minutes != null">{{ t('За отчитане:', 'Billable:') }} {{ item.rounded_minutes }} {{ t('мин', 'min') }}</span></div></td>
              <td :data-label="t('Източник', 'Source')">
                <span>{{ t('Вход', 'Entry') }}: {{ sourceLabel(item.entry_source) }}</span>
                <span>{{ t('Изход', 'Exit') }}: {{ sourceLabel(item.exit_source) }}</span>
              </td>
              <td data-label="Barsy">
                <span v-if="item.barsy_table">{{ item.barsy_table.display_name }}</span>
                <span v-else class="cc-muted">—</span>
              </td>
            </tr>
          </tbody>
        </table>
      </div>

      <div v-else-if="loading" class="cc-empty" role="status">{{ t('Зареждане…', 'Loading…') }}</div>
      <div v-else class="cc-empty">
        <h3>{{ t('Няма намерени посещения', 'No visits found') }}</h3>
        <p>{{ t('Променете периода или търсеното име.', 'Change the period or searched name.') }}</p>
      </div>

      <div v-if="nextCursor" class="cc-more">
        <button type="button" class="cc-primary" :disabled="loading" @click="loadMore">
          {{ loading ? t('Зареждане…', 'Loading…') : t('Зареди още', 'Load more') }}
        </button>
      </div>
    </section>
  </main>
</template>

<script setup lang="ts">
import { inject, onMounted, onUnmounted, reactive, ref } from 'vue'

import { invokeApplicationOperation } from './application-api'
import { useChildCenterLanguage } from './language'

type EventSource = 'identifier_event' | 'operator' | 'administrator' | 'internal'

type HistoryItem = {
  visit_id: string
  child_id: string
  child_display_name: string
  guardian_display_name: string
  entered_at: string
  exited_at: string
  duration_seconds: number
  rounded_minutes?: number | null
  entry_source: EventSource
  exit_source: EventSource
  barsy_table: null | {
    table_slot_id: string
    barsy_place_id: number
    display_name: string
    timing_state: 'mock_confirmed' | 'confirmed' | 'retryable' | 'ambiguous' | 'manual_review'
  }
}

type HistoryResponse = { items: HistoryItem[]; next_cursor: string | null }

const { language, locale, t, toggleLanguage } = useChildCenterLanguage()
const can = inject<(operation: string) => boolean>('childCenterCan', () => false)
let disposed = false
const draft = reactive({ query: '', dateFrom: '', dateTo: '' })
const applied = reactive({ query: '', dateFrom: '', dateTo: '' })
const items = ref<HistoryItem[]>([])
const nextCursor = ref<string | null>(null)
const loading = ref(false)
const error = ref('')

function localDate(daysAgo = 0) {
  const date = new Date()
  date.setHours(0, 0, 0, 0)
  date.setDate(date.getDate() - daysAgo)
  const year = date.getFullYear()
  const month = String(date.getMonth() + 1).padStart(2, '0')
  const day = String(date.getDate()).padStart(2, '0')
  return `${year}-${month}-${day}`
}

function startOfDayIso(value: string) {
  return value ? new Date(`${value}T00:00:00`).toISOString() : null
}

function endOfDayIso(value: string) {
  if (!value) return null
  const date = new Date(`${value}T00:00:00`)
  date.setDate(date.getDate() + 1)
  return date.toISOString()
}

async function request(cursor: string | null, append: boolean) {
  if (loading.value || disposed) return
  loading.value = true
  error.value = ''
  try {
    if (!can('list_visit_history')) throw new Error(t('Нямате права за историята на посещенията.', 'You do not have access to visit history.'))
    const token = localStorage.getItem('authToken') || ''
    const result = await invokeApplicationOperation<HistoryResponse>('operator', 'list_visit_history', token, {
      query: applied.query,
      date_from: startOfDayIso(applied.dateFrom),
      date_to: endOfDayIso(applied.dateTo),
      cursor,
      limit: 50,
    })
    if (disposed || !can('list_visit_history') || token !== localStorage.getItem('authToken')) return
    items.value = append ? [...items.value, ...result.items] : result.items
    nextCursor.value = result.next_cursor
  } catch (reason) {
    error.value = reason instanceof Error ? reason.message : t('Историята не може да бъде заредена.', 'Visit history could not be loaded.')
  } finally {
    loading.value = false
  }
}

async function applyFilters() {
  applied.query = draft.query
  applied.dateFrom = draft.dateFrom
  applied.dateTo = draft.dateTo
  await request(null, false)
}

async function selectPeriod(days: number) {
  draft.dateFrom = localDate(Math.max(0, days - 1))
  draft.dateTo = localDate()
  await applyFilters()
}

async function clearFilters() {
  draft.query = ''
  draft.dateFrom = ''
  draft.dateTo = ''
  await applyFilters()
}

async function loadMore() {
  if (nextCursor.value) await request(nextCursor.value, true)
}

function formatDate(value: string) {
  return new Intl.DateTimeFormat(locale.value, { dateStyle: 'short', timeStyle: 'short' }).format(new Date(value))
}

function formatDuration(total: number) {
  const hours = Math.floor(total / 3600)
  const minutes = Math.floor((total % 3600) / 60)
  const seconds = total % 60
  return [hours, minutes, seconds].map((value) => String(value).padStart(2, '0')).join(':')
}

function sourceLabel(source: EventSource) {
  if (source === 'identifier_event') return t('гривна', 'bracelet')
  if (source === 'administrator') return t('администратор', 'administrator')
  if (source === 'internal') return t('система', 'system')
  return t('оператор', 'operator')
}

onMounted(async () => {
  draft.dateFrom = localDate(7)
  draft.dateTo = localDate()
  await applyFilters()
})
onUnmounted(() => { disposed = true; items.value = []; nextCursor.value = null })
</script>

<style scoped>
.cc-page {
  --text-color: var(--text-primary, #20242a);
  --muted-text-color: var(--text-secondary, #626b75);
  --surface-color: var(--card-bg, #fff);
  --surface-muted: var(--color-background-soft, var(--panel-bg, #f3f5f7));
  --border-color: var(--card-border, #d8dde3);
  --danger-color: var(--error-color, #b42318);
  max-width: 90rem; margin: 0 auto; padding: clamp(1rem, 3vw, 2.5rem); color: var(--text-color);
}
.cc-header, .cc-panel-heading { display: flex; align-items: center; justify-content: space-between; gap: 1rem; }
.cc-header { align-items: flex-start; margin-bottom: 1rem; }
.cc-header > div > p:last-child, .cc-panel-heading p { margin: .35rem 0 0; color: var(--muted-text-color, #626b75); }
.cc-eyebrow { margin: 0 0 .35rem !important; color: var(--primary-color, #356ae6) !important; font-size: .75rem; font-weight: 700; letter-spacing: .08em; text-transform: uppercase; }
h1, h2, h3, p { margin-top: 0; } h1 { margin-bottom: 0; font-size: clamp(1.5rem, 4vw, 2.2rem); } h2 { margin-bottom: 0; font-size: 1.15rem; } h3 { margin-bottom: .35rem; }
.cc-language { min-width: 2.7rem; min-height: 2.55rem; padding: .4rem .6rem; border: 1px solid var(--border-color, #cbd1d8); border-radius: 999px; color: inherit; background: var(--surface-color, #fff); font-weight: 700; cursor: pointer; }
.cc-panel { margin-bottom: 1rem; border: 1px solid var(--border-color, #d8dde3); border-radius: .85rem; background: var(--surface-color, #fff); overflow: hidden; }
.cc-panel-heading { padding: 1rem 1.15rem; border-bottom: 1px solid var(--border-color, #d8dde3); }
.cc-periods { display: flex; flex-wrap: wrap; gap: .4rem; }
.cc-filters { display: grid; grid-template-columns: minmax(15rem, 2fr) repeat(2, minmax(10rem, 1fr)) auto; align-items: end; gap: .8rem; padding: 1rem 1.15rem; }
label { display: grid; gap: .35rem; color: var(--muted-text-color, #626b75); font-size: .78rem; font-weight: 600; }
input { width: 100%; min-height: 2.6rem; padding: .55rem .7rem; border: 1px solid var(--input-border, var(--border-color, #cbd1d8)); border-radius: .5rem; color: var(--text-color, #20242a); background: var(--input-bg, var(--surface-color, #fff)); font: inherit; font-weight: 400; color-scheme: inherit; }
input:focus-visible, button:focus-visible { outline: 2px solid var(--primary-color, #356ae6); outline-offset: 2px; }
.cc-primary, .cc-subtle { min-height: 2.6rem; padding: .55rem .85rem; border: 1px solid var(--border-color, #cbd1d8); border-radius: .5rem; cursor: pointer; }
.cc-primary { border-color: var(--primary-color, #356ae6); color: var(--button-primary-text, #fff); background: var(--primary-color, #356ae6); }
.cc-subtle { color: inherit; background: var(--surface-color, #fff); }
button:disabled { cursor: not-allowed; opacity: .55; }
.cc-error { margin-bottom: 1rem; padding: .75rem 1rem; border-radius: .55rem; color: var(--danger-color, #b42318); background: var(--error-surface, rgb(180 35 24 / 8%)); }
.cc-table-wrap { overflow-x: auto; }
table { width: 100%; border-collapse: collapse; font-size: .86rem; }
th, td { padding: .8rem 1rem; border-bottom: 1px solid var(--border-color, #e2e5e9); text-align: left; vertical-align: top; }
th { color: var(--muted-text-color, #626b75); background: var(--surface-muted, #f7f8fa); font-size: .72rem; letter-spacing: .04em; text-transform: uppercase; white-space: nowrap; }
tbody tr:last-child td { border-bottom: 0; }
td span { display: block; margin-top: .15rem; color: var(--muted-text-color, #626b75); font-size: .78rem; }
.cc-duration { font-variant-numeric: tabular-nums; white-space: nowrap; }
.cc-muted { color: var(--muted-text-color, #626b75); }
.cc-empty { min-height: 16rem; display: grid; place-content: center; padding: 2rem; color: var(--muted-text-color, #626b75); text-align: center; }
.cc-empty p { margin: 0; }
.cc-more { display: flex; justify-content: center; padding: 1rem; border-top: 1px solid var(--border-color, #d8dde3); }
@media (max-width: 58rem) { .cc-filters { grid-template-columns: 1fr 1fr; } .cc-search { grid-column: 1 / -1; } }
@media (max-width: 44rem) {
  .cc-header, .cc-panel-heading { align-items: flex-start; flex-direction: column; }
  .cc-language { position: absolute; right: 1rem; }
  .cc-filters { grid-template-columns: 1fr; }
  .cc-search { grid-column: auto; }
  .cc-table-wrap { overflow: visible; }
  table, tbody, tr, td { display: block; } thead { display: none; }
  tr { padding: .7rem 1rem; border-bottom: 1px solid var(--border-color, #e2e5e9); }
  td { display: grid; grid-template-columns: minmax(5.5rem, .7fr) 1fr; gap: .5rem; padding: .28rem 0; border: 0; }
  td::before { content: attr(data-label); color: var(--muted-text-color, #626b75); font-size: .75rem; }
  td[data-label=''] { display: block; padding-bottom: .55rem; }
}
</style>
