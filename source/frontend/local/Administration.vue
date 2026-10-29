<script setup lang="ts">
import { computed, onMounted, onUnmounted, ref } from 'vue'
import { UiButton, UiField, UiSurface } from '@3mm/ui/v1'
import { provideApplicationLocale } from './i18n'
import { useLocal } from './use-local'
import Status from './Status.vue'
import './local.css'

type Client = { registration_id: string; guardian_name: string; status: string }
type Detail = { registration_id: string; status: string; revision: number; consent_version: string; consented_at: string;
  guardian: { display_name: string; phone: string; email: string }; children: { child_id: string; display_name: string }[] }
const props = defineProps<{ locale?: string }>()
const strings = provideApplicationLocale(computed(() => props.locale))
const { t, stateLabel } = strings
const { allowed, busy, error, pending, debugMode, can, access, read, readFailure, command, resolve, reviewed } = useLocal(strings)
const query = ref(''), offset = ref(0), total = ref(0), rows = ref<Client[]>([])
const selected = ref<Detail | null>(null), loading = ref(false), saved = ref(false)
const confirmed = ref(false), exported = ref('')
const appSettings=ref<{revision:number;debug_mode:boolean}|null>(null),draftDebug=ref(false),settingsLoading=ref(false),settingsSaved=ref(false)
let settingsSerial=0
const locked = computed(() => busy.value || !!pending.value)
let serial = 0, disposed = false
onUnmounted(() => { disposed = true; serial++; settingsSerial++ })
function clear() { selected.value = null; saved.value = false; exported.value = ''; confirmed.value = false }
async function refresh() {
  const current = ++serial
  const payload = { query: query.value, status: 'all', offset: offset.value, limit: 20 }
  clear(); rows.value = []; total.value = 0; loading.value = true
  await access()
  if (disposed || current !== serial) return
  if(can('admin_get_settings'))void loadAppSettings()
  try {
    if (!can('admin_list_clients')) return
    const result = await read<{ items: Client[]; total: number }>('admin_list_clients', payload)
    if (!disposed && current === serial) { rows.value = result.items; total.value = result.total }
  } catch (failure) { if (!disposed && current === serial) readFailure(failure) }
  finally { if (!disposed && current === serial) loading.value = false }
}
async function loadAppSettings(){
  const current=++settingsSerial
  settingsLoading.value=true;settingsSaved.value=false;appSettings.value=null
  try{
    const result=await read<{revision:number;debug_mode:boolean}>('admin_get_settings',{})
    if(!disposed&&current===settingsSerial){appSettings.value=result;draftDebug.value=result.debug_mode}
  }catch(failure){if(!disposed&&current===settingsSerial)readFailure(failure)}
  finally{if(!disposed&&current===settingsSerial)settingsLoading.value=false}
}
async function saveAppSettings(){
  if(!appSettings.value||locked.value||settingsLoading.value||draftDebug.value===appSettings.value.debug_mode)return
  settingsSaved.value=false
  const current=settingsSerial
  const result=await command<{revision:number;debug_mode:boolean}>('admin_save_settings',{
    expected_revision:appSettings.value.revision,debug_mode:draftDebug.value,
  })
  if(!disposed&&current===settingsSerial&&result){appSettings.value=result;draftDebug.value=result.debug_mode;debugMode.value=result.debug_mode;settingsSaved.value=true}
}
async function select(id: string) {
  if (locked.value) return
  const current = ++serial
  clear(); loading.value = true
  try {
    const result = await read<Detail>('admin_get_client', { registration_id: id })
    if (!disposed && current === serial) selected.value = result
  } catch { if (!disposed && current === serial) error.value = 'read_unavailable' }
  finally { if (!disposed && current === serial) loading.value = false }
}
async function save() {
  const client = selected.value
  if (!client || locked.value) return
  saved.value = false
  const current = serial
  const result = await command<{ revision: number }>('admin_update_client', {
    registration_id: client.registration_id, expected_revision: client.revision,
    guardian: { ...client.guardian }, children: client.children.map(c => ({ child_id: c.child_id, display_name: c.display_name })),
  })
  if (!disposed && current === serial && result) {
    client.revision = result.revision; saved.value = true
    const row = rows.value.find(r => r.registration_id === client.registration_id)
    if (row) row.guardian_name = client.guardian.display_name
  }
}
async function exportData() {
  if (!selected.value) return
  const current = serial
  exported.value = ''
  const result = await command<{ document_json: string }>('export_personal_data', { registration_id: selected.value.registration_id })
  if (!disposed && current === serial && result) exported.value = result.document_json
}
async function erase() {
  if (!selected.value || !confirmed.value) return
  const current = serial
  exported.value = ''
  const result = await command('erase_personal_data', { registration_id: selected.value.registration_id, confirmed: true })
  if (!disposed && current === serial && result) await refresh()
}
async function review() { await resolve(); await refresh() }
onMounted(refresh)
</script>
<template>
  <UiSurface><main class="ui-section ui-stack cc-local">
    <header><h1>{{ t('administration') }}</h1><UiButton :disabled="busy || loading" @click="refresh">{{ t('refresh') }}</UiButton></header>
    <Status :busy="busy" :error="error" :pending="pending" @resolve="review" @reviewed="reviewed(); refresh()" />
    <p v-if="!allowed.length" role="status">{{ t('access_is_unavailable') }}</p>
    <p v-if="loading" role="status">{{ t('loading') }}</p>
    <section v-if="can('admin_get_settings')" class="ui-stack cc-app-settings" aria-labelledby="app-settings-title">
      <h2 id="app-settings-title">{{t('app_settings')}}</h2>
      <p v-if="settingsLoading" role="status">{{t('loading')}}</p>
      <form v-if="appSettings" @submit.prevent="saveAppSettings">
        <fieldset class="ui-stack" :disabled="locked||settingsLoading||!can('admin_save_settings')">
          <label class="cc-check ui-check"><input id="app-debug-mode" v-model="draftDebug" type="checkbox"/>{{t('app_debug_mode')}}</label>
          <p>{{t('app_debug_mode_hint')}}</p>
          <UiButton type="submit" variant="primary" :disabled="draftDebug===appSettings.debug_mode">{{t('app_save_settings')}}</UiButton>
        </fieldset>
      </form>
      <p v-if="settingsSaved" role="status">{{t('changes_saved')}}</p>
      <UiButton v-if="!appSettings&&!settingsLoading" :disabled="locked" @click="loadAppSettings">{{t('refresh')}}</UiButton>
    </section>
    <section v-if="can('admin_list_clients')">
      <form class="cc-toolbar" @submit.prevent="offset = 0; refresh()">
        <UiField id="admin-search" v-model="query" :label="t('search')" :disabled="locked" :maxlength="120" />
        <UiButton type="submit" :disabled="locked || loading">{{ t('search') }}</UiButton>
      </form>
      <div class="cc-grid">
        <section><h2>{{ t('clients') }} · {{ total }}</h2>
          <p v-if="!loading && !rows.length">{{ t('no_records') }}</p>
          <ul class="cc-client-list"><li v-for="row in rows" :key="row.registration_id"><button type="button" class="cc-row cc-client-row" :disabled="locked || !can('admin_get_client')" :aria-pressed="selected?.registration_id === row.registration_id" @click="select(row.registration_id)"><strong>{{ row.guardian_name }}</strong><span class="cc-client-status">{{ stateLabel(row.status) }}</span></button></li></ul>
          <div class="cc-toolbar"><UiButton :disabled="locked || loading || offset === 0" @click="offset -= 20; refresh()">{{ t('previous') }}</UiButton><UiButton :disabled="locked || loading || offset + 20 >= total" @click="offset += 20; refresh()">{{ t('next') }}</UiButton></div>
        </section>
        <section v-if="selected" class="cc-client-detail">
          <h2>{{ t('edit_client') }}</h2><p>{{ stateLabel(selected.status) }}</p>
          <form @submit.prevent="save">
            <fieldset class="ui-stack" :disabled="locked || !can('admin_update_client')">
              <legend>{{ t('client_details') }}</legend>
              <UiField id="admin-guardian" v-model="selected.guardian.display_name" :label="t('guardian_name')" required :maxlength="120" />
              <UiField id="admin-phone" v-model="selected.guardian.phone" :label="t('phone')" :maxlength="40" />
              <UiField id="admin-email" v-model="selected.guardian.email" type="email" :label="t('email')" :maxlength="160" />
              <UiField v-for="child in selected.children" :id="`admin-${child.child_id}`" :key="child.child_id" v-model="child.display_name" :label="t('child')" required :maxlength="120" />
              <p>{{ t('recorded_consent') }}: {{ selected.consent_version }} · {{ selected.consented_at }}</p>
              <UiButton variant="primary" type="submit">{{ t('save_changes') }}</UiButton>
            </fieldset>
          </form>
          <p v-if="saved" role="status">{{ t('changes_saved') }}</p>
          <section v-if="can('export_personal_data') || can('erase_personal_data')">
            <h3>{{ t('personal_data') }} · {{ selected.guardian.display_name }}</h3>
            <UiButton v-if="can('export_personal_data')" :disabled="locked" @click="exportData">{{ t('export') }}</UiButton>
            <p>{{ t('finish_all_active_stays_before_erasure_technical_history_remains_downl') }}</p>
            <label class="cc-check ui-check"><input v-model="confirmed" type="checkbox" :disabled="locked" />{{ t('confirm_personal_field_erasure') }}</label>
            <UiButton v-if="can('erase_personal_data')" variant="danger" :disabled="locked || !confirmed" @click="erase">{{ t('erase') }}</UiButton>
            <pre v-if="exported" tabindex="0">{{ exported }}</pre>
          </section>
        </section>
      </div>
    </section>
  </main></UiSurface>
</template>
