<script setup lang="ts">
import { computed, onMounted, onUnmounted, ref } from 'vue'
import { UiButton, UiField, UiSurface } from '@3mm/ui/v1'
import type { ApplicationPayload } from '@3mm/application-ui/v1'
import { provideApplicationLocale } from './i18n'
import { useLocal } from './use-local'
import CommerceSetup from './CommerceSetup.vue'
import './local.css'

type Row = {article_id?: number; place_id?: number; unit_id?: number; category_id?: number; label?: string;
  accounts_count?: number | null; precision?: number | null; time_interval?: number | null}
type Result = {status: 'ready' | 'unavailable' | 'invalid_response'; items: Row[]; has_more: boolean}
const props = defineProps<{locale?: string}>()
const strings = provideApplicationLocale(computed(() => props.locale))
const { t } = strings
const { allowed, can, access, read } = useLocal(strings)
const section = ref('articles'), query = ref(''), offset = ref(0), rows = ref<Row[]>([])
const more = ref(false), loading = ref(false), notice = ref(''), pos = ref<number | null>(null)
let serial = 0, disposed = false
const operation = computed(() => 'barsy_' + section.value)
onUnmounted(() => { disposed = true; serial++ })
function clear() { serial++; rows.value = []; more.value = false; notice.value = ''; pos.value = null; loading.value = false }
function choose(value: string) { clear(); section.value = value; offset.value = 0 }
async function refreshAccess() { clear(); await access() }
async function request(check = false) {
  if (loading.value) return
  const name = check ? 'barsy_check' : operation.value
  if (!can(name)) return
  const current = ++serial
  const payload: ApplicationPayload = check ? {} : section.value === 'articles'
    ? {query: query.value, offset: offset.value} : {offset: offset.value}
  rows.value = []; more.value = false; notice.value = ''; pos.value = null; loading.value = true
  try {
    const result = await read<Result & {pos_id?: number}>(name, payload)
    if (disposed || current !== serial) return
    notice.value = 'barsy_' + result.status
    if (result.status === 'ready') {
      if (check) pos.value = result.pos_id ?? null
      else { rows.value = result.items; more.value = result.has_more }
    }
  } catch { if (!disposed && current === serial) notice.value = 'barsy_unavailable' }
  finally { if (!disposed && current === serial) loading.value = false }
}
function page(delta: number) { offset.value += delta * (section.value === 'articles' ? 50 : 20); request() }
onMounted(access)
</script>
<template>
  <UiSurface><main class="ui-section ui-stack cc-local">
    <header><h1>Barsy</h1><UiButton @click="refreshAccess">{{ t('refresh') }}</UiButton></header>
    <CommerceSetup v-if="can('commerce_settings')"/>
    <p v-if="!allowed.length" role="status">{{ t('access_is_unavailable') }}</p>
    <details class="cc-reference"><summary>{{t('barsy_reference_catalogue')}}</summary>
    <div class="ui-stack">
    <p>{{ t('barsy_setup_in_core') }}</p>
    <p>{{ t('barsy_read_only') }}</p>
    <UiButton v-if="can('barsy_check')" :disabled="loading" @click="request(true)">{{ t('barsy_check_connection') }}</UiButton>
    <p v-if="loading" role="status">{{ t('loading') }}</p>
    <p v-if="notice" role="status" :class="{'cc-error': notice !== 'barsy_ready'}">{{ t(notice) }}<span v-if="pos !== null"> · {{ t('barsy_pos') }} {{ pos }}</span></p>
    <nav :aria-label="t('sections')">
      <UiButton v-for="name in ['articles','places','units','categories']" v-show="can('barsy_' + name)" :key="name" :aria-pressed="section === name" :disabled="loading" @click="choose(name)">{{ t(name==='categories'?'commerce_categories':'barsy_' + name) }}</UiButton>
    </nav>
    <section v-if="can(operation)">
      <form class="cc-toolbar" @submit.prevent="offset = 0; request()">
        <UiField v-if="section === 'articles'" id="barsy-search" v-model="query" :label="t('search')" :disabled="loading" :maxlength="120" />
        <UiButton type="submit" :disabled="loading">{{ section === 'articles' ? t('search') : t('barsy_load') }}</UiButton>
      </form>
      <p v-if="notice === 'barsy_ready' && !loading && !rows.length && pos === null">{{ t('no_records') }}</p>
      <div v-if="rows.length" class="cc-table ui-table"><table>
        <thead><tr><th v-if="section !== 'articles' && section !== 'categories'">{{ t('barsy_identifier') }}</th><template v-if="section === 'units'"><th>{{ t('barsy_precision') }}</th><th>{{ t('barsy_time_interval') }}</th></template><template v-else><th>{{ t('barsy_name') }}</th><th v-if="section === 'places'">{{ t('barsy_open_accounts') }}</th></template></tr></thead>
        <tbody><tr v-for="row in rows" :key="row.article_id ?? row.place_id ?? row.unit_id ?? row.category_id">
          <td v-if="section !== 'articles' && section !== 'categories'">{{ row.place_id ?? row.unit_id }}</td>
          <template v-if="section === 'units'"><td>{{ row.precision ?? t('barsy_unknown') }}</td><td>{{ row.time_interval ?? t('barsy_unknown') }}</td></template>
          <template v-else><td>{{ row.label }}</td><td v-if="section === 'places'">{{ row.accounts_count ?? t('barsy_unknown') }}</td></template>
        </tr></tbody>
      </table></div>
      <div class="cc-toolbar"><UiButton :disabled="loading || offset === 0" @click="page(-1)">{{ t('previous') }}</UiButton><UiButton :disabled="loading || !more" @click="page(1)">{{ t('next') }}</UiButton></div>
    </section>
    </div></details>
  </main></UiSurface>
</template>
