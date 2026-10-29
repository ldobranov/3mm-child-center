<script setup lang="ts">
import { UiButton, UiSurface } from '@3mm/ui/v1'
import { provideApplicationLocale } from './i18n'
import { computed, onMounted, onUnmounted, ref } from 'vue'
import { useLocal } from './use-local'
import Status from './Status.vue'
import './local.css'
const props = defineProps<{ locale?: string }>()
const strings = provideApplicationLocale(computed(() => props.locale))
const { t } = strings
const { busy, pending, error, can, access, command, resolve, reviewed } = useLocal(strings)
const registration = ref(''), confirmed = ref(false), exported = ref('')
let subjectSerial = 0, disposed = false
onUnmounted(() => { disposed = true; subjectSerial++ })
function changeSubject() { subjectSerial++; exported.value = ''; confirmed.value = false }
async function exportData() {
  const serial = subjectSerial
  const subject = registration.value
  exported.value = ''
  const result = await command<{ document_json: string }>('export_personal_data', { registration_id: subject })
  if (!disposed && serial === subjectSerial && subject === registration.value && result) exported.value = result.document_json
}
async function erase() {
  const serial = subjectSerial
  const subject = registration.value
  exported.value = ''
  const result = await command('erase_personal_data', { registration_id: subject, confirmed: confirmed.value })
  if (!disposed && serial === subjectSerial && result) { changeSubject(); registration.value = '' }
}
onMounted(access)
</script>
<template>
  <UiSurface><main class="ui-section ui-stack cc-local"><header><h1>{{ t('personal_data') }}</h1></header>
    <Status :error="error" :pending="pending" :busy="busy" @resolve="resolve" @reviewed="reviewed(); exported = ''; confirmed = false" />
    <label>{{ t('registration_id') }}<input class="ui-control" v-model="registration" :disabled="busy || !!pending" required pattern="reg_[0-9a-f]{32}" maxlength="36" @input="changeSubject" /></label>
    <UiButton v-if="can('export_personal_data')" :disabled="busy || !!pending || !/^reg_[0-9a-f]{32}$/.test(registration)" @click="exportData">{{ t('export') }}</UiButton>
    <p>{{ t('finish_all_active_stays_before_erasure_technical_history_remains_downl') }}</p>
    <label class="cc-check ui-check"><input v-model="confirmed" type="checkbox" />{{ t('confirm_personal_field_erasure') }}</label>
    <UiButton variant="danger" v-if="can('erase_personal_data')" :disabled="busy || !!pending || !confirmed || !/^reg_[0-9a-f]{32}$/.test(registration)" @click="erase">{{ t('erase') }}</UiButton>
    <pre v-if="exported" tabindex="0">{{ exported }}</pre>
  </main></UiSurface>
</template>
