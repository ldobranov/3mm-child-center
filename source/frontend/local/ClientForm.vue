<script setup lang="ts">
import { UiButton, UiField } from '@3mm/ui/v1'
import { useApplicationStrings } from './i18n'
const { t } = useApplicationStrings()
import { computed, ref } from 'vue'
import type { ApplicationPayload } from '@3mm/application-ui/v1'
const props = defineProps<{ disabled: boolean; kiosk?: boolean; choices?:{article_id:number;label:string}[] }>()
const emit = defineEmits<{ submit: [payload: ApplicationPayload] }>()
const name = ref(''), phone = ref(''), email = ref(''), children = ref(['']), consent = ref(false)
const allowed = ref<number[][]>([[]])
const valid = computed(() => name.value.trim() && (phone.value.trim() || email.value.trim()) && children.value.every(c => c.trim()) && consent.value)
function submit() {
  if (props.disabled || !valid.value) return
  emit('submit', { guardian: { display_name: name.value.trim(), phone: phone.value.trim(), email: email.value.trim(),
    consent_version: 'local-registration-v2', consented_at: new Date().toISOString() }, children: children.value.map((c,index) => ({ display_name: c.trim(),allowed_article_ids:allowed.value[index]||[] })) })
}
</script>
<template>
  <form @submit.prevent="submit">
    <fieldset :disabled="disabled">
      <legend>{{ kiosk ? t('registration') : t('new_client') }}</legend>
      <UiField id="client-parent" :label="t('parent')" :model-value="name" required :maxlength="120" @update:model-value="name = String($event)" />
      <div class="cc-grid">
        <label class="ui-field"><span>{{ t('phone') }}</span><input class="ui-control" v-model="phone" type="tel" maxlength="40" autocomplete="tel" /></label>
        <UiField id="client-email" :label="t('email')" :model-value="email" type="email" :maxlength="160" @update:model-value="email = String($event)" />
      </div>
      <div v-for="(_, index) in children" :key="index"><UiField :id="`client-child-${index}`" :label="`${t('child')} ${index + 1}`" :model-value="children[index]" required :maxlength="120" @update:model-value="children[index] = String($event)" />
        <fieldset v-if="choices?.length"><legend>{{t('commerce_parent_choices')}}</legend><label v-for="choice in choices" :key="choice.article_id" class="cc-check ui-check"><input v-model="allowed[index]" type="checkbox" :value="choice.article_id"/>{{choice.label}}</label><p>{{t('commerce_registration_choices')}}</p></fieldset>
      </div>
      <UiButton v-if="children.length < 8" type="button" @click="children.push('');allowed.push([])">{{ t('child_04acb3') }}</UiButton>
      <UiButton v-if="children.length > 1" type="button" @click="children.pop();allowed.pop()">{{ t('remove_last') }}</UiButton>
      <label class="cc-check ui-check"><input v-model="consent" type="checkbox" required />{{ t('i_confirm_local_registration_of_these_contacts_and_children_data_stays') }}</label>
      <UiButton variant="primary" type="submit" :disabled="!valid">{{ t('register') }}</UiButton>
    </fieldset>
  </form>
</template>
