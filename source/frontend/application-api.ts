import { getChildCenterLanguage } from './language'

const MODULE_ID = 'org.3mm.child-center'
const CONNECTOR_ID = 'barsy_api'

type ApplicationAudience = 'kiosk' | 'operator' | 'administrator'

type RuntimeConfiguration = {
  backend_url?: unknown
  backend_port?: unknown
}

export type ApplicationSecretSummary = {
  secret_ref: string
  label: string
  credential_kind: 'basic' | 'bearer' | 'api_key'
  version: number
  revoked: boolean
}

export type ApplicationConnectorStatus = {
  connector_id: string
  destination_origin: string
  enabled: boolean
  last_outcome: string | null
  last_http_status: number | null
  last_checked_at: string | null
  last_error_category: string | null
}

type ApplicationOperationalStatus = {
  connectors: {
    items: ApplicationConnectorStatus[]
  }
}

let backendBasePromise: Promise<string> | null = null

function validatedOrigin(value: string): string {
  const parsed = new URL(value)
  if (!['http:', 'https:'].includes(parsed.protocol) || parsed.username || parsed.password) {
    throw new Error('Backend configuration is invalid.')
  }
  return parsed.origin
}

async function resolveBackendBase(): Promise<string> {
  const response = await fetch('/runtime-config.json', { cache: 'no-store' })
  if (!response.ok) throw new Error('Backend configuration is unavailable.')

  const configuration = await response.json() as RuntimeConfiguration
  if (typeof configuration.backend_url === 'string' && configuration.backend_url.trim()) {
    return validatedOrigin(configuration.backend_url.trim())
  }
  if (
    Number.isInteger(configuration.backend_port) &&
    Number(configuration.backend_port) > 0 &&
    Number(configuration.backend_port) <= 65535
  ) {
    return validatedOrigin(
      `${window.location.protocol}//${window.location.hostname}:${configuration.backend_port}`,
    )
  }
  throw new Error('Backend configuration does not define an API endpoint.')
}

export async function getBackendBase(): Promise<string> {
  if (!backendBasePromise) {
    backendBasePromise = resolveBackendBase().catch((reason) => {
      backendBasePromise = null
      throw reason
    })
  }
  return backendBasePromise
}

function responseMessage(status: number): string {
  const bg = getChildCenterLanguage() === 'bg'
  if (status === 401 || status === 403) return bg ? 'Нямате достъп до тази операция.' : 'You do not have access to this operation.'
  if (status === 404) return bg ? 'Операцията не е налична в активната версия.' : 'The operation is unavailable in the active version.'
  if (status === 409 || status === 422) return bg ? 'Данните са променени или не са валидни.' : 'The data has changed or is invalid.'
  if (status >= 500) return bg ? 'Услугата временно не може да изпълни операцията.' : 'The service is temporarily unavailable.'
  return bg ? 'Операцията не беше изпълнена.' : 'The operation failed.'
}

export function createRequestId(): string {
  const availableCrypto = globalThis.crypto
  if (availableCrypto && typeof availableCrypto.randomUUID === 'function') {
    return availableCrypto.randomUUID()
  }
  const bytes = new Uint8Array(16)
  if (availableCrypto && typeof availableCrypto.getRandomValues === 'function') {
    availableCrypto.getRandomValues(bytes)
  } else {
    for (let index = 0; index < bytes.length; index += 1) {
      bytes[index] = Math.floor(Math.random() * 256)
    }
  }
  bytes[6] = (bytes[6] & 0x0f) | 0x40
  bytes[8] = (bytes[8] & 0x3f) | 0x80
  const hex = Array.from(bytes, (value) => value.toString(16).padStart(2, '0')).join('')
  return `${hex.slice(0, 8)}-${hex.slice(8, 12)}-${hex.slice(12, 16)}-${hex.slice(16, 20)}-${hex.slice(20)}`
}

export async function invokeApplicationOperation<T>(
  audience: ApplicationAudience,
  operation: string,
  token: string,
  payload: Record<string, unknown>,
  idempotencyKey?: string,
): Promise<T> {
  const backendBase = await getBackendBase()
  const audiencePath = audience === 'administrator' ? '' : `/${audience}`
  const response = await fetch(
    `${backendBase}/api/v1/application-extensions/${MODULE_ID}${audiencePath}/operations/${operation}`,
    {
      method: 'POST',
      headers: {
        'Content-Type': 'application/json',
        Authorization: `Bearer ${token}`,
      },
      body: JSON.stringify({
        payload,
        ...(idempotencyKey ? { idempotency_key: idempotencyKey } : {}),
      }),
    },
  )
  if (!response.ok) {
    if (audience === 'operator' && [401, 403].includes(response.status)) window.dispatchEvent(new Event('child-center-access-denied'))
    throw Object.assign(new Error(responseMessage(response.status)), { httpStatus: response.status })
  }
  return await response.json() as T
}

async function administratorRequest<T>(
  token: string,
  path: string,
  method = 'GET',
  body?: Record<string, unknown>,
): Promise<T> {
  const backendBase = await getBackendBase()
  const response = await fetch(
    `${backendBase}/api/v1/application-extensions/${MODULE_ID}${path}`,
    {
      method,
      headers: {
        ...(body ? { 'Content-Type': 'application/json' } : {}),
        Authorization: `Bearer ${token}`,
      },
      ...(body ? { body: JSON.stringify(body) } : {}),
    },
  )
  if (!response.ok) throw new Error(responseMessage(response.status))
  return await response.json() as T
}

export async function listApplicationSecrets(token: string): Promise<ApplicationSecretSummary[]> {
  const result = await administratorRequest<{ items: ApplicationSecretSummary[] }>(token, '/secrets')
  return result.items.filter((item) => item.credential_kind === 'basic' && !item.revoked)
}

export async function createBasicApplicationSecret(
  token: string,
  label: string,
  username: string,
  password: string,
): Promise<ApplicationSecretSummary> {
  return await administratorRequest<ApplicationSecretSummary>(token, '/secrets', 'POST', {
    label,
    credential_kind: 'basic',
    value: { username, password },
  })
}

export async function configureBarsyConnector(
  token: string,
  destinationOrigin: string,
  secretRef: string,
): Promise<ApplicationConnectorStatus> {
  return await administratorRequest<ApplicationConnectorStatus>(
    token,
    `/connectors/${CONNECTOR_ID}`,
    'PUT',
    { destination_origin: destinationOrigin, secret_ref: secretRef },
  )
}

export async function getBarsyConnectorStatus(
  token: string,
): Promise<ApplicationConnectorStatus | null> {
  const result = await administratorRequest<ApplicationOperationalStatus>(
    token,
    '/operational-status',
  )
  return result.connectors.items.find((item) => item.connector_id === CONNECTOR_ID) || null
}
