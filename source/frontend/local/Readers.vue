<script setup lang="ts">
import { computed, onMounted, onUnmounted, ref } from 'vue'
import { UiButton, UiField, UiSurface } from '@3mm/ui/v1'
import { provideApplicationLocale } from './i18n'
import { useLocal } from './use-local'
import { formatTimestamp } from './time'
import Status from './Status.vue'
import './local.css'
type Settings = {revision:number;mode:string;effective_from:string;toggle_ids:string[];entry_ids:string[];exit_ids:string[];device_ids:string[]}
type Activity = {event_id:string;device_id:string;reader_id:string;occurred_at:string;outcome:string;child_name:string|null;visit_id:string|null}
const props = defineProps<{locale?:string}>()
const strings = provideApplicationLocale(computed(()=>props.locale)), {t} = strings
const {allowed,busy,pending,error,can,access,read,readFailure,command,resolve,reviewed} = useLocal(strings)
const settings = ref<Settings|null>(null), mode = ref('disabled'), toggle = ref(''), entry = ref(''), exitIds = ref('')
const activity = ref<Activity[]>([]), total = ref(0), offset = ref(0), loading = ref(false), saved = ref(false)
let serial = 0, disposed = false
onUnmounted(()=>{disposed=true;serial++})
const locked = computed(()=>busy.value || !!pending.value)
const ids = (value:string) => value.split(/[\s,]+/).filter(Boolean)
async function refresh() {
  const current=++serial
  settings.value=null;activity.value=[];total.value=0;loading.value=true;saved.value=false
  await access()
  if(disposed || current!==serial)return
  try {
    const [config,history] = await Promise.all([
      can('get_reader_settings') ? read<Settings>('get_reader_settings',{}) : null,
      can('list_reader_activity') ? read<{items:Activity[];total:number}>('list_reader_activity',{offset:offset.value,limit:20}) : null,
    ])
    if(disposed || current!==serial)return
    if(config){settings.value=config;mode.value=config.mode;toggle.value=config.toggle_ids.join('\n');entry.value=config.entry_ids.join('\n');exitIds.value=config.exit_ids.join('\n')}
    if(history){activity.value=history.items;total.value=history.total}
  }catch(failure){if(!disposed && current===serial)readFailure(failure)}
  finally{if(!disposed && current===serial)loading.value=false}
}
async function save() {
  if(!settings.value || locked.value)return
  const current=serial
  const result=await command('set_reader_settings',{expected_revision:settings.value.revision,mode:mode.value,
    toggle_ids:mode.value==='automatic_toggle'?ids(toggle.value):[],entry_ids:mode.value==='directional'?ids(entry.value):[],exit_ids:mode.value==='directional'?ids(exitIds.value):[]})
  if(!disposed && current===serial && result){
    const refreshed=serial+1
    await refresh()
    if(!disposed && serial===refreshed && settings.value)saved.value=true
  }
}
async function review(){await resolve();await refresh()}
onMounted(refresh)
</script>
<template>
  <UiSurface><main class="ui-section ui-stack cc-local">
    <header><h1>{{t('network_readers')}}</h1><UiButton :disabled="busy || loading" @click="refresh">{{t('refresh')}}</UiButton></header>
    <Status :busy="busy" :error="error" :pending="pending" @resolve="review" @reviewed="reviewed();refresh()"/>
    <p v-if="!allowed.length">{{t('access_is_unavailable')}}</p>
    <p>{{t('reader_core_setup')}}</p><p>{{t('reader_scope_notice')}}</p>
    <p v-if="loading">{{t('loading')}}</p>
    <form v-if="settings" @submit.prevent="save">
      <fieldset class="ui-stack" :disabled="locked || !can('set_reader_settings')">
        <legend>{{t('reader_policy')}}</legend>
        <p>{{t('reader_bound_devices')}}: {{settings.device_ids.join(', ') || t('reader_none')}}</p>
        <UiField id="reader-mode" v-model="mode" type="select" :label="t('reader_mode')" :options="[
          {value:'disabled',label:t('reader_disabled')},{value:'automatic_toggle',label:t('reader_automatic_toggle')},{value:'directional',label:t('reader_directional')} ]"/>
        <UiField v-if="mode==='automatic_toggle'" id="reader-toggle" v-model="toggle" type="textarea" :label="t('reader_toggle_ids')" :maxlength="1552" required/>
        <template v-if="mode==='directional'">
          <UiField id="reader-entry" v-model="entry" type="textarea" :label="t('reader_entry_ids')" :maxlength="1552" required/>
          <UiField id="reader-exit" v-model="exitIds" type="textarea" :label="t('reader_exit_ids')" :maxlength="1552" required/>
        </template>
        <p>{{t('reader_effective_policy')}}</p><UiButton type="submit" variant="primary">{{t('save_changes')}}</UiButton>
      </fieldset>
    </form>
    <p v-if="saved" role="status">{{t('changes_saved')}}</p>
    <section><h2>{{t('reader_activity')}}</h2><p v-if="!activity.length && !loading">{{t('no_records')}}</p>
      <div class="cc-table ui-table"><table v-if="activity.length"><thead><tr><th>{{t('time')}}</th><th>{{t('reader_identifier')}}</th><th>{{t('child')}}</th><th>{{t('reader_outcome')}}</th></tr></thead>
        <tbody><tr v-for="row in activity" :key="row.event_id"><td>{{formatTimestamp(row.occurred_at,strings.locale.value)}}</td><td>{{row.reader_id}}</td><td>{{row.child_name || '—'}}</td><td>{{t('reader_result_'+row.outcome)}}</td></tr></tbody>
      </table></div>
      <div class="cc-toolbar"><UiButton :disabled="loading || locked || offset===0" @click="offset-=20;refresh()">{{t('previous')}}</UiButton><UiButton :disabled="loading || locked || offset+20>=total" @click="offset+=20;refresh()">{{t('next')}}</UiButton></div>
    </section>
  </main></UiSurface>
</template>
