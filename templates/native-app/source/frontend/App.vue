<script setup lang="ts">
import { computed, onMounted, ref } from 'vue'
import { UiSurface, UiButton } from '@3mm/ui/v1'
import { useApplicationHost } from '@3mm/application-ui/v1'
import en from './locales/en.json'
import bg from './locales/bg.json'
import { translate } from './locale'
// The current Core loader supplies this reactive prop from its effective locale.
// Direct consumers may also use the public host.presentation v1 facade.
const props = withDefaults(defineProps<{ locale?: string }>(), { locale: 'en' })
const catalogs = { en, bg }
const text = computed(() => Object.fromEntries(Object.keys(en).map(key => [key, translate(catalogs, props.locale, key)])))
const host = useApplicationHost()
const value = ref<number | null>(null), busy = ref(false), canWrite = ref(false), message = ref('')
const pending = ref<string | null>(null)
let keyName = ''
function saved(request: string | null) {
  pending.value = request
  try { if (request) sessionStorage.setItem(keyName,request); else sessionStorage.removeItem(keyName) } catch { /* In-memory review remains available. */ }
}
onMounted(async () => {
  try {
    const info=await host.getInfo()
    keyName='3mm-starter:'+info.module_id+':pending'
    try { const request=sessionStorage.getItem(keyName); if (request && /^[0-9a-f]{32}$/.test(request)) pending.value=request } catch {}
    canWrite.value=info.operations.some(op=>op.operation_id==='add_value')
    if (info.operations.some(op=>op.operation_id==='read_value')) value.value=(await host.invoke('read_value',{})).value as number
  } catch { message.value='unavailable' }
})
async function add() {
  if (busy.value || pending.value || !canWrite.value) return
  const request=Array.from(crypto.getRandomValues(new Uint8Array(16)),v=>v.toString(16).padStart(2,'0')).join('')
  saved(request); busy.value=true
  try {
    const result=await host.invoke('add_value',{amount:1},{idempotencyKey:request})
    if (!['applied','conflict','full'].includes(String(result.status)) || typeof result.value!=='number') throw new Error('Invalid result')
    value.value=result.value; saved(null); message.value=''
  } catch { message.value='unknown' } finally { busy.value=false }
}
async function resolve() {
  if (!pending.value || busy.value) return
  busy.value=true
  try {
    const result=await host.invoke('request_outcome',{request_id:pending.value})
    if (result.found===true && typeof result.result_json==='string') {
      const outcome=JSON.parse(result.result_json)
      if (!['applied','conflict','full'].includes(outcome.status) || typeof outcome.value!=='number') throw new Error('Invalid receipt')
      value.value=outcome.value; saved(null); message.value=''
    } else message.value='unknown'
  } catch { message.value='unknown' } finally { busy.value=false }
}
</script>
<template>
  <UiSurface><main class="starter-page ui-section">
    <h1>{{ text.title }}</h1><p>{{ text.value }}: {{ value ?? '—' }}</p>
    <p v-if="message" role="status">{{ message === 'unknown' ? text.unknown : text.unavailable }}</p>
    <UiButton variant="primary" v-if="canWrite" :disabled="busy || !!pending" @click="add">{{ text.add }}</UiButton>
    <section v-if="pending"><code>{{ pending }}</code><UiButton :disabled="busy" @click="resolve">{{ text.check }}</UiButton></section>
  </main></UiSurface>
</template>
<style scoped>
.starter-page{max-width:60rem;margin:auto;overflow-wrap:anywhere}.starter-page section{display:grid;gap:calc(var(--ui-space)*3);margin-top:calc(var(--ui-space)*3)}
</style>
