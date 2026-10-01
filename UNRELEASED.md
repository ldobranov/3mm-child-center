# 0.6.9 — 2026-09-15

Workflow fixes for Core beta.17: match legacy delivery readiness to ownership,
adaptive read-only UI polling, and durable denied-scan diagnostics visible to
staff with visits_manage. Migration 0018 and the new runtime are packaged via
release_069.py. See RELEASE_NOTES_0.6.9.md for scope and installation.

# 0.6.8 release preparation — 2026-09-15

The runtime, configuration/review route, operator status panels and package
declarations are now integrated. See `RELEASE_NOTES_0.6.8.md` for supported scope,
installation, deadlines, driver requirements and limitations. The entries below
are historical implementation notes, not the current release status.

Final verification: 264 tests passed (124 warnings); the isolated browser
regression passed. The 24 staged files in `.runtime/child-center-0.6.8` match
the deterministic builder, validated aarch64 contract and wheel digest.
The folder is ready for manual ZIP creation. No outer ZIP, deployment,
Core/Agent edits, commit or push were performed.

# Historical increments — access journal and commercial adapter (2026-09-13)

Beta.16 integration increment (2026-09-15): verified Core `c56d8b1` and integrated
the original `not_after` deadline and read-only `command_lookup` in the extension
journal. Submit/status recovery validates command identity, generation, status,
claimed flag and authoritative expiry, rejecting deadline extensions. Lost replies
can recover correlation without another submit or a business/time transition.
Shorter authoritative expiry is used for passage acceptance. Slow replies retain
their identity even after maintenance has moved the request to review.

An active submitting worker prevents concurrent recovery. Expired, invalidated
or not-found results do not automatically release unresolved physical work.
Configured pulse arguments are strict, bounded and owned by immutable point
configuration, not by scans. Platform binding validation remains independent.

Tests include the actual SDK serialization and Core broker/queue against temporary
databases, with only transport replaced. No physical action or deployed service
was used. Runtime declarations, configuration/review UI and packaging are still
pending; manifest/entrypoint/version remain unchanged at this intermediate step.
Verification: 253 extension tests passed, including 15 new deadline/recovery and
SDK/Core bridge cases. The 112 warnings are dependency deprecations/test JWT keys.

Review fixes (2026-09-14), still draft-only:

- Operator finish and the durable dispatch claim are serialized by SQLite write
  transactions. Finish first retires prepared intents as definitely unsent;
  dispatch first blocks finish until passage is confirmed. Unknown, restored or
  invalidated outcomes stay blocked even after local expiry. This does not cancel
  hardware or supply the still-missing uncertain-outcome reconciliation workflow.
- Maintenance expiry preserves `expired_before_submit` for current prepared
  intents, so administrator resolution works without retrying a command.
- Draft 0016 adds an explicit identifier-erasure flag, recognizing only exact
  legacy tombstones on migration. Prefix-like raw bracelet values are processed.
- Identifier retention revokes the affected child's existing export artifacts in
  the same transaction. Other subjects' exports and command receipts remain.

Verification: all 238 extension tests passed (110 existing dependency/test-key
warnings), including 18 new regression cases. No Core/Agent changes, deployment,
release activation, ZIP, commit or push.

Fifth increment (2026-09-14): the prepared schema-0016 runtime now handles the
existing `export_personal_data`, `erase_personal_data` and `apply_retention`
contracts. Its `delete_client` path uses the same transactional privacy checks.
The published manifest/entrypoint/schema remain unchanged, so this is not a new
installable release. See [PRIVACY_IMPLEMENTATION.md](PRIVACY_IMPLEMENTATION.md)
for the exact implemented scope and remaining retention/restore limitations.

Export is subject-scoped, fails rather than truncating at the inline size limit,
and stores a short-lived artifact separately from permanent command receipts.
Erasure redacts selected personal fields, revokes artifacts, and invalidates
matching cached results without deleting their idempotency identities. Active
visits, allocated accounts and unresolved financial/access commands block it.
Legacy updates cannot repopulate redacted subjects. No Barsy mutation is issued.

Retention uses provisional CC-0 30-day guardian / 7-day retired identifier rules
and bounded pages with a rotating guardian cursor. Export artifact expiry is a
new provisional 15-minute test default. `deleted` counts expired export artifacts,
not historical visits. The 24-month history archive/purge is still outstanding;
this implementation does not promise complete irreversible anonymization or
erasure of independent backups, downloaded files or external-system records.

Fourth increment: `AccessReview` is attached to the prepared runtime, but is not
yet exposed through application operations/UI. It provides bounded admin-only
review listing, explicit/idempotent resolution of provably unsubmitted requests,
and registration-scoped export of the access journal. Resolution preserves a
terminal `resolved` tombstone, audits the real administrator, and never changes
time, closes an account, releases a table, or sends a physical command.

Only `expired_before_submit` and `visit_changed_before_submit` without any command,
generation or passage correlation are eligible. A prepared record in an old
snapshot does NOT prove it was never submitted after that snapshot; therefore
`startup_unsubmitted_review`, unknown execution and restore invalidation cannot
be cleared with this operation. Full manual reconciliation still needs its own
reviewed evidence/policy; there is no general override or blind retry button.

Privacy audit found a pre-existing release gap: `apply_retention`,
`export_personal_data` and `erase_personal_data` are declared but absent from the
current service handler map. The existing `delete_client` redacts selected fields
and retains history; it is NOT a complete erasure implementation. The new scoped
journal export does not claim to export or erase the full customer record.
Full privacy handlers, including cached operation results and financial retention
boundaries, must be addressed before activating the new release. No production
personal data was exported or deleted in this work.

Verification: 11 final review/export tests and 14 migration/contract/package tests
passed; the earlier combined access regression run passed 48 tests before the
additional restored-snapshot refusal case. No deployment, ZIP or version change.

Third increment: prepared `access_runtime:create_service` entrypoint (not yet
selected by the manifest). On schema 0016 it creates one journal before exposing
the internal adapter. Old prepared/submitting intents go to review on every
startup, including normal restart: no reliable restore discriminator is supplied
in ApplicationContext. Submitted identities are preserved, never re-submitted;
passage still requires current platform authority. This trades automatic recovery
of unsent work for fail-closed behaviour. Construct the journal once per service,
not once per request. Storage/migration failure prevents its construction.

The prepared runtime rejects legacy scan/resume transitions for sensor-managed
stays. Confirmed passage and explicit operator finish remain valid. Schema 0015
uses the existing scan workflow. Expiry maintenance classifies uncertain requests
as review without freeing a table or treating timeout as proof of non-execution.
This maintenance method is not yet registered as a runtime job.

Recovery tests use SQLite's backup API, all four intent stages, simulated Core
invalidation, and unchanged command identities. They do not exercise a deployed
Core restore, GPIO, power loss or two Raspberry devices. The manifest still uses
the old entrypoint; the prepared runtime has no new publicly callable operations.
Next: operation/subscription routing and privacy/review contracts, then configured
bindings and UI. The physical submit deadline gate also remains open.

Second increment: `sensor_admission.py` connects the journal to the existing
account reservation, commercial preflight and actual stay-interval mutations.
Migration 0016 remains an unreleased draft and now includes `access_sensor_stays`.
Commerce admission marks these stays account-ready without starting an interval.
Unmarked stays keep the existing scan-only behaviour, including on schema 0016.
No new Barsy endpoint or driver action was introduced.

Tests exercise real extension workflows with simulated Barsy/broker peers:
first-account creation, capacity rejection, readiness recheck, passage-only timing,
pause/re-entry into the same account, final minute rounding and bracelet detach,
unknown account replies, unused grants, restart and internal-only adapter access.

The adapter is NOT registered as a runtime operation. Before enabling it we still
need runtime routing (including blocking legacy scan/resume for sensor stays),
strict public/internal contracts, reviewed device bindings/arguments, lifecycle
and privacy integration, review operations and administration UI. Reservation
time is still the visit's historical `entered_at`; confirmed playing intervals
are separate. UI must distinguish these before release. Hardware deadlines and
restore gates in ACCESS_POINT_STAGE3.md remain open. No physical test is claimed.

An internal SQLite admission journal and additive migration 0016 are implemented
and tested but NOT wired into the running service. The application contract still
targets 0015. No new version, staged package, UI or hardware action is enabled.
Do not rebuild/reinstall this intermediate source as 0.6.7. The previously staged
0.6.7 folder is unchanged. Integration gates and remaining work are tracked in
[ACCESS_POINT_STAGE3.md](ACCESS_POINT_STAGE3.md).

# Changes after 0.6.6 — included in 0.6.7

These changes are now included in [0.6.7](RELEASE_NOTES_0.6.7.md).
The previously staged `.runtime/child-center-0.6.6` folder is unchanged.

## Staff history and uncertain-action recovery

- History now uses the same server-owned access snapshot as Operator and Visits.
  Its existing route, visits_manage permission and operation contract are kept.
  Denied screens do not fetch history; detected revocation unmounts the screen
  and clears data. Late responses after unmount or token change are not applied.
- A rejected recovery of an uncertain commercial request no longer discards the
  original idempotency key. A rejection now does not prove that the earlier
  request was never accepted. Successful recovery clears the saved attempt.
- Browser regressions cover history revocation and initial denial, legacy and
  other-user pending attempts, revoked payment rights, explicit same-owner
  recovery, key preservation after HTTP 409, and no fiscal payment from preview
  recovery. All remote responses are simulated, not live Barsy operations.
- No new grants, roles, schema migrations, Core/Agent edits or deployment.

The separate cashier is included in 0.6.7 through additive payment-scoped queries,
without changing existing grants. Delegated administration remains dependent on
the separate generic platform contract described in the handoff.
