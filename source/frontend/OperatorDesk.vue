<template>
  <main class="cc-page" aria-labelledby="operator-title">
    <header class="cc-header">
      <div>
        <p class="cc-eyebrow">{{ t('Оператор', 'Operator') }}</p>
        <h1 id="operator-title">{{ t('Работно място', 'Operator desk') }}</h1>
      </div>
      <div v-if="can('list_operator_clients') && section === 'clients'" class="cc-header-actions">
        <button v-if="can('register_client')" type="button" class="cc-button cc-button--primary" :disabled="busy" @click="startNewClient">
          {{ t('Нов клиент и гривна', 'New client and bracelet') }}
        </button>
        <label class="cc-filter">
          <span>{{ t('Покажи', 'Show') }}</span>
          <select v-model="statusFilter" :disabled="busy" @change="loadRegistrations()">
            <option value="submitted">{{ t('Чакащи', 'Pending') }}</option>
            <option value="approved">{{ t('Одобрени', 'Approved') }}</option>
            <option value="all">{{ t('Всички', 'All') }}</option>
          </select>
        </label>
        <button type="button" class="cc-button" :disabled="busy" @click="loadRegistrations()">{{ t('Обнови', 'Refresh') }}</button>
        <button type="button" class="cc-language" :aria-label="t('Смени езика', 'Change language')" @click="toggleLanguage">
          {{ language === 'bg' ? 'EN' : 'BG' }}
        </button>
      </div>
    </header>
    <nav class="cc-sections" :aria-label="t('Операторски секции', 'Operator sections')">
      <button v-if="can('list_operator_clients')" class="cc-button" :class="{ 'cc-button--primary': section === 'clients' && statusFilter === 'approved' }" @click="showClients('approved')">{{ t('Одобрени клиенти', 'Approved clients') }}</button>
      <button v-if="can('list_operator_clients')" class="cc-button" :class="{ 'cc-button--primary': section === 'clients' && statusFilter === 'submitted' }" @click="showClients('submitted')">{{ t('Чакащи одобрение', 'Pending approval') }}</button>
      <button v-if="can('list_active_visits')" class="cc-button" :class="{ 'cc-button--primary': section === 'stays' }" @click="section = 'stays'">{{ t('В залата', 'In the play area') }}</button>
      <button v-if="can('list_operator_accounts')" class="cc-button" :class="{ 'cc-button--primary': section === 'payment' }" @click="section = 'payment'">{{ t('За плащане', 'Awaiting payment') }}</button>
    </nav>
    <p v-if="!can('list_operator_clients') && !can('list_active_visits')" role="status">{{ t('Нямате предоставени права за работния екран. Обърнете се към администратор.', 'No desk permissions have been assigned. Contact an administrator.') }}</p>
    <ActiveVisits v-if="section !== 'clients' && can('list_active_visits')" embedded :account-filter="section === 'payment' ? 'closed' : 'open'" @playing-finished="section = 'payment'" />
    <div v-if="can('list_operator_clients')" v-show="section === 'clients'">

    <p v-if="error" class="cc-error" role="alert">{{ error }}</p>
    <p v-if="notice" class="cc-notice" role="status">{{ notice }}</p>

    <form v-if="creating" class="cc-create" @submit.prevent="registerClient">
      <div class="cc-detail-header">
        <div>
          <p class="cc-eyebrow">{{ t('Нова регистрация', 'New registration') }}</p>
          <h2>{{ t('Клиент и гривна', 'Client and bracelet') }}</h2>
        </div>
        <button type="button" class="cc-link" :disabled="busy" @click="creating = false">{{ t('Отказ', 'Cancel') }}</button>
      </div>

      <fieldset :disabled="busy">
        <legend>{{ t('Родител / придружител', 'Parent / guardian') }}</legend>
        <div class="cc-fields">
          <label class="cc-field cc-field--wide">
            <span>{{ t('Имена', 'Names') }}</span>
            <input v-model.trim="newClient.guardian.display_name" required maxlength="120" autocomplete="name" />
          </label>
          <label class="cc-field">
            <span>{{ t('Телефон', 'Phone') }}</span>
            <input v-model.trim="newClient.guardian.phone" type="tel" maxlength="40" autocomplete="tel" />
          </label>
          <label class="cc-field">
            <span>{{ t('Имейл', 'Email') }}</span>
            <input v-model.trim="newClient.guardian.email" type="email" maxlength="160" autocomplete="email" />
          </label>
        </div>
      </fieldset>

      <fieldset :disabled="busy">
        <legend>{{ t('Дете и гривна', 'Child and bracelet') }}</legend>
        <div class="cc-fields">
          <label class="cc-field cc-field--wide">
            <span>{{ t('Имена на детето', 'Child name') }}</span>
            <input v-model.trim="newClient.child.display_name" required maxlength="120" />
          </label>
          <label class="cc-field cc-field--wide">
            <span>{{ t('Код на гривната', 'Bracelet code') }}</span>
            <input
              v-model.trim="newClient.child.opaque_identifier"
              required
              maxlength="512"
              autocomplete="off"
              :placeholder="t('Сканирайте гривната или въведете кода', 'Scan the bracelet or enter its code')"
            />
          </label>
        </div>
<ConsumptionChoices v-model="newClient.child.allowed_consumption_codes" audience="operator" />
      </fieldset>

      <label class="cc-check cc-consent">
        <input v-model="consentConfirmed" type="checkbox" required />
        <span>{{ t('Родителят потвърди регистрацията и предаването на своите имена и контакти към Barsy, с име на детето към сметката.', 'The parent confirmed registration and sharing their name and contacts with Barsy, with the child name on the account.') }}</span>
      </label>

      <div class="cc-actions">
        <button type="button" class="cc-button" :disabled="busy" @click="creating = false">{{ t('Отказ', 'Cancel') }}</button>
        <button type="submit" class="cc-button cc-button--primary" :disabled="busy || !consentConfirmed || !hasNewClientContact">
          {{ t('Регистрирай клиента и гривната', 'Register client and bracelet') }}
        </button>
      </div>
    </form>

    <form v-if="!creating" class="cc-search" @submit.prevent="loadRegistrations()"><label>{{ t('Намери клиент', 'Find a client') }}<input v-model.trim="clientQuery" maxlength="120" :placeholder="t('Родител, дете, телефон или имейл', 'Parent, child, phone or email')" /></label><button class="cc-button" :disabled="busy">{{ t('Търси', 'Search') }}</button></form>
    <div v-if="!creating" class="cc-workspace">
      <aside class="cc-list" :aria-label="t('Регистрации', 'Registrations')">
        <div class="cc-list-title">
          <h2>{{ t('Регистрации', 'Registrations') }}</h2>
          <span>{{ registrations.length }}</span>
        </div>
        <button
          v-for="item in registrations"
          :key="item.registration_id"
          type="button"
          class="cc-list-item"
          :class="{ 'cc-list-item--active': detail?.registration_id === item.registration_id }"
          @click="loadDetail(item.registration_id)"
        >
          <strong>{{ item.guardian_display_name }}</strong>
          <span>{{ item.child_display_names.join(', ') }}</span>
          <span>{{ statusLabel(item.status) }}</span>
          <time>{{ formatDate(item.updated_at) }}</time>
        </button>
        <p v-if="!busy && registrations.length === 0" class="cc-empty">{{ t('Няма регистрации за избрания филтър.', 'No registrations match this filter.') }}</p>
        <button v-if="nextCursor" type="button" class="cc-button" :disabled="busy" @click="loadRegistrations(true)">{{ t('Още клиенти', 'More clients') }}</button>
      </aside>

      <section class="cc-detail" aria-live="polite">
        <div v-if="!detail" class="cc-empty cc-empty--detail">
          {{ t('Изберете регистрация за преглед.', 'Select a registration to review.') }}
        </div>

        <section v-else-if="detail.status === 'approved'" class="cc-form">
          <header><h2>{{ detail.guardian.display_name }}</h2><p>{{ detail.guardian.phone }} {{ detail.guardian.email }}</p></header>
          <article v-for="child in detail.children" :key="child.child_id" class="cc-child">
            <h3>{{ child.display_name }}</h3>
            <p>{{ activeAssignment(child) ? t('Гривната е свързана. Входът се отчита на входния четец.', 'Bracelet assigned. Entry is recorded at the entrance reader.') : t('Няма гривна — готово за даване.', 'No bracelet — ready to assign.') }}</p>
            <button v-if="can('assign_identifier')" type="button" class="cc-button cc-button--primary" :disabled="busy" @click="beginAttach(child.child_id)">{{ activeAssignment(child) ? t('Смени гривна', 'Replace bracelet') : t('Дай гривна', 'Give bracelet') }}</button>
            <form v-if="attachingChild === child.child_id" class="cc-attach" @submit.prevent="assignIdentifier(child.child_id)">
              <label>{{ t('Код на гривната', 'Bracelet code') }}<input :id="'attach-' + child.child_id" v-model.trim="identifierDrafts[child.child_id]" required maxlength="512" autocomplete="off" :disabled="busy" /></label>
              <small>{{ t('Ръчен код или клавиатурен скенер. Не използвайте входния четец за даване на гривна.', 'Type the code or use a keyboard scanner. Do not use the entrance reader to assign bracelets.') }}</small>
              <button class="cc-button" :disabled="busy">{{ t('Потвърди гривната', 'Confirm bracelet') }}</button>
              <button type="button" class="cc-link" :disabled="busy" @click="attachingChild = null">{{ t('Отказ', 'Cancel') }}</button>
            </form>
            <button v-if="can('retire_identifier') && activeAssignment(child)" type="button" class="cc-link" :disabled="busy" @click="retireIdentifier(activeAssignment(child)!.assignment_id)">{{ t('Откачи гривната', 'Detach bracelet') }}</button>
          </article>
        </section>
        <form v-else class="cc-form" @submit.prevent="saveCorrection">
          <div class="cc-detail-header">
            <div>
              <p class="cc-eyebrow">{{ shortId(detail.registration_id) }}</p>
              <h2>{{ t('Данни за регистрацията', 'Registration details') }}</h2>
            </div>
            <span class="cc-status">{{ statusLabel(detail.status) }}</span>
          </div>

          <fieldset :disabled="detail.status !== 'submitted' || busy">
            <legend>{{ t('Родител / придружител', 'Parent / guardian') }}</legend>
            <div class="cc-fields">
              <label class="cc-field cc-field--wide">
                <span>{{ t('Имена', 'Names') }}</span>
                <input v-model.trim="detail.guardian.display_name" required maxlength="120" />
              </label>
              <label class="cc-field">
                <span>{{ t('Телефон', 'Phone') }}</span>
                <input v-model.trim="detail.guardian.phone" type="tel" maxlength="40" autocomplete="tel" />
              </label>
              <label class="cc-field">
                <span>{{ t('Имейл', 'Email') }}</span>
                <input v-model.trim="detail.guardian.email" type="email" maxlength="160" autocomplete="email" />
              </label>
            </div>
          </fieldset>

          <fieldset>
            <legend>{{ t('Деца', 'Children') }}</legend>
            <article v-for="(child, index) in detail.children" :key="child.child_id" class="cc-child">
              <div class="cc-child-title">
                <h3>{{ t('Дете', 'Child') }} {{ index + 1 }}</h3>
                <span>{{ child.status === 'active' ? t('Активно', 'Active') : t('Чака одобрение', 'Pending approval') }}</span>
              </div>
              <label class="cc-field">
                <span>{{ t('Имена', 'Names') }}</span>
                <input v-model.trim="child.display_name" :disabled="detail.status !== 'submitted' || busy" required maxlength="120" />
              </label>
<ConsumptionChoices v-model="child.allowed_consumption_codes" audience="operator" :disabled="detail.status !== 'submitted' || busy" />

              <div v-if="detail.status === 'approved'" class="cc-identifier">
                <div>
                  <strong>{{ t('Гривна', 'Bracelet') }}</strong>
                  <p v-if="activeAssignment(child)">{{ t('Има активна гривна. Кодът не се показва.', 'An active bracelet is assigned. Its code is hidden.') }}</p>
                  <p v-else>{{ t('Няма регистрирана гривна.', 'No bracelet is assigned.') }}</p>
                </div>
                <div class="cc-identifier-actions">
                  <input
                    v-model.trim="identifierDrafts[child.child_id]"
                    maxlength="512"
                    autocomplete="off"
                    :placeholder="t('Сканирайте гривната или въведете кода', 'Scan the bracelet or enter its code')"
                    :aria-label="t('Код на гривната', 'Bracelet code')"
                  />
                  <button
                    type="button"
                    class="cc-button"
                    :disabled="busy || !identifierDrafts[child.child_id]"
                    @click="assignIdentifier(child.child_id)"
                  >
                    {{ activeAssignment(child) ? t('Смени гривната', 'Replace bracelet') : t('Регистрирай гривна', 'Assign bracelet') }}
                  </button>
                  <button
                    v-if="activeAssignment(child)"
                    type="button"
                    class="cc-link cc-link--danger"
                    :disabled="busy"
                    @click="retireIdentifier(activeAssignment(child)!.assignment_id)"
                  >
                    {{ t('Откачи гривната', 'Detach bracelet') }}
                  </button>
                </div>
              </div>
            </article>
          </fieldset>

          <div v-if="detail.status === 'submitted'" class="cc-actions">
            <button type="submit" class="cc-button" :disabled="busy">{{ t('Запази корекциите', 'Save changes') }}</button>
            <button type="button" class="cc-button cc-button--primary" :disabled="busy" @click="approveRegistration">{{ t('Одобри', 'Approve') }}</button>
          </div>
        </form>
      </section>
    </div>
    </div>
  </main>
</template>

<script setup lang="ts">
import { computed, inject, nextTick, onMounted, ref } from 'vue'

import { createRequestId, invokeApplicationOperation } from './application-api'
import { useChildCenterLanguage } from './language'
import ConsumptionChoices from './ConsumptionChoices.vue'
import ActiveVisits from './ActiveVisits.vue'

type RegistrationListItem = {
  registration_id: string
  status: string
  updated_at: string
  guardian_display_name: string
  child_display_names: string[]
}

type Assignment = {
  assignment_id: string
  assigned_at: string
  retired_at: string | null
  retire_reason: string | null
}

type ChildDetail = {
  child_id: string
  display_name: string
  allowed_consumption_codes: string[]
  status: string
  identifier_assignments: Assignment[]
}

type RegistrationDetail = {
  registration_id: string
  status: string
  submitted_at: string
  guardian: { guardian_id: string; display_name: string; phone: string; email: string }
  children: ChildDetail[]
}

type NewClient = {
  guardian: { display_name: string; phone: string; email: string }
  child: { display_name: string; allowed_consumption_codes: string[]; opaque_identifier: string }
}

const { language, locale, t, toggleLanguage } = useChildCenterLanguage()
const can = inject<(operation: string) => boolean>('childCenterCan', () => false)

const registrations = ref<RegistrationListItem[]>([])
const detail = ref<RegistrationDetail | null>(null)
const identifierDrafts = ref<Record<string, string>>({})
const statusFilter = ref<'submitted' | 'approved' | 'all'>('approved')
const clientQuery = ref(''), nextCursor = ref<string | null>(null)
const attachingChild = ref<string | null>(null)
const busy = ref(false)
const error = ref('')
const notice = ref('')
const creating = ref(false)
const section = ref<'clients' | 'stays' | 'payment'>('clients')
const consentConfirmed = ref(false)

function emptyNewClient(): NewClient {
  return {
    guardian: { display_name: '', phone: '', email: '' },
    child: { display_name: '', allowed_consumption_codes: [], opaque_identifier: '' },
  }
}

const newClient = ref<NewClient>(emptyNewClient())
const hasNewClientContact = computed(() => Boolean(
  newClient.value.guardian.phone.trim() || newClient.value.guardian.email.trim(),
))

async function invoke<T>(operation: string, payload: Record<string, unknown>, command = false): Promise<T> {
  if (!can(operation)) throw new Error(t('Нямате достъп до това действие.', 'You do not have access to this action.'))
  const token = localStorage.getItem('authToken') || ''
  return await invokeApplicationOperation<T>(
    'operator',
    operation,
    token,
    payload,
    command ? createRequestId() : undefined,
  )
}

function shortId(value: string) {
  return value.slice(-8).toUpperCase()
}

function formatDate(value: string) {
  return new Intl.DateTimeFormat(locale.value, { dateStyle: 'short', timeStyle: 'short' }).format(new Date(value))
}

function statusLabel(status: string) {
  if (status === 'approved') return t('Одобрена', 'Approved')
  if (status === 'rejected') return t('Отхвърлена', 'Rejected')
  return t('Чака одобрение', 'Pending approval')
}

function activeAssignment(child: ChildDetail) {
  return child.identifier_assignments.find((item) => item.retired_at === null)
}

function startNewClient() {
  newClient.value = emptyNewClient()
  consentConfirmed.value = false
  creating.value = true
  error.value = ''
  notice.value = ''
}

async function run(action: () => Promise<void>) {
  if (busy.value) return
  busy.value = true
  error.value = ''
  notice.value = ''
  try {
    await action()
  } catch (reason) {
    error.value = reason instanceof Error ? reason.message : t('Възникна неочаквана грешка.', 'An unexpected error occurred.')
  } finally {
    busy.value = false
  }
}

async function showClients(status: 'approved' | 'submitted') { if (busy.value) return; section.value = 'clients'; statusFilter.value = status; creating.value = false; await loadRegistrations() }
async function beginAttach(childId: string) { attachingChild.value = childId; identifierDrafts.value[childId] = ''; await nextTick(); document.getElementById('attach-' + childId)?.focus() }
async function loadRegistrations(append = false) {
  await run(async () => {
    const result = await invoke<{ items: RegistrationListItem[]; next_cursor: string | null }>('list_operator_clients', {
      query: clientQuery.value,
      status: statusFilter.value === 'all' ? null : statusFilter.value,
      cursor: append === true ? nextCursor.value : null,
      limit: 100,
    })
    registrations.value = append === true ? [...registrations.value, ...result.items] : result.items
    nextCursor.value = result.next_cursor
    if (detail.value && !registrations.value.some((item) => item.registration_id === detail.value?.registration_id)) {
      detail.value = null
    } else if (detail.value && !append) {
      detail.value = await invoke<RegistrationDetail>('get_registration', { registration_id: detail.value.registration_id })
      attachingChild.value = null
      identifierDrafts.value = {}
    }
  })
}

async function loadDetail(registrationId: string) {
  await run(async () => {
    detail.value = await invoke<RegistrationDetail>('get_registration', { registration_id: registrationId })
    identifierDrafts.value = {}
    attachingChild.value = null
  })
}

async function registerClient() {
  if (!consentConfirmed.value || !hasNewClientContact.value) return
  const form = newClient.value
  await run(async () => {
    const result = await invoke<{ registration_id: string }>('register_client', {
      guardian: {
        display_name: form.guardian.display_name,
        phone: form.guardian.phone,
        email: form.guardian.email,
        consent_version: 'operator-registration-v1',
        consented_at: new Date().toISOString(),
      },
      child: {
        display_name: form.child.display_name,
        allowed_consumption_codes: form.child.allowed_consumption_codes,
        opaque_identifier: form.child.opaque_identifier,
      },
    }, true)
    creating.value = false
    clientQuery.value = ''
    statusFilter.value = 'approved'
    const list = await invoke<{ items: RegistrationListItem[]; next_cursor: string | null }>('list_operator_clients', {
      query: '',
      status: 'approved',
      cursor: null,
      limit: 100,
    })
    registrations.value = list.items
    nextCursor.value = list.next_cursor
    detail.value = await invoke<RegistrationDetail>('get_registration', { registration_id: result.registration_id })
    identifierDrafts.value = {}
    notice.value = t('Клиентът е регистриран и гривната е активна.', 'The client is registered and the bracelet is active.')
  })
}

async function saveCorrection() {
  if (!detail.value) return
  const current = detail.value
  await run(async () => {
    await invoke('correct_registration', {
      registration_id: current.registration_id,
      guardian: {
        display_name: current.guardian.display_name,
        phone: current.guardian.phone,
        email: current.guardian.email,
      },
      children: current.children.map((child) => ({
        child_id: child.child_id,
        display_name: child.display_name,
        allowed_consumption_codes: child.allowed_consumption_codes,
      })),
    }, true)
    notice.value = t('Корекциите са запазени.', 'Changes saved.')
    detail.value = await invoke<RegistrationDetail>('get_registration', { registration_id: current.registration_id })
  })
}

async function approveRegistration() {
  if (!detail.value) return
  const registrationId = detail.value.registration_id
  await run(async () => {
    await invoke('approve_registration', { registration_id: registrationId }, true)
    detail.value = await invoke<RegistrationDetail>('get_registration', { registration_id: registrationId })
    if (statusFilter.value === 'submitted') {
      registrations.value = registrations.value.filter((item) => item.registration_id !== registrationId)
    } else {
      registrations.value = registrations.value.map((item) => (
        item.registration_id === registrationId ? { ...item, status: 'approved' } : item
      ))
    }
    notice.value = t('Регистрацията е одобрена. Вече може да се регистрира гривна.', 'Registration approved. A bracelet can now be assigned.')
  })
}

async function assignIdentifier(childId: string) {
  const opaqueIdentifier = identifierDrafts.value[childId]
  if (!detail.value || !opaqueIdentifier) return
  const registrationId = detail.value.registration_id
  const child = detail.value.children.find(c => c.child_id === childId)
  const previous = child ? activeAssignment(child) : undefined
  if (previous && !window.confirm(t('Да сменим гривната? Старата ще спре да работи; престоят се запазва.', 'Replace this bracelet? The old one will stop working; the stay is preserved.'))) return
  await run(async () => {
    await invoke('assign_identifier', { child_id: childId, opaque_identifier: opaqueIdentifier, expected_assignment_id: previous?.assignment_id || null }, true)
    identifierDrafts.value[childId] = ''
    detail.value = await invoke<RegistrationDetail>('get_registration', { registration_id: registrationId })
    attachingChild.value = null
    notice.value = t('Гривната е свързана. Готово за сканиране на входа.', 'Bracelet assigned. Ready to scan at the entrance.')
  })
}

async function retireIdentifier(assignmentId: string) {
  if (!detail.value) return
  if (!window.confirm(t('Да откачим гривната?', 'Detach this bracelet?'))) return
  const registrationId = detail.value.registration_id
  await run(async () => {
    await invoke('retire_identifier', { assignment_id: assignmentId, reason: 'manual' }, true)
    detail.value = await invoke<RegistrationDetail>('get_registration', { registration_id: registrationId })
    notice.value = t('Гривната е откачена.', 'Bracelet detached.')
  })
}

onMounted(() => { if (can('list_operator_clients')) void loadRegistrations(); else if (can('list_active_visits')) section.value = 'stays' })
</script>

<style scoped>
.cc-search { display: flex; gap: .7rem; align-items: end; margin: 1rem 0; }
.cc-search label { display: grid; gap: .4rem; flex: 1; min-width: 0; }
.cc-attach { display: grid; gap: .6rem; }
.cc-attach label { display: grid; gap: .4rem; }
input, select { box-sizing: border-box; min-width: 0; }
.cc-page {
  --text-color: var(--text-primary, #20242a);
  --muted-text-color: var(--text-secondary, #626b75);
  --surface-color: var(--card-bg, #fff);
  --surface-muted: var(--color-background-soft, var(--panel-bg, #f3f5f7));
  --border-color: var(--card-border, #d8dde3);
  --danger-color: var(--error-color, #b42318);
  max-width: 86rem; margin: 0 auto; padding: clamp(1rem, 3vw, 2.5rem); color: var(--text-color);
}
.cc-header, .cc-header-actions, .cc-detail-header, .cc-list-title, .cc-child-title, .cc-actions { display: flex; align-items: center; justify-content: space-between; gap: 1rem; }
.cc-header { align-items: flex-start; margin-bottom: 1.25rem; }
.cc-sections { display: flex; flex-wrap: wrap; gap: .6rem; margin-bottom: 1rem; }
.cc-eyebrow { margin: 0 0 .35rem; color: var(--primary-color, #356ae6); font-size: .75rem; font-weight: 700; letter-spacing: .08em; text-transform: uppercase; }
h1, h2, h3, p { margin-top: 0; } h1 { margin-bottom: 0; font-size: clamp(1.5rem, 4vw, 2.2rem); } h2 { margin-bottom: 0; font-size: 1.15rem; } h3 { margin-bottom: 0; font-size: 1rem; }
.cc-workspace { display: grid; grid-template-columns: minmax(14rem, 19rem) minmax(0, 1fr); min-height: 34rem; border: 1px solid var(--border-color, #d8dde3); border-radius: .9rem; overflow: hidden; background: var(--surface-color, #fff); }
.cc-create { display: grid; gap: 1.5rem; max-width: 54rem; padding: clamp(1rem, 3vw, 1.75rem); border: 1px solid var(--border-color, #d8dde3); border-radius: .9rem; background: var(--surface-color, #fff); }
.cc-list { border-right: 1px solid var(--border-color, #d8dde3); background: var(--surface-muted, #f7f8fa); }
.cc-list-title { padding: 1rem; border-bottom: 1px solid var(--border-color, #d8dde3); }
.cc-list-title span, .cc-status { padding: .3rem .55rem; border: 1px solid var(--border-color, #d8dde3); border-radius: 999px; color: var(--muted-text-color, #626b75); font-size: .75rem; }
.cc-list-item { width: 100%; padding: .85rem 1rem; display: grid; gap: .25rem; border: 0; border-bottom: 1px solid var(--border-color, #d8dde3); color: inherit; text-align: left; background: transparent; cursor: pointer; }
.cc-list-item span, .cc-list-item time { color: var(--muted-text-color, #626b75); font-size: .78rem; }
.cc-list-item--active { box-shadow: inset .2rem 0 var(--primary-color, #356ae6); background: var(--surface-color, #fff); }
.cc-filter { display: flex; align-items: center; gap: .5rem; color: var(--muted-text-color, #626b75); font-size: .82rem; }
.cc-detail { min-width: 0; padding: clamp(1rem, 3vw, 1.75rem); }
.cc-detail-header { align-items: flex-start; }
.cc-form { display: grid; gap: 1.5rem; }
fieldset { min-width: 0; margin: 0; padding: 0; border: 0; } legend { margin-bottom: .75rem; font-weight: 700; }
.cc-fields { display: grid; grid-template-columns: 10rem 1fr; gap: .8rem; }
.cc-field { display: grid; gap: .35rem; color: var(--muted-text-color, #626b75); font-size: .85rem; }
.cc-field--wide { grid-column: 1 / -1; }
input, select, button { font: inherit; }
input:not([type='checkbox']), select { width: 100%; min-height: 2.65rem; padding: .6rem .7rem; border: 1px solid var(--input-border, var(--border-color, #cbd1d8)); border-radius: .5rem; color: var(--text-color, #20242a); background: var(--input-bg, var(--surface-color, #fff)); }
.cc-child { display: grid; gap: .75rem; margin-top: .75rem; padding: 1rem; border: 1px solid var(--border-color, #d8dde3); border-radius: .7rem; background: var(--surface-muted, #f7f8fa); }
.cc-child-title span, .cc-consumption, .cc-identifier p { color: var(--muted-text-color, #626b75); font-size: .82rem; }
.cc-consumption { display: flex; flex-wrap: wrap; gap: .5rem 1rem; }
.cc-consumption > span { flex-basis: 100%; }
.cc-check { display: flex; align-items: center; gap: .4rem; }
.cc-check input { accent-color: var(--primary-color, #356ae6); }
.cc-consent { align-items: flex-start; padding: .85rem; border-radius: .55rem; background: var(--surface-muted, #f7f8fa); }
.cc-identifier { display: grid; grid-template-columns: minmax(9rem, 1fr) minmax(16rem, 2fr); gap: 1rem; padding-top: .8rem; border-top: 1px solid var(--border-color, #d8dde3); }
.cc-identifier p { margin: .3rem 0 0; }
.cc-identifier-actions { display: flex; flex-wrap: wrap; gap: .5rem; }
.cc-identifier-actions input { flex: 1 1 13rem; }
.cc-button { min-height: 2.65rem; padding: .6rem .85rem; border: 1px solid var(--border-color, #cbd1d8); border-radius: .5rem; color: inherit; background: var(--surface-color, #fff); cursor: pointer; }
.cc-button--primary { border-color: var(--primary-color, #356ae6); color: var(--button-primary-text, #fff); background: var(--primary-color, #356ae6); }
.cc-language { min-width: 2.7rem; min-height: 2.65rem; padding: .45rem .6rem; border: 1px solid var(--border-color, #cbd1d8); border-radius: 999px; color: inherit; background: var(--surface-color, #fff); font-weight: 700; cursor: pointer; }
.cc-button:disabled, .cc-link:disabled { cursor: not-allowed; opacity: .55; }
.cc-link { padding: .45rem; border: 0; color: var(--primary-color, #356ae6); background: transparent; cursor: pointer; }
.cc-link--danger, .cc-error { color: var(--danger-color, #b42318); }
.cc-error, .cc-notice { margin-bottom: 1rem; padding: .75rem 1rem; border-radius: .55rem; }
.cc-error { background: var(--error-surface, rgb(180 35 24 / 8%)); } .cc-notice { color: var(--success-color, #067647); background: var(--success-surface, rgb(6 118 71 / 8%)); }
.cc-empty { padding: 1rem; color: var(--muted-text-color, #626b75); } .cc-empty--detail { min-height: 25rem; display: grid; place-items: center; text-align: center; }
.cc-actions { justify-content: flex-end; }
@media (max-width: 52rem) { .cc-workspace { grid-template-columns: 1fr; } .cc-list { max-height: 18rem; overflow: auto; border-right: 0; border-bottom: 1px solid var(--border-color, #d8dde3); } }
@media (max-width: 38rem) { .cc-fields, .cc-identifier { grid-template-columns: 1fr; } .cc-field--wide { grid-column: auto; } .cc-header { align-items: stretch; flex-direction: column; } .cc-header-actions { justify-content: flex-start; flex-wrap: wrap; } .cc-actions { align-items: stretch; flex-direction: column; } }
</style>
