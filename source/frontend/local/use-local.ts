import { onUnmounted, provide, ref, type InjectionKey, type Ref } from 'vue'
import { useApplicationHost, type ApplicationPayload } from '@3mm/application-ui/v1'
import { useApplicationStrings } from './i18n'

export const UI_DEBUG_MODE: InjectionKey<Ref<boolean>> = Symbol('child-center-debug-mode')

export type Pending = { request_id: string; operation_id: string }
type Outcome = { status: 'applied' | 'rejected'; data: ApplicationPayload | null; message: string | null }
function outcome(value: unknown, receipt = false): value is Outcome {
  if (!value || typeof value !== 'object' || Array.isArray(value)) return false
  const candidate = value as Outcome
  if (candidate.status === 'rejected') return candidate.data === null && typeof candidate.message === 'string'
  return candidate.status === 'applied' && candidate.message === null &&
    ((receipt && candidate.data === null) || (!!candidate.data && typeof candidate.data === 'object' && !Array.isArray(candidate.data)))
}
export function useLocal(strings = useApplicationStrings()) {
  const host = useApplicationHost()
  const { t, domainMessageKey } = strings
  let disposed = false
  let accessSerial = 0
  onUnmounted(() => { disposed = true; accessSerial++ })
  // An unavailable presentation preference retains the detailed interface.
  const debugMode = ref(true)
  provide(UI_DEBUG_MODE, debugMode)
  const allowed = ref<string[]>([])
  const busy = ref(false)
  const error = ref('')
  const pending = ref<Pending | null>(null)
  // Only an opaque request identity survives reload; no payload or credential.
  const storageKey = 'child-center-local-pending-v1'
  try {
    const saved = JSON.parse(sessionStorage.getItem(storageKey) || 'null')
    if (saved && /^[0-9a-f]{32}$/.test(saved.request_id) && /^[a-z_]+$/.test(saved.operation_id)) pending.value = saved
  } catch { /* A denied browser store does not prevent in-memory operation. */ }
  function save(value: Pending | null) {
    pending.value = value
    try {
      if (value) sessionStorage.setItem(storageKey, JSON.stringify(value))
      else sessionStorage.removeItem(storageKey)
    } catch { /* The visible identity still permits manual outcome review. */ }
  }
  async function access() {
    const serial = ++accessSerial
    debugMode.value = true
    allowed.value = []
    try {
      const info = await host.getInfo()
      if (!disposed && serial === accessSerial) {
        allowed.value = info.operations.map(item => item.operation_id)
        const preferencesOperation = allowed.value.find(name => name.startsWith('ui_preferences_'))
        if (preferencesOperation) {
          try {
            const preferences = await read<{debug_mode: boolean}>(preferencesOperation, {})
            if (!disposed && serial === accessSerial && typeof preferences.debug_mode === 'boolean') debugMode.value = preferences.debug_mode
          } catch { /* An optional presentation read never revokes business access. */ }
        }
        if (disposed || serial !== accessSerial) return
        if (!pending.value && ['read_unavailable','access_unavailable','access_denied'].includes(error.value)) error.value = ''
      }
    }
    catch { if (!disposed && serial === accessSerial) error.value = 'access_unavailable' }
  }
  async function read<T>(operation: string, payload: ApplicationPayload): Promise<T> {
    return await host.invoke(operation, payload) as unknown as T
  }
  function readFailure(failure: unknown, fallback = 'read_unavailable') {
    if (disposed) return
    // A query/transport conflict does not revoke the host's permission catalog.
    // Personal results are cleared by the caller; no invocation is retried.
    if (failure && typeof failure === 'object' && 'code' in failure && failure.code === 'access_denied') {
      allowed.value = []; error.value = 'access_denied'
    } else error.value = fallback
  }
  async function command<T>(operation: string, payload: ApplicationPayload): Promise<T | undefined> {
    if (disposed || busy.value || pending.value) return
    if (!allowed.value.includes(operation)) { error.value = 'access_denied'; return }
    const bytes = crypto.getRandomValues(new Uint8Array(16))
    const request_id = Array.from(bytes, b => b.toString(16).padStart(2, '0')).join('')
    save({ request_id, operation_id: operation })
    busy.value = true
    error.value = ''
    try {
      const result = await host.invoke(operation, payload, { idempotencyKey: request_id })
      if (disposed) return
      if (!outcome(result)) throw new Error('Invalid operation result')
      save(null)
      if (result.status === 'rejected') {
        error.value = domainMessageKey(result.message)
        return
      }
      return result.data as unknown as T
    } catch {
      // An error never proves rollback and never generates a replacement command.
      if (!disposed) error.value = 'outcome_needs_review'
    } finally { busy.value = false }
  }
  async function resolve() {
    if (!pending.value || busy.value) return
    busy.value = true
    try {
      const name = pending.value.operation_id
      const specific = name === 'admin_save_settings' ? 'admin_request_outcome' : name === 'family_retry_open' ? 'family_open_outcome' : name.startsWith('family_') ? 'visit_request_outcome' : ['commerce_release_empty','commerce_release_unlinked'].includes(name) ? 'commerce_recovery_outcome' : name === 'commerce_save_settings' ? 'commerce_settings_outcome' : name === 'commerce_allow_child' ? 'commerce_child_outcome' : name.startsWith('cashier_') ? 'cashier_request_outcome' : name.startsWith('commerce_') ? 'commerce_request_outcome' : null
      const operation = (specific ? [specific] : ['kiosk_request_outcome','request_outcome','visit_request_outcome','privacy_request_outcome','admin_request_outcome','reader_request_outcome']).find(name => allowed.value.includes(name))
      if (!operation) throw new Error('No outcome read is permitted')
      const identity = pending.value
      const result = await read<{ status: string; result_json: string | null }>(operation, identity)
      if (disposed) return
      if (result.status === 'confirmed' && result.result_json) {
        const observed: unknown = JSON.parse(result.result_json)
        if (!outcome(observed, true)) throw new Error('Invalid receipt')
        save(null)
        error.value = observed.status === 'rejected' ? domainMessageKey(observed.message) : ''
        return { operation: identity.operation_id, status: observed.status }
      }
      else error.value = 'unknown_outcome_review_the_saved_records_before_continuing'
    } catch { if (!disposed) error.value = 'review_unavailable' }
    finally { busy.value = false }
  }
  function reviewed() {
    if (busy.value || !pending.value) return
    try {
      const previous = JSON.parse(sessionStorage.getItem('child-center-local-reviewed-v1') || '[]')
      sessionStorage.setItem('child-center-local-reviewed-v1', JSON.stringify([...previous, pending.value].slice(-20)))
    } catch { /* The identity remains visible until this explicit acknowledgement. */ }
    save(null); error.value = ''
  }
  return { allowed, busy, error, pending, debugMode, access, read, readFailure, command, resolve, reviewed,
    can: (operation: string) => allowed.value.includes(operation) }
}
