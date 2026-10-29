<script setup lang="ts">
import { UiButton, UiSurface } from '@3mm/ui/v1'
import { provideApplicationLocale } from './i18n'
import { computed, onMounted, onUnmounted, ref } from 'vue'
import type { ApplicationPayload } from '@3mm/application-ui/v1'
import { useLocal } from './use-local'
import ClientForm from './ClientForm.vue'
import Status from './Status.vue'
import './local.css'
const props = defineProps<{ locale?: string }>()
const strings = provideApplicationLocale(computed(() => props.locale))
const { t } = strings
const { busy, pending, error, access, can, read, command, resolve, reviewed } = useLocal(strings)
const choices = ref<{article_id:number;label:string}[]>([])
const submitted = ref(false), formKey = ref(0)
const staffSubmission = ref(false)
const surface = ref<HTMLElement|null>(null), fullscreen = ref(false), fullscreenError = ref(false)
let disposed = false
function fullscreenChanged() { fullscreen.value = document.fullscreenElement === surface.value }
async function toggleFullscreen() {
  fullscreenError.value = false
  try {
    if (fullscreen.value) await document.exitFullscreen()
    else if (surface.value?.requestFullscreen) await surface.value.requestFullscreen()
    else throw new Error('Fullscreen unavailable')
  } catch { if (!disposed) fullscreenError.value = true }
}
onMounted(() => document.addEventListener('fullscreenchange',fullscreenChanged))
onUnmounted(() => { disposed = true; document.removeEventListener('fullscreenchange',fullscreenChanged) })
async function submit(payload: ApplicationPayload) {
  const operation = can('submit_registration') ? 'submit_registration' : 'register_client'
  const result = await command(operation, payload)
  if (result) { staffSubmission.value = operation === 'register_client'; submitted.value = true; formKey.value++ }
}
async function review() {
  const result = await resolve()
  if (result && ['submit_registration','register_client'].includes(result.operation) && result.status === 'applied') {
    staffSubmission.value = result.operation === 'register_client'
    submitted.value = true; formKey.value++
  }
}
onMounted(async()=>{await access();const operation=can('kiosk_registration_choices')?'kiosk_registration_choices':'registration_choices';if(disposed||!can(operation))return
  try{const result=await read<{items:{article_id:number;label:string}[]}>(operation,{});if(!disposed)choices.value=result.items}catch{if(!disposed)error.value='read_unavailable'}
})
</script>
<template>
  <UiSurface><main ref="surface" class="ui-section ui-stack cc-local cc-kiosk">
    <header><div><h1>{{ t('child_center') }}</h1><p>{{ t('registration') }}</p></div><UiButton @click="toggleFullscreen">{{ fullscreen ? t('exit_fullscreen') : t('fullscreen') }}</UiButton></header>
    <p v-if="fullscreenError" role="status">{{ t('fullscreen_unavailable') }}</p>
    <Status :busy="busy" :pending="pending" :error="error" @resolve="review" @reviewed="reviewed(); formKey++" />
    <p v-if="submitted" role="status">{{ staffSubmission ? t('registration_saved') : t('submitted_for_staff_approval') }}</p>
    <UiButton v-if="submitted" @click="submitted = false">{{ t('next_registration') }}</UiButton>
    <ClientForm v-else-if="can('submit_registration') || can('register_client')" :key="formKey" :choices="choices" :kiosk="!can('register_client')" :disabled="busy || !!pending" @submit="submit" />
    <p v-else role="status">{{ t('use_an_enrolled_registration_terminal') }}</p>
  </main></UiSurface>
</template>
