# Child Center application extension

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
