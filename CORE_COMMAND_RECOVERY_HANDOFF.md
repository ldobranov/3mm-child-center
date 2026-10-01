# 0.6.8 access runtime — platform prerequisites

## Status update — 2026-09-15

Platform prerequisites A/B below are implemented in `c56d8b1` / beta.16.
The extension journal now submits the original absolute deadline, validates the
returned authoritative expiry, and uses the read-only SDK lookup after lost replies.
Recovery refuses an active submit worker; absence, expiry or invalidation does
not automatically clear uncertain physical work. The SDK/Core bridge is tested
using isolated databases, including a lost committed reply and a delayed request.

The extension tasks under "Work remaining" are still a release checklist, not a
claim that routing, configuration, review UI or the 0.6.8 folder are complete.
The original analysis below is retained as the historical handoff.

Verified 2026-09-14 against checkout `4c895a7` (beta.15). This is a
handoff for separately authorized Core/SDK work, NOT a Core modification.
No 0.6.8 release folder has been produced. Existing scan-only 0.6.7 is unchanged.

## Why the extension cannot finish this locally

The current SDK exposes `submit_command(..., ttl_seconds, direction)` and
`command_status(command_id)`. The signed platform dispatcher accepts only
`command.submit` and `command.status` for this feature.

1. `backend/services/device_commands.py:queue_command` calculates expiry from
   queue creation. If submission is delayed, the original admission's deadline
   may already have passed before a new full TTL begins. A check immediately
   before SDK submission or after its reply cannot prevent this race.
2. `backend/services/application_commands.py:command_status` requires a returned
   command ID. If Core commits the request but its response is lost, the extension
   retains only its own request ID. Sending the same submission again is NOT a
   read-only lookup: if the original request was never committed, this can create
   a new physical command. Guessing a device command ID is not supported either.

Current extension behavior therefore remains conservative: uncertain intents
block further grants and operator finish. A timeout alone is never proof of
non-execution. This is safe blocking, not a complete staff recovery workflow.

## A. Absolute submission deadline — generic additive contract

Proposed field name: `not_after` (final API naming belongs to the platform).

- Add an optional, validated timezone-aware UTC deadline to the shared submit
  contract and SDK. Preserve the existing relative TTL contract for older callers.
- For new submissions use `min(queue time + permitted TTL, not_after)`;
  refuse a request whose deadline has already passed. Never extend an existing
  command's deadline when replaying its idempotency key.
- Include deadline semantics in canonical request conflict checks. A changed
  deadline must not silently reauthorize the same request.
- Propagate/enforce the resulting expiry through the existing queue, live permit
  and Agent pre-driver checks. Retain the documented limitation: an already issued
  permit/in-flight physical action cannot be retracted and this is not hard real time.
- Return the authoritative expiry in submit/status/lookup responses. This lets
  the extension use one deadline for passage confirmation and review.

Acceptance: delayed request arriving after the deadline queues nothing; delay
before queueing does not reset the deadline; replay does not extend it; changed
payload/deadline conflicts; Agent refuses expired execution; legacy callers work.

## B. Read-only lookup by application request identity

Proposed SDK method: `command_lookup(request_id=..., binding_id=...)`.

- Authenticate and scope lookup to the owning application installation. It must
  never enqueue, claim, authorize, retry, or otherwise change the physical command.
- Persist or otherwise safely retain the original request association. Lookup of
  a historical request must not depend solely on the binding's CURRENT target
  device: configuration can change after submission. Resolve ambiguity explicitly.
- Return explicit `found` / `not_found`, and for a found command the original
  command ID, generation, authoritative expiry, claimed flag, status and accepted
  passage correlation. Preserve visibility of invalidated historical outcomes to
  their owner without reviving authority.
- Keep authorization failure/unavailable transport distinct from `not_found`.
  A not-found result while the original submission is still in flight is NOT
  proof of non-submission. Extension recovery must also respect the absolute
  deadline and synchronize/finish its submitting worker before clearing work.
- No cross-installation enumeration, global administrator credentials or direct
  Core database access from an extension.

Acceptance: commit followed by lost reply is discoverable without another submit;
never-received requests return not-found without creating a command; changed target
configuration cannot hide an existing request; cross-installation lookup is denied;
disable/restore keep old results invalidated; racing lookup and submit is covered.

## Work remaining only in the extension after these contracts exist

1. Use deadline + lookup in the durable journal, with strict schema and idempotency
   tests. Reconcile unknown results only from platform evidence and explicit staff
   observation where necessary; never infer person passage from a successful pulse.
2. Complete configured point/driver bindings, immutable configuration snapshots,
   scan routing, account readiness, automatic dispatch, passage subscription and
   maintenance jobs. Keep unconfigured installations in existing scan-only mode.
3. Add administrator point configuration/diagnostics/review and clear operator
   pending-admission/passage states. Preserve BG/EN, themes and scoped permissions.
4. Wire the prepared privacy handlers and document retention/restore limits.
5. Test the declared runtime end-to-end with mock peers, lifecycle/restore, delayed
   submit, lost responses, replay, payment separation, packaged wheel and installer;
   visually review the UI. No real-hardware certification is implied.
6. Only then select the new entrypoint/schema, finalize 0.6.8 and stage a new
   `.runtime/child-center-0.6.8` folder for manual archiving. No deployment or ZIP.

These two platform additions remain generic. They must not introduce children,
parents, visits, tariffs, bracelets or any POS vendor into Core or Agent.
