<template>
  <div v-if="snapshot" :key="generation"><slot v-if="snapshot.allowed_route_ids.includes(routeId)" :can="can" /><p v-else role="status">{{ t('Нямате достъп до този екран. Обърнете се към администратор.', 'You do not have access to this screen. Contact an administrator.') }}</p></div>
  <section v-else class="staff-access" role="status">
    <p>{{ failed ? t('Правата не могат да бъдат потвърдени. Проверете входа и връзката.', 'Access could not be verified. Check your login and connection.') : t('Проверка на достъпа…', 'Checking access…') }}</p>
    <button v-if="failed" @click="refresh">{{ t('Опитай отново', 'Retry') }}</button>
  </section>
</template>
<script setup lang="ts">
import { onMounted, onUnmounted, provide, ref } from 'vue'
import { getBackendBase } from './application-api'
import { useChildCenterLanguage } from './language'
const { t } = useChildCenterLanguage()
defineProps<{ routeId: string }>()
type Snapshot = { module_id: string; active_version: string; user_id: number; allowed_route_ids: string[]; allowed_operation_ids: string[] }
const snapshot = ref<Snapshot | null>(null), failed = ref(false), generation = ref(0)
let signature = '', token = '', serial = 0, disposed = false
let timer: number | undefined
let controller: AbortController | undefined
const can = (operation: string) => token === (localStorage.getItem('authToken') || '') && Boolean(snapshot.value?.allowed_operation_ids.includes(operation))
provide('childCenterCan', can)
provide('childCenterUserId', () => snapshot.value?.user_id)
async function refresh() {
  const request = ++serial
  controller?.abort()
  const activeController = new AbortController()
  controller = activeController
  const currentToken = localStorage.getItem('authToken') || ''
  if (token !== currentToken) { snapshot.value = null; signature = ''; token = currentToken }
  const timeout = window.setTimeout(() => activeController.abort(), 8000)
  try {
    if (!currentToken) throw new Error('No user session')
    const response = await fetch(`${await getBackendBase()}/api/v1/application-extensions/org.3mm.child-center/access`, { headers: { Authorization: `Bearer ${currentToken}` }, cache: 'no-store', signal: activeController.signal })
    if (!response.ok) throw new Error('Access unavailable')
    const value = await response.json() as Snapshot
    if (value.module_id !== 'org.3mm.child-center' || !Number.isInteger(value.user_id) || value.user_id < 1 || typeof value.active_version !== 'string' || !Array.isArray(value.allowed_route_ids) || !Array.isArray(value.allowed_operation_ids) || ![...value.allowed_route_ids, ...value.allowed_operation_ids].every(v => typeof v === 'string')) throw new Error('Invalid access response')
    if (disposed || request !== serial || currentToken !== localStorage.getItem('authToken')) return
    const next = JSON.stringify([value.user_id, value.active_version, [...value.allowed_route_ids].sort(), [...value.allowed_operation_ids].sort()])
    if (next !== signature) { generation.value++; signature = next }
    snapshot.value = value; failed.value = false
  } catch {
    if (!disposed && request === serial) { snapshot.value = null; signature = ''; failed.value = true }
  } finally { window.clearTimeout(timeout) }
}
function denied() { snapshot.value = null; signature = ''; void refresh() }
function visible() { if (document.visibilityState === 'visible') void refresh() }
onMounted(() => {
  void refresh()
  timer = window.setInterval(refresh, 15000)
  window.addEventListener('focus', refresh)
  window.addEventListener('storage', refresh)
  window.addEventListener('child-center-access-denied', denied)
  document.addEventListener('visibilitychange', visible)
})
onUnmounted(() => {
  disposed = true; controller?.abort(); window.clearInterval(timer)
  window.removeEventListener('focus', refresh)
  window.removeEventListener('storage', refresh)
  window.removeEventListener('child-center-access-denied', denied)
  document.removeEventListener('visibilitychange', visible)
})
</script>
<style scoped>
.staff-access { padding: 1rem; color: var(--text-primary); background: var(--card-bg); border: 1px solid var(--card-border); border-radius: .7rem; }
button { padding: .6rem; font: inherit; color: inherit; background: var(--input-bg); border: 1px solid var(--input-border); border-radius: .4rem; }
</style>
