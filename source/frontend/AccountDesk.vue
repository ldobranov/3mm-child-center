<template>
  <section class="account-desk" aria-labelledby="accounts-title">
    <header><div><h2 id="accounts-title">{{ cashier ? t('Сметки за плащане', 'Accounts for checkout') : t('Престои и сметки', 'Stays and accounts') }}</h2><p>{{ cashier ? t('Изберете сметка. Сумата и начините за плащане се взимат от Barsy.', 'Select an account. Amounts and payment methods come from Barsy.') : t('Изберете дете за консумация, приключване на играта или плащане.', 'Select a child to add consumption, finish playing or take payment.') }}</p></div><button :disabled="busy" @click="refresh">{{ t('Обнови сметките', 'Refresh accounts') }}</button></header>
    <p v-if="error" role="alert" class="error">{{ error }}</p>
    <p v-if="notice" role="status">{{ notice }}</p>
    <button v-if="hasPendingAttempt && canRecover" :disabled="busy" @click="recoverPending">{{ t('Възстанови резултата от предишното действие', 'Recover the previous action result') }}</button>
    <p v-if="hasPendingAttempt && !canRecover" role="alert">{{ t('Има непотвърдено действие от предишна сесия или без текущо разрешение. Не го повтаряйте; нужна е проверка от отговорния служител.', 'An unconfirmed action belongs to a previous session or requires missing permissions. Do not repeat it; the responsible staff member must review it.') }}</p>
    <p v-if="!accounts.length && !busy">{{ t('Няма отворени сметки по новия модел.', 'No open accounts in the new workflow.') }}</p>
    <div class="desk-filters">
      <label>{{ t('Търсене в тази страница', 'Search this page') }}<input v-model="search" :placeholder="t('Дете или маса', 'Child or table')" /></label>
      <label>{{ t('Показвай', 'Show') }}<select v-model="filter"><option value="all">{{ t('Всички', 'All') }}</option><option value="open">{{ t('Игра / пауза', 'Playing / paused') }}</option><option value="closed">{{ t('За приключване на сметка', 'Awaiting checkout') }}</option></select></label>
    </div>
    <div class="desk-workspace">
    <div>
    <div class="account-list">
      <button v-for="account in visibleAccounts" :key="account.visit_id" :aria-pressed="selected === account.visit_id" :class="{ selected: selected === account.visit_id }" :disabled="busy" @click="select(account.visit_id)">
        <strong>{{ account.child_name }}</strong><span>{{ account.table_name }} · {{ account.account_id ? '#' + account.account_id : t('Чака сметка', 'Opening account') }}</span>
        <span class="stay-phase">{{ phaseLabel(account) }} <strong v-if="stay(account.visit_id)">{{ stay(account.visit_id)?.duration }}</strong></span>
        <small v-if="!account.live">{{ t('Тест — без изпращане', 'Test — no delivery') }}</small>
        <small v-if="account.error_code">{{ t('Нужна е проверка', 'Needs review') }}</small>
      </button>
    </div>
    <p v-if="accounts.length && !visibleAccounts.length">{{ t('Няма съвпадения на тази страница.', 'No matches on this page.') }}</p>
    <footer v-if="offset || more"><button :disabled="busy || offset === 0" @click="offset -= 50; refresh()">{{ t('Назад', 'Previous') }}</button><button :disabled="busy || !more" @click="offset += 50; refresh()">{{ t('Напред', 'Next') }}</button></footer>
    </div>
    <section v-if="current && detail" class="account-detail">
      <h3>{{ current.child_name }} · {{ current.table_name }} · {{ current.account_id ? '#' + current.account_id : t('Чака сметка', 'Opening account') }}</h3>
      <div class="stay-summary"><strong>{{ phaseLabel(current) }}</strong><strong v-if="stay(current.visit_id)" class="duration">{{ stay(current.visit_id)?.duration }}</strong></div>
      <p v-if="remoteClosed" role="status" class="external-closure error">{{ t('Сметката е затворена в Barsy. Това не потвърждава, че времето и консумацията са начислени и платени. Проверете редовете и плащането в Barsy; не изпращайте повторно. След приключване на престоя използвайте проверката по-долу.', 'The account is closed in Barsy. This does not confirm that playing time and consumption were charged and paid. Check the rows and payment in Barsy; do not send again. After finishing the stay, use the verification below.') }}</p>
      <p v-else-if="!current.admitted" role="status" :class="{ error: current.error_code }">{{ admissionMessage(current) }}</p>
      <p v-else-if="current.visit_state !== 'closed'">{{ t('Изходът е пауза, не край на играта. Приключете само когато детето няма да влиза отново.', 'Exit is a pause, not the end of playing. Finish only when the child will not enter again.') }}</p>
      <p v-if="current.remote_observation?.error_code === 'barsy_unavailable'" role="status">{{ t('Последната проверка в Barsy е неуспешна. Показаните локални данни не потвърждават дали сметката още е отворена.', 'The latest Barsy check failed. Local data does not confirm whether the account is still open.') }}</p>
      <p v-if="current.pending" role="status">{{ t('Има заявка в обработка или с неясен резултат. Не я дублирайте.', 'A request is pending or has an unknown outcome. Do not duplicate it.') }}</p>
      <p v-if="hasFailedArticles && !remoteClosed" role="status">{{ t('Преди плащане трябва да бъдат изпратени времето и консумацията. Прегледайте неизпратените заявки по-долу и ги повторете поотделно.', 'Playing time and consumption must be sent before payment. Review the unsent requests below and retry them individually.') }}</p>
      <div class="checkout-actions">
        <slot v-if="current.visit_state !== 'closed' && can('close_visit')" name="finish" :account="current" :locked="busy || hasPendingAttempt" />
        <button v-if="current.visit_state === 'closed' && current.live && !remoteClosed && !quote && can('preview_account_payment') && can('pay_account')" class="primary-action" :disabled="busy || hasPendingAttempt || current.pending || hasFailedArticles || !current.admitted" @click="previewPayment">{{ t('Към плащане', 'Proceed to payment') }}</button>
        <button v-if="current.visit_state === 'closed' && !current.live && can('close_test_account')" :disabled="busy" @click="closeTest">{{ t('Освободи тестовата маса', 'Release test table') }}</button>
      </div>
      <template v-if="!quote">
      <template v-if="can('add_account_consumption')">
      <h4 class="consumption-heading">{{ t('Консумация', 'Consumption') }}</h4>
      <p><strong>{{ t('Разрешено за детето:', 'Allowed for the child:') }}</strong> {{ detail.choices.filter(c => c.allowed_for_child).map(c => c.label).join(', ') || t('Няма разрешени артикули', 'No articles allowed') }}</p>
      <div class="quick-consumption" :aria-label="t('Бърза консумация за детето', 'Quick child consumption')"><button v-for="choice in detail.choices.filter(c => c.allowed_for_child)" :key="choice.article_id" :disabled="busy || hasPendingAttempt || remoteClosed || !current.admitted || current.pending" @click="quickConsumption(choice)">+1 · {{ choice.label }}</button></div>
      <form class="consumption" @submit.prevent="addConsumption">
        <label>{{ t('За кого', 'Consumer') }}<select v-model="consumer" :disabled="busy" @change="articleId = ''"><option value="child">{{ t('Дете', 'Child') }}</option><option value="guardian">{{ t('Родител', 'Parent') }}</option></select></label>
        <label>{{ t('Артикул', 'Article') }}<select v-model="articleId" :disabled="busy" required><option disabled value="">{{ t('Избери артикул', 'Select article') }}</option><option v-for="choice in choices" :key="choice.article_id" :value="String(choice.article_id)">{{ choice.label }}</option></select></label>
        <label>{{ t('Количество', 'Quantity') }}<input v-model="quantity" type="number" min="0.001" max="100" step="0.001" required :disabled="busy" /></label>
        <button :disabled="busy || hasPendingAttempt || remoteClosed || !current.admitted || current.pending || !articleId">{{ t('Добави към сметката', 'Add to account') }}</button>
      </form>
      </template>
      <details class="commands" v-if="detail.commands.length" :open="detail.commands.some(c => ['prepared', 'ambiguous', 'failed'].includes(c.state))">
        <summary>{{ t('Изпращания по сметката', 'Account requests') }} · {{ detail.commands.length }}</summary>
        <article v-for="command in detail.commands" :key="command.command_id">
          <span>{{ command.kind === 'payment' ? t('Плащане', 'Payment') : command.kind === 'time' ? t('Време', 'Playing time') : t('Консумация', 'Consumption') }}<template v-if="command.article_id"> · {{ articleLabel(command.article_id) }} × {{ command.quantity }}<template v-if="command.kind === 'time'"> {{ command.billing_unit === 'minutes' ? t('мин', 'min') : t('ч', 'h') }}</template></template></span>
          <strong>{{ status(command.state) }}</strong>
          <p v-if="command.state === 'ambiguous'" class="error">{{ ambiguousMessage(command) }}</p>
          <p v-if="command.state === 'failed'">{{ command.kind === 'payment' ? t('Не е изпратено плащане. Обновете сумата и потвърдете отново.', 'No payment was sent. Refresh the amount and confirm again.') : t('Не е изпратено. ', 'Not sent. ') + (barsyProblem(command.error_code) || t('Проверете артикула, сметката и връзката.', 'Check the article, account and connection.')) }}</p>
          <button v-if="can('reconcile_account_command') && command.state === 'ambiguous' && command.kind !== 'payment' && !remoteClosed" :disabled="busy" @click="reconcileCommand(command.command_id)">{{ t('Провери редовете в Barsy', 'Check rows in Barsy') }}</button>
          <button v-if="can('retry_account_command') && command.state === 'failed' && command.kind !== 'payment'" :disabled="busy || remoteClosed || current.pending" @click="retry(command.command_id)">{{ t('Повтори неизпратената заявка', 'Retry unsent request') }}</button>
        </article>
      </details>
      <details class="recovery-actions" :open="remoteClosed"><summary>{{ t('Разрешаване на проблем', 'Resolve a problem') }}</summary><div class="checkout-actions">
        <button v-if="can('cancel_pending_admission') && !current.admitted && !current.account_id" :disabled="busy" @click="cancelAdmission">{{ t('Откажи неизпратен прием', 'Cancel unsent admission') }}</button>
        <button v-if="can('verify_account_closure') && current.live && current.visit_state === 'closed'" :disabled="busy" @click="verifyClosure">{{ t('Провери вече платена сметка в Barsy', 'Verify an account already paid in Barsy') }}</button>
        <button v-if="remoteClosed && can('release_incomplete_closed_account') && current.visit_state === 'closed'" :disabled="busy" @click="releaseIncomplete">{{ t('Освободи непълната затворена сметка', 'Release incomplete closed account') }}</button>
      </div></details>
      </template>
      <form v-if="quote && !remoteClosed && can('pay_account')" class="payment" @submit.prevent="pay">
        <h4>{{ t('Потвърди плащане и фискално приключване', 'Confirm payment and fiscal closure') }}</h4>
        <p><strong>{{ t('Сметка', 'Account') }} #{{ quote.account_id }} · {{ quote.amount }} {{ quote.currency_code }}</strong></p>
        <p>{{ t('Сумата е от Barsy. Потвърждението е валидно 2 минути. Поддържат се фискални плащания в брой и карта без външен платежен провайдър; останалите се приключват в Barsy.', 'The amount comes from Barsy. The preview expires in 2 minutes. Fiscal cash and card methods without an external payment provider are supported; complete other payment types in Barsy.') }}</p>
        <label>{{ t('Начин на плащане', 'Payment method') }}<select v-model="methodId" required :disabled="busy"><option disabled value="">{{ t('Избери', 'Select') }}</option><option v-for="method in quote.methods" :key="method.paymethod_id" :value="String(method.paymethod_id)">{{ method.label }}</option></select></label>
        <div class="checkout-actions"><button :disabled="busy || !methodId">{{ t('Плати и закрий сметката', 'Pay and close account') }}</button><button type="button" :disabled="busy" @click="quote = null">{{ t('Отказ', 'Cancel') }}</button></div>
      </form>
    </section>
    <p v-else class="selection-hint">{{ t('Изберете дете от списъка. Всички действия по неговата сметка ще се покажат тук.', 'Select a child from the list. All actions for their account will appear here.') }}</p>
    </div>
  </section>
</template>

<script setup lang="ts">
import { computed, inject, onMounted, onUnmounted, ref, watch } from 'vue'
import { createRequestId, invokeApplicationOperation } from './application-api'
import { useChildCenterLanguage } from './language'
const { t } = useChildCenterLanguage()
const permitted = inject<(operation: string) => boolean>('childCenterCan', () => false)
const checkoutOperations = new Set(['list_checkout_accounts', 'get_checkout_account', 'preview_account_payment', 'pay_account', 'verify_account_closure'])
const can = (operation: string) => permitted(operation) && (!props.cashier || checkoutOperations.has(operation))
const staffUserId = inject<() => number | undefined>('childCenterUserId', () => undefined)
const props = withDefaults(defineProps<{ cashier?: boolean; refreshToken?: number; initialFilter?: 'open' | 'closed'; stays?: Array<{ visit_id: string; phase: string; duration: string }> }>(), { cashier: false, stays: () => [] })
const emit = defineEmits<{ 'accounts-loaded': [ids: string[]] }>()
const search = ref(''), filter = ref(props.initialFilter || 'all')
const visibleAccounts = computed(() => accounts.value.filter(a => (filter.value === 'all' || (filter.value === 'closed' ? a.visit_state === 'closed' : a.visit_state !== 'closed')) && `${a.child_name} ${a.table_name}`.toLocaleLowerCase().includes(search.value.trim().toLocaleLowerCase())))
function stay(id: string) { return props.stays.find(s => s.visit_id === id) }
function phaseLabel(account: Account) {
  if (account.remote_observation?.status === 'closed') return t('Затворена в Barsy — нужна проверка', 'Closed in Barsy — review required')
  if (!account.admitted) return account.error_code ? t('Приемът е блокиран', 'Admission blocked') : t('Чака прием', 'Awaiting admission')
  if (account.visit_state === 'closed') return account.pending ? t('Изчаква изпращане / проверка', 'Awaiting delivery / review') : t('За приключване на сметка', 'Awaiting checkout')
  if (stay(account.visit_id)?.phase === 'paused') return t('На пауза', 'Paused')
  if (stay(account.visit_id)?.phase === 'inside') return t('Играе', 'Playing')
  return t('Отворен престой', 'Open stay')
}
type Account = { visit_id: string; child_name: string; table_name: string; account_id: number | null; admitted: boolean; live: boolean; visit_state: string; pending: boolean; error_code: string | null; remote_observation?: { status: 'unknown' | 'open' | 'closed'; checked_at: string | null; error_code: string | null } }
type Choice = { article_id: number; label: string; allowed_for_child: boolean }
type Command = { command_id: string; kind: string; state: string; article_id: number | null; quantity: string | null; billing_unit?: 'hours' | 'minutes' | null; error_code: string | null }
type Quote = { quote_id: string; account_id: number; amount: string; currency_id: number; currency_code: string; expires_at: string; methods: Array<{ paymethod_id: number; label: string; type_id: number }> }
const accounts = ref<Account[]>([]), selected = ref(''), detail = ref<{ choices: Choice[]; commands: Command[] } | null>(null)
const busy = ref(false), error = ref(''), notice = ref(''), offset = ref(0), more = ref(false)
const consumer = ref<'child' | 'guardian'>('child'), articleId = ref(''), quantity = ref('1')
const quote = ref<Quote | null>(null), methodId = ref('')
const current = computed(() => accounts.value.find(a => a.visit_id === selected.value))
const remoteClosed = computed(() => current.value?.remote_observation?.status === 'closed')
const hasFailedArticles = computed(() => detail.value?.commands.some(c => c.kind !== 'payment' && c.state === 'failed') || false)
const choices = computed(() => detail.value?.choices.filter(c => consumer.value === 'guardian' || c.allowed_for_child) || [])
let timer: number | undefined
let disposed = false, lastPoll = 0
const attemptKey = 'childCenterCommercialAttemptV1'
let pendingAttempt: { signature: string; key: string; userId?: number } | null = null
try { const stored = JSON.parse(sessionStorage.getItem(attemptKey) || 'null'); if (typeof stored?.signature === 'string' && typeof stored?.key === 'string') pendingAttempt = stored } catch { /* Storage may be unavailable. */ }
const hasPendingAttempt = ref(Boolean(pendingAttempt))
const canRecover = computed(() => {
  if (!hasPendingAttempt.value || pendingAttempt?.userId !== staffUserId()) return false
  try { return can(JSON.parse(pendingAttempt!.signature)[0]) } catch { return false }
})
function clearAttempt() {
  pendingAttempt = null; hasPendingAttempt.value = false
  try { sessionStorage.removeItem(attemptKey) } catch { /* No persistent identity available. */ }
}
function invoke<T>(op: string, payload: Record<string, unknown>, key?: string) {
  if (!can(op)) return Promise.reject(new Error(t('Нямате достъп до това действие.', 'You do not have access to this action.')))
  const audience = op === 'release_incomplete_closed_account' ? 'administrator' : 'operator'
  return invokeApplicationOperation<T>(audience, op, localStorage.getItem('authToken') || '', payload, key)
}
async function command<T>(op: string, payload: Record<string, unknown>): Promise<T> {
  if (!can(op)) throw new Error(t('Нямате достъп до това действие.', 'You do not have access to this action.'))
  if (pendingAttempt && pendingAttempt.userId !== staffUserId()) throw new Error(t('Непотвърденото действие изисква проверка от отговорния служител.', 'The unconfirmed action requires review by the responsible staff member.'))
  const signature = JSON.stringify([op, payload])
  if (pendingAttempt && pendingAttempt.signature !== signature) throw new Error(t('Има непотвърден отговор за предишното действие. Повторете същото действие със същите полета, за да получите резултата му.', 'A previous action has an unconfirmed response. Retry that same action with the same fields to retrieve its result.'))
  const recovering = Boolean(pendingAttempt)
  pendingAttempt ||= { signature, key: createRequestId(), userId: staffUserId() }
  hasPendingAttempt.value = true
  try { sessionStorage.setItem(attemptKey, JSON.stringify(pendingAttempt)) } catch { /* Keep the in-memory identity. */ }
  try {
    const result = await invoke<T>(op, payload, pendingAttempt.key)
    clearAttempt()
    return result
  } catch (reason) {
    // A rejected recovery says nothing about whether the original request was
    // accepted. Preserve that identity even if access/version has since changed.
    if (!recovering && [401, 403, 404, 409, 422].includes(Number((reason as { httpStatus?: number })?.httpStatus))) clearAttempt()
    throw reason
  }
}
async function recoverPending() {
  if (!pendingAttempt) return
  await run(async () => {
    const [op, payload] = JSON.parse(pendingAttempt!.signature)
    if (!['add_account_consumption', 'preview_account_payment', 'pay_account', 'retry_account_command', 'close_test_account', 'verify_account_closure', 'cancel_pending_admission', 'reconcile_account_command', 'release_incomplete_closed_account'].includes(op)) throw new Error(t('Невалидно запазено действие.', 'Invalid stored action.'))
    const result = await command<Quote>(op, payload)
    if (op === 'preview_account_payment') { selected.value = payload.visit_id; quote.value = result; methodId.value = '' }
    else quote.value = null
    await read()
    notice.value = t('Предишният резултат е възстановен със същия идентификатор.', 'The previous result was recovered using the same request identity.')
  })
}
async function read() {
  const token = localStorage.getItem('authToken') || ''
  const listOperation = props.cashier ? 'list_checkout_accounts' : 'list_operator_accounts'
  const valid = () => !disposed && token === (localStorage.getItem('authToken') || '') && can(listOperation)
  const result = await invoke<{ items: Account[]; has_more: boolean }>(props.cashier ? 'list_checkout_accounts' : 'list_operator_accounts', { offset: offset.value })
  if (!valid()) return
  const previous = current.value
  accounts.value = result.items; more.value = result.has_more
  if (remoteClosed.value) { quote.value = null; methodId.value = '' }
  lastPoll = Date.now()
  emit('accounts-loaded', result.items.map(a => a.visit_id))
  if (selected.value && !current.value) {
    selected.value = ''; detail.value = null; quote.value = null
    if (previous?.pending) notice.value = t('Сметката вече не е в списъка с отворени сметки. Проверете приключването в историята.', 'The account is no longer in the open list. Check its closure in history.')
  }
  if (current.value) {
    const visit = selected.value
    const result = await invoke<{ choices: Choice[]; commands: Command[] }>(props.cashier ? 'get_checkout_account' : 'get_operator_account', { visit_id: visit })
    if (valid() && selected.value === visit) detail.value = result
  }
}
async function run(action: () => Promise<void>) {
  if (busy.value) return
  busy.value = true; error.value = ''; notice.value = ''
  try { await action() } catch (reason) { error.value = reason instanceof Error ? reason.message : t('Операцията е неуспешна.', 'Operation failed.') }
  finally { busy.value = false }
}
async function refresh() { await run(read) }
async function select(visit: string) { selected.value = visit; detail.value = null; quote.value = null; articleId.value = ''; await refresh() }
async function addConsumption() {
  if (!current.value || busy.value || hasPendingAttempt.value || remoteClosed.value || current.value.pending || !current.value.admitted) return
  if (!window.confirm(`${current.value.child_name} · ${articleLabel(Number(articleId.value))} × ${quantity.value}\n${consumer.value === 'child' ? t('За детето', 'For the child') : t('За родителя', 'For the parent')}\n${t('Добавяне към тази сметка?', 'Add to this account?')}`)) return
  await run(async () => { await command('add_account_consumption', { visit_id: selected.value, article_id: Number(articleId.value), quantity: String(quantity.value), consumer: consumer.value }); quote.value = null; await read(); notice.value = t('Заявката е записана. Следете статуса ѝ по-долу.', 'Request recorded. Check its status below.') })
}
async function quickConsumption(choice: Choice) {
  if (!choice.allowed_for_child || busy.value || hasPendingAttempt.value || current.value?.pending) return
  consumer.value = 'child'; articleId.value = String(choice.article_id); quantity.value = '1'
  await addConsumption()
}
async function retry(commandId: string) { if (remoteClosed.value) return; await run(async () => { await command('retry_account_command', { command_id: commandId }); await read() }) }
async function reconcileCommand(commandId: string) {
  await run(async () => {
    const result = await command<{ status: string }>('reconcile_account_command', { command_id: commandId })
    await read()
    notice.value = result.status === 'retry_available'
      ? t('Barsy няма този ред. След като поправите артикула и цената в Barsy, използвайте „Повтори неизпратената заявка“.', 'Barsy does not contain this row. After correcting the article and price in Barsy, use “Retry unsent request”.')
      : result.status === 'confirmed'
        ? t('Редът е намерен и потвърден от Barsy.', 'The row was found and confirmed in Barsy.')
        : t('Редовете не дават еднозначен резултат. Нужна е администраторска проверка.', 'The rows are not conclusive. Administrator review is required.')
  })
}
async function previewPayment() { if (remoteClosed.value || hasFailedArticles.value) return; await run(async () => { quote.value = await command<Quote>('preview_account_payment', { visit_id: selected.value }); methodId.value = '' }) }
async function pay() {
  if (busy.value || remoteClosed.value || !quote.value || !methodId.value) return
  const method = quote.value.methods.find(m => m.paymethod_id === Number(methodId.value))
  if (!method || !window.confirm(t(`Получено плащане ${quote.value.amount} ${quote.value.currency_code} чрез ${method.label} (при карта — потвърдено от терминала)?\nФискално приключване на сметка #${quote.value.account_id}?`, `Payment of ${quote.value.amount} ${quote.value.currency_code} received via ${method.label} (card confirmed by terminal)?\nFiscal closure of account #${quote.value.account_id}?`))) return
  await run(async () => { await command('pay_account', { quote_id: quote.value!.quote_id, paymethod_id: Number(methodId.value), confirmed: true }); quote.value = null; await read(); notice.value = t('Плащането е заявено. Успех има само след потвърждение от Barsy; не го дублирайте.', 'Payment requested. It succeeds only after Barsy confirmation; do not duplicate it.') })
}
async function closeTest() { await run(async () => { await command('close_test_account', { visit_id: selected.value }); await read() }) }
async function cancelAdmission() {
  if (!window.confirm(t('Отказ на приема само ако заявката още не е изпратена към Barsy?', 'Cancel admission only if its request has not been sent to Barsy?'))) return
  await run(async () => { await command('cancel_pending_admission', { visit_id: selected.value }); await read() })
}
async function verifyClosure() {
  if (!window.confirm(t('Проверихте ли в Barsy цялата сметка, отчетеното време, плащането и издадената фискална бележка? Това действие само проверява и освобождава масата; не изпраща ново плащане.', 'Have you checked the full account, playing time, payment and issued fiscal receipt in Barsy? This only verifies and releases the table; it does not send another payment.'))) return
  await run(async () => { await command('verify_account_closure', { visit_id: selected.value, reviewed: true }); await read() })
}
async function releaseIncomplete() {
  if (!current.value || !window.confirm(t('Barsy сметката е затворена, но липсват очаквани начисления или плащане. Да се освободи ли масата, като непълното приключване остане записано за одит?', 'The Barsy account is closed but expected charges or payment are missing. Release the table while retaining the incomplete closure for audit?'))) return
  await run(async () => {
    await command('release_incomplete_closed_account', { visit_id: selected.value, accepted_missing_charges: true })
    quote.value = null
    await read()
    notice.value = t('Масата е освободена. Сметката не е отбелязана като напълно начислена или платена.', 'The table was released. The account was not marked as fully charged or paid.')
  })
}
function articleLabel(id: number) { return detail.value?.choices.find(c => c.article_id === id)?.label || `ID ${id}` }
function barsyProblem(code: string | null) {
  const messages: Record<string, string> = {
    barsy_article_price_missing: t('Записан е проблем с продажната цена. В 0.7.2–0.7.3 това можеше да е грешна предварителна проверка, без изпращане към Barsy. Ако цената е зададена, повторете неизпратената заявка по-долу.', 'A sale price issue was recorded. In 0.7.2–0.7.3 this could be an incorrect preflight check, without sending to Barsy. If the price is set, retry the unsent request below.'),
    barsy_place_timing_enabled: t('Типът на мястото в Barsy е с включено автоматично отчитане. Администраторът трябва да го изключи за локално измерване.', 'The Barsy place type has automatic timing enabled. An administrator must disable it for local measurement.'),
    barsy_place_timing_unknown: t('Не може да се потвърди дали мястото в Barsy отчита време автоматично. Администраторът трябва да провери типа на мястото и връзката с Barsy.', 'Automatic timing for the Barsy place could not be verified. An administrator must check the place type and Barsy connection.'),
    barsy_order_timer_active: t('Стара проверка по ненадежден флаг е блокирала потвърждението. Използвайте „Провери редовете в Barsy“, без повторно добавяне на артикула.', 'An obsolete check of an unreliable flag blocked confirmation. Use “Check rows in Barsy” without adding the article again.'),
    barsy_orders_invalid: t('Barsy не върна валиден списък с редовете на сметката. Обновете проверката; не изпращайте повторно.', 'Barsy did not return a valid account row list. Check again; do not send again.'),
    account_requires_review: t('Сметката не е преминала проверката за безопасно отчитане. Проверете сметката и настройките в Barsy; не създавайте втора сметка.', 'The account has not passed the billing safety check. Check the account and settings in Barsy; do not create a second account.'),
    operator_verified_absent_in_barsy: t('Проверката потвърди, че редът липсва в Barsy. Поправете артикула или цената и повторете заявката ръчно.', 'The check confirmed that the row is absent in Barsy. Correct the article or price and retry the request manually.'),
  }
  return code ? messages[code] || '' : ''
}
function admissionMessage(account: Account) {
  if (account.error_code) return (barsyProblem(account.error_code) || t('Приемът изисква проверка на сметката и връзката с Barsy.', 'Admission requires a check of the account and Barsy connection.')) + ' ' + t('Не допускайте детето, докато проверката не мине.', 'Do not admit the child until the check passes.')
  return account.account_id
    ? t('Сметката е отворена. Изчаква се автоматична проверка от Barsy преди допускане на детето.', 'The account is open. An automatic Barsy check is pending before the child can be admitted.')
    : t('Изчаква се Barsy да потвърди отварянето на сметката. Не допускайте детето още.', 'Waiting for Barsy to confirm account opening. Do not admit the child yet.')
}
function ambiguousMessage(command: Command) {
  // Only a bounded numeric status is displayed; never show a raw remote error.
  const httpStatus = /^barsy_http_([1-5]\d{2})$/.exec(command.error_code || '')?.[1]
  const cause = httpStatus ? t(`Barsy върна HTTP ${httpStatus}. `, `Barsy returned HTTP ${httpStatus}. `) : (barsyProblem(command.error_code) ? barsyProblem(command.error_code) + ' ' : '')
  return cause + (command.kind === 'payment'
    ? t('Резултатът от плащането не е потвърден. Проверете сметката, плащането и фискалното устройство в Barsy. Няма автоматично повторение; не плащайте повторно.', 'The payment outcome is unconfirmed. Check the account, payment and fiscal device in Barsy. There is no automatic retry; do not pay again.')
    : t('Добавянето на артикула не е потвърдено. Проверете редовете на сметката в Barsy. Няма автоматично повторение; не добавяйте артикула повторно преди проверка.', 'Adding the article is unconfirmed. Check the account rows in Barsy. There is no automatic retry; do not add the article again before review.'))
}
function status(value: string) {
  if (value === 'confirmed') return t('Потвърдено от Barsy', 'Confirmed by Barsy')
  if (value === 'prepared') return t('На опашката', 'Queued')
  if (value === 'mock_confirmed') return t('Само тест', 'Test only')
  if (value === 'failed') return t('Не е изпратено', 'Not sent')
  return t('Неясен резултат — проверка в Barsy', 'Unknown outcome — check Barsy')
}
async function poll() {
  const fast = accounts.value.some(a => a.pending || !a.admitted)
  if (disposed || document.hidden || busy.value || Date.now() - lastPoll < (fast ? 2000 : 10000)) return
  // Read-only polling preserves mutation notices and never repeats a command.
  busy.value = true
  lastPoll = Date.now()
  try { await read() } catch { if (!disposed) error.value = t('Неуспешно обновяване на статуса. Не повтаряйте плащането.', 'Status refresh failed. Do not repeat payment.') }
  finally { busy.value = false }
}
onMounted(() => { refresh(); timer = window.setInterval(() => { void poll() }, 1000) })
watch(() => props.refreshToken, () => refresh())
watch(() => props.initialFilter, value => { filter.value = value || 'all' })
onUnmounted(() => { disposed = true; if (timer !== undefined) window.clearInterval(timer) })
</script>

<style scoped>
.account-desk { margin-top: 1rem; padding: 1rem; border: 1px solid var(--card-border); border-radius: .8rem; color: var(--text-primary); background: var(--card-bg); }
header, footer, .checkout-actions { display: flex; flex-wrap: wrap; gap: .7rem; align-items: center; justify-content: space-between; }
h2, h3, h4 { margin: 0 0 .6rem; } h2 { font-size: 1.2rem; } p, small { color: var(--text-secondary); line-height: 1.5; }
.desk-filters { display: grid; grid-template-columns: 1fr 1fr; gap: .7rem; margin: 1rem 0; }
.desk-workspace { display: grid; grid-template-columns: minmax(14rem, .8fr) minmax(0, 2fr); gap: 1rem; align-items: start; }
.desk-workspace > * { min-width: 0; }
.account-list { display: grid; gap: .6rem; }
.stay-phase, .stay-summary { display: flex; justify-content: space-between; gap: .5rem; flex-wrap: wrap; }
.stay-phase strong, .duration { font-variant-numeric: tabular-nums; }
.duration { font-size: 1.4rem; }
.consumption-heading { margin-top: 1.5rem; }
.quick-consumption { display: flex; flex-wrap: wrap; gap: .5rem; } .quick-consumption button { overflow-wrap: anywhere; text-align: left; }
.primary-action { border-color: var(--primary-color); font-weight: 700; }
summary { cursor: pointer; padding: .8rem 0; font-weight: 600; }
.selection-hint { padding: 1.5rem; border: 1px dashed var(--card-border); border-radius: .6rem; }
.account-list button { display: grid; gap: .35rem; text-align: left; overflow-wrap: anywhere; }
.account-list .selected { border-color: var(--primary-color); box-shadow: inset .2rem 0 var(--primary-color); }
button, select, input { font: inherit; } button { min-height: 2.6rem; padding: .55rem .8rem; border: 1px solid var(--card-border); border-radius: .5rem; background: var(--card-bg); color: var(--text-primary); cursor: pointer; }
button:disabled { opacity: .5; cursor: not-allowed; } footer { justify-content: flex-start; margin-top: .8rem; }
.account-detail { padding: 1rem; border: 1px solid var(--card-border); border-radius: .6rem; }
.consumption { display: grid; grid-template-columns: 1fr 2fr 1fr auto; gap: .7rem; align-items: end; margin: 1rem 0; }
label { display: grid; gap: .4rem; min-width: 0; } input:not([type=checkbox]), select { width: 100%; min-width: 0; box-sizing: border-box; padding: .65rem; border: 1px solid var(--input-border); border-radius: .4rem; color: var(--text-primary); background: var(--input-bg); }
.commands article { display: grid; gap: .5rem; padding: .8rem 0; border-bottom: 1px solid var(--card-border); overflow-wrap: anywhere; } .commands button { justify-self: start; } .commands p { margin: 0; }
.checkout-actions { justify-content: flex-start; margin-top: 1rem; }
.payment { display: grid; gap: .75rem; margin-top: 1rem; padding: 1rem; border: 2px solid var(--primary-color); border-radius: .6rem; }
.error { color: var(--error-color); }
@media (max-width: 52rem) { .consumption { grid-template-columns: 1fr 1fr; } }
@media (max-width: 64rem) { .desk-workspace { grid-template-columns: 1fr; } }
@media (max-width: 32rem) { .consumption { grid-template-columns: 1fr; } }
</style>
