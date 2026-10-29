# Child Center application extension

## Current application: 0.7.22

The current application uses manifest v2, the public Core application SDK/UI host
and its own migrated SQLite storage (`local_0007`). Its working entry points are:

- `local_contract.py` and `build_local_package.py` for the application package.
- `service/child_center_local/` for registrations, stays, family billing and recovery.
- `source/frontend/local/` for the operator, kiosk, administration and cashier UI.
- `app-development.json`, `tools/` and `templates/native-app/` for repeatable
  application development and acceptance checks.

The working flow covers registration/approval, bracelets, entry/pause/resume,
parental consumption permissions, one family Barsy bill, stay charging and
cashier payment/closure. Core supplies identity, permissions, connector credentials,
locale and the visual theme. Network reader events and Core kiosk pairing are
integrated; turnstiles and physical device/failure acceptance remain to be finished.
Known slow operations/lost replies still need platform stabilization.

**Debug mode** is in **Child Center -> Administration -> Application settings**.
Save the switch there; other open pages read it on refresh. Normal mode uses clear
confirmation buttons, quiet progress indicators and actionable errors. Uncertain
external results are checked using their original identity without replay.
The Core Extensions gear manages connector settings and credentials.

Build a new, non-existing output path with:

```sh
python build_local_package.py --output dist/3mm-child-center-0.7.22.zip
```

Run the local checks with `tools/Check-Application.ps1` in the configured Windows
workspace, or follow [APPLICATION_DEVELOPMENT.md](docs/APPLICATION_DEVELOPMENT.md).
See [WORKING_STATE.md](docs/WORKING_STATE.md) for exact check/artifact evidence and
remaining device acceptance. Generated ZIPs and runtime/check outputs are ignored.
The tag-publishing workflow still uses the historical builder; review it before
requesting a tag or GitHub release.

## Development entry points

### Version 0.7.16: parent identity verification

Package: `dist/3mm-child-center-0.7.16.zip`. Uses the same documented exact-code
client lookup for synchronization and account opening, including the linked
Barsy client ID. A hidden card code in Clients_get no longer blocks opening.
Real differences still refuse before creating a bill; EN/BG messages identify
missing code/client or differing ID, name, phone or email. Continuing uses the
existing prepared command. Earlier distributed ZIPs remain immutable.

### Version 0.7.15: family account opening and parent consumption

Package: `dist/3mm-child-center-0.7.15.zip`. Fixes parent identity and place
validation during automatic family-bill opening. A lost opening reply is
reconciled by its exact marker without creating another bill. Cashier shows
opening progress and loads the configured parent category when Parent is selected;
products and quantities go onto the shared family bill. Child consents remain
separate. Includes the category parser fix and Categories in the detailed directory.
Installed Core UI-trust failures still require their separate Core correction.

### Version 0.7.14: family cashier and client/stay layouts

Package: `dist/3mm-child-center-0.7.14.zip`. Client lists now show clear names,
statuses and selection, with details alongside on desktop and below on mobile.
Stay filters and actions are clearer, and narrow screens show readable stay rows.
The package also includes the family cashier workflow, local live stay display
and timestamp display correction described below.

This replaces the separate-stay/manual-opening workflow of the older packaged
versions below. Work stays on `/child-center/local/cashier`.

- In the existing Barsy settings select a **default place** and a **parent
  consumption category** from the catalogue, then save. The category includes
  its subcategories. Several separate family bills may use the same place;
  its Barsy time calculation must remain off.
- First entry records a durable family-opening intent. The supervised native
  service links the parent and opens one empty Barsy bill after the scan commits,
  without needing an open browser. Other children's entries join that family
  bill; each child retains its own time and parental consumption permissions.
- On Cashier, Overview shows the children and pause/resume controls. Exit pauses
  time and reentry resumes it on the same bill. Consumption selects a child and
  its permitted articles, or the parent's configured category catalogue.
- Finish all family stays, then **Charge stay time**. Each child's measured stay
  rounds up to a minute once; quantities are summed and priced by Barsy. On
  Payment, read the current amount, select a supported payment method and confirm
  receipt, then **Pay and close bill**. This uses the documented `Accounts_close`
  fiscal workflow. Real printer/payment acceptance is still required.
- Add/charge/pay each prepares one durable command, sends it once and checks its
  result. Uncertainty stops the sequence. Pending commands remain visible; use
  explicit review, not a new sale/payment. Automatic opening never sends time,
  consumption or payments, and has no periodic retry. Opening errors require
  cashier review/Continue account opening.

Staff need `commerce_manage` for bills and consumption, `visits_manage` for
pause/resume/finishing and `payments_manage` for payment. Child-consent changes
also need `children_manage`. These permissions remain distinct.

Migration `local_0006` preserves existing bill identities and data, groups
unlinked active siblings only when there is one unambiguous family bill, and
removes the one-bill-per-place index. Several older bills for the same parent
remain separate and must be settled before a new family stay. Nothing is reset,
merged remotely or billed retrospectively by migration. A checkout in progress
blocks new stays until that family bill is settled.

Verified official API references (documentation access required):
[category list](https://docs.lukanet.com/barsy.api/methods/categories/getlist.html),
[article filters including parent_cat_id](https://docs.lukanet.com/barsy.api/methods/articles/getlist.html),
[fiscal close](https://docs.lukanet.com/barsy.api/methods/accounts/close.html).

### Previously packaged versions

Version **0.7.13** packages the account/cashier layout with overview, consumption,
payment and journal sections. Prepared and unconfirmed actions stay visible across
sections and journal pages. It also includes the Barsy article-name/mobile layout
correction. Artifact: `dist/3mm-child-center-0.7.13.zip`.

Version **0.7.12** packages a more compact Barsy configuration screen, including
one save status, aligned catalogue controls and a collapsible connection/detailed
directory section. Download `dist/3mm-child-center-0.7.12.zip`. Existing Core
theme, roles and explicit save behavior continue to apply.

Version **0.7.11** packages the subsequent UI corrections:
Core navigation instead of the duplicate full-reload link bar; visible time
selection and save feedback; explicit child-consent save guidance; configured
place names from Barsy, green add actions and red danger removals. Changes still
require Save changes. Artifact: `dist/3mm-child-center-0.7.11.zip`; earlier ZIPs
remain immutable. Installed commercial/fiscal acceptance remains required.

Version **0.7.10** packages **interactive commerce** in
`dist/3mm-child-center-0.7.10.zip`. All automatic gates pass; installed commercial
and fiscal acceptance remains required. Delivered 0.7.9/0.7.8 stay unchanged.

1. Core Extensions: configure the Barsy connector, then approve the new exact
   native/UI artifact and its **mutating** connector scope. Grant application
   `barsy_manage`, `commerce_manage`, `children_manage` and/or `payments_manage`
   to the appropriate staff. Core administrator status alone is insufficient.
2. Child Center → Barsy → Commercial configuration: choose the time article,
   hours/minutes, places and consumption articles from the directory. Hours need
   at least three decimal places; fixed-quantity articles only, Barsy timers off.
3. Register/approve the parent and children; record each child's permitted
   consumption articles. Assign a bracelet and start the local stay as before.
4. Accounts: select the stay, prepare parent synchronization, **Send once**, then
   **Check result**. Repeat those explicit steps to open the account at a free
   configured place and add permitted child or separate guardian consumption.
5. Finish the local stay, then prepare/send/check its final time quantity.
   Minutes round up once; Barsy supplies pricing. Zero time creates no sale.
6. Cashier (separate `payments_manage`, no stay permission required): read the
   current amount, select cash or independently confirmed card, confirm receipt,
   prepare/send/check payment. Quotes belong to the current actor and expire in
   two minutes; the amount/method/account are checked again before sending.

Prepared steps can be cancelled before sending. **Unconfirmed results cannot be
resent or cancelled.** Use Check result; a lost opening reply needs the exact
Barsy account ID. Lost sale/payment acknowledgements need an explicit review in
Barsy as well as matching account quantities/closure evidence. Cashier can verify
an externally completed, paid and closed account without posting another payment.
No card terminal or fiscal device is driven by this app. Financial/fiscal
acceptance on the actual configured Barsy is still required.

`local_0005` migrates existing local data without reset; existing children start
with no consumption permission. Exports include commercial records/consent;
unsettled accounts block erasure. No automatic financial send is attached to
kiosk submissions, scans or finishing a stay. The explicit interactive preset
uses public SDK connectors, at most one POST per send, 2s connector deadlines and
an internal 8.5s operation budget; no network spans a SQLite transaction.
Background processing, sensor-confirmed physical access, automatic retention
and historical commercial database import remain separate work. Delivered
0.7.9 and 0.7.8 ZIPs are unchanged; 0.7.10 requires fresh exact-package approvals.

Version **0.7.9** packages the browser/USB registration and stay-history work,
optional network readers and integration with Core-owned kiosk pairing. It needs
the updated Core kiosk/optional-device mechanisms described below. Storage moves
to `local_0004` without a reset. Delivered 0.7.8 stays immutable; Barsy commercial
work remains deferred. New artifact: `dist/3mm-child-center-0.7.9.zip`.

Working sources add `/child-center/local/readers` for administrators with
`readers_manage`: optional Core-selected devices, explicit disabled/toggle/
directional modes, and paginated technical outcomes. Processing starts disabled.
Core delivers `identifier.scan.v1` through its broker and signed native host;
the original event ID deduplicates stay/timeline changes atomically. Late,
unmapped, degraded or wrong-source scans do not toggle a stay. No raw tag or scan
metadata is stored in the technical reader journal. Schema `local_0004` adds
settings/receipts without resetting existing data. No physical access or Barsy
mutation is added.

The current local Core implements the [kiosk/optional-reader contract](docs/CORE_KIOSK_AND_READER_CONTRACT.md).
The exact Child Center package is tested through Core code pairing/recovery,
kiosk-only catalog, signed native registration, token renewal, terminal isolation
and revoke. Standard HTTP activation now succeeds with zero devices, one selected
reader or both optional bindings; an unknown supplied device still denies.
Pairing/credentials stay entirely in Core. Roll out the new Core before installed
acceptance; legacy kiosk terminals require re-pairing. Delivered 0.7.8 is unchanged.

For installed acceptance after that rollout:

1. Upload the next distinct Child Center version and approve its exact native/UI
   artifact. In Core Extensions use **Terminals / Connect kiosk**, create a code
   and open its Core link (or `/kiosk/connect`) on the registration browser.
2. Submit a registration on the connected kiosk; it must appear for staff approval.
   Check session renewal and revoke in Core. The revoked kiosk must lose access.
3. For network readers, select approved event devices in Core configuration and
   approve their event scopes. In Child Center **Readers**, enable automatic or
   directional mode with the reader IDs shown in activity. Repeated delivery of
   the same event must not toggle twice. Separate scans use distinct event IDs.
   Device transport/driver setup remains in Core; Child Center consumes its events.

Working sources after 0.7.8 add the owner-selected browser/USB workflow:
`/child-center/local/register-staff` for an authenticated employee (existing
`registrations_manage` permission), fullscreen registration, named bracelet
preview + explicit confirmation, and stay search/details with Europe/Sofia date
filters and UTC offsets. New transitions have an atomic paginated timeline;
`local_0003` preserves existing stays as explicitly incomplete historical
snapshots. It does not invent old pause/resume events or reset data. Subject
exports include these events within the existing bounded export limits.
These changes are not in the immutable delivered 0.7.8 ZIP. Barsy behavior is
unchanged; the owner confirmed 0.7.8 works on Raspberry and reads real Barsy data.

- [Full Child Center migration map](docs/CHILD_CENTER_MAP.md): original behavior,
  current coverage, gaps and acceptance criteria; machine source is JSON.
- [Application starter and one-command checks](docs/APPLICATION_DEVELOPMENT.md).
  From this configured Windows checkout: `.\tools\Check-Application.ps1 -RequireReady`.
- `templates/native-app` plus `tools/new_application.py` create a new standalone
  project with the verified ordinary native/own-SQLite preset and public UI.
- [Core connector administration contract](docs/CORE_CONNECTOR_ADMINISTRATION_CONTRACT.md):
  original proposal and the implemented Core Extensions setup path.

Version **0.7.8** integrates Core's public
initial/live locale and optional **read-only Barsy directory**. Route
`/child-center/local/barsy` requires administrator audience + `barsy_manage`.
Configure the Basic connection using the Core Extensions settings gear (plain
origin, no endpoint path), follow Core's stop/review/access approval flow and
activate. Native/UI review must cover the exact new artifact. Unconfigured or
ungranted Barsy does not prevent local registrations/stays; directory reads show
unavailable. POS/articles/places/sale units load only on explicit request; no
account/order/payment is created. The application never receives credentials.
The original financial journals are preserved but are not ported to this profile.
Tests use a fake HTTP server, not a live Barsy installation.

The owner-requested build is `dist/3mm-child-center-0.7.8.zip`. The delivered
0.7.7 ZIP remains unchanged and lacks these new integrations. Neither package
includes account creation, consumption delivery or payment workflows.

Version **0.7.7** adds `/child-center/local/admin`: administrator-only
client search/correction with revision conflicts, plus export/erasure of the
selected client. Names/contacts can be corrected without changing child IDs,
consent, bracelets or stays. The already delivered local.2 ZIP is unchanged and
does **not** contain this administration slice. The delivered 0.7.7 has no Barsy connector or billing.

The working UI now uses public components/Core theme tokens and no application
theme/language selector. English is the required catalogue and per-language/key
fallback; Bulgarian is optional reference data. Public initial/live binding is
implemented; actual installed visual/device acceptance remains pending.
See [the presentation contract](docs/CORE_PRESENTATION_CONTRACT.md). No new release ZIP is implied.

## Local candidate for the current Core — 2026-10-27

**The earlier 0.7.6 local ZIP is withdrawn for normal installation:** it requested
scoped SQL, which the standard activation path refuses. The corrected local
version is **0.7.8**, using owner-approved application-owned SQLite.

The first migration slice is an independent **local candidate**, built with
`build_local_package.py`. It contains staff/kiosk registration, approval,
bracelet assignment/replacement/retirement, explicitly selected start/pause/resume,
operator-finalized measured stays, history and administrator data export/erasure.
The UI uses `@3mm/application-ui/v1`; the service uses SDK 1.3
`ApplicationStorage` for its own SQLite database. Native application approval and
Core human permissions still apply. There is no per-transaction scoped SQL grant
or cooperative scoped-SQL quota in this profile. It has no jobs or physical command.
Working sources add the optional read-only connector and event subscriptions above.

```powershell
python build_local_package.py --output .runtime/child-center-candidate.zip
```

Output must be a new file. Version 0.7.7 includes the administration slice,
Core theme/component and catalogue changes. Its locale binding was completed
later in working sources. Installed acceptance remains pending. Earlier ZIPs are unchanged; this test build is not a
full product release. The wheel contains only `child_center_local`; historical
commercial/access services and release patch scripts are not bundled. The local
candidate uses version 0.7.8 to avoid replacing previously uploaded
package identities. It is not a published release and
must not be substituted for an existing commercial installation. It uses the same
application ID, so it cannot be installed alongside that installation on one Core.

Routes: `/child-center/local` (registrations staff), `/child-center/local/visits`
(visits staff, independent of registration permission), `/child-center/local/register` (already
enrolled kiosk), `/child-center/local/privacy` (administrator). Reader input in
this slice is a keyboard scanner or a manually entered code. Scan/identify the
bracelet, inspect the named child and proposed entry/pause/resume, then confirm.
Changed assignments/stay transitions invalidate that confirmation. Finish excludes paused
time and rounds total measured microseconds upward to minutes once. It creates
no bill or payment. Finishing first shows the selected child's name for explicit
confirmation and refuses a changed stay snapshot. A backward wall clock cannot
start a new stay before that child's previous finish. UI time is a snapshot at
refresh, not a continuously running counter. The working UI accepts a read-only
locale input, preserves forms on changes and falls back to English per key.
The current public Core loader supplies the reactive locale prop; the application
also consumes public host.presentation and unsubscribes on unmount. No local
preference/store is used. Theme and appearance come from Core's
public UiSurface/components and --ui-* tokens. Stale read/export replies are discarded, and malformed mutation/receipt
responses keep the original uncertain request blocked for review.
Terminal enrollment and automatic kiosk-token renewal are implemented by Core;
the application uses its public host without an authentication store. An
unavailable/revoked host stops requests and Core removes the kiosk surface.

Working-source storage revision `local_0004` adds reader settings and event receipts
after `local_0003`'s stay timeline and `local_0002`'s client revision column;
populated upgrade and real host reactivation are locally tested.
The first migration is **fresh-profile only**. Historical 0020 data has
no automatic import into this profile; migration refuses a legacy database.
There is no reset, deletion or production upgrade procedure in this work.
For rollback, retain the previous immutable package and the standard activation
data snapshot; restore the matching snapshot via Core recovery before starting
the previous schema. Calling an older migration target is refused, not a rollback.
Standard activation now runs the application's own schema migrations in the
normal host. Native UI/code consent and human permission grants are still
required before using the application screens. ZIP validation alone is not an
activation test. Preserve existing data/rollback snapshots and perform
the eventual import as a separate reviewed task.

Mutations use durable actor-bound request identities and receipts. Domain
refusals are recorded distinctly from transport/SQL uncertainty. After a lost
reply, the UI looks up the original identity without replay. Unknown remains
unknown; continuing requires explicit manual review of saved records. Only opaque
identities, never contact payloads or credentials, are kept in browser session
storage. Exports include subject contacts/consent, children, assignment history
and visits; oversized inline exports refuse instead of truncating. Explicit
erasure is blocked by active stays, clears personal fields and bracelet codes,
and preserves technical history/receipts. It does not erase downloaded exports,
SQLite free pages, independent backups or external records.

Before delivery, run both `tests/test_local_profile.py` and
`tests/test_local_activation.py` against the current read-only Core SDK/runtime.
The activation checks use an actual separate host process and signed Unix
sockets; only systemd/helper transport is replaced with an isolated test bridge.
They do not test the installed Raspberry/systemd policy.

For the earlier failed card: use its ordinary **Uninstall** action, which first
checks/stops an interrupted runtime and preserves data. Do not select data
erasure. Then upload the corrected distinct version. If recovery/uninstall
itself refuses, retain the error and stop; do not reset/delete its database or
retry the failed activation. No device recovery was performed by the agent.

Current scope and verification: [working state](docs/WORKING_STATE.md).
The builder and the release notes below describe the historical commercial
package, not the local candidate.

`org.3mm.child-center` is an independent `ApplicationExtensionV1` package. It
owns its domain state and consumes only generic 3mm application, connector and
`identifier.scan.v1` contracts.

## Current release: 0.7.6 — single payment confirmation

See [release notes](RELEASE_NOTES_0.7.6.md) for the payment confirmation
correction. The database revision remains 0020. Upgrade without deleting existing
extension data.

Prepare a folder for manual archiving (no outer ZIP):

```powershell
python modules/child-center/build_child_center_package.py --output-dir .runtime/child-center-0.7.6
```

The sections below describe historical releases, not the current checkout model.

## Historical release: 0.6.1 — operator workflow and row-timer correction

`/child-center/operator` now has Clients and bracelets / Stays and Barsy sections.
It reuses ActiveVisits, with Finish and send to Barsy and a live delivery list
showing child, rounded minutes, quantity, account number and state. Operators can
reprepare only definitely unsent/retryable bills after configuration is corrected;
ambiguous or confirmed writes cannot be sent again. Configuration and exceptional
account reconciliation remain administrator-only. No Core or Agent changes.

Correction to the 0.6.0 findings below: the account's `time_calculation = 0` DOES
NOT prove the order row has no active timer. Demo account #30, article 26, amount
0.017 had `active_time_orders = 1`. The visible Stop reporting button changed the
row to `active_time_orders = 0` and set served_date while the account remained open
and its quantity remained 0.017. The test account is left open/unpaid; only its
timer was stopped. No fiscal operation was performed. The public Orders API
catalog lists getlist, not a supported timer-stop mutation; no private web endpoint
or browser automation is embedded in this extension.

For fixed quantities, configure a separate non-timed sale article in Barsy. One
sale unit must represent one hour of play, priced accordingly by Barsy, with 3–9
quantity decimal places. Its quantity unit must have no time interval (null/0),
NOT the built-in timed Hour unit (60). Select it in Administration after confirming
the one-unit/one-hour mapping. The extension does not change Barsy configuration.
Previously selected timed articles fail preflight without creating a new account.
Post-delivery verification now requires zero active_time_orders on the matching row.

Migration 0013 marks 0.6.0 remote-confirmed bills for review without changing their
identity, quantity or account number and without resending them. Verification can
confirm them only after the row timer is demonstrably inactive. This check runs
once at upgrade, not every restart. Back up before upgrading.

Build: `python modules/child-center/build_child_center_package.py --output .runtime/child-center-0.6.1.zip`.

## Historical release: 0.6.0 — operator-finalized stays (timer claims corrected above)

Only the extension changes. No Core, Agent, deployment, commit or push changes.
New stays measure play locally, pause on exit and resume on re-entry. Only an
operator or administrator finishes a stay. Paused stays remain in Active visits.
The extension sums intervals using integer microseconds, then rounds the total
up to a minute exactly once. 12m20s + 17m50s = 30m10s = 31 billable minutes.
Pauses, including the delay before an operator finishes, are excluded. Finishing
while inside includes the final interval. Zero elapsed time creates no remote bill.

In Administration / Barsy, expand Articles — billing time and allowed consumption,
search for the hourly play article and select **Use for time**. Selection checks
an ordinary sale article, an hour unit (`time_interval = 60`) and quantity precision
between 3 and 9. No IDs are preselected. Prices are never copied or overridden.
The existing live/test switch is preserved. Live completion requires an article;
test completion never becomes a real charge after switching to live mode.

Operator completion atomically closes the local stay and stores a durable bill
with the selected article and quantity snapshot. The singleton job creates one
normal account for the verified parent, child name in its title, and a single
`article_id` / `amount` row. No timed table is allocated, no payment or fiscal
closure is performed. Minutes / 60 are rounded to the Barsy unit's decimal
precision using HALF_UP: 31 minutes becomes 0.517 hours at 3 places. Exact measured
time and rounded minutes are retained independently. This is a quantity precision
conversion, not a second upward time rounding.

The job verifies the returned account, parent, non-timed mode, article and quantity.
Uncertain writes are never resent automatically. Find the account by its displayed
`3mm UUID` marker and verify its number in Stay billing. Preflight failures can
retry without making a remote write. Pending bills block local client deletion.
Do not change the connector destination while accounts or bills are outstanding.

Forward-only SQLite migration `0012` adds stay intervals, settings and bill records;
it does not alter historical visits or re-bill existing accounts. Existing active
visits are marked **Legacy** and retain the previous table workflow: finish them
and settle their existing Barsy account before using a new stay. Old Start/Stop
records remain in the legacy administration area. Disable preserves this data;
backup/restore includes it as extension-owned SQLite. Rollback requires the
platform's matching pre-upgrade data snapshot, not running old code against new stays.

Demo verification created synthetic account #29 with article 26, amount 0.517,
`time_calculation = 0` and the default non-timed place. It remains unpaid/open;
no fiscal closure was requested. Credentials and demo records are not packaged.
References: [Accounts_create](https://docs.lukanet.com/barsy.api/methods/accounts/create.html),
[Amounttypes_getlist](https://docs.lukanet.com/barsy.api/methods/amounttypes/getlist.html).

## Earlier capabilities (0.5.0)

Version `0.5.0` implemented CC-2, CC-3, the safe CC-4A table-pool boundary and
the CC-4B read-only Barsy discovery boundary on
top of the accepted CC-1 skeleton. It contains:

- strict kiosk, operator, administrator and internal operation contracts;
- six server-authorized compiled route declarations;
- extension-owned SQLite revisions `0001` through forward-only `0011`;
- kiosk registration with a hashed status receipt and no enumeration;
- operator review, permitted corrections and approval;
- operator-side atomic client and bracelet registration;
- separate phone and email fields plus extension-local BG/EN switching;
- a tablet fullscreen kiosk mode that renders only the registration surface;
- a public tablet bootstrap route with one-time administrator enrollment;
- administrator listing and access revocation for paired registration tablets;
- automatic return to pairing mode when a tablet credential is revoked;
- administrator client search, approved-client editing and safe personal-data deletion;
- compact administrator navigation across Clients, Devices, Barsy and System;
- administrator reader-mode configuration and safe recent-scan diagnostics;
- operator visit history with name/date filters and measured-time details;
- App-aligned light/dark theme variables across every Child Center screen;
- extension-owned renewal of short-lived kiosk access tokens;
- a Raspberry-browser-compatible request identity fallback;
- opaque identifier assignment, replacement, retirement and redacted audit history;
- extension-owned runtime API discovery through `runtime-config.json`;
- pending, approved and combined operator registration filters;
- automatic toggle, operator-selected or dedicated reader-purpose configuration;
- idempotent `identifier.scan.v1` entry/exit transitions with late-event handling;
- append-only visit events, one-active-visit enforcement and restart-safe elapsed time;
- responsive active-visits UI with explicit stale/offline state;
- administrator-managed mappings to preconfigured Barsy place IDs;
- bounded read-only discovery through `Places_getlist` and the platform connector;
- administrator configuration of any HTTP(S) Barsy host through the platform
  connector and protected Basic credential store;
- local integration readiness counts without raw connector payloads;
- atomic table-pool allocation, same-visit binding and release invariants;
- durable local mock start/stop identities and opt-in live account opening;
- one supervised service wheel with a health operation;
- identifier subscription, retention job and a destination-restricted Barsy
  connector boundary;
- deterministic package tooling and focused tests.

Child Center does not calculate prices or own tariff rules. It registers clients,
maintains opaque identifier assignments and records measured entry/exit time.
Barsy owns prices, bills and fiscal operations. Live mode opens accounts, but
exit remains local: the reviewed API catalog does not document a timer-only
stop, while `Accounts_close` performs commercial/fiscal closure. Business decisions
are recorded in `docs/CHILD_CENTER_CC0_DECISIONS.md` and
`docs/CHILD_CENTER_CC4A_DECISIONS.md`.

## Build

From the repository root:

```powershell
python modules/child-center/build_child_center_package.py `
  --output .runtime/child-center-0.6.0.zip
```

The ZIP does not contain a reader device ID. The target device is selected from
the devices available to 3mm when the extension is activated, which keeps the
same reviewed package portable between installations.

Build output is generated and must not be committed.

## Discovery correction (since 0.4.10)

Discovery excludes Barsy's service-only places (`place_type = 1`), which are
returned once per salon but omitted from Barsy's own place list. It does not
filter on `is_public` or on the place number: those fields do not identify a
service place reliably. Labels use `name` when supplied, otherwise the place
type and `place_num`, with the API identity kept separately.

The demo check found six real places and two service places.

## 0.4.12 connector identity correction

The POST request now uses the platform-required `connector_<32 hex>` identity,
derived deterministically from the existing command UUID. The Barsy UUID and
account alias remain unchanged. Regression tests exercise the real connector
broker, including rejection of the former identifier before network I/O.

One-time migration `0010` requeues only the legacy 0.4.11 start commands with
the known invalid-ID ambiguity marker, a valid legacy command ID, a saved place
and no remote account ID. Under the platform contract those requests could not
reach the network. Existing confirmed accounts and other review states remain
untouched. Active visits are delivered by the existing job after activation;
do not scan again to retry. Ended visits never open an account retroactively:
verify with a blank account ID to release the definitely unsent binding.
Future ambiguous requests are never requeued by this migration on restart.

## Live account opening (since 0.4.11)

Install and activate, configure the connector, and add intended places to the
pool in Administration / Barsy. With no allocated places, enable live opening.
This checks the API user's personal POS. Default mode remains mock.

A registered bracelet entry queues account creation. The singleton job checks
the remote place and open accounts, then sends `Accounts_create` with a durable
UUID, place ID, verified parent client ID, child name in the alias, and empty
rows. The job runs every five seconds. Parent names and supplied contacts are
transmitted to Barsy following approval in live mode. Bracelet identifiers are
never transmitted.

The sending state is persisted before POST. An uncertain result needs manual
verification, never automatic POST replay: the demo rejects duplicate UUIDs.
Find the account by its `3mm <UUID>` alias and enter its ID in the verification
form. Only matching accounts and places are accepted. After local exit, complete
the account in Barsy; background checks automatically release the place after
verifying remote closure, account identity and local exit. Manual verification
remains available for uncertain opening results. A blank ID cancels
only a definitely unsent command after local exit.

Reserve these places for the extension: occupancy preflight is not an atomic
reservation against other clients. Do not change the connector destination while
accounts are outstanding. No automatic timer stop, timed-article insertion,
payment or fiscal closing is implemented.

The local scan-to-job demo probe created an account; event replay sent no second
POST. An increasing elapsed account period does not prove chargeable timed
article configuration. Raspberry installation remains a separate user step.

## 0.5.0 parent profiles and consumption permissions

The parent is the Barsy client; each new account title contains the child name
after the stable `3mm <UUID>` marker. Registration approval and direct operator
registration queue parent creation. Delivery occurs only in live mode. Existing
approved parents can be queued in Administration / Barsy / Parents in Barsy,
or lazily when their next live visit starts. Upgrade does not bulk-export all
historical registrations. Already-open accounts retain their original title.

`Clients_createsmart` may reuse an existing client according to Barsy's uniqueness
setting. Before linking, the extension verifies both name and supplied contacts.
Same-name/different-contact conflicts require administrator review. An uncertain
POST is not resent: read-only recovery uses the opaque client code. Administrators
may verify the correct client ID. Local profile edits do not silently overwrite
an existing Barsy client. Local erasure does not erase Barsy's independent records.

Administration / Barsy / Articles for the registration form searches active sale
articles in pages of 50 and permits up to 128 enabled choices. Only article IDs,
names, enabled flags and refresh timestamps are cached in extension SQLite. No
prices, quantities or orders are imported. Kiosks read only this administrator-
approved list, not the full catalogue or parent directory. Empty configuration
means no choices and no default permission. Reload open forms after changing the
list. Unknown/newly disabled choices are rejected on new registrations; existing
legacy choices remain visible for explicit review, never guessed or remapped.

Each job tick performs one bounded workflow, fairly rotating between parent sync,
account opening and one remote completion check. Checks rotate by last-check time.
A still-open remote account never releases its place.
Stopping time and commercial/fiscal completion are still actions in Barsy.

Demo verification created synthetic client #4 and verified client lookup by our
marker. The article search contract was checked read-only. Local browser tests
cover light/dark themes, narrow layouts and the article toggle with synthetic
API responses; they do not claim Raspberry deployment or full live checkout.

## Focused verification

```powershell
python -m pytest -q modules/child-center/tests
```
