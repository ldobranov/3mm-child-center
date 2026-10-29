# Public connector administration contract — proposal, not an implemented API

**Current integration status:** Core implemented a Core-owned settings gear in
Extensions instead of the proposed in-application facade. This satisfies the
chosen no-workaround setup path. The facade below remains historical proposal
text and must not be imported. Delivered 0.7.8/0.7.9 declare optional read-only
`barsy_api`; Core saves the origin/reference/binding/credential atomically, and
the application consumes only the existing SDK broker. No credential UI or
private HTTP/CLI fallback is added to the application. Exact-package tests cover
Core bootstrap/settings, real compiled UI provenance, native/resource approval,
fake HTTP with injected Basic authentication and denial after credential revoke.
Working source now explicitly declares mutating connector authority for the
interactive account/order/cashier workflow, tested against a local fake only.
It requires fresh approval of the exact future package. Periodic composition
remains separate; the proposed facade below is still not imported.

Scope agreed with the owner on 2026-10-27: prepare this contract in Child Center;
do not change Core or restore private HTTP/token calls. The connector broker
already exists. The missing part is safe, public, installation-scoped setup from
an administrator route, including bootstrap before connector authority is ready.

## Evidence from the current Core checkout

Read-only references, relative to the separate Core repository:

- `frontend/src/extension-ui/application-v1.ts`: public administration covers
  devices, modules, capabilities, commands and resource inspection. It has no
  connector or credential configuration API.
- `three_mm_protocol/application_extension.py:ApplicationRouteV1`: closed read/
  action allowlists likewise have no connector administration declarations.
- `backend/routes/application_operations.py`: protected administrator endpoints
  already list/create/rotate/revoke secrets, bind connectors and inspect status.
  Those REST endpoints are implementation dependencies, not application UI APIs.
- `backend/services/application_secrets.py`: Basic credentials are encrypted,
  owned by one installation and versioned. A missing encryption key refuses writes.
- `backend/services/application_connectors.py`: binding validates the declared
  origin/authentication and installation-owned, non-revoked credential. Authority
  writes advance the installation epoch/binding revision.
- `backend/services/application_authority_sources.py:_connector`: absent/disabled
  binding yields `connector_binding_unavailable`; origin must equal the configured
  origin and the secret reference/kind/version must match. This is a bootstrap
  constraint for native authority approval, not just a missing form field.

## Minimum public surface

Extend the existing public `ApplicationAdministration` with an optional
`connectors` facade. It is scoped by the host to the current installation and
approved artifact; callers cannot supply a module/installation ID, URL, headers,
credential value or arbitrary configuration patch. The host opens a **Core-owned
dialog** for origin and credential selection/creation/rotation/revocation. Secret
values never enter application components, invoke payloads, logs or SQLite.

Proposed TypeScript contract (names are proposals, not exports to import now):

```ts
type ConnectorAdminState = {
  connector_id: string
  artifact_sha256: string
  snapshot: string // opaque CAS token: artifact + authority + config + binding/secret revisions
  authentication: 'none' | 'basic' | 'bearer' | 'api_key'
  allowed_schemes: readonly ('http' | 'https')[]
  path_prefix: string
  destination_origin: string | null
  credential: null | {
    secret_ref: string; label: string; version: number; revoked: boolean
  } // metadata only; never username/password/token/ciphertext
  state: 'unconfigured' | 'configured' | 'disabled' | 'unavailable'
  reasons: readonly string[] // stable codes, translated by Core
  authority: 'not_granted' | 'granted' | 'stale'
}
type ConnectorSetupOutcome =
  | { request_id: string; status: 'applied'; state: ConnectorAdminState }
  | { request_id: string; status: 'cancelled' }
  | { request_id: string; status: 'rejected'; reason:
      'access_denied' | 'conflict' | 'invalid_request' | 'unavailable' }
  | { request_id: string; status: 'unknown' }
interface ApplicationConnectorAdministration {
  inspect(connectorId: string): Promise<ConnectorAdminState>
  configure(connectorId: string, options: {
    expectedSnapshot: string; requestId: string
  }): Promise<ConnectorSetupOutcome>
  outcome(requestId: string): Promise<ConnectorSetupOutcome>
}
```

`host.getInfo().features.administration_reads` advertises `connectors.inspect`
and `connectors.outcome`; actions advertise `connectors.configure`. Corresponding
route declarations must explicitly request them, plus a nonempty allowlist
`administration_connector_ids`. IDs must exist in the artifact's connector
declarations. These declarations are valid only on administrator routes and are
verified at package validation and on every host call. No wildcard IDs or
arbitrary network access. Missing facade/features show setup unavailable; they
never trigger a private REST fallback.

`inspect` is a bounded local read, not a network test. `configure` opens one Core
dialog, validates the CAS snapshot again on Save and performs **no remote HTTP
request**. Cancel commits nothing. A credential rotation/revocation is explicitly
named and confirmed in that dialog; its affected same-installation bindings are
shown before acceptance. No cross-installation credential selection.

The Core transaction must persist matching declaration-owned configuration keys
(`destination_config_key`, `credential_ref_config_key`) and the connector binding
together. The existing bind REST operation alone does not establish that property.
Unrelated configuration stays unchanged. Creating a new credential and binding it
on Save is atomic; cancelling does not leave an orphan credential. Rotation and
revocation use the existing authority guards, invalidate affected consent and
cannot silently restore an old grant. An applied setup result means configured,
not granted, reachable or commercially enabled.

`requestId` is 32 lowercase hex characters generated before opening the dialog.
Core persists a redacted receipt scoped to installation, artifact, administrator
and action. Concurrent/repeated submissions with the same identity cannot create
two credentials or execute a rotation twice. A different target/expected snapshot
with that identity conflicts. Password material and a password-derived digest
must not be stored in receipts. After transport loss the application calls only
`outcome`; it never automatically reopens the dialog or repeats Save. A bare
HTTP conflict is not evidence that an earlier write did not happen. Receipts for
other actors/installations are inaccessible. Session/role/artifact changes are
rechecked before every read and immediately before commit; errors are redacted.

## Bootstrap and approval order

Core must expose this Core-owned setup path for the **installed, validated
artifact** even when its service is disabled or native consent is blocked by an
unconfigured connector. Either mount its declared administrator setup route in
that state or provide the same host dialog from Core's Extensions screen. Do not
require calling the service to configure the resource it needs to start. Keep
normal business operations denied until activation and required authority pass.

Required order for a clean installation:

1. Upload/validate immutable package; inspect declared connector without starting
   commercial work or requiring credentials in ZIP/config defaults.
2. Current Core administrator opens setup, enters an allowed plain origin and
   selects/creates a credential in Core's UI; Core atomically saves both settings
   and binding, returning an opaque setup receipt.
3. Review/approve the resulting authority scope, then activate the native service.
   Changing origin, credential version or artifact requires fresh authority review.
4. Child Center invokes its explicit catalog/connection check through the existing
   SDK connector broker. Core continues to enforce path/method/size limits and
   secret injection. No automatic commercial send follows setup or activation.

## Core acceptance tests required before Child Center consumes this API

1. Brand-new installation with no binding/secret can complete the order above.
   Missing encryption key, invalid origin or Cancel leaves configuration, binding,
   credentials and existing healthy runtime unchanged.
2. Kiosk/operator/non-admin, wrong installation, undeclared connector/read/action,
   disposed route, revoked session and changed artifact all deny before mutation.
3. Concurrent administrators: stale snapshot refuses the complete save, without
   partial config, orphan secret, lost unrelated settings or stale grant.
4. Rotation/revocation invalidates authority and prevents further connector sends;
   no other installation can select/read/revoke the credential. Credential values
   never occur in inspect/results, audit, receipts, exceptions or application DB.
5. Lost reply + repeated original ID + status lookup produces one atomic effect;
   changed target conflicts. Unknown stays unknown across restart until resolved.
6. Configuration/approval perform zero network calls. A fake external server tests
   declared method/path/origin/redirect limits separately. Its failure leaves Core
   administration and unrelated local operations usable.
7. Core dialog inherits Core theme/language, supports initial/live locale and
   EN fallback. Public type exports, route schema, loader gates, protocol docs,
   runtime clients and representative consumers are updated together.

## Child Center integration after Core acceptance

Only then add `barsy_api` to a separately verified connector-enabled package
profile (the current own-SQLite acceptance preset deliberately admits no
connectors). Keep the existing local-only ZIP immutable. Test clean upload,
unconfigured bootstrap, normal approval/activation, configured restart and
revocation with a fake server before any device trial.

First application slice is explicit connection check and bounded catalog browsing
using the original `Places_getlist`, `Articles_getlist`, `Amounttypes_getlist` and
`Poses_getcurrent` handling in `service/child_center_application/service.py`.
Preserve original response validation and reference identities; do not invent
live Barsy response schemas from this proposal. It is not a new billing engine.
Next port the original durable account/consumption/payment journals and uncertain
outcome reconciliation, with separate cashier permission and confirmation. Unknown
POST outcomes never auto-replay; connection setup does not enable charging.
Periodic connector/event composition remains a separate platform task (CC13).

This document prepares the Core work for another scoped task. It does not claim
that these methods, connector-enabled packaging or Barsy business operations are
implemented or tested in the current local candidate.
