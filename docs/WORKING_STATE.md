# Child Center working state

Updated: 2026-10-29. Imported baseline: `15349d0`.

## Authorized commit, push and release 0.7.22, 2026-10-29

Owner explicitly authorized commit, push and release after reviewing the local
documentation follow-up. Scope is the eleven documentation/workflow files on
existing main, followed by tag v0.7.22 and publication of the verified draft.
Application/package inputs remain unchanged from 0cab723. No Core edit, version
bump, device deployment, reset, branch creation or history rewrite is included.

Preflight: origin/main is 0cab723ac3f6b8f7086c5afa4979e468d000d658;
remote v0.7.22 tag/release do not yet exist. Reuse the application and release
checks below for unchanged inputs. Before committing review the exact staged
diff, rebuild from the index and require the immutable approved package hash.
Then push main/tag normally, wait for the tag workflow, verify its draft assets
against the delivered ZIP/checksum and publish that existing draft. Final remote
commit/tag/workflow/release evidence belongs in ignored
.runtime/release-publish-0.7.22/ and in the user handoff.

## Current documentation and release preparation, 2026-10-29

Requested application commit 0cab723ac3f6b8f7086c5afa4979e468d000d658 is
pushed to origin/main. The owner then asked whether documentation, Core
requirements and release preparation were complete. Audit found missing current
compatibility/operator/release docs and a tag workflow still using the legacy
builder. That gap is now corrected locally; this follow-up has no new commit,
push, tag, GitHub release, device deployment or Core edit.

Current references: CORE_REQUIREMENTS.md records SDK 1.3 / manifest v2 / public
UI contracts and the tested development baseline, without inventing a minimum
published Core semver. OPERATIONS.md covers setup, permissions, family workflow,
debug and guarded recovery. RELEASING.md and RELEASE_NOTES_0.7.22.md define the
immutable artifact, acceptance limits and publishing procedure. Historical Core
handoff documents are labelled and point to the current requirements.

The tag workflow now uses build_local_package.py, pinned official actions and
Python 3.14.4. It reproduces the ZIP twice, validates declarations/wheel digest
and the approved release-notes checksum, then prepares a draft release. Actual
publication and missing hardware acceptance remain separate; packaging does not
claim the integration/device gates passed.

New local verification: .runtime/release-docs-check/50f590ed/report.json. YAML
parse and all shell syntax passed; executed packaging steps reproduced the
immutable 95295-byte 0.7.22 artifact, SHA-256
abd17c52b9c537a733a9f6264dcb315500837453196cc6ceeffdf0ac71f3f5f3.
Wrong tag, absent notes, incorrect SDK, altered wheel and differing approved
checksum were refused; restored valid input passed. The gh command was checked
for syntax only and never executed. Relative document links and final whitespace
were checked. Prior 192 Python / 111 UI plus six targeted cases remain evidence
for unchanged application content; no runtime/UI rebuild is claimed for these
documentation/workflow-only edits. Core system timezone and physical-device
acceptance remain open and are documented explicitly.

## Functional handoff and requested commit, 2026-10-29

Owner reports the application now performs its intended main workflow and asks
for one local commit of the accumulated Child Center work. Remaining work is
turnstile/physical-reader/terminal integration, power/network/restart acceptance
with active business state, and stabilization of slow operations/lost replies.
This does not authorize Core edits, deployment, a push, a new tag or a release.

Commit scope: current native application, contracts/UI/catalogues, reusable
application starter/checking tools, corresponding tests, development map/contracts,
README and this working state. Tracked legacy files with only CRLF/LF differences
are excluded; their source content is preserved. Generated dist/.runtime outputs
and local device/access metadata remain ignored. Existing main branch/history
stay intact. The two repository commits use ldobranov's author identity; use the
same identity for this requested commit without changing global Git settings.

Verification reuse: exact service/UI bytes in delivered 0.7.22; full 192 Python /
111 UI at `.runtime/application-checks/20261029-104102-33dc30de/report.json`, then
six targeted configuration/settings/migration cases and new version/package /
AF_UNIX activation-restart checks in
`.runtime/package-checks/0.7.22-a6c03331/report.json`. Recheck current inputs and
artifact bytes before staging. README/working-state edits require only diff and
whitespace/link review. No old run is relabelled as a fresh runtime test.

Historical publishing finding at that commit: the tag workflow still invoked
build_child_center_package.py. The documentation follow-up above replaces it;
its new workflow/docs remain local pending separately requested commit/push/tag.

## Current delivery: 0.7.22, visible debug setting and quiet progress, 2026-10-29

Owner found no debug switch in the Core gear dialog. Root cause verified in Core
source, read-only: that dialog edits connectors/credentials, not arbitrary
manifest fields. The earlier gear instruction below is superseded. No Core edit.

Debug now has an actual visible control at Child Center -> Administration ->
Application settings -> Debug mode -> Save settings. Existing administration_manage
and administrator audience protect both get/save, including command-receipt
replay. A separate revision rejects concurrent edits; a lost reply resolves via
admin_request_outcome without another save. Mode changes only on explicit Save.
Other open application pages read the saved mode on refresh/navigation.

Explicit additive migration local_0007 creates local_ui_settings, default normal
mode, without rewriting business tables. Tests preserve registrations, active
stays, open bill identity, settings and receipts through upgrade; injected failure
rolls back and repeated migration is idempotent. Real AF_UNIX host test saves the
setting through its public operation and retains it after restart. All current
health/schema declarations use local_0007; historical migration tests retain their
intended old targets. Core can retain DEBUG_MODE from installed 0.7.21 config;
its strict configuration resolver refuses undeclared saved keys. The old marker
therefore stays accepted WITHOUT a new default and is ignored by presentation.
The visible SQLite setting is the single source. Core connection keys are kept.

Owner also requested spinner-only progress. Normal mode now shows only an
accessible, theme-token spinner while an operation/check is in flight. The full
pending panel/opaque identifiers remain in debug. A genuinely lost response stops
the spinner and shows one concise actionable failure with a saved-result check;
no endless spinner, replay or automatic financial confirmation. Manual recovery
remains folded under that actual-failure state.

Verification: full candidate
`.runtime/application-checks/20261029-104102-33dc30de/report.json` — **192 Python /
111 UI**, zero failures/errors/skips, strict types/build, real local activation/
restart and exact input/package integrity. Then **6 targeted cases** in
`.runtime/visible-debug-settings/installation-config.xml` cover the retained
installation marker, persisted mode, existing rights, revision/receipt isolation
and migration; two configuration cases are new after that full gate. Packaged UI
and service source bytes match the full gate; current public UI deps rechecked.
Visual review used real admin UI with synthetic data: light/BG desktop toggle and
5-second save (spinner only), saved success, dark/BG phone layout. Screenshots in
this chat's visualization folder: child-center-debug-settings-mobile.png and
child-center-normal-spinner.png. Temporary tabs/server closed; owner tab untouched.

Delivered `dist/3mm-child-center-0.7.22.zip`, 95295 bytes, SHA-256
abd17c52b9c537a733a9f6264dcb315500837453196cc6ceeffdf0ac71f3f5f3.
Receipt `.runtime/package-checks/0.7.22-a6c03331/report.json`:
new package/schema/config validation and real activation/restart/data-preservation
passed; declared inputs and immutable 0.7.21 ZIP/hash verified. No Pi deployment,
Core edit, commit, push or data reset. Actual installed acceptance remains pending.

## Current delivery: 0.7.21, normal/debug procedures, 2026-10-29

Owner reports the installed 0.7.20 workflows now succeed, despite several lost
replies and slow operations. This task is presentation; do not reopen the paused
Core 409/performance investigation or claim latency has been fixed.

DEBUG_MODE is a boolean in the extension's initial Core configuration, default
false. Permission-specific presentation reads reuse each route's existing grant;
no new grant or Core change is needed. They return only the strict boolean, never
connection settings or credential references. Kiosk/internal/unauthorized reads
are denied. Unavailable/invalid preference discovery retains the detailed UI.
No database migration or retained business-data change.

Normal commerce/cashier view removes routine diagnostic IDs, observed-state lines,
instructions, quote timestamps, duplicate amount-read buttons, duplicate status
panels and repeated errors. History remains accessible. One contextual payment or
time recovery action is shown, rather than duplicate journal controls. Failed
saved-result checks keep the current dialog context. Shared Status hides opaque
identities in normal mode and folds the last-resort manual acknowledgement into
an explicit recovery section; the saved-result check remains available.

Automatic review initially rejected blanket removal of send/payment/permission
attestations. No workaround was used. Owner then explicitly approved replacing
routine checkboxes with clearly named confirmation buttons. Each named click
records acknowledgement and calls the ORIGINAL guarded handler: received payment
with displayed amount/method, parental consumption permission, family finishing,
or a prepared send. No financial result is assumed and no old command is replayed.
Unacknowledged uncertain results still require actual review; privacy/registration
consent, article choices, administrative-release review and erasure confirmation
remain meaningful explicit controls. Debug retains the prior detailed procedure
presentation. Backend commercial validation, once-only fences and receipts are
unchanged.

New exact-source full gate:
`.runtime/application-checks/20261029-101204-e56268c5/report.json` — **193 Python /
106 UI**, zero failures/errors/skips, strict types, production build, deterministic
package/presentation checks and real local AF_UNIX activation/restart/data
preservation. Source inventory and current public UI dependencies rechecked after
completion. New tests cover presentation rights/no config leakage, strict boolean,
fallback, normal/debug visibility, one visible failure, lost-result no-replay,
explicit-click payment/parental permission and continued prepared/uncertain payment.
Visual synthetic review: light/EN desktop, dark/BG 390 px phone, normal payment,
detailed debug, and uncertain payment with only a guarded read-only check.
Proof image: `child-center-normal-payment.png` in this chat's visualization folder.
Temporary preview server and four tabs closed; owner's Categories tab unchanged.

Owner explicitly requested a new ZIP with these changes. Delivered
`dist/3mm-child-center-0.7.21.zip`, 93694 bytes, SHA-256
6aeb3c7aefc8bbec3704f0f1ca328729cf6032bb8fd66874836c4084da6cb2ef.
Receipt `.runtime/package-checks/0.7.21-d1418ea8/report.json`:
new deterministic package validation and real AF_UNIX activation/restart/data
preservation passed. Reused the exact-source 193 Python / 106 UI, types/build
and presentation evidence above: all inputs/public UI dependencies matched before
the metadata-only bump, and packaged frontend/service source bytes are identical.
Distributed 0.7.20 ZIP/hash remains immutable. No device deployment, commit or push.
After installing: Core Extensions -> Child Center settings gear -> Debug mode,
off by default for the simplified procedures; enable for the detailed interface.
Installed acceptance of this new UI/configuration toggle remains pending.

## Current delivery: 0.7.20, archived unlinked parent requests, 2026-10-29

Owner confirms bill 41 is cleaned. Remaining historical request has finished
zero-minute child stay, no Barsy account and uncertain parent synchronization.
Owner reports a name collision at creation; exact historical response is not
available, so do not classify it as proven rollback or match a client by name.

Implemented administration_manage archive for closed unlinked families only:
no local account, no account-opening/sale/payment intent, readonly exact-code
parent lookup, no client write/deletion. Parent attempt becomes abandoned with
audit; no old command is replayed. Archived family is excluded from Active,
automatic opening/retry and future family joins. Legacy closed visits without a
family row retain archive metadata. A new attempt must use corrected details or
find the exact existing registration code; same-data POST replay is blocked.
Existing clients remain untouched. Late failed/successful parent-worker responses
cannot reopen the archived family or cause a bill opening. No schema alteration.

Owner initially chose source-only, then requested another review before the ZIP.
Review reproduced a permission-boundary gap: a recovery receipt could be read
through a lower-permission commerce/cashier/settings/child receipt alias by the
same actor. Receipt routing now restricts BOTH administrative recovery operations
to commerce_recovery_outcome, with current admin permission and actor isolation.
Eight negative/positive permission regressions added. Negative test reproduced
the former leak; corrected targeted group passed 23 cases. Review covered current
consumers, pending-owner fences, new family membership, readonly archived UI,
receipt loss, concurrent changes, later parent replies and corrected new intent.

New full gate for exact **0.7.20**: **188 Python / 96 UI**, zero failures/errors/
skips, strict types, production build, exact input/package integrity and real
AF_UNIX activation/restart/data preservation. Report:
`.runtime/application-checks/20261029-091859-e8a4862a/report.json`.
This supersedes the earlier 180/96 candidate. Reused dark/BG phone and light/EN
desktop synthetic visual review for unchanged UI sources; temporary tabs/server
already closed, owner's Categories tab untouched. No real Barsy request/account,
Raspberry deployment or Core source was changed. Guardian-catalog 409 set aside.

Delivered `dist/3mm-child-center-0.7.20.zip`, 92289 bytes, SHA-256
4802013e82660e526bf75eec0c6049df067ca745430193ac789900383f7c243f.
Receipt `.runtime/package-checks/0.7.20-eda89ab3/report.json`: exact full-gate ZIP copied unchanged; source inventory and
current public UI dependencies verified again. Previous 0.7.19 ZIP/hash preserved.
No commit or push. Actual installed recovery of the old client-only request is
pending; do not claim it has already been cleared.

After upload/approval/activation: Accounts/Cashier -> old parent -> Commercial
journal -> Archive request without account; enter a reason and explicit
acknowledgement. Old request leaves Active, remains in All/history. Correct
parent details before starting a separate new request; do not re-send the old
uncertain command. No association based only on a client's name.

## Current delivery: 0.7.19 and recovery of empty account 41, 2026-10-29

Owner explicitly approved annulling empty test account 41 without orders/payment.
Read-only exact-alias check found it open/empty/zero. Browser auto-review rejected
our final close click as a financial action requiring human takeover; no bypass
was attempted. Owner then closed it in Barsy. Independent re-read confirms exact
account/alias, status=1, zero totals and empty orders/payments/payments_history.
Owner subsequently confirms this local account was cleaned through the new action.
Record acceptance for empty bill 41; do not infer other recoveries from it.

Delivered `dist/3mm-child-center-0.7.19.zip`, 90473 bytes, SHA-256
c8f04d3e53f171936e0a4c2f0bc978208b3adae69663d5c5b28762ba834ae7a6.
Receipt `.runtime/package-checks/0.7.19-70df92e7/report.json`: new real AF_UNIX
activation/restart/data-preservation passed. Reused exact-source **165 Python /
90 UI**, types/build and presentation/integrity from
`.runtime/application-checks/20261029-080003-c086fae5/report.json`; all inputs and
public UI dependencies matched before the metadata-only version bump, and
packaged service/UI source bytes match that full-gate candidate. Earlier ZIPs
remain immutable; no deployment, commit, push or Core edit.

New commerce_release_empty requires administration_manage, explicit review,
accepting no test-stay charge, a nonblank reason and expected remote account ID.
It performs only one GET (no remote POST), validates exact identity, externally
closed state, no orders/payments/history, zero totals and a closed local family.
It refuses acknowledged/confirmed nonzero charges, pending parent/open commands,
missing proof or concurrent local account/family/command changes. Pending sale
steps become waived, never confirmed or cancelled-before-send. Original IDs,
quantity, baseline and acknowledgement remain; recovery reason/operator/time and
remote snapshot are added. A separate confirmed LOCAL release journal entry
retains the audit even when there are no pending commands. Quotes are invalidated
and account closes locally; the active list drops it, All/export retain history.
Existing free-text state/kind columns and JSON fields need no schema alteration;
all current consumers cover waived/release. Scoped receipt uses current admin
permission and actor isolation; replay cannot send the old charge again.

Full gate: **165 Python / 90 UI**, zero failures/errors/skips. Includes manual
finish while inside and after pause -> same correct duration and one charge;
18 release/proof/denial/race/no-replay checks; explicit admin UI review, refusal,
lost reply and scoped receipt. Visual synthetic review passed dark/BG 390 px
release+retained waived history and light/EN admin form. Temporary tabs/server
closed; user's Categories tab untouched. No real bill mutation by the agent.

Owner steps after upload/approval/activation: Accounts -> Test 2 / bill 41 ->
Commercial journal -> Release empty test account. Enter a reason, explicitly
accept no test charge and submit the danger button. Confirm it disappears from
Active and remains in All with waived history. If denied, keep data and inspect
the fixed reason/proof; never reset uncertain back to prepared or delete rows.
Guardian-catalog 409 remains set aside. Prior time-review/checkout UI improvements
are included in 0.7.19. Owner cash closure in 0.7.18 is already accepted.

## Current result: bill checkout and payment continuation, 2026-10-29

**Installed owner acceptance:** owner confirms successfully closing a real bill
in cash through Cashier on 0.7.18. Record this as cash payment/account closure;
do not infer card-terminal, fiscal-print or all failure-mode device acceptance.
Earlier owner screenshots confirmed opening/time/reconciliation for account 42.

Completed checkout access in the existing Accounts view for current Core cashier
permissions. Close family bill reads the Barsy amount and opens the payment form.
Cashier route/title/permissions stay intact; no new route or direct navigation.
Prepared payment continues the same command, with the original amount/method and
explicit received-payment attestation; uncertain payment checks only, using the
shared reviewed checkbox when acknowledgement is missing. No new preview/prepare
is generated for an existing pending payment. Expired unsent payment can be
cancelled before a fresh quote. External-close review has its own checkbox,
separate from child-consumption permission. Active list and visible confirmation
follow the checked server result. Ready-to-pay notice no longer asks to finish
an already finished stay. Prior stay-control/review corrections remain included.

Final new frontend evidence:
`.runtime/family-checkout/frontend/frontend-check.json` — **84 UI**, strict types
and production build passed. Covers both views; confirmed/lost/refused replies;
prepared/uncertain/mismatched result; blocked active/time/pending states; denied
cashier access; expired-payment cancellation; independent external review.
Reused prior **145 Python** only for unchanged backend/contracts/build inputs,
verified by hashes. Existing two-child family test already covers child/parent
consumption, summed stay time, one Accounts_close and closure of that shared bill.
No later backend change is claimed tested by an earlier run.

Visual synthetic review: BG dark 390 px Accounts -> Close family bill -> amount,
method/receipt -> confirmed closed state; EN light desktop amount/method/disabled
payment before confirmation. Saved task screenshot; temporary tabs/server closed.
Readonly actual Barsy metadata confirmed cash/card method shapes, account 42's
pre-close 25.50 EUR and closed sample Accounts_get status/totals/fx. No live
mutation was sent by the agent. Vendor docs login rejected the prior access;
no new documentation access or credential change is claimed. Existing documented
Accounts_close body/strict confirmation were preserved unchanged.

No Core edit, backend/API/schema/permission changes, deployment, commit, version
bump or new distributed ZIP. Distributed 0.7.18 remains immutable; new UI work is
local and awaits owner-requested packaging. Guardian-catalog 409 remains set aside.
Next: requested ZIP, then owner acceptance of the new Accounts checkout controls.
The older uncertain two-minute command remains separate and is never replayed.

## Current correction: explicit review on the primary time-check button, 2026-10-29

**Installed owner acceptance:** the subsequent screenshot now shows account 42
with parent synchronization, opening and time all confirmed after explicit review.
The charge was not resent. This confirms opening/time/reconciliation for that
bill, not consumption/payment/closure or the reason the original send reply was
lost. The older two-minute bill is a separate unresolved historical attempt.

Owner's new screenshots show Barsy account 42 with article 28 / 51 minutes and
Child Center's matching 51.000-minute uncertain command. The visible refusal is
commerce_manual_review_required (lost send acknowledgement); the journal review
checkbox is unchecked. The current 0.7.18 already permits the owner to tick it
and use the journal button directly below, which sends only a check, not a sale.
Manual finishing while a child is inside is supported; do not attribute the
historical uncertainty to that action without evidence.

Found a separate primary-control defect: chargeTime() always sends reviewed=false
for uncertain time, ignoring the shared journal attestation. Now the primary
card exposes the same explicit checkbox when ack=0, disables checking until it
is ticked and sends its actual reviewed value. Checking never prepares, validates
or executes the sale. A mismatch stays uncertain and requires a fresh review.
Three new UI regressions cover primary/journal attestation and mismatched result.
Final frontend evidence: `.runtime/stay-time-review/frontend/frontend-check.json`
— **72 UI**, strict types and production build passed. New regressions cover both
routes, primary/journal attestation, no mutation calls and mismatched quantities.
Visual synthetic review passed: 390 px dark/BG Consumption shows the control;
light/EN desktop shows the same shared checkbox enabling the primary check.
Temporary tabs/server closed. Reused the prior **145 Python** evidence only for
unchanged backend/contracts/build inputs, verified by hashes. Earlier visibility
correction remains in this candidate.

Guardian-catalog 409 investigation remains explicitly out of scope. No backend,
Core, live bill, stored uncertainty, version or distributed ZIP changed. 0.7.18
bytes remain immutable; current UI corrections have not been deployed/packaged.

## Current narrow correction: stay-charge control across sections, 2026-10-29

Owner reports missing Charge stay time while in Consumption; clarified this is
not payment/closing. The time control was hidden by section==='overview'. It now
remains visible in every section of the open family bill after stays finish.
An uncertain time command still offers read-only checking, with the existing
explicit no-resend explanation. Existing prepared/fresh/zero/lost/refused flow
and permissions are unchanged. Extended the existing eight time UI regressions
to operate from Consumption/Payment/Journal. That narrow candidate passed 69 UI,
strict types and build before the next owner report.

Owner explicitly set aside the guardian-catalog 409 investigation. No catalogue,
backend, Core, stored command or live bill change. Earlier read-only Pi access
logs showed three commerce_catalog=409 without inner error details; do not infer
a specific cause from that. The pictured old two-minute command stays uncertain.
Distributed 0.7.18 remains immutable; current correction is source-only.

## Current delivery: 0.7.18 after the requested workflow audit, 2026-10-29

Owner requested a ZIP with the time fix, then an audit for similar gaps.
First delivered immutable 0.7.17 (receipt below); final recommended package is
**`dist/3mm-child-center-0.7.18.zip`**, 88105 bytes, SHA-256
a1af4dbf725d144516cd21649378b06f5c144c32e5917496329e6e2d2c2c8b78. Its bytes equal the exact full-gate candidate.
0.7.16 and 0.7.17 hashes remain unchanged; no overwrite, Core edit or deployment.

Audit examined parent synchronization, opening/continuing a family bill,
consumption, time, payable quote, payment/closure and journal receipt recovery.
Parent/open/payment sends have at most two pre-send reads per Session; sale
validation has its separate three-read budget. Checks/observations do not POST.
Existing permission, consent, identity, quantity, no-replay, crash and receipt
checks were retained. No new routes, framework, schema or credentials.

Reproduced two additional backend defects: a proven-not-sent payment restored
prepared state but retained quote.used=1; malformed local quantities reported
invalid Barsy data. Five negative regression cases failed before repair.
Now only the same explicitly proven unsent payment releases its quote, preserving
actor, amount and original expiry checks; ambiguous payment remains fenced.
Bad local quantity gives the form's invalid-quantity reason, without network I/O.
Also corrected two UI gaps: confirmed consumption/payment had no nearby success
feedback; a paid bill remained in the active list. Both now update after the
server confirmation. Lost/refused replies show an error beside the action and
never show success. Shared submit/journal paths keep the existing Core controls.

Targeted commerce/family: **69 passed**. Final exact full gate:
`.runtime/application-checks/20261029-065235-d74191ad/report.json` — **145 Python /
69 UI**, zero failures/errors/skips; real AF_UNIX activation/restart/data retention,
strict types, build, presentation and input/byte integrity all passed. No reused
runtime result is claimed for later code. Visual synthetic review: BG dark at
390 px consumption success and payment/closed confirmation; EN light desktop
consumption success. Temporary tabs/server closed; user Barsy tab untouched.
Screenshot artifact remains in the task visualization directory.

No live account/order/payment or device changes. Installed Raspberry/native
approval/financial acceptance remains pending. The old two-minute uncertain
command stays uncertain: Core's missing attempt row is not proof of no send.
Next owner test: install/approve 0.7.18, use a fresh/prepared command and complete
entry -> child/parent consumption -> pause/resume -> finish -> charge -> pay.
Do not recreate or resend the old uncertain charge to test this package.

Interim 0.7.17: 87595 bytes, SHA-256
7522cc9c2bcac6b186461595fdae1a679bf741a36505511e705a5638bade77b2.
New activation/restart passed; reused exact-source 137 Python / 66 UI after
metadata-only packaging. Receipt `.runtime/package-checks/0.7.17-bd1fc6e0/report.json`.

## Current result: separate sale validation and one-shot dispatch, 2026-10-29

Owner supplied the Core read-only result: no application_connector_attempts row
for connector_023a4b9340a34300a556b61e14316ab4. outcome/http_status/error_category
are unavailable. Keep the old live two-minute command uncertain; absence of that
row or of current Barsy orders does not prove no historical remote send.

The new commerce_validate operation performs the three sale preflight GETs under
15 s / internal 13.5 s, without a financial POST. commerce_execute keeps 10 s /
8.5 s and sends one POST using the validated quantity/baseline. Proof expires in
15 s and binds the current actor, family/consent, account identity and settings
revision. It is checked again under the durable send fence. A failed revalidation
invalidates any earlier proof. The existing charge/consumption and journal Send
once controls validate then send/check, stopping on lost/rejected validation.
An uncertain command still only checks; no validation can unlock or resend it.
Zero-time local confirmation and accepted parent/open/payment behavior remain.
No migration is needed: existing prepared commands are explicitly revalidated;
old uncertain commands never acquire a fresh dispatch path.

New targeted commerce/family group before final two denial regressions: 59 passed.
Exact final full candidate:
`.runtime/application-checks/20261029-063435-fb348438/report.json` — **137 Python /
66 UI**, zero failures/errors/skips; standard activation/restart/data preservation,
strict typecheck, build, presentation and source/byte integrity all passed.
Candidate SHA-256 eac8c77abf9525ade24f0782692ea8fe1e488f9cc6577b219dfaa88a671b58ad,
87589 bytes. This is an ignored verification artifact, not a new distribution.
Reused the earlier dark/BG phone and light/EN desktop visual inspection for the
unchanged layout/styles; the current UI diff changes event handling/permission
checks only. Lost/refused validation feedback is covered by current UI tests.

No Core edit, deployment, live financial action, commit or version change.
Distributed 0.7.16 bytes/hash remain immutable. All local gates passed; real
installed Raspberry/staff/financial acceptance remains pending. Next: owner-
requested new version/ZIP, then explicit real test of a fresh/prepared charge.
Do not claim the old historical two-minute uncertainty has been resolved.

## Current result: uncertain two-minute charge and proven pre-send recovery, 2026-10-28

Owner clarified no new journal row, then supplied the decisive journal screenshot:
time command commercial_023a4b9340a34300a556b61e14316ab4 is uncertain, quantity
2.000 minutes, without acknowledgement. Opening command f9568e86eae54354b817db5408a08b88
is confirmed. Repeated prepare attempts do not imply new sends. The original
historical failure reason remains unknown; do not treat missing rows as proof
that an ambiguous request was never dispatched.

A read-only authenticated Barsy lookup for place 6 / open accounts found one exact
opening alias, account 41: status=0, time_calculation=0, orders=[], totals=0 at the
observation. Only that account's minimal numeric metadata was output. No sale,
account change or payment was sent. Vendor docs confirm Accounts_place's input
and integer acknowledgement. Core access logs expose HTTP statuses, not this
connector's historical response. Attempted read-only Core-UID SQLite inspection
stopped at sudo requiring a password; no DB statement ran or permission changed.
Asked owner to retrieve only outcome/http_status/error_category in the Core chat
for connector_023a4b9340a34300a556b61e14316ab4. Owner supplied the Core read-only result: no row for that connector attempt.
The three fields are unavailable; this alone is not proof of no remote send.

Meanwhile reproduced and corrected a separate definite application defect:
a local Session budget failure after preflight but before calling the SDK left
the write uncertain forever. Now only a local pre-send refusal or the public
SDK's explicit phase=not_dispatched can restore the same command to prepared.
The conditional update requires uncertain/ack=0/no candidate, clears baseline,
and records a fixed EN/BG delivery-not-sent reason. A concurrent confirmed command
is preserved. No automatic retry. Ambiguous SDK phases, HTTP failures, malformed
replies and absence of remote orders retain the uncertainty fence. Existing old
uncertain commands, including this live two-minute one, are not reclassified.

Targeted commerce/family: **49 passed**. Two proven-not-sent regressions fail on
the old code; ambiguous-phase/no-replay regression remains green. Exact final
candidate `.runtime/application-checks/20261028-225730-4d9b3953/report.json` passed:
**125 Python / 64 UI**, zero failures/errors/skips, standard activation/restart,
typecheck, build, presentation and integrity. Includes the previously unshipped
inline time-result/continuation UI correction below. No Core edit or deployment.
Version remains 0.7.16; distributed ZIP is immutable. Old live uncertainty needs
its diagnostic evidence before any recovery decision; new source is not a claim
that that historical case is resolved. Temporary API/docs tabs closed.

Read-only Core diagnostic selection (no credentials/business payloads):

```sql
SELECT a.outcome, a.http_status, a.error_category
FROM application_connector_attempts a
JOIN application_extension_installations i ON i.id=a.application_installation_id
WHERE i.module_id='org.3mm.child-center'
  AND a.request_id='connector_023a4b9340a34300a556b61e14316ab4';
```

## Latest correction: continuing stay-time charging, 2026-10-28

Owner confirms family bill opening works on 0.7.16; do not reopen the accepted
parent-identity path. New report: Charge stay time does not visibly charge, with
no reported error. Asked for the journal step/state; that answer remains pending.
Read-only Pi access logs show prepare=200 followed by detail=200, with no execute
for the last two attempts (21:24:42 and 21:26:09 in the journal). HTTP statuses do
not establish the domain result or kind/state of those attempts. The exact live
blocking result is therefore not claimed as proven.

Found and reproduced a frontend recovery defect: the button always prepares a
new time command, even if a prepared/uncertain time step already exists. Domain
refusals render at the modal top, potentially outside the current scroll view.
The corrected button reuses the existing prepared command; an uncertain step
performs only check, never execute. Fresh time charging retains prepare/send/check;
a lost response stops the sequence. Missing continuation permissions or unexpected
states no longer silently return. Consumption/payment retain the same guarded
send/check sequence. Time controls are shared by Accounts and Cashier.

The action uses Core primary/loading styles and shows confirmed quantity/unit,
zero-time explanation or current error alongside the button. No backend/API,
storage, Core or grant changes. Exact public Barsy catalogue reads confirmed
article 28=Зала Мин., type=1, amount_type_id=8; that unit has time_interval=1 and
value_precision=3, compatible with minutes. Official Accounts_place returns int,
matching the existing parser. No live sale, account change or payment was invoked.

Six new regressions fail on the previous implementation and pass after repair:
fresh/prepared/uncertain/zero/lost/refused. **64 UI tests**, strict typecheck and
production build passed against staged sources in
`.runtime/stay-time-frontend/frontend/frontend-check.json`. Reused prior **122
Python** checks for unchanged service/contracts; VERSION metadata alone is 0.7.16.
Synthetic visual review: dark/BG 390px Cashier prepared-step continuation and
light/EN desktop Accounts uncertain-step check, both showing confirmed quantity.
Preview server/tabs closed. No installed-device acceptance is claimed.

Distributed 0.7.16 remains immutable; no new version/ZIP, deployment or Core edit.
Next: separately requested packaging, then repeat the real pending time action;
if still blocked, inspect the now-inline reason and actual journal state.

## Latest delivery: 0.7.16 ZIP, 2026-10-28

Owner requested a new ZIP with the identity correction. Delivered
`dist/3mm-child-center-0.7.16.zip` (85898 bytes) and `.sha256`.
SHA-256: `786c5b5517c03163c2360da242cafc49e2aa3597c8498fc1ad87b2d296c5f1e9`. Prior distributed 0.7.15 hash is unchanged.

Reused **122 Python / 58 UI**, typecheck, production build and presentation
checks from `.runtime/application-checks/20261028-210230-65fb40f8/report.json`.
Verified every prior application input and copied public Core UI dependency
before the version-only change; packaged UI and service code remain byte-identical
to that checked candidate. New 0.7.16 package validation/preset, deterministic build
and real AF_UNIX activation/restart/data preservation passed. Exact distribution
bytes match the new checked candidate. Receipt: `.runtime/package-checks/0.7.16-b960f3ae/report.json`.
No Core edit, deployment or live Barsy/fiscal action. Next owner acceptance:
install/approve 0.7.16, use Continue account opening on the prepared step, and
inspect the specific field reason if the actual remote data still differs.

## Latest correction: parent identity verification, 2026-10-28

Owner screenshots show an open command still prepared/unsent with the generic
identity-conflict message. Its commercial_* token identifies the local command;
parent verification uses the registration's client code and saved Barsy client ID.
This branch rejects before Accounts_create. The precise differing field on the
installed Raspberry is not established from those screenshots alone.

Verified official Clients_get/Clients_getlist docs: get can hide client_code
according to API rights even when requested; getlist has an exact client_code_match
filter and explicit client ID/name/code/contact fields. A realistic fake that
hides the card code only on get reproduced the prepared/opening failure before
this correction. Synchronization, confirmation and account preflight now use the
same bounded exact-code lookup, require one result and still verify its actual
code, saved client ID, name, phone and email. No fuzzy matching, ignored missing
code, broadened permissions or private API fallback.

Specific EN/BG reasons now distinguish absent code/client, changed code/client ID,
and changed name/phone/email. The worker retains only these bounded reason keys
on the pending command, never remote field values or connector exception text.
Correcting a genuine remote difference and continuing reuses the existing prepared
command/UUID; tests prove no create before validation and exactly one afterward.

Targeted commerce/family checks: **46 passed**. Exact final candidate
`.runtime/application-checks/20261028-210230-65fb40f8/report.json` passed:
**122 Python / 58 UI**, no failures/errors/skips, real activation/restart,
typecheck, production build, presentation and source integrity. The UI regression
checks the specific phone reason in EN and BG without sending the action.
No live Barsy write or installed-device acceptance, Core edit, deployment,
version bump or new distributed ZIP. Version remains 0.7.15; its delivered ZIP
hash remains 55a90e9aae8791dfc978a00995780bec698976787a898bffba819e15a97fa51b.
Next: separately requested packaging and real continuation of the pending opening;
if contacts genuinely differ, use the specific field reason to correct the data.

## Latest delivery: 0.7.15 ZIP, 2026-10-28

Owner requested a new ZIP. All application inputs matched the prior successful
115 Python / 57 UI run before the version-only change to VERSION/WHEEL_VERSION
0.7.15; README records this package's scope. Exact candidate gate
`.runtime/application-checks/20261028-203049-2b712d72/report.json` passed again:
**115 Python / 57 UI**, zero failures/errors/skips; package validation,
standard AF_UNIX activation/restart/data preservation, typecheck, production
frontend build, presentation and input integrity all passed.

Delivered `dist/3mm-child-center-0.7.15.zip` (85244 bytes) plus `.sha256`.
SHA-256: `55a90e9aae8791dfc978a00995780bec698976787a898bffba819e15a97fa51b`. Distribution copy matches the checked candidate exactly;
previous distributed 0.7.14 hash remains unchanged. Includes the opening/parent
consumption corrections below and the previously unshipped category fixes.
No Core edits, deployment, live Barsy mutation or installed-device acceptance.
Core UI-trust recovery and real Barsy/fiscal acceptance remain separate work;
the automatic gate does not claim those manual checks passed.

## Latest result: opening the family bill and parent consumption, 2026-10-28

Owner requests finishing account opening, including products for the parent
from the configured Barsy category on the same family bill. No new screen.
Verified official authenticated API docs for Clients_get, Places_getlist,
Accounts_create and Accounts_getlist. Two application defects were confirmed:
Clients_get hides client_code unless explicitly requested, yet opening compared
that missing code; Places_getlist does not guarantee time_calculation and its
place_type is an arbitrary type ID, yet opening required that field and rejected
type 1. Request client_code explicitly and validate documented place identity.
Optional timer hints can deny early; Accounts_get must confirm timer=0 before
the bill becomes usable. A timed account stays unconfirmed with no app orders.
The stricter synthetic Client_get reproduced the failure before the correction.

After a lost Accounts_create reply, confirmation now reads at most 101 open
accounts filtered by client/place, requires a single exact unique app marker,
then independently checks the account identity/status/timer. More than 100 rows,
duplicate markers, foreign clients and missing matches require review. No second
create POST, including explicit continuation/restart. Successful confirmation
clears the previous opening warning; bounded public reasons remain on the journal.

Cashier details expose opening_state. While opening, the mounted view follows
status with at most 15 sequential, read-only checks, two seconds apart; it stops
on completion/review/error/close/unmount. Existing explicit refresh remains.
Configured automatic opening no longer also offers the manual place/open form.
Selecting Parent loads that category immediately; search/paging and quantity
remain available. Explicit article_type data is requested and unsupported types
excluded. Add uses Core's primary button; child consents remain per child.
Late catalogue replies are ignored after changing consumer/detail. Parent
consumption is tested even when the selected child has no allowed articles.

Exact final candidate gate `.runtime/application-checks/20261028-202127-2e6d4a97`
passed: **115 Python / 57 UI**, no failures/errors/skips; package/preset, real
AF_UNIX activation/restart/data preservation, strict typecheck, production build,
presentation and source-integrity gates passed. Synthetic public-Core-component
preview reviewed dark/BG parent category/quantity/primary action at 390px and
light/EN opening status. Preview server stopped and preview tabs closed.
Earlier full run preceded the stricter Client_get reproduction; final run above
includes that correction and clearing a manually reconciled opening warning.

Core UI-trust 409 below remains a separate installed-device blocker; no live
account/sale/fiscal action or real-device acceptance is claimed. Core unchanged.
No version bump, deployment or new ZIP; distributed 0.7.14 remains immutable.
Next acceptance after Core repair and separately requested packaging: one entry
opens one bill, sibling joins it, parent category products plus separately allowed
child consumption, pause/resume, measured-time charge and fiscal checkout.

## Current blocker: Core UI code-trust refusal in cashier, 2026-10-28

Owner reports POST operator/operations/commerce_places returning HTTP 409 with
detail="Application UI code trust is unavailable". A Barsy customer exists;
the family UI still shows no linked account and an opening requiring review.
Customer synchronization alone does not establish that an account was opened.

Read-only SSH confirmed Core release local-0f5e4e5ce7f985e9bc848597 is active.
Journal entries at 14:52:19/39/41 show commerce_places=409, while cashier_list
and cashier_detail continue returning 200; family_retry_open also returns 409.
Journal status codes do not establish the detail of those other failed calls.
The installed release includes the previously accepted trust optimization;
neither missing package approval nor the old shared-reader defect is proven.

Source trace: Core compiled_ui.application_ui_artifact wraps internal native
review/key/binding failures with this message; application_extensions invocation
preparation propagates it. The relay repeats preparation at admission and
completion, so this response alone does not prove non-execution. The app's
commerce_places declaration is an authorized commerce_manage query; its handler
only reads configured IDs and Places_getlist. No application-side trust bypass
is appropriate. Next Core diagnosis must retain the failing stage and internal
exception/reason, comparing it with the successful cashier reads on this release.
Protected authority data is unavailable to the diagnostic SSH account; the exact
underlying reason remains unconfirmed. No Core edit, approval change, reset,
financial replay, live business invocation, version bump or ZIP was performed.
This handoff is documentation-only; no runtime checks/build were needed.

## Latest correction: category catalogue response and detailed directory, 2026-10-28

Owner reports working articles/places/units but failing categories on 0.7.14.
Their facade response was status=invalid_response, items=[], has_more=false.
Owner subsequently supplied the raw Categories_getlist JSON: a sequential list
beginning with the service record cat_id=-1 / Uncategorized, followed by actual
categories 1=Бар, 2=КУХНЯ, 3=Игрална зала. The positive-ID validator rejected -1
and therefore the entire catalogue. This is now a reproduced application defect.

Fixed a proven UI defect: CommerceSetup replaced invalid_response with the
connection-unavailable message and retained errors on later successful reads.
It now preserves the distinction and clears an old error on an explicit read.
The official JSON example uses empty extra_properties=[]; request now follows it.
The parser now excludes that known -1 service record before identity validation
and pagination. Other malformed/duplicate IDs and error objects still fail.
Removed the preceding unshipped numeric-object hypothesis: the confirmed response
is a list. A regression uses the exact owner-provided records and verifies all
three real names, selected-category lookup and an empty service-only catalogue.
No alternate endpoint, retry, credential or private Core fallback.

Owner also requested Categories inside Connection and detailed directory.
Added the tab beside Articles/Places/Sale units, using the existing approved
barsy_categories query, names only, explicit loading and 20-row pagination.
Both the commercial catalogue and detailed directory share the fixed backend.

Targeted checks: all **28 test_local_barsy cases** passed, including real Core
broker/grant/revocation against local HTTP fake; **53 UI tests**, strict typecheck
and production build passed against staged sources in
`.runtime/category-response-final/frontend/frontend-check.json`. Browser preview
with synthetic data verified expand → Categories → Load directory and a named
result. No installed/live Barsy acceptance is claimed. Preview closed.
Delivered 0.7.14 ZIP stays immutable. No version bump, new ZIP, deployment or
live Barsy mutation. The correction awaits separately requested packaging.
Diagnostic SSH connected but protected application data was unavailable to that
account; no privilege/access changes were made. Chrome was in active use and no
input action was completed there. Documentation credentials were not saved.

## Latest handoff: client and stay layouts, 0.7.14 ZIP, 2026-10-28

Owner requested clearer clients and stays, then a ZIP. Client lists in Desk and
Administration now show a name and status in a selectable row with visible and
accessible selection. Selected details are alongside the list on wide screens
and below it on phones. On Stays, filters are grouped; name and state lead the
row; details and finish actions are aligned and distinct; mobile rows carry
their labels. Existing permissions, confirmation, timer, locale, theme and data
handling remain in use. Core design tokens/components drive appearance.

Checked exact package `.runtime/application-checks/20261028-142444-9485487a`:
**99 Python and 51 UI tests**, no failures/errors/skips; standard activation and
restart, typecheck, production build, Core broker, presentation and input
integrity gates passed. Public Core-component synthetic preview reviewed dark/BG
desktop and 390px phone for client selection and Stays; light/EN desktop Stays.
Preview closed. Real Raspberry, live Barsy/fiscal acceptance remains pending.

Created `dist/3mm-child-center-0.7.14.zip` (83,540 bytes) and its SHA-256 file;
verified against the exact checked candidate:
`e3cd958975eec7008df34a5446add8cb6c8cd653319765a99878167fbcf0369f`.
The ZIP includes the previously unshipped family cashier, local running timer,
timestamp correction and local_0006 migration. Old 0.7.13 ZIP hash verified
unchanged. No Core edit, deployment, commit or live Barsy write.

## Latest handoff: family cashier flow, 2026-10-28

Owner requests the complete existing `/cashier` workflow, no additional screens.
Accepted: one shared Barsy bill per parent including all children's stays and
consumption; child choices remain per-child parental permissions; guardian
consumption comes from an administrator-selected Barsy category. All operator
work occurs in Child Center; Barsy handles POS/fiscal-device operations. Entry
opens/joins the family bill, exit pauses, reentry resumes, final checkout charges
measured time and consumption and closes the paid bill.

Owner confirmed that several separate bills can coexist on one Barsy place.
Removed the local exclusive-place index and remote empty-place preflight. The
existing Barsy settings now select a default place and guardian category. Verified
official Categories_getlist fields, Articles_getlist parent_cat_id (including
descendants), and the Accounts_close fiscal method through authorized docs access;
credentials are not stored in source or reports.

Implemented local_0006 membership migration: existing bill identities/orders are
preserved; unlinked active siblings join one unambiguous bill, and older separate
bills remain separate. A durable family-opening intent is created with entry.
An entry/startup/explicit-continuation-triggered native worker performs only
parent synchronization and empty-bill opening after commit. It does not depend
on an open browser, hold SQLite over HTTP, or periodically retry failed writes.
Prepared/uncertain journal fences survive restart; opening errors stay reviewable.
This is application-owned native processing, not a new general Core task contract.

Cashier lists one row per family bill. Overview has each child's pause/resume and
CAS-checked finish-all; each child's rounded duration contributes once to the
shared final time quantity. Consumption selects one child's own permission list
or the parent's paginated category catalogue. Add/charge/pay performs explicit
prepare, one send, and read-only verification with separate RPC receipts; transport
uncertainty stops the sequence. Payment uses documented Accounts_close, checks
remote identity, settled totals and unchanged quantities, and never repeats an
uncertain close. Existing separate commerce/visits/child-consent/payments rights
remain in force. Pending financial actions remain visible on all sections.

Exact-package gate `.runtime/application-checks/20261028-140133-288d1886/report.json`
passed: **99 Python / 49 UI**, no failures/errors/skips; standard migration,
activation/restart, Core connector/grant/revocation, strict typecheck, production
build, presentation and input-integrity gates passed. New checks cover family
membership/timing/consent/category separation, multiple bills on one place,
network entry/pause/resume, atomic migration rollback, changing-member CAS,
lost opening/fiscal replies with no replay, and actor-scoped continuation receipts.

Public Core component preview with synthetic data reviewed in light/EN and
dark/BG, including a 390px iframe. Child without permission has no article choice;
parent receives the separate category catalogue. Sections precede child controls;
payment stays disabled until final time is confirmed. Preview server/tabs closed
after review. No installed data, live Barsy mutation, fiscal print, Core edit,
deployment, version bump or distributed ZIP replacement. Source is still 0.7.13;
new packaging/version is a separate request. Real configured Barsy/fiscal-device
acceptance remains required. Setup: save default place/category, grant the staff
commerce/visits/payments permissions (children_manage for consent changes), then
exercise one family with two children through the existing Cashier route.

## Latest correction: timestamp display and system-zone contract, 2026-10-28

Removed GMT/Greenwich from ordinary timestamps. The repeated Sofia autumn hour
retains a numeric UTC offset only when needed to distinguish the two instants.
The frontend and date filters still use Europe/Sofia: Core's public presentation
facade exposes locale but no general system time zone. The maintenance-window
time zone is not a global setting. A general UI/service SDK contract and DST,
multi-client and live-change acceptance are recorded in
`CORE_PRESENTATION_CONTRACT.md`; no Core files were edited. Once Core supplies
the contract, update both formatting and calendar-day bounds together.

Exact staged frontend sources passed strict typecheck, production build and
45 UI tests including normal Bulgarian display and both repeated-hour offsets;
`.runtime/timezone-display/frontend/frontend-check.json`. No browser/device
review, deployment, version bump or ZIP. This correction and the preceding local
stay timer await a separately requested package.

## Latest correction: local live stay display, 2026-10-28

Owner requested a running timer on Stays without a heavy backend solution.
Frontend now takes the authoritative duration/phase from list_visits and uses a
monotonic browser clock plus one local second ticker for rows last observed as
inside. Paused and closed rows stay fixed. Every explicit refresh or successful
transition reanchors to the server response; no polling or new backend/API/DB
mechanism. Ticker and visibility listener are disposed with the page.

The label states that this display is approximate and requires refresh to see
changes from other devices. It is never used for finishing, billing or storage;
server state remains authoritative, including CAS and consent. Changes made by
another operator cannot be detected until refresh. Browser sleep/background clock
behavior can affect the approximation; refresh synchronizes it.

Exact frontend snapshot `.runtime/stay-live-timer/stage` passed strict types,
production build and **45 UI tests**; report
`.runtime/stay-live-timer/frontend-check.json`. New test covers active ticking,
minute rollover, paused/closed immobility, refresh reanchoring, zero extra API
calls and cleanup. Browser/public Core UI with synthetic data showed 10m 0s
advance to 10m 7s; no installed/Raspberry data was used. Reuse previous 91 Python
tests for unchanged backend/contract; not a fresh backend run. Preview closed.
No Core edit, deployment, version bump, ZIP replacement, commit or live Barsy
write. This frontend correction awaits a separately requested ZIP.

## Latest handoff: accounts/cashier layout and 0.7.13 ZIP, 2026-10-28

Owner requested the accounts/cashier visual improvement and ZIP. Accounts now has
Overview, Consumption and Journal sections; cashier defaults to Payment, with
Overview and Journal. Switching sections retains in-progress form choices.
Summary and all prepared/unconfirmed actions remain visible in every section;
technical command IDs are collapsed. An action belonging to another permission
explicitly tells the cashier/operator that an appropriately authorized staff member
must handle it. Journal consumption uses article labels, not numeric article IDs.
Existing one-send, review, quote and permissions behavior is retained.

To keep unresolved actions visible even when older than the current journal page,
the application detail query adds a separately bounded `attention` array (at
most one pending parent and one pending visit action, enforced by existing owner
uniqueness). No schema migration, Core change or automatic financial action.
The ZIP also contains the preceding Barsy article-name and mobile-row correction.

Full exact-package gate `.runtime/application-checks/20261028-130722-bd15280e/report.json`:
**91 Python / 44 UI**, no failures/errors/skips, standard activation, Core broker,
permissions, typecheck/build, presentation and integrity pass. RequireReady
exit_code=2 is remaining manual installed/financial acceptance. Includes an
unresolved action older than 50 journal records, section switching, draft
preservation, distinct permissions, no-replay, quote and consent checks.

Public Core UI browser review with synthetic data: light/EN desktop and dark/BG
390px cashier iframe. No mobile horizontal overflow; pending action visible and
other-role instruction present. Screenshots `.runtime/admin-preview/accounts-0.7.13.png`
and `cashier-0.7.13-mobile.png`. No real Barsy write or deployment.

Created `dist/3mm-child-center-0.7.13.zip` (74,474 bytes) and its checksum through
exclusive creation; SHA256 equals the checked candidate:
`a61e8b0b3a828e90087bc9a4175df1db939d2ad4520049f467be86d637eaa692`.
Delivered 0.7.12 SHA256 verified unchanged. No Core edit, branch/commit/tag/push.
Next: upload and approve the exact new package, then verify installed behavior.

## Latest correction: article names and mobile grouping, 2026-10-28

Owner reports numeric stay article/catalogue IDs are unhelpful and the mobile
row/buttons were visually ambiguous. Barsy settings now looks up the configured
stay article by its numeric ID through the existing bounded directory, displays
its name (or a localized unavailable indication), and renders catalogue rows
without article/place IDs. The read-only detailed article directory likewise
does not display article IDs. IDs remain in payloads/storage and no migration is
needed. On narrow screens each catalogue item has its own Core-token border,
padding and gap enclosing the label and both controls. Existing Core primary /
danger / neutral appearance, explicit save, permission and timeout behavior stay.

The existing barsy_articles query accepts an optional article_id, using Barsy's
existing article_id filter and length 2. The backend verifies exact identity and
refuses wrong/multiple rows; ordinary directory requests remain unchanged. Names
are transient, refreshed on access and never fabricated if Barsy is unavailable.
No Core change, real Barsy write, version bump, ZIP replacement or deployment.

Full local gate `.runtime/application-checks/20261028-130153-e7658c2c/report.json`:
**90 Python / 43 UI**, no failures/errors/skips, standard activation, Core broker,
typecheck/build, presentation and integrity pass. RequireReady exit_code=2 is
remaining manual installed acceptance. Tests cover exact-name lookup, wrong ID
refusal and no numeric IDs in the catalogue. Real public-Core synthetic preview:
390px dark/BG iframe, correct stay name and clearly bounded catalogue item rows;
`.runtime/admin-preview/barsy-names-mobile.png`. Preview closed. Corrections await
an explicitly requested new ZIP; delivered 0.7.12 remains unchanged.

## Latest handoff: Barsy settings layout and 0.7.12 ZIP, 2026-10-28

Owner requested the Barsy settings visual improvement and a ZIP. Arranged selected
time/unit, named places and consumption choices in one clear block. Catalogue
filters and actions are aligned; the duplicated lower summary and second save
button are replaced by one visible save/status bar. Kept explicit save/CAS,
uncertain-result review, primary/danger and neutral time buttons. Connection
check and the full read-only directory, including units, remain available inside
a labelled disclosure. One Core-locale string added (EN/BG); no Core edit.

Exact 0.7.12 package gate:
`.runtime/application-checks/20261028-124910-0ec9c3b8/report.json`: **89 Python /
42 UI**, standard activation, typecheck/build, presentation, broker and integrity
pass. RequireReady exit_code=2 is outstanding manual/installed acceptance. The
first gate had one stale translated-heading assertion; it was updated for the
new reference section, and the complete gate was rerun successfully.

Browser review with public Core UI and synthetic local data: dark/BG desktop,
light/EN outline, dark/BG 390px iframe. Mobile save/status bar had no horizontal
overflow; selected a stay article and saved it, then opened connection/reference
controls. Screenshot `.runtime/admin-preview/barsy-layout-0.7.12.png`. No live
Barsy writes or device deployment. Earlier 0.7.11 ZIP SHA256 checked unchanged.

Created `dist/3mm-child-center-0.7.12.zip` (73,499 bytes) and its checksum via
exclusive creation. SHA256 equals checked candidate:
`9e4009c209231854bfbe4321659d1523447acbd7401e816b09a3d02e9ee1724d`.
No Core change, branch/commit/tag/push. Next: upload and approve the exact new
package on the device and perform installed acceptance.

## Latest UI correction: standard Core primary/danger controls, 2026-10-28

Owner rejected visible Remove prefixes, green time selection, uneven catalogue
alignment and mixing solid danger with a custom outline green. Final explicit
instruction supersedes the former success-color request: use public UiButton
primary for additions, danger for removals. Removed cc-add and all custom action
color overrides. Time selection stays secondary/neutral; place and consumption
additions use primary. Core owns both palette and solid/outline appearance.

Configured place and article buttons show only their names, directly on danger
buttons; accessible names/tooltips still explain the Remove action. Name chips
wrap with spacing. Catalogue rows use aligned name/time/consumption columns with
a narrow-screen two-column control layout. Save changes semantics, CAS, pending
outcomes, service/contracts/storage and delivered ZIPs are unchanged.

Exact final frontend source snapshot `.runtime/core-button-style-check/stage`:
strict types, production build and **42 UI tests** pass; report
`.runtime/core-button-style-check/frontend-check.json`. Reused **89 Python**
evidence from the preceding unchanged backend/contract release gate. No new
backend run is claimed. Updated relevant UI assertions for primary additions,
neutral selected time and name-only danger buttons.

Actual browser/public Core components with synthetic data: dark/BG solid and
light/EN outline. Both primary and danger follow the same supplied Core setting;
time remains neutral. Catalogue button X coordinates match across rows. Screenshots:
`.runtime/admin-preview/core-actions-solid-dark.png` and
`core-actions-outline-light.png`. Preview closed. No Core edit, deployment, live
Barsy mutation, new version/ZIP, commit or push. This correction awaits packaging.

## Latest handoff: requested 0.7.11 ZIP, 2026-10-28

Owner requested a new ZIP containing all recent UI corrections. Bumped current
application/wheel version to 0.7.11; no additional behavioral change in packaging.
Exact-package full gate:
`.runtime/application-checks/20261028-122253-a30ab4d3/report.json`.
**89 Python / 42 UI**, no failures/errors/skips; standard activation/restart,
Core integration, strict types/build, presentation and input integrity pass.
RequireReady exit_code=2 remains manual installed/commercial/fiscal acceptance.
Prior visual evidence is reused for unchanged UI sources.

Created `dist/3mm-child-center-0.7.11.zip` (73,191 bytes) and `.zip.sha256` with
exclusive creation, without replacing earlier ZIPs. SHA256 equals checked candidate:
`802e0f606f1f101467e09b057936b3cd37d2172461d2597c5d9f7aca4a17962b`.
Delivered 0.7.10 hash verified unchanged. Includes removal of reload navigation,
selection/consent save feedback, named configured places and semantic green add /
danger remove buttons. Explicit Save changes remains per owner decision.
No Core edit, device deployment, live Barsy write, branch/commit/tag/push.
Next: upload/approve this exact package and verify UI/commercial behavior on device.

## Latest UI correction: named places and semantic action colors, 2026-10-28

Owner requested configured place names instead of IDs and red danger removals,
then clarified green additions/red removals. Explicit answer: colors only;
changes still require Save changes. No immediate-persistence behavior was added.

Configured places now render named rows with separate accessible danger Remove
buttons. Article removals also use danger; catalogue additions/time selections
use Core's success foreground/border token with an outline (the public button
has no success variant or success text/background pair). Danger styling and all
palette values remain owned by Core/theme settings, without hardcoded colors or
application preferences. No Core code edit.

To resolve names on initial opening without crawling the catalogue, existing
barsy_places query accepts optional max-32 place_ids. Projection filters before
the existing 20-row pagination; the external Places_getlist request is unchanged.
UI fetches at most two pages of configured IDs, also learns names from manual
catalogue pages, and falls back honestly to Place #ID if a label is unavailable.
Settings still save numeric IDs, not labels. Names clear on access refresh.

Full gate before the final color-only styling:
`.runtime/application-checks/20261028-121549-a9e56e30/report.json` — **89 Python /
42 UI**, standard activation, Core grants/broker/kiosk, types/build, presentation
and integrity pass. RequireReady exit_code=2 remains manual installed acceptance.
Final color/layout sources: `.runtime/place-buttons-check/stage`, strict types,
production build and **42 UI** pass; `.runtime/place-buttons-check/frontend-check.json`.
89 Python evidence reused for unchanged backend/contracts after that full run.
Tests cover initial label lookup, danger style, explicit draft-only removal,
save of only remaining IDs, and bounded filtering across both directory pages.

Actual dark/BG browser with synthetic data confirms named rows, red removals,
green additions and readable spacing. Screenshot:
`.runtime/admin-preview/place-action-colors.png`. Preview closed. No version bump,
ZIP replacement, deployment, live Barsy write, branch/commit/push or Core change.

## Latest UI correction: visible commercial selection/save, 2026-10-28

Owner reports Use for stay time appears inert and child consumption cannot save.
Diagnosis: time selection changes only a draft; the save/readout was above the
catalogue, off screen, with no local acknowledgement. Screenshot's consent-save
button is disabled because parent attestation is unchecked. No backend failure
after attestation was reproduced; do not claim an installed failure was diagnosed.

CommerceSetup now marks the selected time article (aria-pressed), prevents
time/consumption overlap, shows the current draft plus unsaved/saved status and
an adjacent Save changes button below the catalogue. Still explicit one local
CAS save; no automatic external write. Consent form now explains the attestation
requirement, guards submit independently of HTML validation, reports successful
save after reloading the child choices and stops showing success after new edits.
Uncertain-outcome and permission protections remain unchanged.

Final exact UI snapshot `.runtime/selection-fix-check/stage` passed strict types,
production build and **41 UI tests**, report
`.runtime/selection-fix-check/frontend-check.json`. Extended the configuration
test through draft selection/save/reload and added consent pre-account save,
attestation gating, persisted selection and stale-success cleanup. Targeted
`tests/test_local_commerce.py`: **24 passed**, including new pre-account consent
save with CAS and permission denial, with zero outbound Barsy calls. Other
unchanged service/Core integration evidence remains the previous full 87-test
gate; not claimed as a fresh full run of this UI patch.

Real browser/public Core components with synthetic local host: clicked time and
consumption selection, saved and observed reloaded values; checked parent
attestation and clicked native submit, observed persisted selection + success.
Screenshots `.runtime/admin-preview/settings-saved.png` and `consent-saved.png`.
Visual evidence precedes only the final stale-success-on-further-edit guard,
which is covered by the final UI test. Preview closed; no live Barsy write,
Core/device change, commit, version bump or delivered ZIP replacement. These UI
corrections and removal of reload navigation still await a new requested ZIP.

## Latest UI correction: remove document-reloading navigation, 2026-10-28

Owner's reload-button message was criticism of the new in-application navigation,
not a request for additional reload buttons. Removed the mistaken ReloadPage
addition completely. Removed Navigation.vue and its duplicate route-anchor bar
from Desk/Visits, Accounts/Cashier, Administration, Barsy and Readers. Those href
links caused full document loads. Existing Core Menu/ApplicationShell and Command
Palette already use router transitions with Core route/auth/locale/theme handling;
use that navigation. Keep explicit data Refresh buttons and internal client/stay
controls. No history/popstate trick, private router injection/import, new public
API or Core edit. Public application host currently exposes no navigation facade.

Targeted final source snapshot `.runtime/navigation-fix-check/stage` passed strict
types, production build and **40 UI tests**, evidence
`.runtime/navigation-fix-check/frontend-check.json`. Previous **87 Python** evidence
is reused only for unchanged service/contracts/storage. No new backend run or
new release claim. Actual dark/EN synthetic admin preview confirms the duplicate
bar is gone: `.runtime/admin-preview/navigation-clean-dark.png`. Preview closed.
Delivered 0.7.10 ZIP remains unchanged; this UI correction awaits a separately
requested new package/version. No deployment, real Barsy call or commit.

## Latest handoff: requested 0.7.10 ZIP, 2026-10-28

Owner requested the ZIP after interactive commerce completion. Bumped only the
current application/wheel version from 0.7.9 to 0.7.10; no business/UI changes.
Full exact-package gate passed **87 Python / 40 UI**, types/build, real standard
activation/restart, migration/rollback, Core broker/kiosk/readers, presentation
and input integrity. Report:
`.runtime/application-checks/20261028-113245-e15e96b8/report.json`.
RequireReady exit_code=2 is remaining installed/manual acceptance, not an
automatic failure. Earlier desktop/mobile visual evidence is reused: UI unchanged.

Created `dist/3mm-child-center-0.7.10.zip` (72,658 bytes) and `.zip.sha256` without
overwriting existing files. SHA256 exactly matches the checked candidate:
`13a42da76d85f2fbb18ea182c2e5d1a6d0757d7233ee26b1fbaf708382747993`.
Delivered 0.7.9 hash verified unchanged. No Core edit, deployment, real Barsy
write, branch/commit/tag/push. Next: upload 0.7.10, approve its exact native/UI and
mutating connector scope, assign commerce/payments staff permissions, configure
commercial articles/places and perform supervised real Barsy/cashier acceptance.

## Current scope: interactive commercial completion, 2026-10-28

Owner authorized completing the interactive application. Work remains exclusively
in this application checkout; no Core edit, device deployment, live Barsy write,
branch/commit/version/tag/push or delivered ZIP replacement. Mock-reader test is
owner-accepted. Background connector composition and sensor-confirmed access,
automatic retention and old commercial-database import remain separate scope.

Working source adds local_0005 (forward/atomic, no reset), commercial settings
from the directory, per-child consumption choices in staff/kiosk registration
and an explicit timestamped staff consent correction. Registration notice now
describes parent-contact transmission to Barsy. Accounts route prepares parent,
place/account, consumption and final time. Stable identities, current parent,
free place, timer-off and fixed-quantity unit/precision checks precede sends.
Minutes round once; zero time has no sale. Barsy owns all prices.

Cashier route requires payments_manage independently of commerce/stay rights.
Actor-scoped two-minute quotes, actual receipt confirmation and rechecking the
amount/method precede one payment/close POST. Cash/manual confirmed card only;
no card terminal/fiscal device driver. There is a read/verify path for outside
payment closure, including matching quantities and closed/paid/fx evidence.

Durable prepared/uncertain/confirmed/cancelled ledger commits uncertainty before
POST. Retries/restarts never resend an uncertain step. Lost acknowledgements need
explicit remote review; missing/extra quantities or wrong identities cannot be
confirmed. Only unsent prepared steps can be cancelled. Stable subject-scoped
RPC receipts cover interruption separately from external business reconciliation.
No SQLite transaction spans the network. Each send has at most one POST and an
8.5s budget with declared 2s connector deadlines. Export includes commercial
records and consent; unsettled accounts block erasure. Outside closure review
refuses more than 1000 journal steps rather than loading unbounded data.

New explicit native_sqlite_interactive_commerce_events_v1 preset supports this
mutating declaration; starter/read-only presets still reject it. Future package
needs new exact native/UI/connector approval and explicit staff permissions.
Prior delivered 0.7.9 stays immutable. The previous query-error and Stay details
UI corrections remain in working source too.

Final exact-source gate:
`.runtime/application-checks/20261028-112107-c3099f5d/report.json`.
**87 Python / 40 UI**, zero failures/errors/skips; strict types, production UI
build, package/preset, real activation/upgrade/restart, presentation and input
integrity passed. Includes exact Core native/resource grant and SDK broker to a
local HTTP fake (one mutating parent send, no replay, denial after credential
revoke), crash after external effect, migration rollback, stale observation/races,
missing quantities and unknown unit metadata. RequireReady returns exit_code=2
for remaining manual/installed acceptance, not an automatic check failure.

Visual check with synthetic data and real public Core components: desktop light/EN
account journal exposes uncertain steps immediately and collapses confirmed ones;
dark/BG cashier in a real 390px iframe, amount/method and confirmation controls.
Dialog clientWidth=scrollWidth=340; long technical IDs wrap. Screenshots:
`.runtime/admin-preview/commerce-light.png` and `commerce-mobile-dark.png`.
No real financial/fiscal result is claimed. Preview tabs/server closed at handoff.
Delivered 0.7.9 SHA256 verified unchanged:
`c96d5866fcedb94633e52eb024642246a71c3fdcb394cb77e1239383fc7abe61`.
Next: owner-requested distinct-version ZIP, exact Core approvals, commercial
configuration and supervised real Barsy/cashier acceptance. No platform blocker
is inferred for the completed interactive scope.

## Latest handoff: visible Stay details dialog, 2026-10-28

Owner confirms the reader test passed, then reports Stay details appears to do
nothing. Treat the reported mock-reader acceptance as accepted; do not reopen
the former provider onboarding blocker or infer physical-reader acceptance.
Read-only device journal shows get_visit returning HTTP 200 repeatedly. The app
rendered its result below the full stay table, with no scroll/loading indication.

Working source now uses public Core UiDialog for Stay details. It opens
immediately with loading feedback, then named child/parent and the paginated
timeline. Errors/retry are visible in the dialog; retry is explicit and read-only.
Close/Escape/section change/Refresh invalidate the pending detail response, so a
late reply cannot reopen it or restore personal fields. Actual access_denied
clears access and closes the dialog. Core owns theme/focus/top layer; app adds
only EN/BG Close labels. No database/API/business behavior change.

Added two UI regressions for immediate dialog loading, exact visit/page identity,
timeline rendering, pagination, late reply after Escape, visible query error,
explicit recovery and denial cleanup. jsdom's native dialog presentation methods
are shimmed only in tests; actual browser review verifies the real component.

Current Core source changed its public UI CSS import and requires exact fresh
provider health for event grants. Updated this checkout's public-source test
snapshot to include Core CSS, and refreshed the synthetic reader fixture's health
digest after its declaration change. No Core code edit or bypass. First check
exposed these fixture/toolchain changes; final exact sources pass the full gate:
`.runtime/application-checks/20261028-092433-5783a713/report.json`.
**64 Python / 35 UI**, no failures/errors/skips, strict types/build, package,
actual host lifecycle/upgrade, kiosk, broker, presentation and integrity passed.
RequireReady remains exit_code=2 only for manual/installed acceptance.

Actual browser with synthetic data: light/EN desktop dialog, Escape restores focus
to Stay details, and dark/BG dialog inside a real 390px iframe. Timeline wraps,
controls remain visible. Screenshot `.runtime/admin-preview/stay-details-dialog.png`.
Preview tabs/server closed. No installed application/UI change, deployment,
version bump, dist ZIP replacement, live Barsy call, branch/commit/tag/push.
Delivered 0.7.9 remains c96d5866fcedb94633e52eb024642246a71c3fdcb394cb77e1239383fc7abe61.
Next: owner-requested next-version ZIP, then installed dialog acceptance. Earlier
query-error UI correction is also still in working source awaiting that build.

## Latest diagnosis: mock scans accepted but no application activity, 2026-10-28

Follow-up screenshot: Application access offers connector:barsy_api only; event
checkboxes are absent. The prior instruction to select reader_primary was
therefore incomplete. Read-only resolution on installed Core confirms both event
scopes return SourceIssue reason capability_unresolved. The effective registry
for the selected Raspberry exposes only gpio.digital.control; there is no
device_capability_providers row advertising/selected identifier.scan.v1. Agent
hello's bare capability and successful event ingestion do not create an approved
effective provider. Current consent preview consequently has subject_version=1,
zero resolved events and no event choices; optional unresolved resources are
omitted. This is a Core/Agent mock-provider integration gap, not an app mode/tag
setting or a checkbox the owner missed. No permission/provider was fabricated.
Required general correction and acceptance added to the existing Core contract.
Owner still owns Core work; no Core source/device mutation here. Need that fix,
fresh explicit event consent, then one NEW scan; never replay old test scans.

Owner emits TEST-001 through the installed Agent mock reader; UI shows selected
device and automatic mode but no activity. Read-only SSH/SQLite mode=ro verifies:
Agent mock driver enabled, reader.mock.1; outbox empty; all 3 scans stored in Core
device_events (IDs 18/19/20), including two after policy revision 2 became active.
Child Center 0.7.9 is active/enforced, both reader config slots select the same
Raspberry device; reader policy saved correctly. However sealed grant selection
contains only connector:barsy_api, no event:reader_primary/reader_secondary.
No application_event_deliveries exist for the installation and no local reader
receipts exist. Missing event approval explains this test's empty activity;
bracelet matching has not yet been reached. Selecting device != approving its
event scope. No new scan, grant/config edit, replay, restart or deployment by agent.

Next: owner approves the chosen event subscription in Core Application access,
preserving existing Barsy/user selections, follows Core lifecycle prompts, then
emits ONE fresh scan and checks Refresh. Historical unadmitted scans must not be
replayed or turned into stays. Both slots currently point to one device; primary
scope alone suffices for this one-source test, second scope is optional. Existing
original-ID dedup protects delivery via both subscriptions if both are approved.
Documentation-only diagnosis; no runtime tests required or claimed for this edit.

## Active diagnosis: installed 409 on page reads / misleading access message

Owner supplied the exact response: list_registrations HTTP 409 with
`Application result is unconfirmed; do not replay`. This is Core relay's generic
boundary error; it still hides the original cause. Extended the local exact-ZIP
test to actual ApplicationResponses socket/FD relay and concurrent UI-bound HTTP
reads, retaining production's 0.25-second key admission budget. Targeted current
test: **1 passed / 33 dependency warnings / 6.96 seconds**. Earlier full 64/33
report is reused for unchanged production/UI; it does not cover this later test
edit. Final expanded integration itself passes; no installed HTTP fix claimed.

Additional installed read-only probe uses the real Core UID/groups/environment,
current package preparation and actual Runtime response handoff: both
list_registrations and get_reader_settings return verified schema-valid frames.
It does not run HTTP actor re-admission or the completion write fence. Thus the
remaining Core confirmation failure needs its original exception/stage; changing
Child Center business logic or replaying requests has no evidence behind it.
The precise evidence and next Core diagnostic/acceptance scope are appended to
the existing CORE_KIOSK_AND_READER_CONTRACT.md. Core is still read only; moving
that diagnostic/fix into Core requires owner scope, per the earlier instruction.

Owner reports pages first load and later show Read unavailable / Access is
unavailable with HTTP 409. Existing authorized SSH diagnostics are read only.
Current device logs confirm exact 0.7.9 artifact, ui-host GET 200 followed by
list_registrations POST 409 while list_visits POST 200, and get_reader_settings
409 while list_reader_activity 200. Some older ui-host requests also returned
409; this is not proof of a business permission revoke.

Read-only signed native probes on the installed host succeed for all those reads,
including simultaneous registration/stay reads; installed package output schema
validation also passes. No business mutation, permission change or restart.
The separate Core code trust inspection passes sequentially/concurrently on ARM;
observed cold/warm costs alone do not establish the cause of the HTTP failures.
An initial diagnostic used the default unconfigured database URL and created an
unused zero-byte DB under the deployed release; that exact newly created empty
file was checked and removed immediately. Subsequent metadata reads explicitly
use SQLite mode=ro against the actual Core DB. No installed data was changed.

One concrete app UI defect fixed in working sources: Desk, Administration and
Readers cleared the permission catalog for every failed read, incorrectly treating
query/transport conflicts as revoked access and hiding the page. They now clear
personal results but retain the last freshly checked catalog for generic failures;
explicit public host access_denied still removes access. Successful explicit
refresh clears stale read/access messages. No automatic retry, command replay,
HTTP bypass or stale personal data retention was added.

Added 3 UI regressions across those pages: initial success -> query conflict ->
clear personal results without false access loss -> explicit successful refresh
clears error -> explicit access denial clears access. Expanded exact-package
HTTP integration with concurrent reads. Its Core policy fixture uses production
configured_manager's 0.25-second admission lock budget: default fail-fast policy
fixtures reproduce UI code trust unavailable during contention, whereas the
production-budget run passes. This is a diagnostic clue, NOT confirmation of the
device's exact 409 reason or authorization to alter Core locks.

Final local report `.runtime/application-checks/20261027-213343-c2fa5c76/report.json`:
**64 Python / 33 UI**, zero failures/errors/skips; all automatic gates/types/build
and exact-input integrity passed. RequireReady still exit_code=2 for installed/
manual acceptance. No layout/style changes; prior visual evidence reused.

**Remaining task:** root cause of installed HTTP 409 is not yet proven/fixed.
Asked owner asynchronously for Network -> failed request -> Response/detail only,
without Authorization/tokens. The public host deliberately maps POST failures to
unconfirmed, and device access logs do not include their response body. Retain
this diagnosis until exact detail is available; do not claim the 409 is solved.
Core remains read only. No new version/build delivery, deployment, commit or
live Barsy call. Immutable delivered 0.7.9 stays
`c96d5866fcedb94633e52eb024642246a71c3fdcb394cb77e1239383fc7abe61`.

## Latest handoff: owner-requested 0.7.9 ZIP

Owner requests a new ZIP. Module/wheel version advanced to **0.7.9**; no behavior
change in this build turn. Includes the previously checked browser/USB/stay
history, optional network reader and new-Core kiosk integration work.

Exact-version full report:
`.runtime/application-checks/20261027-210115-ce2ae6e2/report.json`.
**64 Python / 30 UI**, no failures/errors/skips; all automatic gates passed,
including types/build, real host upgrade/restart, Core HTTP optional-device
activation, exact-package kiosk pairing/renew/revoke and event delivery tests.
RequireReady exit_code=2 records outstanding manual/device acceptance only;
platform_blockers=[] and local_checks_passed=true. Reuse prior visual evidence
for identical UI; no device acceptance claim.

Copied the exact tested candidate bytes, without rebuilding, to
`dist/3mm-child-center-0.7.9.zip`, **49645 bytes**, with sibling `.zip.sha256`.
SHA256: `c96d5866fcedb94633e52eb024642246a71c3fdcb394cb77e1239383fc7abe61`.
Copy hash matches the report. Delivered 0.7.8 remains unchanged at
`fc77ca39c64ea0559b9c8ef0a3ffceedbb8607053f8bcc8fbbea726c7e09b90d`.

Requires the newly completed Core kiosk/optional-device implementation on the
target; Core reports it has not yet been deployed to Raspberry. After rollout,
old kiosk terminals require re-pairing. No Core edit, deployment, reset, live
Barsy call, branch/commit/tag/push or publication. Next acceptance: upload 0.7.9
after Core rollout, fresh exact native/UI approval, clean-browser kiosk pairing
and real reader/USB workflow. Barsy commercial work remains deferred.

## Latest handoff: integration after Core kiosk/optional-reader completion

Owner reports Core complete and authorizes finishing this application integration.
Read current Core WORKING_STATE/public contracts: Extensions terminals,
`/kiosk/connect`, original claim recovery, single-flight auth-only renewal,
mounted-surface revoke and optional device omission/clear are now Core-owned.
Child Center continues using declared kiosk routes and the public host; no new
pairing facade, private HTTP, token/credential store or Core source edit is needed.
Core says Raspberry has not been updated and legacy terminals require re-pairing.

Closed the former optional-reader blocker using the actual Child Center package:
HTTP activation runs real wheel/migrations/signed host with zero devices and no
binding, primary only, and both slots selected. Missing keys remain absent;
an explicitly unknown supplied ID refuses before helper dispatch. Removed that
demonstrated obsolete blocker from app-development.json; hardware acceptance
remains an explicit manual gate. Earlier blocker descriptions below are history.

Added tests/test_local_kiosk.py: exact ZIP compiled by Core's real compiler,
current sealed native/UI review and grant, separate actual application host,
Core HTTP enrollment/claim and same-proof recovery, kiosk-only compiled catalog,
UI-bound signed registration/invoke, original outcome read, session renewal,
same-ID replay with exactly one submitted record, cross-terminal outcome
isolation, forbidden listing and immediate denial after terminal revocation.
Only the disposable process controller/HTTP response-transport harness replace
installed systemd/Runtime services; no fake pairing, grant, native app or result.
Updated direct native human test envelopes with Core's required stable subject_id;
application behavior and kiosk terminal identity rules are unchanged.

Final full report:
`.runtime/application-checks/20261027-205917-11e85a44/report.json`.
**64 Python / 30 UI**, no failures/errors/skips. Package/preset, actual host
activation/restart and populated upgrade, reader broker/dedup/revoke, connector
regressions, frontend types/build, presentation and exact-input integrity passed.
The first current-Core run exposed obsolete test expectations/envelopes; the
final report covers the corrected current sources, not a relabelled old run.
RequireReady exit_code=2: local_checks_passed=true, platform_blockers=[],
release_ready=false only for outstanding installed/manual acceptance.

No product UI/layout changes: reuse previous dark/BG, light/EN, live locale and
390px preview evidence for identical application UI bytes. No browser pairing on
installed Core or real hardware is claimed. README, feature map and existing
Core handoff now describe the supported path and old-terminal re-pairing.
Documentation-only handoff text after the run does not invalidate runtime checks.

No Core/device edit or deployment, live Barsy call, reset, version bump, dist ZIP
replacement, branch/commit/tag/push. Delivered 0.7.8 SHA256 still
`fc77ca39c64ea0559b9c8ef0a3ffceedbb8607053f8bcc8fbbea726c7e09b90d`.
The checker-built candidate is test evidence using the working version, not a
replacement installable release of that immutable version. Next: owner-requested
distinct-version build, new Core rollout and real clean-browser/kiosk/reader
acceptance. Barsy commercial behavior remains deferred.

## Latest handoff: network reader processing and separate Core kiosk contract

Owner requests self-service kiosk connection and network readers. After the
missing public kiosk bootstrap was identified, owner explicitly chose **prepare
the exact contract for the separate Core task**. Core remains read only; no
private HTTP/token wrapper was restored. The contract is
`docs/CORE_KIOSK_AND_READER_CONTRACT.md`: Core-owned terminals/code claim UI,
concrete transport DTO additions, recoverable one-time claim, renewal with no
business replay, revocation, installation isolation and required acceptance.
Kiosk self-service is therefore pending Core implementation, not delivered here.

Application implementation:
- Optional primary/secondary Core-selected `identifier.scan.v1` subscriptions,
  existing public protocol decoder, internal original event identity, signed host
  callback and after-commit acknowledgement. Own SQLite receipt deduplicates
  duplicate/restarted delivery in the same transaction as stay/timeline changes.
  Wrong-source, old-policy, out-of-order/reassigned-tag, future, degraded and
  unmapped scans do not mutate stays. Raw tag/metadata are not copied into the
  technical receipt. No door command, finish, billing or Barsy write.
- `/child-center/local/readers`, administrator + readers_manage: mode disabled by
  default, automatic toggle or explicit entry/exit IDs, CAS settings and paginated
  outcomes. Public Core UI/theme/locale, EN + reference BG, stale-read clearing,
  durable uncertain-save lookup with no replay. Selected devices/grants are set
  in Core, not by app-owned discovery/credentials.
- Additive local_0004 settings/event receipts migration preserves old records.
  Kiosk request/outcome keys now include verified SDK terminal_id; two terminals
  cannot read or replay one another's request. Missing identity denies. Existing
  audience-only receipts are preserved and not guessed into a terminal owner.

Demonstrated **Core blocker**: final HTTP activation recheck treats absent optional
event device keys as required (409); Extensions configuration also requires a
nonempty device list. Regression reproduces omission failure and exercises actual
activation with both slots explicitly selected. The checker retains this blocker;
the contract specifies the general correction and denial/race cases. No fake
default device, check bypass or Core edit. Reader-enabled release waits for this
fix; hardware/installed acceptance also remains pending.

Final full report: `.runtime/application-checks/20261027-183447-dd8e67a3/report.json`.
**61 Python / 30 UI**, zero failures/errors/skips; types/production build,
deterministic ZIP/Core validation, real native host activation/reactivation and
populated upgrade, connector regressions, public presentation and input integrity
passed. The event integration uses real Core review/grant/event delivery and a
signed separate native host, verifies duplicate subscriptions produce one stay,
then revokes the grant and proves no further app dispatch. Synthetic Linux
fixtures, not a physical reader or Raspberry/systemd test. RequireReady records
exit_code=2 / release_ready=false for the explicit blocker and manual acceptance.

Disposable preview inspected dark/BG and light/EN with Core outline/raised
appearance, live EN→BG preserving reader fields, and an actual 390px iframe
including the lower activity table. Screenshot `.runtime/admin-preview/readers.png`.
Preview tabs/server closed. Documentation-only handoff edits after the full run
do not alter its declared inputs or runtime evidence; checks are reused for them.

No version change, dist ZIP replacement, installed device change, reset,
branch/commit/tag/push or live Barsy call. Immutable delivered 0.7.8 hash remains
`fc77ca39c64ea0559b9c8ef0a3ffceedbb8607053f8bcc8fbbea726c7e09b90d`.
Next: separate Core implementation against the contract, then next-version build
and clean browser/kiosk + real reader acceptance. Barsy commercial work remains
deferred.

## Latest handoff: browser/USB local workflow, stay history and staff registration

Owner confirms **0.7.8 works on Raspberry and reads real Barsy**, and explicitly
defers the remaining Barsy integration. Do not reopen that accepted connection.
Asked about target hardware; owner selected **browser + USB/keyboard scanner for
now**, not a tablet/network-reader integration. Core remains read only. Scope of
this bounded result is the local employee registration/scan/stay/history workflow.

Implemented:
- `/child-center/local/register-staff`, authenticated operator audience with the
  existing registrations_manage permission; same registration component now
  chooses the authorized staff registration vs kiosk submission operation. Staff
  saves approved records; kiosk still submits for approval. Explicit fullscreen/
  exit affects the registration main only. Browser rejection leaves the form
  usable; fullscreen listeners are removed on unmount. No auth/enrollment bypass.
- Desk USB/manual scanner now identifies the named child and proposed entry,
  pause or resume before an explicit confirmation. `preview_scan` returns an
  opaque CAS digest covering assignment, child/name, active stay, phase, latest
  transition timestamp AND journal sequence (same-clock phase cycles cannot
  resurrect an old confirmation). `confirm_scan` validates that snapshot in the
  mutation transaction and uses the existing durable actor/request outcome
  handling. Lost replies are not replayed. Changed code, refresh/unmount or stale
  preview replies cannot restore a previous child's confirmation. The existing
  direct explicit-action scan operation remains available; the UI uses the guarded
  confirmation flow and never auto-toggles a keyboard event with no stable ID.
- Stay search by parent/child name, active/history selection and paginated detail.
  Optional calendar-day start filters use Europe/Sofia on the service, including
  the 25-hour DST day. A connection-local SQLite casefold function handles Cyrillic
  without searching guardian contact fields through stay permissions. UI times
  show Sofia and UTC offset, disambiguating repeated local DST hours.
- Additive **local_0003** transition journal. Entry/pause/resume/finish is atomic
  with the stay, technical receipt and audit. Existing stays get explicitly marked
  historical snapshots; no invented pause/resume times or changed totals. Detail
  events paginate; subject exports include events with the existing bounded inline
  export refusal policy. No reset, automatic retention, financial mutation or
  installed data migration was performed. Standard runtime upgrade checks now
  cover the complete migration chain.

Final full check report:
`.runtime/application-checks/20261027-180004-51adc2a3/report.json`.
**46 Python / 27 UI tests**, zero failures/skips; strict types/build, exact ZIP
validation, actual host initial activation/reactivation and populated upgrade,
existing Core connector setup/authority/fake-server/revocation regressions,
catalog/presentation and input integrity all passed. RequireReady remains
exit_code=2 / release_ready=false for manual/device acceptance, not a test failure.
Tests include stale/reassigned/same-clock scanner snapshots, idempotent no-extra-
event replay, atomic rollback on event-write failure, old-data preservation,
timeline pagination/kiosk denial, Cyrillic/date/DST boundaries, delayed previews,
staff registration and fullscreen refusal. No live Barsy request was made.

Disposable synthetic-data browser review covered desktop dark/BG stay scan and
event detail, light/EN staff registration, actual fullscreen entry/exit, and an
actual 390px iframe viewport with vertically/horizontally scrolled content. Fixed
the root grid's min-content expansion so the table cannot push controls outside
the narrow viewport; fullscreen aligns form content at the top. These layout
fixes are in the final tested sources. Screenshot:
`.runtime/admin-preview/stay-history.png`. Preview tab/server closed afterwards.

No version bump, new dist ZIP, Core edit, device deployment, reset, branch,
commit/tag/push or publication. Delivered 0.7.8 SHA256 stays
`fc77ca39c64ea0559b9c8ef0a3ffceedbb8607053f8bcc8fbbea726c7e09b90d` and does not
contain this new slice. Feature map records owner acceptance only for the stated
0.7.8 application/Barsy evidence, not every historical permission/device case.
Next: owner-selected new-version build and actual USB/browser acceptance. Remaining
larger scope includes public self-service kiosk bootstrap/renewal, Core/network
reader and physical access composition, explicit retention policy and legacy
0020 import. Barsy commercial work remains deferred by the owner.

## Latest handoff: owner-requested 0.7.8 build

Owner requests the next build after Core locale/Barsy directory integration.
Selected next patch version `0.7.8` to preserve delivered 0.7.7; module/wheel
versions and README updated. No additional behavior/schema change.

Full exact-version checks:
`.runtime/application-checks/20261027-133454-b917fa1b/report.json`.
All automatic gates passed: **40 Python / 23 UI tests**, no skips/failures,
types/build, actual host activation/reactivation, schema-upgrade preservation,
Core connector setup/authority/fake HTTP/revocation, public presentation/catalog
and exact-input integrity. Reused previous visual evidence for unchanged UI.
RequireReady reports **exit_code=2**, `local_checks_passed=true`, platform blockers
empty and release readiness false pending manual/device/real Barsy acceptance.

Copied the exact checked ZIP, without rebuilding, to
`dist/3mm-child-center-0.7.8.zip`, **36571 bytes**. SHA256:
`fc77ca39c64ea0559b9c8ef0a3ffceedbb8607053f8bcc8fbbea726c7e09b90d`.
Sibling `.zip.sha256` provided; copied bytes verified against the report.
Delivered 0.7.7 hash remains unchanged. No Core/device change, live Barsy traffic,
commit/tag/push or publication. This version includes locale + read-only Barsy
directory, not account/consumption/payment workflows. Next: owner uploads it,
uses Core Extensions settings/approval and performs installed acceptance.

## Latest handoff: Core locale and first Barsy integration

Owner reports the needed Core capabilities implemented and requests Barsy and
localization integration. Read the current Core working state/public types:
initial/live locale is public presentation v1 plus a reactive loader root prop;
connector setup is Core's Extensions settings gear, **not** the proposed app
administration facade. Core remains read only; all changes are in this checkout.

Child Center now reads host.presentation synchronously and subscribes/unsubscribes
for live locale. The real loader's matching reactive prop remains authoritative
when supplied. Removed artificial default EN props that masked host presentation.
Required EN per-key/language fallback and optional BG catalogue are preserved;
there is no app locale selector, private Core import or extra preference store.
The obsolete locale platform blocker is resolved on the updated Core, while
installed acceptance remains manual. Starter comments/metadata now reflect the
implemented loader prop; its plain native-SQLite resource profile is unchanged.

Declared optional SDK 1.3 `connector:barsy_api`: Core-owned Basic credential
reference and plain origin configuration; narrow `/endpoints/json/` prefix,
read-only, timeout 5s, request 8KiB, response 512KiB. No URL or credential defaults.
Unconfigured/ungranted Barsy permits normal local health/registration/stay use.
New administrator route `/child-center/local/barsy`, separate `barsy_manage`
permission, offers explicit personal POS check and articles/places/sale-unit
directory reads. Endpoint filters/projections follow the preserved original
service. Bounded pages, strict IDs/duplicate validation, service-place exclusion,
redacted failures, no partial results, no network during mount/health and no retry.
External reads hold no local SQLite transaction; no app data/schema changes.
The app never receives a password, calls private HTTP or sends a commercial
mutation. Parent sync, accounts, consumption, billing/payment journals and
periodic workflows remain unported (CC09–CC13), not silently replaced by a new
billing implementation. This agreed first integration slice is complete locally.

The checker now supports an explicitly selected
`native_sqlite_read_connectors_v1` profile with those bounded optional connector
constraints. Original starter defaults remain strict and mutation declarations
are refused by the read-only profile. Exact-package integration uses Core's real
compiler/build provenance, Core-owned settings/bootstrap and native/UI/resource
review, the existing SDK method + Core admission/broker test transport, a local
fake HTTP server verifying injected Basic authentication, and real credential
revocation that denies the next request before external I/O. It is not a signed
separate network-worker/systemd/ARM or live Barsy test. Test-only POSIX policy keys
use cleaned Linux temporary directories, never weakened Windows mount modes.

Final full gate run:
`.runtime/application-checks/20261027-121010-0087645b/report.json`:
**40 Python / 23 UI tests**, zero skips/failures, strict types/production build,
real standard host activation/reactivation and populated schema upgrade,
catalog/presentation checks and exact-input integrity passed. RequireReady
`local_checks_passed=true`, **exit_code=2**, `release_ready=false` solely for
retained manual acceptance; platform_blockers is empty. Early integration fixture
failures were corrected (real POSIX key directory, real compiled UI provenance/
review and SDK-to-broker body decoding), not bypassed. Final run tests all fixes.

Disposable browser review with current public Core components/CSS/design defaults
covered light/solid and dark/outline/raised, initial BG, live BG/EN and unknown
language EN fallback with search/results preserved. Screenshot:
`.runtime/admin-preview/barsy-dark.png`. It uses synthetic data/public presentation
fixture, not an actual installed shell; phone/device/real Barsy acceptance remains.
Preview tab/server closed. Feature map and current contract docs updated.

No version bump, new dist ZIP, commit/tag/push, Core change, device deployment,
reset, real Barsy traffic or financial action. Delivered 0.7.7 SHA256 remains
`61ca8fe59354b2ae23e0f827f00b0047aafa7678e676ab073dd53aa822f4ad85` and does not
contain this new integration. Next owner-selected action: a new-version build and
normal Core settings/approval/device test; then port the original durable
commercial workflows under their separate confirmation/reconciliation rules.

## Latest handoff: owner-requested 0.7.7 ZIP

Owner explicitly requested version 0.7.7. Updated the authoritative module/wheel
versions to `0.7.7` and README; no additional functional/schema change. Includes
the administration slice described below; Barsy remains proposal-only and the
Core initial/live locale binding is still absent. Core/device state unchanged.

Full exact-version gate run:
`.runtime/application-checks/20261027-090919-d5d69a1d/report.json`.
All automatic gates passed: **23 Python / 19 UI tests**, no skips/failures, strict
types, production build, actual host activation/migration/reactivation, public
presentation/catalog policy and exact-input integrity. RequireReady reports
`local_checks_passed=true`, **exit_code=2**, `release_ready=false` for retained
platform/manual blockers. Reused preceding visual fixture review; presentation
sources/dependencies are unchanged by this version-only build.

Copied the exact checked candidate without rebuilding to
`dist/3mm-child-center-0.7.7.zip`, **30667 bytes**. SHA256:
`61ca8fe59354b2ae23e0f827f00b0047aafa7678e676ab073dd53aa822f4ad85`.
Sibling `.zip.sha256` provided; copied bytes verified against the check report.
Earlier ZIPs remain unchanged. No commit, tag, push, publication or device upload.
This is the owner-requested test package, not full Barsy/product readiness.
Next: owner upload/normal approval, verify administration and retained client data
on device; implement the generic connector setup contract in a separate Core task.

## Latest handoff: administration and the Barsy setup contract

Owner accepted the preceding local workflow and requested administration/Barsy.
On identifying the absent public connector setup facade, the owner explicitly
selected a precise Core contract and **no temporary HTTP/CLI workaround**.
Work remains exclusively in this application checkout; Core was read only.

Implemented `/child-center/local/admin`, permission `administration_manage`,
administrator audience: bounded client search/pagination, selection, correction
of guardian contacts/name and existing child names, with revision CAS and durable
actor-scoped outcomes. Stale corrections retain the form and refuse overwrites;
lost responses are looked up without resending. Child IDs, consent and all stay/
bracelet relationships remain unchanged. Export and confirmed erasure use the
selected client instead of copying a UUID and retain their existing separate
privacy permission and active-stay refusal. Delayed reads/replies are discarded;
revoked refresh clears personal data. EN and optional reference BG cover new text.

Additive `local_0002` migration adds revision=1 to existing registrations; the
first migration remains unchanged. Approval/erasure advance revision. Tests cover
populated local_0001 upgrade with IDs/receipts/bracelets/active stays intact,
idempotent migration and refused downgrade. The real standard host reactivation
test also upgrades a populated local_0001 schema and replays the original receipt.
Recovery is through the standard activation snapshot and matching old package,
not an automatic schema downgrade or a reset. No installed database was touched.

`docs/CORE_CONNECTOR_ADMINISTRATION_CONTRACT.md` records read-only Core evidence,
typed proposed inspect/configure/outcome API, explicit route/connector allowlists,
Core-owned credential dialog, atomic configuration+binding, CAS and redacted
receipts, revocation, and unconfigured-installation bootstrap **before** native
approval. It includes required Core security/activation tests and the subsequent
Barsy port order. This is a proposal, not an implemented/exported SDK API. The
current package still declares no connector; catalog/account/payment operations
are not yet ported. No live Barsy request or financial action was made.

Final full local gate run:
`.runtime/application-checks/20261027-085946-3247a00e/report.json`:
**23 Python / 19 UI tests**, zero skips/failures, strict types, production build,
real activation/migration/reactivation, presentation/catalog rules and exact-input
integrity all passed. `local_checks_passed=true`, RequireReady **exit_code=2**,
`release_ready=false` for the retained Core locale/manual deployment blockers.
First frontend checks caught UiField prop mistakes; corrected final sources were
tested in this run. No claim that earlier runs covered later corrections.

Visually inspected the final administrator edit screen in a disposable browser
fixture with the actual public Core components, CSS, default design variables,
light/solid and dark/outline/raised appearance. Reference BG and unknown-locale
EN fallback render correctly; this fixture supplies locale explicitly and is not
evidence that the installed Core loader now supplies it. Fixed application label
layout overriding UiField required markers. Screenshot retained under
`.runtime/admin-preview/dark.png`. Phone/systemd/ARM/actual permission and installed
UI acceptance remain pending. Preview uses synthetic data only.

No new dist ZIP, version bump, branch, commit, Core edit, device deployment or
publication. Previously delivered local.2 artifact remains unchanged and does not
contain this administration slice. Next: separately implement/accept the generic
Core connector setup contract, then prove a connector-enabled profile with a fake
server and port the original Barsy workflows. A requested upload build must use a
new version rather than overwrite delivered local.2.

## Latest handoff: owner-requested theme test build

Owner requests a build and testing of the current presentation work. Module
version is now `0.7.6-local.2`, Python wheel `0.7.6+local.2`, avoiding collision
with the already uploaded local.1. No schema, Core/device, commit/tag/publication
or deployment change. Full Windows-wrapper run:
`.runtime/application-checks/20261027-083020-614e8f33/report.json`.
All six automatic gates passed: **20 Python / 15 UI tests**, zero skips, types,
production build, real standard host initial activation/reactivation, catalogue/
presentation policy and exact-input integrity. RequireReady returns **2**, not
release acceptance: actual Core locale binding and manual/device checks remain.

Copied the exact checked candidate, without rebuilding different bytes, to
`dist/3mm-child-center-local-0.7.6-local.2.zip`, **26226 bytes**; SHA256
`76ca39fd30d96559c0eaf362f6f30bd13763cbcd0f688d988347f3c27219b001`.
A sibling `.sha256` file is provided. All declared source hashes matched at
delivery. Previous ZIPs remain immutable. This is an explicitly requested test
artifact, not a claim of full release readiness or an installed ARM test.

Owner next: upload/activate the new version, perform normal exact-artifact UI
approval if requested, test Core light/dark/button/card settings and the local
registration/bracelet/stay workflow while retaining data. Expected language is
English until Core supplies the documented locale capability. No agent device
upload or UI automation occurred.

## Current result: Core-owned presentation and English-first application catalogues

Owner clarifies that all theme/appearance settings and the active language must
come from Core. Applications support multiple languages; missing languages/keys
fall back to English. Bulgarian is optional reference data, never mandatory or
the fallback. This does not authorize modifying Core in this workspace.

Child Center routes now use actual public UiSurface/UiButton and registration
UiField components. Surface/card/button appearance, font, density, control sizes,
radii, focus and colors come from Core's CSS/context. App CSS retains layout,
viewport adaptation and --ui-* tokens, with no palette or OS dark-mode logic.
Native phone input retains type=tel and uses the public ui-control styling.
The separate LanguageSwitch and local preference/event store are removed.

Added stable message-key JSON catalogues: required `locales/en.json`, optional
`bg.json`, currently 100 English/reference keys. Lookup normalizes the input
locale, tries its regional/base catalogue, then English per key. Unknown/missing
English source keys are authoring errors checked before delivery. Domain error
keys are rendered in the current input locale, so already displayed errors also
retranslate. Adding a catalogue requires registry membership, not a new Core
business branch or a second language preference. Builder stages nested JSON.

The same locale/fallback mechanism is in the starter. Root `locale?: string`
props are a tested read-only preview/input boundary, not a fabricated Core API.
The inspected public host still has no initial/current locale subscription, so
installed routes default to English until the separately scoped Core binding is
implemented. That remains an explicit platform/readiness blocker. Requirements
and a proposal-only API are in `docs/CORE_PRESENTATION_CONTRACT.md`.

Final full gate run via the Windows wrapper:
`.runtime/application-checks/20261027-082305-8ff04070/report.json`:
**20 Python / 15 UI tests passed**, no skips, strict types/production build,
actual host activation/reactivation, presentation/catalog policy and exact inputs
all passed. Tests cover English per-language/per-key fallback without Bulgarian,
regional locales, form preservation, retranslation of an existing refusal and
live Core-provided button/card appearance through the real UiSurface. Static
authoring rules now also reject application theme preferences, OS-derived dark
mode and hardcoded surface/control palettes. The initial run caught the removed
language.ts reference in the feature map; the corrected final full run is green.

Freshly generated `.runtime/core-presentation-verified` also passed all automatic
gates (one behavior/two UI tests plus real host activation/restart and types/build):
`.runtime/core-presentation-verified/.runtime/application-checks/20261027-082305-869175e1/report.json`.
Both reports record **exit_code 2 / release_ready false** under RequireReady,
correctly retaining the Core locale binding and manual visual/installed checks.
No claim that the props are already supplied by Core or that screenshots have
been accepted. Core/device state is unchanged; no new dist ZIP, version bump,
commit, publication or deployment. Previous delivered ZIPs are unchanged and
do not include this new working UI. Next: separate Core locale contract work,
owner visual acceptance, then the next feature-map slice.

## Previous result: feature map, application starter and acceptance command

Owner requests these three deliverables after identifying installation, scope,
theme and translation failures. Work stays in this application repository; no
Core source, device, installed service, grant, network, commit/tag/publication or
product version changed in this pass. The product's known visual/locale defects
are recorded and detected, not represented as repaired by this tooling task.

- `docs/CHILD_CENTER_MAP.md` / `docs/child-center-map.json`: 20 feature areas,
  original/current source references, current gaps and concrete acceptance. Later
  implemented release decisions override historical plans. Local checks are not
  installed business acceptance. Unported Barsy/recovery/data import remains
  visible; unsupported periodic/sensor composition is separated from available
  interactive connector mechanisms. Retention policy needs explicit product
  agreement rather than assuming indefinite storage restores earlier behavior.
- `templates/native-app` and `tools/new_application.py`: new-directory-only
  standalone approved-native/own-SQLite skeleton with descriptors, deterministic
  wheel/ZIP builder, migration, durable actor-bound request/outcome example,
  public UiSurface/UiButton, behavior/UI tests and copied acceptance tools. No
  private Core frontend APIs, new component framework or external package.
  The locale preview prop is explicitly NOT current Core locale integration.
- `tools/check_application.py` orchestrates exact ZIP/preset validation, real
  host migration/health/reactivation, declared Python tests, staged-ZIP frontend
  checks, presentation rules and input-integrity hashes. It writes each run to a
  fresh ignored directory. `tools/application_process_check.py` is the shared
  subprocess supervisor extracted from the activation tests; no second activation
  implementation or fabricated ready client. `check_local_frontend.mjs` now reads
  the project's declarations and public UI snapshots rather than hardcoded routes.
- `tools/Check-Application.ps1` provides the one-command Windows/WSL entry. Machine
  paths are configured only in ignored `.runtime/application-dev.json`.
  Reproduction and the separate Core dependencies are in
  `docs/APPLICATION_DEVELOPMENT.md`. No new release ZIP is delivered by this task.

Final evidence:

- Generated `.runtime/starter-verified` from the template and ran the copied
  checker through the actual Windows wrapper with `-RequireReady`. All six local
  gates passed: real host/socket initial activation and reactivation/data check,
  one behavior test, two UI tests, strict types/production build, public component
  rules and exact-input integrity. Report
  `.runtime/starter-verified/.runtime/application-checks/20261027-075601-df464264/report.json`
  records `local_checks_passed: true`, `release_ready: false`, **exit_code 2**:
  Core initial/live locale binding plus manual visual/installed acceptance pending.
  No skipped tests treated as passes. This is a locally checked skeleton, not
  a fully integrated locale/theme/ARM product acceptance claim.
- Final Child Center run via `.\tools\Check-Application.ps1 -RequireReady`:
  `.runtime/application-checks/20261027-075817-c33b40d2/report.json`.
  **19 Python tests passed / zero skips**, **12 UI tests passed**; type-check,
  production build, actual activation/reactivation and exact inputs passed.
  The 19 include the existing 15 domain/activation cases plus four authoring-tool
  checks. **presentation_contract FAILED / exit_code 1 / release_ready false**,
  correctly identifying missing public UiSurface/component reuse, obsolete
  CSS theme tokens and the application-managed Core locale store/event. This
  expected rejection is not a successful application release gate.
- Source/ZIP hashes, logs and exact scope are stored per run. Required output
  test counts must be nonzero and unskipped. --require-ready distinguishes local
  test success from pending product/platform/manual acceptance. Static UI scans
  are diagnostic authoring rules, not a security or visual proof. The target
  Raspberry's installed build/systemd/native binary is still a separate check.

Next bounded result: move the existing Child Center UI onto the public components
and correct tokens using the feature map, without silently dropping domain work.
Core must separately expose/define a typed initial locale/subscription and target
execution-profile preflight. These are described requirements, not permission to
modify Core. Visual acceptance remains with the owner. Do not clear blockers or
manual requirements merely to make the acceptance command green.

## Previous result: ordinary activation correction

Owner reports the delivered 0.7.6 ZIP fails activation and leaves `Recovery
Required`. Local reproduction through the actual current
`activate_application_package` raises `Application relational storage runtime is
not implemented` before creating runtime paths. Package/schema validation did
not cover this gate. The earlier candidate's 11 Python/12 UI passes were not
installation readiness; the earlier 0.7.6 local ZIPs are withdrawn for ordinary
installation, including `dist/3mm-child-center-local-0.7.6.zip`.

Owner explicitly chooses **application-owned SQLite on the standard activation
path**, replacing the scoped-SQL design. Current descriptor no longer requests
`storage.relational`; the service uses SDK 1.3 `ApplicationStorage.transaction`
and checks its migrated schema through `status`. No fallback or removal of an
existing prepared relational lifecycle is attempted. Native code/UI consent and
Core human permission checks remain required. This profile has no per-SQL
transaction grant or cooperative scoped SQL bounds; it trusts the approved native
application to manage its own database. No jobs, connectors, hardware commands,
network grants or task loops are introduced.

Corrected module version **0.7.6-local.1** is distinct because Core enforces
unique `(module_id, version)` for uploaded packages. Python wheel distribution
version is PEP 440 `0.7.6+local.1`; this is a local candidate, not publication of
the historical commercial 0.7.6 release. No Git commit, push or tag.

All source edits and retained evidence are in `3mm-child-center`. Current Core
SDK/runtime/routes were read-only test dependencies, with Python bytecode writes
disabled. Real test Unix sockets/data use disposable short Linux `/tmp` paths,
removed after each test; logs/XML/hashes stay under `.runtime/activation-checks`.
No installed service, Raspberry state, credentials, network or Core source changed.

## Verification and artifact

- Final targeted integration command: `python -m pytest -q
  tests/test_local_profile.py tests/test_local_activation.py -p no:cacheprovider
  --basetemp=.runtime/pytest-release-own
  --junitxml=.runtime/activation-checks/results-final.xml` with current read-only
  Core source on PYTHONPATH and `PYTHONDONTWRITEBYTECODE=1`.
  **15 passed / 12 dependency or test-environment warnings / 7.03 seconds**.
- The new activation tests use the actual standard runtime activation, wheel
  import/migration and separate application-host process with signed AF_UNIX
  health and SDK requests. They prove initial activation, registration, kiosk
  audience denial, reactivation with SQLite snapshot/data preservation and stable
  request replay without duplicate registration. Systemd's process controller is
  replaced with a disposable subprocess supervisor; no fake ready client.
- Actual Core HTTP activation endpoint and its SQL lifecycle journal return
  `200 / active / enabled` through a test helper bridge invoking the real runtime.
  Anonymous and ordinary staff activation are denied before helper dispatch.
  The helper IPC/root/systemd/OS-principal boundaries are not installed acceptance.
- Regression tests reproduce the rejected scoped SQL descriptor and prove the
  current own-SQLite package refuses an existing `relational.json` without changing
  it or starting a process. This is not authorization to downgrade existing data.
- Domain tests retain registration/approval, Cyrillic search, audience/actor
  isolation, idempotency, bracelet CAS, pause/resume and single rounding, stale
  finish fence, clock rollback, privacy export/erasure and legacy-data refusal.
  The old mocked scoped-transaction grant test is removed; it is not evidence for
  the newly selected storage model.
- UI unchanged: reuse the checked 12 UI tests, strict vue-tsc and Vite production
  build. Every UI source hash matches `.runtime/local-profile/evidence-r2.json`.
  No new browser/device visual acceptance claimed. UI still uses the public host,
  BG/EN selection, theme tokens, late-response guards and explicit outcome review.

Current ZIP: `dist/3mm-child-center-local-0.7.6-local.1.zip`, **23573 bytes**.
SHA256: `c9a59fa94064a30392c8da5832e6bfd2fa6b0235432265fa0d9e4f9f932332a4`.
Deterministic bytes pass current Core ZIP validation for aarch64 structure and
standard wheel-name parsing. Final source hashes/XML hash and precise scope are
in `.runtime/activation-checks/evidence.json`. This is Linux process/HTTP evidence,
not an installed ARM/native-binary/systemd or Raspberry result.

## Owner recovery and next acceptance

The already failed 0.7.6 card is lifecycle-fenced; uploading a new ZIP alone does
not clear its `Recovery Required`. Use that Child Center card's ordinary Uninstall
flow: it first verifies/stops an interrupted runtime and preserves data. Do not
choose data erasure. Then upload the corrected distinct version and follow normal
application access/native UI consent. If uninstall/recovery refuses, retain the
specific response and investigate; do not delete/reset the database or repeatedly
activate the old ZIP. No device recovery has been performed by this agent.

Storage schema remains `local_0001`. Historical commercial 0020 databases require
a separately reviewed import and are refused, not reset. Barsy, effectful
recurrence, sensor-confirmed access, new kiosk enrollment/token renewal and
installed visual/upgrade acceptance remain separate work. The original commercial
source/builder remains unchanged and excluded from the local candidate.
