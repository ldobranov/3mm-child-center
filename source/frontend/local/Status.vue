<script setup lang="ts">
import { UiButton } from '@3mm/ui/v1'
import { useApplicationStrings } from './i18n'
import { UI_DEBUG_MODE, type Pending } from './use-local'
import { inject, ref, watch } from 'vue'
const { t } = useApplicationStrings()
const debugMode = inject(UI_DEBUG_MODE, ref(true))
const props = defineProps<{ error: string; pending: Pending | null; busy: boolean }>()
defineEmits<{ resolve: []; reviewed: [] }>()
const acknowledged = ref(false)
watch(() => props.pending?.request_id, () => { acknowledged.value = false })
</script>
<template>
  <span v-if="busy&&!debugMode" class="cc-working" role="status" :aria-label="t('loading')"><span class="cc-spinner" aria-hidden="true"/></span>
  <p v-if="error && (!pending || debugMode)" role="alert" class="cc-error">{{ t(error) }}</p>
  <aside v-if="pending&&(debugMode||!busy)" role="status" class="cc-review" :class="{'cc-review-compact':!debugMode}">
    <strong>{{ t(debugMode?'pending_review':'unconfirmed_operation') }}</strong>
    <p v-if="debugMode">{{ pending.operation_id }} · <code>{{ pending.request_id }}</code></p>
    <UiButton :disabled="busy" @click="$emit('resolve')">{{ t('check_saved_outcome') }}</UiButton>
    <details :open="debugMode" class="cc-manual-review">
      <summary v-if="!debugMode">{{ t('manual_recovery') }}</summary>
      <label class="cc-check ui-check"><input v-model="acknowledged" type="checkbox" />{{ t('i_reviewed_the_actual_saved_records_unknown_does_not_mean_cancelled') }}</label>
      <UiButton :disabled="busy || !acknowledged" @click="$emit('reviewed'); acknowledged = false">{{ t('finish_manual_review') }}</UiButton>
    </details>
  </aside>
</template>
