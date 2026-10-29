# Kiosk connection and optional reader setup — Core handoff

## Installed blocker: mock identifier has no effective provider, 2026-10-28

Owner's mock POST succeeds and Core stores all three identifier.scan.v1 events,
but consent offers only Barsy. Read-only installed inspection now proves:

- Agent mock is enabled and hello advertises identifier.scan.v1; selected device
  is dev_65dba727720a40539c7d68cb70fef671; both application device keys are saved.
- Core registered_capabilities for that device contains only gpio.digital.control.
  There is no DeviceCapabilityProvider row for an identifier source.
- Calling the actual read-only `_event` source resolver for both declarations
  yields `capability_unresolved` on event:reader_primary/reader_secondary.
- Latest consent subject_version=1 has zero resolved events, so neither event
  scope appears in its checkboxes. The active grant selects only connector:barsy_api.
  No application deliveries or application reader receipts exist.

Agent's generic mock advertises a bare legacy capability in current_inventory;
that announcement is not effective provider selection in Core's unified registry.
Do not infer authority from accepted ingestion, enable compatibility, create a
fake provider directly in SQL, auto-grant the application or implement a special
Child Center source resolver. Existing app broker tests supply an explicitly
registered/selected synthetic provider; they do not cover Agent mock onboarding.

Required Core/Agent integration: use the existing generic provider advertisement/
selection and control-revision pipeline to expose an enabled mock identifier
provider when configured. Preserve device approval, capability selection, current
provider/control pinning and explicit application event consent. Diagnose missing
optional sources in the setup UI instead of making event choices disappear with
no explanation. Enabling mock must not grant an app by itself.

Acceptance: enabled/selected mock source resolves identifier.scan.v1 and consent
offers optional event scopes; existing Barsy/user choices survive. After explicit
event approval, a fresh mock scan reaches broker -> actual native Child Center
receipt/stay once. Same event delivered through both bindings stays deduplicated.
Disabled/unselected/revoked/stale/conflicting provider is denied. Unselected
optional readers still permit app activation. Do not re-enqueue the old test
events or turn them into stays after approval. Core remains a separate task.

## Current follow-up: installed query confirmation 409

Owner-provided response for POST
`/api/v1/application-extensions/org.3mm.child-center/operator/operations/list_registrations`:
`{"detail":"Application result is unconfirmed; do not replay"}`.
The source of that text is Core's `application_invocation_relay.py`. It is a
generic boundary error, not the original exception; it does not establish which
admission/completion/transport condition failed. Do not suppress it, skip trust
or replay mutations to make the screen work.

Evidence on installed 0.7.9 / Core local-84228718477a9363de03a33d:

- Core access logs show ui-host 200 followed by list_registrations 409 while
  list_visits succeeds; get_reader_settings also 409 while activity succeeds.
- Read-only signed native probes for the same query inputs succeed, including
  concurrent reads; installed output schemas validate. No business mutation.
- Read-only probes as the real Core UID and supplementary groups, using its
  actual environment, prepare and dispatch both list_registrations and
  get_reader_settings through the installed response Runtime. Both response
  frames verify and validate. These probes do NOT execute HTTP actor admission or
  the installation completion writer; they are not a claim that HTTP is fixed.
- The local exact-package integration now uses the real ApplicationResponses
  socket/FD handoff rather than the response helper. It includes concurrent
  HTTP reads with ui_context, real compiled artifact trust and the configured
  0.25-second key-lock admission budget; it passes on local WSL. Fail-fast policy
  fixtures can produce UI code trust unavailable under contention; this alone
  does not prove the installed cause or justify increasing a timeout.

Next Core task: reproduce the installed HTTP read with bounded **metadata-only**
stage/cause observation around begin_invocation, Runtime receive and
finish_invocation, including wrapped HTTPException causes. Do not log request or
result bodies, credentials, tokens or personal fields. Check current actor/login,
exact artifact/UI trust, lifecycle snapshot/key comparison, completion fence and
key/DB lock ordering. Capture the original failure before selecting a fix.
Keep invalid trust, actual revoke/lifecycle change, wrong key, malformed response
and uncertain mutation outcomes denied. Add the failing concurrency/cold-start
case plus those denial regressions before claiming the defect fixed. No special
Child Center condition or app-side HTTP/token/retry workaround.

Child Center's separate UI defect is fixed in working sources: a failed query
no longer fabricates a permission revocation, successful explicit refresh clears
the stale read message, and a real access_denied still clears the view. This UI
fix does not resolve the Core 409 and is not in delivered 0.7.9.

## Integration status after the Core completion

The owner reports the shared Core implementation complete. Read-only verification
of Core's current `docs/WORKING_STATE.md` and
`docs/EXTENSION_PLATFORM_V2_PUBLIC_CONTRACTS.md#core-owned-kiosk-pairing-and-optional-device-selection-2026-10-27`
confirms Core-owned Extensions terminals, `/kiosk/connect`, claim recovery,
auth-only renewal/revoke and optional device omission/clear. Public application
host APIs stay unchanged; Child Center needs no pairing wrapper or token store.
The proposed/observed gaps below are the original handoff, superseded by that
implementation and the integration evidence in Child Center WORKING_STATE.

`tests/test_local_kiosk.py` uses the exact compiled Child Center package and a
separate signed native host with the actual Core enrollment/claim/catalog/invoke/
renew/revoke paths. It checks original claim recovery, one registration after
original-ID replay, another terminal's unknown outcome and denial after revoke.
`test_local_activation.py` now expects real HTTP activation success for zero,
primary-only and two optional bindings, while an unknown selected ID is refused.
The old optional-device platform blocker is removed only after these checks.

The Core completion is local: Raspberry rollout and real clean-browser/reader
acceptance remain outstanding. Core migration `b096b7e82f86` preserves old terminal
rows but requires re-pairing; do not reset or adopt old credentials. No device,
Core source or immutable delivered ZIP is changed by this app integration.

## Original requested handoff (reference)

Owner decision, 2026-10-27: prepare the exact contract in Child Center for the
separate Core task. **Do not edit Core or restore app-owned HTTP/token wrappers.**
Network reader application logic is implemented separately using the existing
Core event broker. This document specifies the missing shared platform pieces.

## Observed current boundaries

Read-only references relative to the separate Core checkout:

- `backend/routes/application_extensions.py`: administrator enrollment creation,
  anonymous one-time claim, kiosk session renewal, terminal list and revoke exist
  under `/{module_id}/kiosk/...`. Claim returns a terminal credential and access
  token, renewal returns a short-lived token. These are Core transport APIs, not
  exports for application Vue components.
- `frontend/src/extension-ui/application-v1.ts`: no public kiosk claim/renewal or
  administrator terminal facade. No Core terminal setup screen was found.
- `frontend/src/router/index.ts` and `utils/compiled-ui.ts`: kiosk routes/catalog
  depend on Core's `applicationKioskToken`; pasting it from application code is
  not a supported bootstrap flow.
- `frontend/src/utils/application-host.ts`: Core selects kiosk credentials for
  the mounted route and dispatches one invoke. Application code remains
  credential-free. That boundary must be retained.
- `OperationContext.terminal_id` is now public SDK context. Core's kiosk gateway
  supplies its verified terminal ID; an application payload cannot choose it.

The old Child Center `source/frontend/kiosk-session.ts` demonstrates the desired
workflow but uses direct HTTP and app-local token/credential keys. It is preserved
reference code, excluded from the current ZIP, and must not be restored.

## Minimal solution: Core-owned terminal UI and bootstrap route

Follow the implemented connector-settings approach: Core owns identity setup;
the application continues to declare an ordinary `audience: kiosk` route. No
Child Center name, route or business rule belongs in Core.

1. Extensions derives `has_kiosk_interface` from each exact validated artifact:
   there must be a declared kiosk route and kiosk operations. Only applicable
   packages show a **Terminals / Connect kiosk** action for a current administrator.
   This screen lists metadata (ID, label, enabled/revoked, last seen), creates a
   bounded-expiry one-time code/link, and explicitly revokes selected terminals.
   It never displays a terminal's long-lived credential or another app's records.
2. An unauthenticated browser opens a static Core bootstrap route, e.g.
   `/kiosk/connect`, with an application locator/code supplied by Core. Core shows
   its own pairing form and theme/locale. It does not load unapproved application
   JavaScript or require an administrator session on the kiosk browser.
3. Core claims the code, stores the resulting terminal identity/credential in its
   existing Core authentication/session controller and obtains a kiosk token.
   Neither secret is returned through host info, invoke, application components,
   URL query strings, application SQLite, logs, analytics or generic receipts.
   A link may carry a short-lived code in a URL fragment; Core removes it from
   visible history after capture. Never encode credentials/tokens in a link.
4. Refresh the Core compiled-UI catalog under the new kiosk identity before
   navigation. Resolve the destination from the current approved artifact's kiosk
   declarations. No caller-supplied arbitrary return URL, module switch, operator
   route or administrator route is allowed. The kiosk enters its existing kiosk
   layout; Core verifies active installation, current UI trust and kiosk identity.
5. The application uses only `useApplicationHost()`, its existing kiosk operations,
   public presentation and public UI components. Enrollment/session renewal does
   not require a new application service operation, SDK secret broker, anonymous
   registration command or application-specific Core code.

Same-origin reviewed application JS is still not a browser sandbox. The API must
avoid exposing credentials without making a stronger isolation claim than Core
actually provides. Do not add a second per-app authentication/preference store.

## Core transport contract to implement

The following is the proposed coordinated prototype contract, **not a claim that
these additions already exist**. All paths are relative to
`/api/v1/application-extensions/{module_id}`; only Core frontend code calls them.
Retain existing route names and extend their request models in the Core task.

| Method/path | Request | Successful response / authority |
| --- | --- | --- |
| POST `/kiosk/enrollments` | `{request_id, label, expires_in_minutes}` | `{request_id, code, expires_at}`; live administrator; same ID + same body returns the original bounded result, changed body conflicts. |
| POST `/kiosk/enrollments/claim` | `{request_id, recovery_proof, code}` | `{terminal_id, credential, access_token, expires_in_seconds}`; anonymous code possession plus original client proof for recovery; one terminal. |
| POST `/kiosk/sessions` | `{terminal_id, credential}` | Existing `{access_token, expires_in_seconds}`; verified enabled terminal in this installation. |
| GET `/kiosk/terminals` | No body | Existing `{items:[{terminal_id,label,enabled,created_at,last_seen_at,revoked_at}]}`; live administrator; no credentials/codes. |
| DELETE `/kiosk/terminals/{terminal_id}` | No body | Existing `{status:'revoked'}`; live administrator; repeating for an already revoked owned terminal is safe. |

`request_id` is 32 lowercase hex characters. `recovery_proof` is an independently
generated 32-byte random base64url secret, persisted only by Core before claim;
it is never an application idempotency key. Keep the existing label/expiry/code
validation bounds; reject extra fields. Recovery retries the same exact enrollment
or claim request after transport loss, never a business invocation. Resolve the
current administrator login/installation and compare the original fingerprint
again on every enrollment recovery. For claim, compare the proof in constant time;
store only its hash outside the encrypted, expiry-bounded credential receipt.
The response recovery window must not outlive the enrollment's original expiry.
Concurrent claims/receipt writes are one transaction. Expired recovery does not
reissue a credential: Core shows revoke/reissue review.

Use 400 for invalid/expired code, 401/403 for missing or revoked authority, 404 for
an unavailable owned resource and 409 for conflicting identity/body or consumed
code belonging to another claim. No error contains the secret or confirms another
installation's terminal details. Core's controller owns states `unpaired`,
`claiming`, `ready`, `renewing`, `offline` and `revoked`; only `ready` mounts approved
kiosk application code. Network loss preserves identity; revoked state removes
the mounted surface. The code/token fields remain Core-internal transport data.

## Identity, renewal and uncertain outcomes

- Bind enrollments/terminals to the current installation identity/incarnation and
  declaration. Existing terminals may survive a normal approved app update, but
  cannot bypass fresh native/UI trust, enable/disable, module ownership or revoke.
  Uninstall/reinstall must not silently adopt another incarnation's credentials.
- Preserve high-entropy codes, bounded expiry and one-time concurrent claim.
  Enrollment creation needs an original request ID + outcome lookup, scoped to
  the administrator's live login, so a lost response cannot create unseen codes.
- Initial claim must be recoverable without a second terminal. Use an original
  opaque claim request ID and a random browser-generated recovery proof. Persist
  the proof hash on first claim. Only that same client can recover its result
  after response loss; another ID/proof cannot reuse the consumed code. A short
  Core-owned encrypted response receipt may retain the initial credential for
  this bounded recovery window; never put it into generic audit/plaintext receipts.
  After an unrecoverable claim, show explicit review/revoke/reissue actions.
- Token renewal is Core-owned and single-flight. It may run before a request or
  while the kiosk page is mounted, but must never replay an application mutation.
  A failed/lost business response remains pending under its original request ID;
  renewed auth permits an outcome read, not a replacement registration command.
- Transient network failure retains identity and pending opaque request IDs.
  Definitive credential revocation rejects future dispatch and unmounts the
  registration surface/clears displayed personal fields. Do not clear another
  Core login or terminal's browser state. Server session expiry remains authoritative.
- Every kiosk dispatch supplies verified `OperationContext.terminal_id` and no
  human role escalation. Request receipts must be terminal-scoped. Current Child
  Center checks this boundary; legacy receipts without an attributable terminal
  cannot be guessed into a new owner or automatically replayed.

## Required Core acceptance

1. Clean anonymous browser → Core code claim → current approved kiosk catalog →
   registration, without copying tokens/admin login or application HTTP calls.
2. Initial and live Core locale, EN fallback, light/dark/appearance, fullscreen
   compatibility, 390px layout and a populated form across language changes.
3. Non-admin cannot create/list/revoke enrollments; expired/revoked login denies.
   Cross-module code, terminal, session and destination substitution deny before
   execution. Kiosk cannot invoke operator/admin/read-other-registration methods.
4. Concurrent claim yields one terminal. Lost claim reply/reload recovers only for
   the original client proof; another browser/code reuse fails. Expired codes and
   exhausted recovery windows produce a clear recovery path without a device wipe.
5. Parallel renewal, expiry before/during invoke and revoked terminal: one auth
   renewal, **zero automatic business replays**, original outcome reads retained.
6. Disable, package/UI trust change, uninstall/reinstall, admin/terminal revoke and
   server restart preserve isolation. Two kiosks using the same application
   request ID cannot read/replay one another's result.
7. Passwords/terminal credentials/tokens/codes never appear in app props, host info,
   diagnostics, URLs/query logs or generic receipts. Core's credential store/key
   failures reject atomically. Show explicit failures rather than a false success.

## Separate demonstrated reader blocker: optional device configuration

Current Core `backend/routes/application_extensions.py:activate_application_extension`
first validates only required device keys, but its final locked recheck iterates
**all** `configurable_device_keys`. An omitted optional device resolves to None,
which is not in `current_devices`; authority rejects with 409. The Child Center
HTTP regression reproduces it with both optional event bindings unset, while a
real configured fixture activates successfully. No fake default device is used.

`frontend/src/views/Extensions.vue:canSaveApplicationConfiguration` additionally
requires a nonempty device list even when every declared field is optional. This
prevents choosing “no reader” on a device-free Core. Native host activation alone
does not exercise either defect; the application checker retains the blocker.

Required general correction:

- Missing optional keys stay missing, not empty strings or implicit first-device
  defaults. Only required keys need a selection; an explicitly supplied optional
  ID must still exist and be rechecked under the existing authority lock.
- Permit saving zero selected devices when every relevant field is optional.
  Required fields with zero suitable devices remain blocked with an explanation.
- Exercise the same rules through first activation, stopped candidate/staging and
  update. Preserve config CAS, current device revocation checks and fresh approval.
  No grant resurrection, arbitrary IDs, automatic start or scope widening.
- Tests: no devices + no optional binding succeeds; one selected optional source
  + second absent succeeds; invalid/revoked supplied optional source fails; missing
  required source fails; revocation between preview and commit fails; unconfigured
  optional scopes remain ungranted while local operations remain usable.

Application-side reader code is ready for this supported selection boundary. A
new reader-enabled ZIP must not be described as ready for unrestricted clean
setup until these Core checks pass. No installed Raspberry, Core source or
existing 0.7.8 artifact was changed by this handoff.
