<template>
  <section v-if="admin || status?.enabled" class="access-panel">
    <div class="access-heading"><h2>{{ t('Точки за достъп', 'Access points') }}</h2><button :disabled="busy" @click="refresh(true)">{{ t('Обнови', 'Refresh') }}</button></div>
    <p v-if="error" role="alert">{{ error }}</p>
    <p v-if="status && !status.binding_valid" role="alert">{{ t('Устройствата са променени. Достъпът е блокиран; проверете настройките.', 'Device bindings changed. Access is blocked; check configuration.') }}</p>
    <p v-if="status?.enabled" class="muted">{{ t('Началният час на посещението е часът на резервацията. Отчетеното време включва само потвърдените интервали в залата. За нов вход използвайте гривната, не ръчно стартиране.', 'The visit start timestamp is its reservation time. Measured time includes only confirmed intervals inside. Use the bracelet for a new entry, not manual start.') }}</p>
    <template v-if="admin && settings">
      <p>{{ t('Без турникет остава обичайният режим. Датчикът трябва да изпраща корелирани access.passage.v1 събития; GPIO импулсът не доказва преминаване.', 'Without a turnstile, the existing scan workflow remains. The sensor must publish correlated access.passage.v1 events; a GPIO pulse is not passage evidence.') }}</p>
      <p class="muted">{{ t('Изберете устройствата в настройките на инсталирания extension. Идентификатор на датчика:', 'Select devices in the installed extension settings. Sensor identity:') }} <code>access.sensor</code></p>
      <dl class="access-devices"><template v-for="field in deviceFields" :key="field.key"><dt>{{ field.label }}</dt><dd>{{ settings[field.key] || '—' }}</dd></template></dl>
      <form @submit.prevent="save">
        <fieldset :disabled="busy || !!pending">
          <label class="check"><input v-model="form.enabled" type="checkbox">{{ t('Режим с потвърдено преминаване', 'Confirmed-passage mode') }}</label>
          <div class="access-fields">
            <label>{{ t('Идентификатор на четеца', 'Reader identity') }}<input v-model="form.reader_id" required maxlength="96"></label>
            <label>{{ t('Изходен канал на драйвера', 'Driver output channel') }}<input v-model="form.channel" required maxlength="32" placeholder="gpio.output.1"></label>
            <label>{{ t('Импулс (ms)', 'Pulse (ms)') }}<input v-model.number="form.duration_ms" type="number" min="50" max="500" required></label>
          </div>
          <label class="check"><input v-model="form.safety_confirmed" type="checkbox">{{ t('Проверени са драйверът, датчикът и независимото аварийно излизане.', 'The driver, sensor and independent emergency egress have been checked.') }}</label>
          <p class="muted">{{ t('Промяна е възможна само без активни посещения и непроверени заявки. Записът не задейства устройството.', 'Changes require no active visits or unresolved requests. Saving does not actuate hardware.') }}</p>
          <button type="submit" :disabled="form.enabled && !form.safety_confirmed">{{ t('Запази настройките', 'Save settings') }}</button>
        </fieldset>
      </form>
    </template>
    <p v-if="status && !status.items.length">{{ status.enabled ? t('Няма чакащи преминавания.', 'No pending passages.') : t('Активен е режимът без турникет.', 'Scan-only mode is active.') }}</p>
    <div v-for="item in status?.items || []" :key="item.request_id" class="access-request">
      <strong>{{ item.child_name }}</strong><span>{{ stateLabel(item.state) }}</span>
      <small>{{ item.inside_since ? t('Отчетен вътре', 'Recorded inside') : t('Отчетен извън залата', 'Recorded outside') }}</small>
      <p v-if="item.state === 'prepared'" class="muted">{{ t('Изчаква готовност на сметката и разрешение. Времето започва само при потвърден вход.', 'Waiting for account readiness and authorization. Time starts only on confirmed entry.') }}</p>
      <p v-if="!admin && ['review', 'invalidated'].includes(item.state)">{{ t('Необходима е проверка от администратор. Не сканирайте повторно за отключване.', 'Administrator review required. Do not rescan to retry an unlock.') }}</p>
      <template v-if="admin && ['review', 'invalidated'].includes(item.state)">
        <small>{{ item.error_code || t('Неясен резултат', 'Uncertain outcome') }}</small>
        <button v-if="item.state === 'review' && ['expired_before_submit', 'visit_changed_before_submit'].includes(item.error_code || '')" :disabled="busy || !!pending" @click="clearUnsent(item)">{{ t('Потвърди неизпратената заявка', 'Resolve unsent request') }}</button>
        <button :disabled="busy || !!pending" @click="selected = item; isolated = false; observedInside = !!item.inside_since; confirmed = false">{{ t('Ръчна проверка', 'Manual review') }}</button>
      </template>
    </div>
    <p v-if="status?.has_more">{{ t('Показани са първите 100 заявки. След разрешаване обновете списъка.', 'Showing the first 100 requests. Resolve and refresh for the next entries.') }}</p>
    <form v-if="selected && admin" class="review-box" @submit.prevent="reconcile">
      <h3>{{ t('Проверка на място:', 'On-site review:') }} {{ selected.child_name }}</h3>
      <p>{{ t('Първо физически обезопасете устройството и проверете къде е детето. Това не е команда за аварийно спиране. Корекцията е към момента на проверката, не преизчислява неизвестния минал период и не приключва сметката.', 'First physically isolate the device and check the child’s location. This is not an emergency-stop command. Correction applies at observation time, does not recalculate the uncertain past period and does not close the account.') }}</p>
      <fieldset :disabled="busy || !!pending">
        <label>{{ t('Наблюдавано положение', 'Observed location') }}<select v-model="observedInside"><option :value="false">{{ t('Извън залата', 'Outside') }}</option><option :value="true">{{ t('В залата', 'Inside') }}</option></select></label>
        <label class="check"><input v-model="isolated" type="checkbox">{{ t('Устройството е физически обезопасено; няма чакащо движение.', 'The device is physically isolated; no movement is pending.') }}</label>
        <label class="check"><input v-model="confirmed" type="checkbox">{{ t('Проверих положението и приемам корекцията към настоящия момент.', 'I verified the location and accept correction at the current time.') }}</label>
        <button type="submit" :disabled="!isolated || !confirmed">{{ t('Запиши проверката', 'Record review') }}</button>
        <button type="button" @click="selected = null">{{ t('Отказ', 'Cancel') }}</button>
      </fieldset>
    </form>
    <button v-if="pending && !busy" @click="sendPending">{{ t('Повтори същата заявка', 'Retry the same request') }}</button>
  </section>
</template>
<script setup lang="ts">
import { computed, inject, onMounted, onUnmounted, reactive, ref } from 'vue'
import { createRequestId, invokeApplicationOperation } from './application-api'
import { useChildCenterLanguage } from './language'
const props = defineProps<{ admin?: boolean }>()
const { t } = useChildCenterLanguage()
const can = inject<(operation: string) => boolean>('childCenterCan', () => false)
type Item = { request_id: string; visit_id: string; child_name: string; state: string; error_code: string | null; inside_since: string | null; expires_at: string }
type Status = { enabled: boolean; binding_valid: boolean; items: Item[]; has_more: boolean }
type Settings = { point_id: string | null; enabled: boolean; binding_valid: boolean; reader_id: string; channel: string; duration_ms: number; reader_device: string; output_device: string; sensor_device: string }
const status = ref<Status | null>(null), settings = ref<Settings | null>(null), selected = ref<Item | null>(null)
const busy = ref(false), error = ref(''), isolated = ref(false), confirmed = ref(false), observedInside = ref(false)
const form = reactive({ enabled: false, reader_id: '', channel: '', duration_ms: 100, safety_confirmed: false })
const pending = ref<{ operation: string; payload: Record<string, unknown>; key: string; token: string } | null>(null)
let disposed = false, serial = 0, timer: number | undefined
const deviceFields = computed(() => [
  { key: 'reader_device' as const, label: t('Четец', 'Reader') },
  { key: 'output_device' as const, label: t('Изход', 'Output') },
  { key: 'sensor_device' as const, label: t('Датчик', 'Sensor') },
])
function stateLabel(value: string) {
  return ({ prepared: t('Изчаква разрешение', 'Awaiting authorization'), submitted: t('Изчаква преминаване', 'Awaiting passage'), submitting: t('Изпращане', 'Submitting'), review: t('За проверка', 'Needs review'), invalidated: t('Обезсилено — за проверка', 'Invalidated — review required') } as Record<string, string>)[value] || value
}
async function refresh(loadSettings = false) {
  if (busy.value || disposed || !can('get_access_status')) return
  const version = ++serial, token = localStorage.getItem('authToken') || ''
  try {
    const result = await invokeApplicationOperation<Status>(props.admin ? 'administrator' : 'operator', 'get_access_status', token, {})
    if (disposed || version !== serial || token !== localStorage.getItem('authToken')) return
    status.value = result
    if (props.admin && (loadSettings === true || !settings.value)) {
      const value = await invokeApplicationOperation<Settings>('administrator', 'get_access_settings', token, {})
      if (disposed || version !== serial || token !== localStorage.getItem('authToken')) return
      settings.value = value
      Object.assign(form, { enabled: value.enabled, reader_id: value.reader_id, channel: value.channel, duration_ms: value.duration_ms, safety_confirmed: false })
    }
  } catch (reason) {
    if (!disposed && version === serial && token === localStorage.getItem('authToken')) error.value = reason instanceof Error ? reason.message : t('Няма връзка.', 'Connection unavailable.')
  }
}
function queue(operation: string, payload: Record<string, unknown>) {
  if (!props.admin || !can(operation) || pending.value || busy.value) return
  pending.value = { operation, payload, key: createRequestId(), token: localStorage.getItem('authToken') || '' }
  void sendPending()
}
async function sendPending() {
  const request = pending.value
  if (!request || busy.value || !can(request.operation) || request.token !== localStorage.getItem('authToken')) return
  busy.value = true; error.value = ''; ++serial
  try {
    await invokeApplicationOperation('administrator', request.operation, request.token, request.payload, request.key)
    if (disposed || request.token !== localStorage.getItem('authToken')) return
    pending.value = null; selected.value = null
  } catch (reason) {
    if (!disposed && request.token === localStorage.getItem('authToken')) error.value = reason instanceof Error ? reason.message : t('Неясен резултат.', 'Uncertain outcome.')
    // Keep the identity after transport failure. Explicit 4xx rejection made
    // no mutation for these CAS-protected configuration/review operations.
    const code = (reason as { httpStatus?: number })?.httpStatus
    if (code && [400, 401, 403, 404, 409, 422].includes(code)) pending.value = null
  } finally { busy.value = false }
  if (!disposed && !pending.value) await refresh(true)
}
function save() { queue('configure_access_point', { ...form, expected_point_id: settings.value?.point_id ?? null }) }
function clearUnsent(item: Item) { queue('resolve_unsent_access', { request_id: item.request_id, expected_error_code: item.error_code, confirmed: true }) }
function reconcile() {
  if (selected.value) queue('reconcile_access', { request_id: selected.value.request_id, expected_state: selected.value.state, observed_inside: observedInside.value, hardware_isolated: isolated.value, confirmed: confirmed.value })
}
onMounted(() => { void refresh(true); timer = window.setInterval(() => { void refresh() }, 5000) })
onUnmounted(() => { disposed = true; ++serial; window.clearInterval(timer) })
</script>
<style scoped>
.access-panel { padding: 1rem; margin-block: 1rem; color: var(--text-primary); background: var(--card-bg); border: 1px solid var(--card-border); border-radius: .7rem; }
.access-heading, .access-request { display: flex; align-items: center; flex-wrap: wrap; gap: .65rem; }
.access-heading { justify-content: space-between; }
h2 { font-size: 1.2rem; margin: 0; } h3 { font-size: 1.05rem; }
.access-fields { display: grid; grid-template-columns: repeat(auto-fit, minmax(180px, 1fr)); gap: .8rem; margin-block: .8rem; }
label { display: grid; gap: .35rem; } .check { display: flex; align-items: center; gap: .5rem; margin-block: .75rem; }
fieldset { border: 0; padding: 0; margin: 0; min-width: 0; }
input:not([type=checkbox]), select, button { font: inherit; color: inherit; background: var(--input-bg); border: 1px solid var(--input-border); border-radius: .4rem; padding: .55rem; min-width: 0; }
button { cursor: pointer; } button:disabled { opacity: .5; cursor: default; }
.access-devices { display: grid; grid-template-columns: auto minmax(0, 1fr); gap: .35rem .8rem; font-size: .85rem; } dd { margin: 0; overflow-wrap: anywhere; }
.access-request { padding-block: .8rem; border-top: 1px solid var(--card-border); } .access-request p { flex-basis: 100%; margin: 0; }
.muted, small { color: var(--text-secondary); } [role=alert] { border-left: 3px solid var(--text-primary); padding-left: .7rem; }
.review-box { border-top: 1px solid var(--card-border); padding-top: 1rem; }
@media(max-width: 560px) { .access-panel { padding: .75rem; } .access-devices { grid-template-columns: 1fr; } }
</style>
