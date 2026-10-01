<template>
  <main ref="kioskRoot" class="cc-page cc-page--kiosk" :class="{ 'cc-page--fullscreen': isFullscreen }">
    <section class="cc-card" aria-labelledby="registration-title">
      <header class="cc-header">
        <div>
          <p class="cc-eyebrow">{{ t('Детски център', 'Child Center') }}</p>
          <h1 id="registration-title">{{ t('Регистрация за посещение', 'Visit registration') }}</h1>
        </div>
        <div class="cc-header-actions">
          <button
            v-if="fullscreenAvailable"
            type="button"
            class="cc-fullscreen"
            :aria-pressed="isFullscreen"
            @click="toggleFullscreen"
          >
            <span aria-hidden="true">{{ isFullscreen ? '×' : '⛶' }}</span>
            {{ isFullscreen ? t('Изход', 'Exit') : t('Цял екран', 'Fullscreen') }}
          </button>
          <button type="button" class="cc-language" :aria-label="t('Смени езика', 'Change language')" @click="toggleLanguage">
            {{ language === 'bg' ? 'EN' : 'BG' }}
          </button>
        </div>
      </header>

      <p v-if="fullscreenError" class="cc-error" role="alert">{{ fullscreenError }}</p>

      <div v-if="sessionBusy" class="cc-session-state" role="status">
        <h2>{{ t('Свързване на таблета…', 'Connecting the tablet…') }}</h2>
      </div>

      <form v-else-if="!kioskReady" class="cc-enrollment" @submit.prevent="enrollTablet">
        <h2>{{ t('Активиране на таблет', 'Activate tablet') }}</h2>
        <p>{{ t('Въведете еднократния код, създаден от администратор в настройките на детския център.', 'Enter the one-time code created by an administrator in Child Center settings.') }}</p>
        <label class="cc-field">
          <span>{{ t('Код за активиране', 'Activation code') }}</span>
          <input v-model.trim="enrollmentCode" required minlength="16" maxlength="128" autocomplete="one-time-code" />
        </label>
        <p v-if="error" class="cc-error" role="alert">{{ error }}</p>
        <button class="cc-button cc-button--primary" type="submit" :disabled="busy">
          {{ busy ? t('Активиране…', 'Activating…') : t('Активирай таблета', 'Activate tablet') }}
        </button>
      </form>

      <div v-else-if="completed" class="cc-success" role="status">
        <h2>{{ t('Регистрацията е изпратена', 'Registration submitted') }}</h2>
        <p>{{ t('Покажете този номер на оператора:', 'Show this number to the operator:') }}</p>
        <strong>{{ completed.registration_id }}</strong>
        <p>{{ t('Статус:', 'Status:') }} <strong>{{ completed.status === 'approved' ? t('Одобрена', 'Approved') : t('Чака одобрение', 'Pending approval') }}</strong></p>
        <p v-if="error" class="cc-error" role="alert">{{ error }}</p>
        <div class="cc-success-actions">
          <button type="button" class="cc-button" :disabled="busy" @click="checkStatus">{{ t('Провери статуса', 'Check status') }}</button>
          <button type="button" class="cc-button" :disabled="busy" @click="resetForm">{{ t('Нова регистрация', 'New registration') }}</button>
        </div>
      </div>

      <form v-else class="cc-form" @submit.prevent="submitRegistration">
        <fieldset>
          <legend>{{ t('Родител / придружител', 'Parent / guardian') }}</legend>
          <div class="cc-fields">
            <label class="cc-field cc-field--wide">
              <span>{{ t('Имена', 'Names') }}</span>
              <input v-model.trim="guardian.display_name" required maxlength="120" autocomplete="name" />
            </label>
            <label class="cc-field">
              <span>{{ t('Телефон', 'Phone') }}</span>
              <input v-model.trim="guardian.phone" type="tel" maxlength="40" autocomplete="tel" />
            </label>
            <label class="cc-field">
              <span>{{ t('Имейл', 'Email') }}</span>
              <input v-model.trim="guardian.email" type="email" maxlength="160" autocomplete="email" />
            </label>
          </div>
        </fieldset>

        <fieldset>
          <div class="cc-legend-row">
            <legend>{{ t('Деца', 'Children') }}</legend>
            <button v-if="children.length < 8" type="button" class="cc-link" @click="addChild">+ {{ t('Добави дете', 'Add child') }}</button>
          </div>
          <article v-for="(child, index) in children" :key="child.local_id" class="cc-child">
            <div class="cc-child-title">
              <h2>{{ t('Дете', 'Child') }} {{ index + 1 }}</h2>
              <button v-if="children.length > 1" type="button" class="cc-link cc-link--danger" @click="removeChild(index)">{{ t('Премахни', 'Remove') }}</button>
            </div>
            <label class="cc-field">
              <span>{{ t('Имена', 'Names') }}</span>
              <input v-model.trim="child.display_name" required maxlength="120" autocomplete="off" />
            </label>
<ConsumptionChoices v-model="child.allowed_consumption_codes" audience="kiosk" />
          </article>
        </fieldset>

        <label class="cc-consent">
          <input v-model="consented" type="checkbox" required />
          <span>{{ t('Потвърждавам данните за обслужване на посещението. След одобрение имената и контактите на родителя се предават към Barsy, а името на детето се показва към сметката.', 'I confirm the information for managing this visit. After approval, the parent name and contacts are shared with Barsy, and the child name appears on the account.') }}</span>
        </label>

        <p v-if="error" class="cc-error" role="alert">{{ error }}</p>
        <button class="cc-button cc-button--primary" type="submit" :disabled="busy || !consented || !hasContact">
          {{ busy ? t('Изпращане…', 'Submitting…') : t('Изпрати регистрацията', 'Submit registration') }}
        </button>
      </form>
    </section>
  </main>
</template>

<script setup lang="ts">
import { computed, onMounted, onUnmounted, reactive, ref } from 'vue'

import { createRequestId, invokeApplicationOperation } from './application-api'
import { claimKioskEnrollment, ensureKioskSession, hasStoredKioskIdentity } from './kiosk-session'
import { useChildCenterLanguage } from './language'
import ConsumptionChoices from './ConsumptionChoices.vue'

type ChildDraft = {
  local_id: string
  display_name: string
  allowed_consumption_codes: string[]
}

type SubmissionResult = {
  registration_id: string
  status: string
  receipt_token: string
}

type WebkitFullscreenElement = HTMLElement & {
  webkitRequestFullscreen?: () => Promise<void> | void
}

type WebkitFullscreenDocument = Document & {
  webkitFullscreenElement?: Element | null
  webkitExitFullscreen?: () => Promise<void> | void
}

const { language, t, toggleLanguage } = useChildCenterLanguage()

const guardian = reactive({ display_name: '', phone: '', email: '' })
const children = ref<ChildDraft[]>([newChild()])
const consented = ref(false)
const busy = ref(false)
const error = ref('')
const completed = ref<SubmissionResult | null>(null)
const kioskRoot = ref<HTMLElement | null>(null)
const fullscreenAvailable = ref(false)
const isFullscreen = ref(false)
const fullscreenError = ref('')
const sessionBusy = ref(true)
const kioskReady = ref(false)
const enrollmentCode = ref('')
const hasContact = computed(() => Boolean(guardian.phone.trim() || guardian.email.trim()))

function activeFullscreenElement(): Element | null {
  const fullscreenDocument = document as WebkitFullscreenDocument
  return document.fullscreenElement || fullscreenDocument.webkitFullscreenElement || null
}

function syncFullscreenState() {
  isFullscreen.value = activeFullscreenElement() === kioskRoot.value
  if (isFullscreen.value) fullscreenError.value = ''
}

async function toggleFullscreen() {
  const root = kioskRoot.value as WebkitFullscreenElement | null
  if (!root) return
  fullscreenError.value = ''
  try {
    const fullscreenDocument = document as WebkitFullscreenDocument
    if (activeFullscreenElement() === root) {
      if (typeof document.exitFullscreen === 'function') {
        await document.exitFullscreen()
      } else if (typeof fullscreenDocument.webkitExitFullscreen === 'function') {
        await fullscreenDocument.webkitExitFullscreen()
      }
    } else if (typeof root.requestFullscreen === 'function') {
      await root.requestFullscreen()
    } else if (typeof root.webkitRequestFullscreen === 'function') {
      await root.webkitRequestFullscreen()
    }
  } catch {
    fullscreenError.value = t(
      'Целият екран не може да бъде включен. Проверете разрешенията на браузъра.',
      'Fullscreen could not be enabled. Check the browser permissions.',
    )
  } finally {
    syncFullscreenState()
  }
}

function newChild(): ChildDraft {
  return { local_id: createRequestId(), display_name: '', allowed_consumption_codes: [] }
}

function addChild() {
  if (children.value.length < 8) children.value.push(newChild())
}

function removeChild(index: number) {
  if (children.value.length > 1) children.value.splice(index, 1)
}

function resetForm() {
  sessionStorage.removeItem('childCenterRegistrationReceipt')
  guardian.display_name = ''
  guardian.phone = ''
  guardian.email = ''
  children.value = [newChild()]
  consented.value = false
  completed.value = null
  error.value = ''
}

async function restoreKioskSession() {
  sessionBusy.value = true
  error.value = ''
  try {
    const storedIdentity = hasStoredKioskIdentity()
    const token = storedIdentity ? await ensureKioskSession() : null
    kioskReady.value = Boolean(token)
    if (storedIdentity && !token) resetForm()
  } catch (reason) {
    kioskReady.value = false
    error.value = reason instanceof Error ? reason.message : t('Kiosk сесията не може да бъде подновена.', 'The kiosk session could not be renewed.')
  } finally {
    sessionBusy.value = false
  }
}

async function enrollTablet() {
  busy.value = true
  error.value = ''
  try {
    await claimKioskEnrollment(enrollmentCode.value)
    enrollmentCode.value = ''
    resetForm()
    kioskReady.value = true
  } catch (reason) {
    error.value = reason instanceof Error ? reason.message : t('Таблетът не може да бъде активиран.', 'The tablet could not be activated.')
  } finally {
    busy.value = false
  }
}

async function submitRegistration() {
  busy.value = true
  error.value = ''
  try {
    const token = await ensureKioskSession()
    if (!token) {
      kioskReady.value = false
      resetForm()
      return
    }
    const result = await invokeApplicationOperation<SubmissionResult>(
      'kiosk',
      'submit_registration',
      token,
      {
        guardian: {
          display_name: guardian.display_name,
          phone: guardian.phone,
          email: guardian.email,
          consent_version: 'child-center-cc2-v1',
          consented_at: new Date().toISOString(),
        },
        children: children.value.map((child) => ({
          display_name: child.display_name,
          allowed_consumption_codes: child.allowed_consumption_codes,
        })),
      },
      createRequestId(),
    )
    sessionStorage.setItem('childCenterRegistrationReceipt', JSON.stringify({
      registration_id: result.registration_id,
      receipt_token: result.receipt_token,
    }))
    completed.value = result
  } catch (reason) {
    error.value = reason instanceof Error ? reason.message : t('Възникна неочаквана грешка.', 'An unexpected error occurred.')
  } finally {
    busy.value = false
  }
}

async function checkStatus() {
  if (!completed.value) return
  busy.value = true
  error.value = ''
  try {
    const token = await ensureKioskSession()
    if (!token) {
      kioskReady.value = false
      resetForm()
      return
    }
    const result = await invokeApplicationOperation<{ registration_id: string; status: string }>(
      'kiosk',
      'get_kiosk_registration_result',
      token,
      {
        registration_id: completed.value.registration_id,
        receipt_token: completed.value.receipt_token,
      },
    )
    completed.value.status = result.status
  } catch (reason) {
    error.value = reason instanceof Error ? reason.message : t('Възникна неочаквана грешка.', 'An unexpected error occurred.')
  } finally {
    busy.value = false
  }
}

onMounted(() => {
  const root = kioskRoot.value as WebkitFullscreenElement | null
  fullscreenAvailable.value = Boolean(root && (
    (typeof root.requestFullscreen === 'function' && document.fullscreenEnabled !== false) ||
    typeof root.webkitRequestFullscreen === 'function'
  ))
  document.addEventListener('fullscreenchange', syncFullscreenState)
  document.addEventListener('webkitfullscreenchange', syncFullscreenState)
  syncFullscreenState()
  try {
    const stored = JSON.parse(sessionStorage.getItem('childCenterRegistrationReceipt') || 'null')
    if (stored && typeof stored.registration_id === 'string' && typeof stored.receipt_token === 'string') {
      completed.value = { ...stored, status: 'submitted' }
    }
  } catch {
    sessionStorage.removeItem('childCenterRegistrationReceipt')
  }
  void restoreKioskSession()
})

onUnmounted(() => {
  document.removeEventListener('fullscreenchange', syncFullscreenState)
  document.removeEventListener('webkitfullscreenchange', syncFullscreenState)
})
</script>

<style scoped>
.cc-page {
  --text-color: var(--text-primary, #20242a);
  --muted-text-color: var(--text-secondary, #626b75);
  --surface-color: var(--card-bg, #fff);
  --surface-muted: var(--color-background-soft, var(--panel-bg, #f3f5f7));
  --border-color: var(--card-border, #d8dde3);
  --danger-color: var(--error-color, #b42318);
  min-height: 100%; padding: clamp(1rem, 4vw, 3rem); color: var(--text-color); background: var(--body-bg, #f3f5f7);
}
.cc-page--kiosk { display: grid; place-items: start center; }
.cc-card { width: min(100%, 54rem); padding: clamp(1.25rem, 4vw, 2.5rem); border: 1px solid var(--border-color, #d8dde3); border-radius: 1rem; background: var(--surface-color, #fff); box-shadow: 0 1rem 3rem rgb(19 28 38 / 8%); }
.cc-header, .cc-child-title, .cc-legend-row { display: flex; align-items: center; justify-content: space-between; gap: 1rem; }
.cc-header { align-items: flex-start; margin-bottom: 1.5rem; }
.cc-header-actions { display: flex; align-items: center; justify-content: flex-end; flex-wrap: wrap; gap: .55rem; }
.cc-eyebrow { margin: 0 0 .4rem; color: var(--primary-color, #356ae6); font-size: .78rem; font-weight: 700; letter-spacing: .08em; text-transform: uppercase; }
h1, h2 { margin: 0; } h1 { font-size: clamp(1.65rem, 5vw, 2.35rem); } h2 { font-size: 1.05rem; }
.cc-language, .cc-fullscreen { min-height: 2.5rem; padding: .4rem .7rem; border: 1px solid var(--border-color, #d8dde3); border-radius: 999px; color: inherit; background: var(--surface-color, #fff); font-weight: 700; cursor: pointer; }
.cc-language { min-width: 2.7rem; }
.cc-fullscreen { display: inline-flex; align-items: center; gap: .4rem; }
.cc-fullscreen span { font-size: 1.15rem; line-height: 1; }
.cc-form { display: grid; gap: 1.5rem; }
fieldset { min-width: 0; margin: 0; padding: 0; border: 0; }
legend { margin-bottom: .8rem; font-weight: 700; }
.cc-legend-row legend { margin: 0; }
.cc-fields { display: grid; grid-template-columns: 10rem 1fr; gap: .9rem; }
.cc-field { display: grid; gap: .4rem; color: var(--muted-text-color, #626b75); font-size: .88rem; }
.cc-field--wide { grid-column: 1 / -1; }
input, select, button { font: inherit; }
input:not([type='checkbox']), select { width: 100%; min-height: 2.85rem; padding: .65rem .75rem; border: 1px solid var(--input-border, var(--border-color, #cbd1d8)); border-radius: .55rem; color: var(--text-color, #20242a); background: var(--input-bg, var(--surface-color, #fff)); }
.cc-child { display: grid; gap: .85rem; margin-top: .8rem; padding: 1rem; border: 1px solid var(--border-color, #d8dde3); border-radius: .75rem; background: var(--surface-muted, #f7f8fa); }
.cc-consumption { display: flex; flex-wrap: wrap; gap: .65rem 1rem; color: var(--muted-text-color, #626b75); font-size: .88rem; }
.cc-consumption > span { flex-basis: 100%; }
.cc-check, .cc-consent { display: flex; align-items: flex-start; gap: .55rem; }
.cc-check input, .cc-consent input { width: 1.1rem; height: 1.1rem; margin-top: .1rem; accent-color: var(--primary-color, #356ae6); }
.cc-consent { line-height: 1.45; }
.cc-link { padding: .25rem; border: 0; color: var(--primary-color, #356ae6); background: transparent; cursor: pointer; }
.cc-link--danger, .cc-error { color: var(--danger-color, #b42318); }
.cc-error { margin: 0; padding: .75rem; border-radius: .55rem; background: var(--error-surface, rgb(180 35 24 / 8%)); }
.cc-button { min-height: 2.85rem; padding: .7rem 1rem; border: 1px solid var(--border-color, #cbd1d8); border-radius: .6rem; cursor: pointer; }
.cc-button--primary { border-color: var(--primary-color, #356ae6); color: var(--button-primary-text, #fff); background: var(--primary-color, #356ae6); }
.cc-button:disabled { cursor: not-allowed; opacity: .55; }
.cc-success { display: grid; gap: 1rem; text-align: center; }
.cc-success strong { overflow-wrap: anywhere; font-size: clamp(1rem, 3vw, 1.25rem); }
.cc-success p { margin: 0; color: var(--muted-text-color, #626b75); }
.cc-success-actions { display: flex; justify-content: center; flex-wrap: wrap; gap: .65rem; }
.cc-session-state, .cc-enrollment { display: grid; gap: 1rem; padding: clamp(1rem, 3vw, 1.5rem); border: 1px solid var(--border-color, #d8dde3); border-radius: .75rem; background: var(--surface-muted, #f7f8fa); }
.cc-session-state { min-height: 12rem; place-content: center; text-align: center; }
.cc-enrollment { max-width: 34rem; margin: 0 auto; }
.cc-enrollment p { margin: 0; color: var(--muted-text-color, #626b75); line-height: 1.5; }
.cc-page:fullscreen, .cc-page:-webkit-full-screen { width: 100vw; height: 100vh; min-height: 100vh; overflow-y: auto; padding: clamp(1rem, 3vw, 2rem); background: var(--body-bg, #f3f5f7); }
.cc-page:fullscreen .cc-card, .cc-page:-webkit-full-screen .cc-card { width: min(100%, 64rem); min-height: calc(100vh - clamp(2rem, 6vw, 4rem)); }
@media (max-width: 38rem) { .cc-fields { grid-template-columns: 1fr; } .cc-field--wide { grid-column: auto; } .cc-header { align-items: flex-start; flex-direction: column; } .cc-header-actions { width: 100%; justify-content: space-between; } }
</style>
