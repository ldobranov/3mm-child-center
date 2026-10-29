<script setup lang="ts">
import { UiButton, UiDialog, UiSurface } from '@3mm/ui/v1'
import { provideApplicationLocale } from './i18n'
import { computed, onMounted, onUnmounted, ref, watch } from 'vue'
import { formatTimestamp } from './time'
import type { ApplicationPayload } from '@3mm/application-ui/v1'
import { useLocal } from './use-local'
import ClientForm from './ClientForm.vue'
import Status from './Status.vue'
import './local.css'
type Registration = { registration_id: string; guardian_name: string; status: string }
type Child = { child_id: string; display_name: string; assignment_id: string | null }
type Detail = { registration_id: string; status: string; guardian: { display_name: string; phone: string; email: string }; children: Child[] }
type Visit = { visit_id: string; child_name: string; phase: string; duration_seconds: number; rounded_minutes: number; last_transition_at: string; entered_at: string; exited_at: string | null }
type StayDetail = Visit & {guardian_name:string;timeline_complete:boolean;event_total:number;events:{event_id:string;kind:string;occurred_at:string;phase:string;duration_seconds:number}[]}
type Scan = {child_name:string;phase:string;action:string;preview_token:string;visit_id:string|null}
const props = withDefaults(defineProps<{ initialSection?: string; locale?: string }>(), { initialSection: 'clients' })
const strings = provideApplicationLocale(computed(() => props.locale))
const { t, stateLabel } = strings
const { allowed, busy, error, pending, access, can, read, readFailure, command, resolve, reviewed } = useLocal(strings)
const section = ref(props.initialSection), query = ref(''), filter = ref('all'), offset = ref(0), total = ref(0)
const rows = ref<Registration[]>([]), selected = ref<Detail | null>(null), formKey = ref(0), creating = ref(false)
const visits = ref<Visit[]>([]), visitState = ref('active'), visitOffset = ref(0), visitTotal = ref(0)
const code = ref(''), loading = ref(false)
const bracelets = ref<Record<string, string>>({})
const choices = ref<{article_id:number;label:string}[]>([])
const finishTarget = ref<Visit | null>(null)
const scan = ref<Scan|null>(null), scanning = ref(false), stayDetail = ref<StayDetail|null>(null), eventOffset = ref(0)
const stayOpen = ref(false), stayLoading = ref(false), stayError = ref(''), stayTarget = ref('')
const stayQuery = ref(''), startedFrom = ref(''), startedTo = ref('')
const visitSnapshotAt = ref(0), visitClock = ref(0)
let readSerial = 0, detailSerial = 0, scanSerial = 0, staySerial = 0, disposed = false
let visitTimer: number | undefined
function updateVisitClock() { if (section.value === 'visits' && visits.value.some(visit => visit.phase === 'inside')) visitClock.value = performance.now() }
onMounted(() => { visitTimer = window.setInterval(updateVisitClock, 1000); document.addEventListener('visibilitychange', updateVisitClock) })
onUnmounted(() => { disposed = true; readSerial++; detailSerial++; scanSerial++; staySerial++; window.clearInterval(visitTimer); document.removeEventListener('visibilitychange', updateVisitClock) })
watch(code, () => { scan.value = null; scanSerial++; scanning.value = false })
const at = (value: string | null | undefined) => value ? formatTimestamp(value,strings.locale.value) : t('ongoing')
function displayedSeconds(visit: Visit) {
  return visit.duration_seconds + (visit.phase === 'inside' ? Math.max(0, Math.floor((visitClock.value - visitSnapshotAt.value) / 1000)) : 0)
}
async function previewScan() {
  if (!can('preview_scan') || !code.value.trim() || busy.value || pending.value) return
  const serial = ++scanSerial, value = code.value
  scan.value = null; scanning.value = true; error.value = ''
  try {
    const result = await read<Scan>('preview_scan', {code:value})
    if (!disposed && serial === scanSerial) scan.value = result
  } catch { if (!disposed && serial === scanSerial) error.value = 'bracelet_preview_unavailable' }
  finally { if (!disposed && serial === scanSerial) scanning.value = false }
}
async function inspectStay(id: string, start = 0) {
  if (disposed || !can('get_visit')) return
  if (!pending.value && error.value === 'read_unavailable') error.value = ''
  const serial = ++staySerial
  stayOpen.value = true; stayLoading.value = true; stayError.value = ''; stayTarget.value = id
  stayDetail.value = null; eventOffset.value = start
  try {
    const result = await read<StayDetail>('get_visit',{visit_id:id,offset:start,limit:20})
    if (!disposed && serial === staySerial) stayDetail.value = result
  } catch (failure) {
    if (!disposed && serial === staySerial) {
      readFailure(failure)
      if (!can('get_visit')) closeStay()
      else stayError.value = error.value
    }
  } finally { if (!disposed && serial === staySerial) stayLoading.value = false }
}
function closeStay() {
  staySerial++; stayOpen.value = false; stayLoading.value = false; stayDetail.value = null; stayError.value = ''
}
watch(section, closeStay)
async function refresh() {
  if (startedFrom.value && startedTo.value && startedFrom.value > startedTo.value) { error.value = 'invalid_stay_dates'; return }
  if (!pending.value) error.value = ''
  const serial = ++readSerial
  detailSerial++
  scanSerial++; closeStay(); scan.value = null; scanning.value = false
  const clientRequest = { query: query.value, status: filter.value, offset: offset.value, limit: 20 }
  const visitRequest = { state: visitState.value, offset: visitOffset.value, limit: 20,
    query:stayQuery.value,started_from:startedFrom.value || null,started_to:startedTo.value || null }
  loading.value = true
  // Remove personal data before rechecking a possibly revoked session.
  rows.value = []; visits.value = []; selected.value = null; total.value = 0; visitTotal.value = 0
  finishTarget.value = null; code.value = ''
  await access()
  if (disposed || serial !== readSerial) return
  if (!can('list_registrations') && can('list_visits')) section.value = 'visits'
  try {
    const [clients, stays, catalogue] = await Promise.all([
      can('list_registrations') ? read<{ items: Registration[]; total: number }>('list_registrations', clientRequest) : null,
      can('list_visits') ? read<{ items: Visit[]; total: number }>('list_visits', visitRequest).then(data => ({data, observedAt:performance.now()})) : null,
      can('registration_choices') ? read<{items:{article_id:number;label:string}[]}>('registration_choices',{}) : null,
    ])
    if (disposed || serial !== readSerial) return
    if (clients) { rows.value = clients.items; total.value = clients.total }
    if (stays) { visits.value = stays.data.items; visitTotal.value = stays.data.total; visitSnapshotAt.value = stays.observedAt; visitClock.value = performance.now() }
    choices.value=catalogue?.items||[]
  } catch (failure) {
    if (disposed || serial !== readSerial) return
    rows.value = []; visits.value = []
    readFailure(failure)
  }
  finally { if (!disposed && serial === readSerial) loading.value = false }
}
async function detail(id: string) {
  const serial = ++detailSerial
  selected.value = null; bracelets.value = {}
  try {
    const result = await read<Detail>('get_registration', { registration_id: id })
    if (!disposed && serial === detailSerial) selected.value = result
  }
  catch { if (!disposed && serial === detailSerial) error.value = 'read_unavailable' }
}
async function mutate(operation: string, payload: ApplicationPayload) {
  const result = await command(operation, payload)
  if (operation === 'confirm_scan' && !pending.value) scan.value = null
  if (result) { code.value = ''; bracelets.value = {}; creating.value = false; formKey.value++; await refresh() }
}
async function review() { await resolve(); await refresh() }
onMounted(refresh)
</script>
<template>
  <UiSurface><main class="ui-section ui-stack cc-local">
    <header><div><p>{{ t('registrations_and_stays') }}</p><h1>{{ t('child_center') }}</h1></div><div><UiButton :disabled="loading" @click="refresh">{{ t('refresh') }}</UiButton></div></header>
    <Status :busy="busy" :error="error" :pending="pending" @resolve="review" @reviewed="reviewed(); refresh()" />
    <p v-if="!allowed.length" role="status">{{ t('access_is_unavailable') }}</p>
    <nav :aria-label="t('sections')"><UiButton v-if="can('list_registrations')" :aria-pressed="section === 'clients'" @click="section = 'clients'">{{ t('clients') }}</UiButton><UiButton v-if="can('list_visits')" :aria-pressed="section === 'visits'" @click="section = 'visits'">{{ t('stays') }}</UiButton></nav>
    <p v-if="loading" role="status">{{ t('loading') }}</p>
    <section v-if="section === 'clients' && can('list_registrations')">
      <form class="cc-toolbar" @submit.prevent="offset = 0; refresh()">
        <label>{{ t('search') }}<input class="ui-control" v-model="query" maxlength="120" /></label>
        <label>{{ t('status') }}<select class="ui-control" v-model="filter"><option value="all">{{ t('all') }}</option><option value="submitted">{{ t('pending') }}</option><option value="approved">{{ t('approved') }}</option></select></label>
        <UiButton variant="primary" type="submit">{{ t('search') }}</UiButton><UiButton v-if="can('register_client')" type="button" @click="creating = !creating">{{ t('new_client') }}</UiButton>
      </form>
      <ClientForm v-if="creating" :key="formKey" :choices="choices" :disabled="busy || !!pending" @submit="mutate('register_client', $event)" />
      <div class="cc-grid">
        <section><h2>{{ t('registrations') }} · {{ total }}</h2>
          <p v-if="!loading && !rows.length">{{ t('no_records') }}</p>
          <ul class="cc-client-list"><li v-for="row in rows" :key="row.registration_id"><button type="button" class="cc-row cc-client-row" :aria-pressed="selected?.registration_id === row.registration_id" @click="detail(row.registration_id)"><strong>{{ row.guardian_name }}</strong><span class="cc-client-status">{{ stateLabel(row.status) }}</span></button></li></ul>
          <div class="cc-toolbar"><UiButton :disabled="offset === 0" @click="offset -= 20; refresh()">{{ t('previous') }}</UiButton><UiButton :disabled="offset + 20 >= total" @click="offset += 20; refresh()">{{ t('next') }}</UiButton></div>
        </section>
        <section v-if="selected" class="cc-client-detail"><h2>{{ selected.guardian.display_name }}</h2><p class="cc-muted">{{ stateLabel(selected.status) }}</p><p>{{ selected.guardian.phone }}<template v-if="selected.guardian.email"> · {{ selected.guardian.email }}</template></p>
          <UiButton v-if="selected.status === 'submitted' && can('approve_registration')" :disabled="busy || !!pending" @click="mutate('approve_registration', { registration_id: selected.registration_id })">{{ t('approve') }}</UiButton>
          <article v-for="child in selected.children" :key="child.child_id">
            <h3>{{ child.display_name }}</h3><p>{{ child.assignment_id ? t('bracelet_assigned') : t('no_bracelet') }}</p>
            <form v-if="selected.status === 'approved' && can('assign_identifier')" @submit.prevent="mutate('assign_identifier', { child_id: child.child_id, code: bracelets[child.child_id] || '', expected_assignment_id: child.assignment_id })">
              <label>{{ t('scan_or_enter_bracelet') }}<input class="ui-control" v-model="bracelets[child.child_id]" required maxlength="512" autocomplete="off" /></label>
              <UiButton variant="primary" type="submit" :disabled="busy || !!pending">{{ t('assign') }}</UiButton>
              <UiButton v-if="child.assignment_id && can('retire_identifier')" type="button" :disabled="busy || !!pending" @click="mutate('retire_identifier', { child_id: child.child_id, expected_assignment_id: child.assignment_id })">{{ t('retire') }}</UiButton>
            </form>
          </article>
        </section>
      </div>
    </section>
    <section v-if="section === 'visits' && can('list_visits')">
      <form v-if="can('preview_scan')" @submit.prevent="previewScan">
        <fieldset :disabled="busy || !!pending"><legend>{{ t('record_a_transition') }}</legend>
          <label>{{ t('bracelet') }}<input class="ui-control" v-model="code" required maxlength="512" autocomplete="off" /></label><UiButton variant="primary" type="submit" :disabled="scanning">{{ t('identify_bracelet') }}</UiButton>
          <section v-if="scan" class="cc-review" aria-live="polite"><h3>{{ scan.child_name }}</h3><p>{{ stateLabel(scan.phase) }}</p>
            <UiButton v-if="can('confirm_scan')" type="button" @click="mutate('confirm_scan',{code,preview_token:scan.preview_token})">{{ scan.action === 'start' ? t('confirm_entry') : scan.action === 'pause' ? t('confirm_pause') : t('confirm_resume') }}</UiButton>
          </section>
        </fieldset>
      </form>
      <div class="cc-stay-filters"><label>{{ t('show') }}<select class="ui-control" v-model="visitState" @change="visitOffset = 0; refresh()"><option value="active">{{ t('active') }}</option><option value="closed">{{ t('history') }}</option></select></label>
      <form class="cc-toolbar" @submit.prevent="visitOffset = 0; refresh()">
        <label>{{ t('search_parent_or_child') }}<input class="ui-control" v-model="stayQuery" maxlength="120" /></label>
        <label>{{ t('started_from') }}<input class="ui-control" v-model="startedFrom" type="date" /></label>
        <label>{{ t('started_to') }}<input class="ui-control" v-model="startedTo" type="date" /></label>
        <UiButton type="submit" :disabled="loading">{{ t('search') }}</UiButton>
      </form></div><p class="cc-muted">{{ t('sofia_time') }} {{ t('live_stay_time_notice') }}</p>
      <p v-if="!loading && !visits.length">{{ t('no_stays') }}</p>
      <section v-if="finishTarget" class="cc-review" role="region" :aria-label="t('finish_stay_confirmation')">
        <h2>{{ t('finish_stay_confirmation') }}</h2>
        <p><strong>{{ finishTarget.child_name }}</strong> · {{ stateLabel(finishTarget.phase) }}</p>
        <p>{{ t('finishing_stops_time_tracking_for_this_stay') }}</p>
        <UiButton :disabled="busy || !!pending" @click="mutate('finish_visit', { visit_id: finishTarget.visit_id, expected_transition_at: finishTarget.last_transition_at, expected_phase: finishTarget.phase })">{{ t('confirm_finish') }}</UiButton>
        <UiButton :disabled="busy" @click="finishTarget = null">{{ t('cancel') }}</UiButton>
      </section>
      <div class="cc-table ui-table cc-stays"><table><thead><tr><th>{{ t('child') }}</th><th>{{ t('state') }}</th><th>{{ t('entered_at') }}</th><th>{{ t('exited_at') }}</th><th>{{ t('time') }}</th><th>{{ t('action') }}</th></tr></thead><tbody>
        <tr v-for="visit in visits" :key="visit.visit_id"><td :data-label="t('child')"><strong>{{ visit.child_name }}</strong></td><td :data-label="t('state')"><span class="cc-client-status">{{ stateLabel(visit.phase) }}</span></td><td :data-label="t('entered_at')">{{ at(visit.entered_at) }}</td><td :data-label="t('exited_at')">{{ at(visit.exited_at) }}</td><td :data-label="t('time')">{{ Math.floor(displayedSeconds(visit) / 60) }}{{ t('m') }} {{ displayedSeconds(visit) % 60 }}{{ t('s') }}</td><td :data-label="t('action')"><div class="cc-stay-actions">
          <UiButton v-if="can('get_visit')" @click="inspectStay(visit.visit_id)">{{ t('stay_details') }}</UiButton>
          <UiButton v-if="visit.phase !== 'closed' && can('finish_visit')" variant="primary" :disabled="busy || !!pending" @click="finishTarget = visit">{{ t('finish_stay') }}</UiButton>
        </div></td></tr>
      </tbody></table></div>
      <div class="cc-toolbar"><UiButton :disabled="visitOffset === 0" @click="visitOffset -= 20; refresh()">{{ t('previous') }}</UiButton><span>{{ visitTotal }}</span><UiButton :disabled="visitOffset + 20 >= visitTotal" @click="visitOffset += 20; refresh()">{{ t('next') }}</UiButton></div>
      <UiDialog v-if="stayOpen" :open="stayOpen" :title="t('stay_details')" :close-label="t('close')" @update:open="!$event && closeStay()">
        <div class="ui-stack" :aria-busy="stayLoading">
          <p v-if="stayLoading" role="status">{{ t('loading') }}</p>
          <template v-if="stayError"><p role="alert" class="cc-error">{{ t(stayError) }}</p><UiButton @click="inspectStay(stayTarget,eventOffset)">{{ t('refresh') }}</UiButton></template>
          <template v-if="stayDetail">
            <h3>{{ stayDetail.child_name }} · {{ stayDetail.guardian_name }}</h3>
            <p v-if="!stayDetail.timeline_complete">{{ t('historical_snapshot_notice') }}</p>
            <p v-if="!stayDetail.events.length">{{ t('no_records') }}</p>
            <ol><li v-for="event in stayDetail.events" :key="event.event_id">{{ at(event.occurred_at) }} · {{ t('event_' + event.kind) }} · {{ Math.floor(event.duration_seconds / 60) }}{{ t('m') }} {{ event.duration_seconds % 60 }}{{ t('s') }}</li></ol>
            <div class="cc-toolbar"><UiButton :disabled="stayLoading || eventOffset === 0" @click="inspectStay(stayDetail.visit_id,eventOffset-20)">{{ t('previous') }}</UiButton><UiButton :disabled="stayLoading || eventOffset+20 >= stayDetail.event_total" @click="inspectStay(stayDetail.visit_id,eventOffset+20)">{{ t('next') }}</UiButton></div>
          </template>
        </div>
        <template #actions><UiButton @click="closeStay">{{ t('close') }}</UiButton></template>
      </UiDialog>
    </section>
  </main></UiSurface>
</template>
