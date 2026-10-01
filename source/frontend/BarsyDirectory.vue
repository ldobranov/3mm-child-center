<template>
  <article class="directory">
    <h2>{{ view === 'review' ? t('Родители и изпращания', 'Parents and deliveries') : t('3. Отчитане на времето', '3. Time measurement') }}</h2>
    <p v-if="error" role="alert" class="error">{{ error }}</p>
    <p v-if="notice" role="status">{{ notice }}</p>
    <section v-show="view !== 'review'" class="timing-profiles" :aria-label="t('Режими за време', 'Timing modes')">
      <p v-if="!timing">{{ t('Настройките не са заредени.', 'Configuration has not loaded.') }} <button :disabled="busy" @click="run(readTiming)">{{ t('Обнови', 'Refresh') }}</button></p>
      <template v-else>
        <p><strong>{{ t('Активен режим:', 'Active mode:') }} {{ timing.active_mode === 'local_quantity' ? t('Локално измерване', 'Local measurement') : t('Таймер в Barsy', 'Barsy timer') }}</strong></p>
        <p v-if="!timing.can_change_active_profile" role="status">{{ t('Има отворени престои или неприключени изпращания. Активният профил е заключен.', 'Open stays or outstanding deliveries lock the active profile.') }}</p>
        <div class="profile-grid">
          <section class="profile">
            <h4>{{ t('Локално измерване', 'Local measurement') }}</h4>
            <p>{{ t('Пауза при изход, продължаване при вход. Сумиране и закръгляне нагоре до минута при приключване от оператор. В Barsy се подава готово количество, без автоматичен таймер.', 'Pause on exit, resume on entry. Sum and round up to a minute when the operator finishes. Send a fixed quantity to Barsy, without an automatic timer.') }}</p>
            <strong>{{ timing.local_quantity.label || t('Няма избран артикул', 'No article selected') }}</strong>
            <p>{{ t('Запазена единица:', 'Saved unit:') }} {{ unitLabel(timing.local_quantity.billing_unit) }}</p>
            <label class="profile-target">{{ t('Подаване на времето', 'Send time as') }}
              <select v-model="selectedUnit" :aria-label="t('Подаване на времето', 'Send time as')" :disabled="busy || !timing.can_change_active_profile">
                <option value="minutes">{{ t('Минути', 'Minutes') }}</option>
                <option value="hours">{{ t('Часове', 'Hours') }}</option>
              </select>
            </label>
            <p>{{ selectedUnit === 'minutes' ? t('6 отчетни минути → количество 6. Цената в Barsy трябва да е за минута.', '6 billable minutes → quantity 6. The Barsy price must be per minute.') : t('6 отчетни минути → количество 0.100. Цената в Barsy трябва да е за час; нужни са поне 3 десетични знака.', '6 billable minutes → quantity 0.100. The Barsy price must be per hour, with at least 3 decimal places.') }}</p>
            <p>{{ t('Мерните единици Минута и Час в Barsy се поддържат. Автоматичното отчитане трябва да е изключено в типа на мястото. Тук не променяме артикула, цената или типа на мястото в Barsy.', 'Barsy Minute and Hour units are supported. Automatic timing must be disabled in the place type. This setting does not change the Barsy article, price or place type.') }}</p>
            <button v-if="selectedUnit !== timing.local_quantity.billing_unit && timing.local_quantity.article_id" :disabled="busy || !timing.can_change_active_profile" @click="setBillingArticle(timing.local_quantity.article_id, 'local_quantity')">{{ t('Запази единицата', 'Save unit') }}</button>
            <span v-if="timing.active_mode === 'local_quantity'" class="active-profile">{{ t('Активен режим', 'Active mode') }}</span>
            <button v-else :disabled="busy || !timing.can_change_active_profile || !timing.local_quantity.article_id" @click="activateMode('local_quantity')">{{ t('Активирай локално измерване', 'Activate local measurement') }}</button>
          </section>
          <details class="profile">
            <summary>{{ t('Таймер в Barsy — бъдеща възможност', 'Barsy timer — future capability') }}</summary>
            <p>{{ t('Barsy отчита всеки интервал. При повторен вход се добавя нов времеви ред към същата сметка.', 'Barsy measures each interval. Re-entry adds a new timed row to the same account.') }}</p>
            <strong>{{ timing.barsy_timer.label || t('Няма избран артикул', 'No article selected') }}</strong>
            <p class="capability-note">{{ t('Само подготовка на настройки — не е активен. Изчаква потвърден API за спиране на времеви ред.', 'Configuration draft only — not active. Waiting for a verified API to stop a timed row.') }}</p>
            <span>{{ t('Активирането е недостъпно', 'Activation unavailable') }}</span>
          </details>
        </div>
      </template>
    </section>
    <details v-show="view !== 'setup'">
      <summary>{{ t('Отчитане на престоя', 'Stay billing') }}</summary>
      <p>{{ t('Ежедневната работа е в Оператор → Престои и Barsy. Изберете артикул за минута или час и място без автоматично отчитане на време.', 'Daily work is in Operator → Stays and Barsy. Select a minute or hour article and a place without automatic timing.') }}</p>
      <p><strong>{{ t('Отчетен артикул:', 'Billing article:') }} {{ billing?.settings.label || t('Не е избран', 'Not selected') }}</strong> <span v-if="billing?.settings.article_id"> · ID {{ billing.settings.article_id }} · {{ billing.settings.quantity_precision }} {{ t('десетични знака', 'decimal places') }}</span></p>
      <button :disabled="busy" @click="run(readBilling)">{{ t('Обнови отчетите', 'Refresh bills') }}</button>
      <p>{{ t('31 минути = 0,517 часа при точност 3 знака. Тестовите престои не се изпращат впоследствие. При неясен отговор проверете сметката — заявката не се повтаря автоматично.', '31 minutes = 0.517 hours at 3 decimal places. Test stays are never sent later. Verify uncertain accounts — the request is never automatically resent.') }}</p>
      <details><summary>{{ t('Проверка на проблемни изпращания', 'Delivery troubleshooting') }}</summary>
      <div class="scroll"><table v-if="billing?.items.length">
        <thead><tr><th>{{ t('Престой', 'Stay') }}</th><th>{{ t('Минути / количество', 'Minutes / quantity') }}</th><th>{{ t('Сметка / състояние', 'Account / status') }}</th><th>{{ t('Проверка', 'Verification') }}</th></tr></thead>
        <tbody><tr v-for="bill in billing.items" :key="bill.bill_id">
          <td>{{ bill.visit_id.slice(-8).toUpperCase() }}<small class="bill-marker">3mm {{ billUuid(bill.bill_id) }}</small></td>
          <td>{{ bill.rounded_minutes }} / {{ bill.quantity }} {{ unitLabel(bill.billing_unit) }}</td><td>{{ bill.remote_account_id || '—' }} · {{ billState(bill) }}</td>
          <td><form v-if="bill.state === 'ambiguous'" @submit.prevent="verifyBill(bill)" class="actions"><input v-model="billIds[bill.bill_id]" type="number" min="1" max="2147483647" required :aria-label="t('Номер на сметка', 'Account number')" /><button :disabled="busy">{{ t('Провери', 'Verify') }}</button></form></td>
        </tr></tbody>
      </table></div>
      <div class="actions"><button :disabled="busy || billOffset === 0" @click="billOffset -= 50; run(readBilling)">{{ t('Назад', 'Previous') }}</button><button :disabled="busy || !billing?.has_more" @click="billOffset += 50; run(readBilling)">{{ t('Напред', 'Next') }}</button></div>
      </details>
    </details>
    <details v-show="view !== 'setup'" :open="view === 'review'">
      <summary>{{ t('Родители в Barsy', 'Parents in Barsy') }}</summary>
      <div class="actions"><button :disabled="busy" @click="loadParents">{{ t('Обнови', 'Refresh') }}</button></div>
      <p>{{ liveDelivery === false ? t('Реалното изпращане е изключено. Родителите чакат на опашката. Включете го от Настройка → 2. Изпращане към Barsy.', 'Live delivery is off. Parents remain queued. Enable it in Setup → 2. Sending to Barsy.') : liveDelivery === null ? t('Проверете режима на изпращане в Настройка. Тук не е зареден.', 'Check the delivery mode in Setup. It has not loaded here.') : t('Одобрените родители се синхронизират автоматично. За чакащ родител обновете статуса; не въвеждайте произволно ID.', 'Approved parents sync automatically. Refresh a queued parent’s status; do not enter arbitrary IDs.') }}</p>
      <div class="scroll"><table>
        <thead><tr><th>{{ t('Родител', 'Parent') }}</th><th>{{ t('Състояние', 'Status') }}</th><th>{{ t('Barsy клиент', 'Barsy client') }}</th><th>{{ t('Действие', 'Action') }}</th></tr></thead>
        <tbody><tr v-for="parent in parents" :key="parent.guardian_id">
          <td>{{ parent.display_name }}</td><td>{{ stateLabel(parent.state) }}</td><td>{{ parent.remote_client_id || '—' }}</td>
          <td><details v-if="parent.state !== 'confirmed'">
            <summary>{{ t('Разрешаване на проблем', 'Resolve a problem') }}</summary>
            <p>{{ t('Само за съществуващ клиент: въведете ID на този родител в Barsy. Името и контактите трябва да съвпадат. Празно поле само поставя на опашката, без повторение на неясна заявка.', 'For an existing client: enter this parent’s Barsy client ID. Name and contacts must match. An empty field only queues the parent; it never repeats an uncertain request.') }}</p>
            <form class="actions" @submit.prevent="syncParent(parent)">
              <label>{{ t('ID на родителя в Barsy', 'Parent’s Barsy client ID') }}<input v-model="clientIds[parent.guardian_id]" type="number" min="1" max="2147483647" /></label>
              <button :disabled="busy">{{ clientIds[parent.guardian_id] ? t('Провери и свържи', 'Verify and link') : t('Постави на опашката', 'Queue for sync') }}</button>
            </form>
          </details></td>
        </tr></tbody>
      </table></div>
      <div class="actions"><button :disabled="busy || parentOffset === 0" @click="parentOffset -= 50; loadParents()">{{ t('Назад', 'Previous') }}</button><button :disabled="busy || !moreParents" @click="parentOffset += 50; loadParents()">{{ t('Напред', 'Next') }}</button></div>
    </details>
    <details v-show="view !== 'review'" open>
      <summary>{{ t('Артикули — отчетно време и разрешена консумация', 'Articles — billing time and allowed consumption') }}</summary>
      <p>{{ t('Изберете кои артикули от Barsy да виждат родителите. Това са разрешения, не поръчки. Цените остават в Barsy.', 'Choose which Barsy articles parents can select. These are permissions, not orders. Prices remain in Barsy.') }}</p>
      <form class="actions" @submit.prevent="articleOffset = 0; searchArticles()">
        <input v-model.trim="query" maxlength="120" :aria-label="t('Търси артикул', 'Search articles')" :placeholder="t('Име на артикул', 'Article name')" />
        <button :disabled="busy">{{ t('Прочети от Barsy', 'Load from Barsy') }}</button>
      </form>
      <label class="profile-target">{{ t('Настрой артикул за:', 'Configure article for:') }}
        <select v-model="selectedProfile" :disabled="busy" :aria-label="t('Настрой артикул за:', 'Configure article for:')">
          <option value="local_quantity">{{ t('Локално измерване — готово количество', 'Local measurement — fixed quantity') }}</option>
          <option value="barsy_timer">{{ t('Таймер в Barsy — подготовка', 'Barsy timer — draft') }}</option>
        </select>
      </label>
      <p>{{ t('Изборът тук настройва профила; не превключва активния режим.', 'This selection configures a profile; it does not switch the active mode.') }}</p>
      <div class="scroll"><table v-if="articles.length">
        <thead><tr><th>{{ t('Артикул', 'Article') }}</th><th>ID</th><th>{{ t('Показвай във формата', 'Show in form') }}</th><th>{{ t('Отчетно време', 'Billing time') }}</th></tr></thead>
        <tbody><tr v-for="article in articles" :key="article.article_id"><td>{{ article.label }}</td><td>{{ article.article_id }}</td><td><input type="checkbox" :checked="article.enabled" :disabled="busy" :aria-label="article.label" @change="setArticle(article.article_id, !article.enabled)" /></td><td><button :disabled="busy || !timing || (selectedProfile === 'local_quantity' && !timing.can_change_active_profile) || timing[selectedProfile].article_id === article.article_id" @click="setBillingArticle(article.article_id)">{{ timing?.[selectedProfile].article_id === article.article_id ? t('Избран', 'Selected') : t('Избери за време', 'Use for time') }}</button></td></tr></tbody>
      </table></div>
      <div class="actions"><button :disabled="busy || articleOffset === 0" @click="articleOffset -= 50; searchArticles()">{{ t('Назад', 'Previous') }}</button><button :disabled="busy || !moreArticles" @click="articleOffset += 50; searchArticles()">{{ t('Напред', 'Next') }}</button></div>
      <h3>{{ t('Показвани артикули', 'Enabled articles') }}</h3>
      <p v-if="!enabled.length">{{ t('Няма избрани артикули.', 'No articles selected.') }}</p>
      <div v-for="choice in enabled" :key="choice.code" class="actions"><span>{{ choice.label }}</span><button :disabled="busy" @click="setArticle(Number(choice.code.slice(6)), false)">{{ t('Премахни', 'Remove') }}</button></div>
    </details>
  </article>
</template>
<script setup lang="ts">
import { onMounted, ref } from 'vue'
import { createRequestId, invokeApplicationOperation } from './application-api'
import { useChildCenterLanguage } from './language'
const { t } = useChildCenterLanguage()
const props = withDefaults(defineProps<{ view?: 'setup' | 'review'; liveDelivery?: boolean | null }>(), { liveDelivery: null })
type Parent = { guardian_id: string; display_name: string; state: string; remote_client_id: number | null }
type Article = { article_id: number; label: string; enabled: boolean }
type BillingUnit = 'hours' | 'minutes'
type Bill = { bill_id: string; visit_id: string; rounded_minutes: number; quantity: string; billing_unit: BillingUnit; state: string; remote_account_id: number | null; error_code: string | null }
type Billing = { settings: { article_id: number | null; label: string | null; quantity_precision: number | null }; items: Bill[]; has_more: boolean }
type TimingMode = 'local_quantity' | 'barsy_timer'
type TimingProfile = { article_id: number | null; label: string | null; quantity_precision: number | null; billing_unit?: BillingUnit }
type TimingConfiguration = { active_mode: TimingMode; can_change_active_profile: boolean; local_quantity: TimingProfile; barsy_timer: TimingProfile & { available: false; unavailable_reason: 'stop_api_unverified'; time_interval: number | null }; local_rounding: 'ceil_total_minute' }
const timing = ref<TimingConfiguration | null>(null)
const selectedProfile = ref<TimingMode>('local_quantity')
const selectedUnit = ref<BillingUnit>('hours')
function unitLabel(unit?: BillingUnit) { return unit === 'minutes' ? t('мин', 'min') : t('ч', 'h') }
const billing = ref<Billing | null>(null), billOffset = ref(0)
const billIds = ref<Record<string, string>>({})
const parents = ref<Parent[]>([]), articles = ref<Article[]>([])
const enabled = ref<Array<{ code: string; label: string }>>([])
const clientIds = ref<Record<string, string>>({})
const query = ref(''), error = ref(''), notice = ref('')
const busy = ref(false), moreParents = ref(false), moreArticles = ref(false)
const parentOffset = ref(0), articleOffset = ref(0)
function invoke<T>(op: string, payload: Record<string, unknown>, mutation = false) {
  return invokeApplicationOperation<T>('administrator', op, localStorage.getItem('authToken') || '', payload, mutation ? createRequestId() : undefined)
}
async function run(action: () => Promise<void>) {
  busy.value = true; error.value = ''; notice.value = ''
  try { await action() } catch (reason) { error.value = reason instanceof Error ? reason.message : t('Операцията е неуспешна.', 'Operation failed.') }
  finally { busy.value = false }
}
async function readParents() {
  const result = await invoke<{ items: Parent[]; has_more: boolean }>('list_barsy_parent_links', { offset: parentOffset.value })
  parents.value = result.items; moreParents.value = result.has_more
}
async function readChoices() { enabled.value = (await invoke<{ items: typeof enabled.value }>('list_consumption_choices', {})).items }
async function readBilling() { billing.value = await invoke<Billing>('get_stay_billing', { offset: billOffset.value }) }
async function readTiming() { timing.value = await invoke<TimingConfiguration>('get_timing_configuration', {}); selectedUnit.value = timing.value.local_quantity.billing_unit || 'hours' }
async function activateMode(mode: TimingMode) {
  if (!window.confirm(t('Потвърждавате ли смяната на режима за новите престои?', 'Confirm the timing mode for new stays?'))) return
  await run(async () => { await invoke('activate_timing_mode', { mode }, true); await readTiming() })
}
async function setBillingArticle(articleId: number, mode = selectedProfile.value) {
  if (!window.confirm(mode === 'local_quantity' ? `${t('Потвърдете единицата и цената в Barsy; автоматичният таймер трябва да е изключен:', 'Confirm the unit and price in Barsy; automatic timing must be off:')} ${unitLabel(selectedUnit.value)}` : t('Запази времевия артикул само като настройка за бъдещия Barsy режим? Това не го активира.', 'Save this timed article for the future Barsy mode? This does not activate it.'))) return
  await run(async () => {
    const result = await invoke<{ status: string; error_code?: string }>('set_timing_profile', { mode, article_id: articleId, ...(mode === 'local_quantity' ? { billing_unit: selectedUnit.value } : {}) }, true)
    if (result.status === 'rejected') {
      const messages: Record<string, string> = {
        settings_locked: t('Приключете отворените престои и сметки, преди да смените настройката.', 'Finish open stays and accounts before changing this setting.'),
        article_unavailable: t('Артикулът не е достъпен за продажба в Barsy.', 'The article is not available for sale in Barsy.'),
        unit_unavailable: t('Единицата на артикула не е поддържана или не може да бъде проверена.', 'The article unit is unsupported or could not be verified.'),
        unit_mismatch: t('Единицата не съвпада. За артикул с единица Минута изберете Минути, а за Час — Часове.', 'Unit mismatch. Select Minutes for a Minute article, or Hours for an Hour article.'),
        precision_incompatible: t('За часове са нужни поне 3 десетични знака в Barsy. За минути може и цяло количество.', 'Hours require at least 3 decimal places in Barsy. Minutes may use whole quantities.'),
      }
      throw new Error(messages[result.error_code || ''] || t('Настройката не е запазена.', 'The setting was not saved.'))
    }
    await readBilling()
    await readTiming()
    notice.value = t('Профилът е запазен. Активният режим не е променен.', 'Profile saved. The active mode has not changed.')
  })
}
function billUuid(value: string) {
  const h = value.slice(5)
  return `${h.slice(0, 8)}-${h.slice(8, 12)}-${h.slice(12, 16)}-${h.slice(16, 20)}-${h.slice(20)}`
}
function billState(bill: Bill) {
  if (bill.error_code === 'zero_duration') return t('Без отчетно време', 'No billable time')
  if (bill.state === 'confirmed') return t('Потвърдена', 'Confirmed')
  if (bill.state === 'mock_confirmed') return t('Тест — не е изпратена', 'Test — not sent')
  if (bill.state === 'prepared') return t('На опашката', 'Queued')
  if (bill.state === 'retryable') return bill.error_code === 'parent_sync_required' ? t('Чака родителя', 'Waiting for parent sync') : t('Проверете артикула и касата', 'Check article and POS')
  return t('Нужна е проверка', 'Needs verification')
}
async function verifyBill(bill: Bill) {
  await run(async () => {
    await invoke('reconcile_stay_bill', { bill_id: bill.bill_id, account_id: Number(billIds.value[bill.bill_id]) }, true)
    await readBilling()
  })
}
async function loadParents() { await run(readParents) }
async function syncParent(parent: Parent) {
  await run(async () => {
    const value = clientIds.value[parent.guardian_id]
    await invoke('sync_barsy_parent', { guardian_id: parent.guardian_id, client_id: value ? Number(value) : null }, true)
    await readParents()
    notice.value = t('Заявката е записана. Обновете след няколко секунди.', 'Request saved. Refresh in a few seconds.')
  })
}
async function searchArticles() {
  await run(async () => {
    const result = await invoke<{ items: Article[]; has_more: boolean }>('discover_consumption_articles', { query: query.value, offset: articleOffset.value })
    articles.value = result.items; moreArticles.value = result.has_more
  })
}
async function setArticle(articleId: number, value: boolean) {
  await run(async () => {
    await invoke('set_consumption_article', { article_id: articleId, enabled: value }, true)
    articles.value = articles.value.map(a => a.article_id === articleId ? { ...a, enabled: value } : a)
    await readChoices()
    notice.value = t('Запазено. Презаредете отворените регистрационни форми.', 'Saved. Reload any open registration forms.')
  })
}
function stateLabel(state: string) {
  if (state === 'confirmed') return t('Свързан', 'Linked')
  if (state === 'prepared') return props.liveDelivery === false ? t('Чака включване на изпращането', 'Waiting for live delivery') : t('На опашката за синхронизация', 'Queued for sync')
  if (state === 'not_queued') return t('Не е изпратен', 'Not queued')
  return t('Изисква проверка', 'Needs review')
}
onMounted(() => run(async () => { await readTiming(); await readBilling(); await readParents(); await readChoices() }))
</script>
<style scoped>
.directory { min-width: 0; max-width: 100%; box-sizing: border-box; color: var(--text-primary); background: var(--card-bg); }
.timing-profiles { margin: 1rem 0; }
.profile-grid { display: grid; grid-template-columns: repeat(auto-fit, minmax(min(100%, 19rem), 1fr)); gap: 1rem; align-items: start; }
.profile { display: flex; flex-direction: column; gap: .65rem; min-width: 0; padding: 1rem; border: 1px solid var(--card-border); border-radius: .6rem; }
.profile h4, .profile p { margin: 0; }
.profile strong { overflow-wrap: anywhere; }
.active-profile { align-self: flex-start; padding: .3rem .6rem; border: 1px solid var(--card-border); border-radius: .4rem; color: var(--success-color); font-weight: 600; }
.profile button { margin-top: auto; align-self: flex-start; }
.capability-note { border-left: .2rem solid var(--primary-color); padding-left: .7rem; }
.profile-target { display: grid; gap: .4rem; margin: .75rem 0; }
.profile-target select { min-width: 0; width: 100%; box-sizing: border-box; padding: .6rem; font: inherit; color: var(--text-primary); background: var(--input-bg); border: 1px solid var(--input-border); border-radius: .4rem; }
.actions label { display: grid; min-width: 0; gap: .4rem; }
.actions input { box-sizing: border-box; max-width: 100%; }
p { color: var(--text-secondary); line-height: 1.5; }
details { border-top: 1px solid var(--card-border); padding: 1rem 0; }
summary { cursor: pointer; font-weight: 600; padding: .4rem 0; }
.actions { display: flex; flex-wrap: wrap; align-items: center; gap: .6rem; margin: .65rem 0; }
input:not([type=checkbox]) { min-width: 8rem; width: min(20rem, 100%); padding: .55rem; color: var(--text-primary); background: var(--input-bg); border: 1px solid var(--input-border); border-radius: .4rem; }
input[type=checkbox] { accent-color: var(--primary-color); }
button { font: inherit; padding: .5rem .7rem; border-radius: .4rem; border: 1px solid var(--card-border); background: var(--card-bg); color: var(--text-primary); cursor: pointer; }
button:disabled { opacity: .5; cursor: default; }
.scroll { overflow-x: auto; }
table { width: 100%; min-width: 38rem; border-collapse: collapse; }
th, td { text-align: left; padding: .65rem; border-bottom: 1px solid var(--card-border); overflow-wrap: anywhere; }
th, td:nth-child(2), td:nth-child(3) { white-space: nowrap; }
.error { color: var(--error-color); }
.bill-marker { display: block; max-width: 18rem; overflow-wrap: anywhere; color: var(--text-secondary); }
</style>
