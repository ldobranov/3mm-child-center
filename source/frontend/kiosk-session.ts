import { getBackendBase } from './application-api'
import { getChildCenterLanguage } from './language'

const MODULE_ID = 'org.3mm.child-center'
const TERMINAL_ID_KEY = 'childCenterKioskTerminalId'
const CREDENTIAL_KEY = 'childCenterKioskCredential'
const ACCESS_TOKEN_KEY = 'childCenterKioskAccessToken'
const ACCESS_TOKEN_EXPIRY_KEY = 'childCenterKioskAccessTokenExpiresAt'

type EnrollmentResult = {
  code: string
  expires_at: string
}

type KioskIdentityResult = {
  terminal_id: string
  credential: string
  access_token: string
  expires_in_seconds: number
}

type KioskSessionResult = {
  access_token: string
  expires_in_seconds: number
}

export type KioskTerminal = {
  terminal_id: string
  label: string
  enabled: boolean
  created_at: string
  last_seen_at: string | null
  revoked_at: string | null
}

let refreshPromise: Promise<string | null> | null = null

class KioskIdentityUnavailableError extends Error {}

function localizedError(bg: string, en: string): Error {
  return new Error(getChildCenterLanguage() === 'bg' ? bg : en)
}

async function postJson<T>(
  path: string,
  payload: Record<string, unknown>,
  authorization?: string,
  clearIdentityOnUnauthorized = false,
): Promise<T> {
  const backendBase = await getBackendBase()
  const response = await fetch(`${backendBase}${path}`, {
    method: 'POST',
    headers: {
      'Content-Type': 'application/json',
      ...(authorization ? { Authorization: `Bearer ${authorization}` } : {}),
    },
    body: JSON.stringify(payload),
  })
  if (!response.ok) {
    if (clearIdentityOnUnauthorized && (response.status === 401 || response.status === 403)) {
      clearStoredKioskIdentity()
      throw new KioskIdentityUnavailableError('Kiosk identity is unavailable.')
    }
    throw localizedError(
      'Kiosk сесията не може да бъде създадена или подновена.',
      'The kiosk session could not be created or renewed.',
    )
  }
  return await response.json() as T
}

async function administratorRequest<T>(
  path: string,
  adminToken: string,
  method = 'GET',
): Promise<T> {
  const backendBase = await getBackendBase()
  const response = await fetch(`${backendBase}${path}`, {
    method,
    headers: { Authorization: `Bearer ${adminToken}` },
  })
  if (!response.ok) {
    throw localizedError(
      'Списъкът с таблети не може да бъде променен.',
      'The tablet list could not be changed.',
    )
  }
  return await response.json() as T
}

function storeAccessToken(accessToken: string, expiresInSeconds: number): string {
  localStorage.setItem(ACCESS_TOKEN_KEY, accessToken)
  localStorage.setItem(
    ACCESS_TOKEN_EXPIRY_KEY,
    String(Date.now() + Math.max(1, expiresInSeconds) * 1000),
  )
  return accessToken
}

export function clearStoredKioskIdentity(): void {
  localStorage.removeItem(TERMINAL_ID_KEY)
  localStorage.removeItem(CREDENTIAL_KEY)
  localStorage.removeItem(ACCESS_TOKEN_KEY)
  localStorage.removeItem(ACCESS_TOKEN_EXPIRY_KEY)
}

export function hasStoredKioskIdentity(): boolean {
  return Boolean(
    localStorage.getItem(TERMINAL_ID_KEY) && localStorage.getItem(CREDENTIAL_KEY),
  )
}

export async function createKioskEnrollment(
  label: string,
  adminToken: string,
): Promise<EnrollmentResult> {
  if (!adminToken) {
    throw localizedError(
      'Необходима е активна администраторска сесия.',
      'An active administrator session is required.',
    )
  }
  return await postJson<EnrollmentResult>(
    `/api/v1/application-extensions/${MODULE_ID}/kiosk/enrollments`,
    { label: label.trim(), expires_in_minutes: 15 },
    adminToken,
  )
}

export async function listKioskTerminals(adminToken: string): Promise<KioskTerminal[]> {
  const result = await administratorRequest<{ items: KioskTerminal[] }>(
    `/api/v1/application-extensions/${MODULE_ID}/kiosk/terminals`,
    adminToken,
  )
  return result.items
}

export async function revokeKioskTerminal(
  terminalId: string,
  adminToken: string,
): Promise<void> {
  await administratorRequest<{ status: 'revoked' }>(
    `/api/v1/application-extensions/${MODULE_ID}/kiosk/terminals/${encodeURIComponent(terminalId)}`,
    adminToken,
    'DELETE',
  )
}

export async function claimKioskEnrollment(code: string): Promise<string> {
  const result = await postJson<KioskIdentityResult>(
    `/api/v1/application-extensions/${MODULE_ID}/kiosk/enrollments/claim`,
    { code: code.trim() },
  )
  if (!result.terminal_id || !result.credential || !result.access_token) {
    throw localizedError(
      'Отговорът за kiosk регистрация е невалиден.',
      'The kiosk enrollment response is invalid.',
    )
  }
  localStorage.setItem(TERMINAL_ID_KEY, result.terminal_id)
  localStorage.setItem(CREDENTIAL_KEY, result.credential)
  return storeAccessToken(result.access_token, result.expires_in_seconds)
}

export async function ensureKioskSession(): Promise<string | null> {
  const terminalId = localStorage.getItem(TERMINAL_ID_KEY)
  const credential = localStorage.getItem(CREDENTIAL_KEY)
  if (!terminalId || !credential) return null

  if (!refreshPromise) {
    refreshPromise = postJson<KioskSessionResult>(
      `/api/v1/application-extensions/${MODULE_ID}/kiosk/sessions`,
      { terminal_id: terminalId, credential },
      undefined,
      true,
    ).then((result) => {
      if (!result.access_token) {
        throw localizedError(
          'Отговорът за kiosk сесия е невалиден.',
          'The kiosk session response is invalid.',
        )
      }
      return storeAccessToken(result.access_token, result.expires_in_seconds)
    }).catch((reason) => {
      if (reason instanceof KioskIdentityUnavailableError) return null
      throw reason
    }).finally(() => {
      refreshPromise = null
    })
  }
  return await refreshPromise
}
