<template>
  <div class="choices">
    <span>{{ t('Разрешена консумация', 'Allowed consumption') }}</span>
    <p v-if="error" role="alert">{{ error }} <button type="button" @click="load">{{ t('Опитай отново', 'Retry') }}</button></p>
    <p v-else-if="loading" role="status">{{ t('Зареждане…', 'Loading…') }}</p>
    <p v-else-if="!options.length">{{ t('Няма настроени артикули. Нищо не е разрешено по подразбиране.', 'No articles are configured. Nothing is allowed by default.') }}</p>
    <label v-for="option in options" :key="option.code">
      <input type="checkbox" :disabled="disabled" :checked="modelValue.includes(option.code)" @change="toggle(option.code)" /> {{ option.label }}
    </label>
    <label v-for="code in unavailable" :key="code">
      <input type="checkbox" :disabled="disabled" checked @change="toggle(code)" /> {{ code }} — {{ t('Стар или вече недостъпен избор; премахнете при преглед.', 'Legacy or unavailable choice; remove during review.') }}
    </label>
  </div>
</template>
<script setup lang="ts">
import { computed, onMounted, ref } from 'vue'
import { invokeApplicationOperation } from './application-api'
import { ensureKioskSession } from './kiosk-session'
import { useChildCenterLanguage } from './language'
const props = defineProps<{ modelValue: string[]; audience: 'kiosk' | 'operator' | 'administrator'; disabled?: boolean }>()
const emit = defineEmits<{ 'update:modelValue': [value: string[]] }>()
const { t } = useChildCenterLanguage()
const options = ref<Array<{ code: string; label: string }>>([])
const loading = ref(true)
const error = ref('')
const unavailable = computed(() => loading.value || error.value ? [] : props.modelValue.filter(code => !options.value.some(o => o.code === code)))
function toggle(code: string) {
  emit('update:modelValue', props.modelValue.includes(code) ? props.modelValue.filter(c => c !== code) : [...props.modelValue, code])
}
async function load() {
  loading.value = true
  error.value = ''
  try {
    const token = props.audience === 'kiosk' ? await ensureKioskSession() : localStorage.getItem('authToken')
    if (!token) throw new Error(t('Сесията е изтекла. Презаредете страницата.', 'The session expired. Reload the page.'))
    options.value = (await invokeApplicationOperation<{ items: Array<{ code: string; label: string }> }>(props.audience, 'list_consumption_choices', token, {})).items
  } catch (reason) { error.value = reason instanceof Error ? reason.message : t('Артикулите не са достъпни.', 'Articles are unavailable.') }
  finally { loading.value = false }
}
onMounted(load)
</script>
<style scoped>
.choices { display: flex; flex-wrap: wrap; gap: .6rem 1rem; color: var(--text-secondary); font-size: .88rem; }
.choices > span, .choices > p { flex-basis: 100%; margin: 0; }
.choices label { display: flex; align-items: flex-start; gap: .4rem; overflow-wrap: anywhere; }
input { accent-color: var(--primary-color); }
button { color: var(--text-primary); background: var(--card-bg); border: 1px solid var(--card-border); border-radius: .4rem; font: inherit; }
</style>
