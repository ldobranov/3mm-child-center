# Operator / Barsy lifecycle correction

Status (2026-09-09): the common account/consumption/payment workflow is implemented
in 0.6.3 and covered by synthetic integration and local browser tests.
Local quantity remains active; Barsy timer settings are a draft and cannot be
activated until the row-stop API is reviewed. Missing stop documentation does not
block the LOCAL mode. New stays open an account at entry; historical stays retain
their existing delivery workflow and are not backfilled or billed again.
No new deployment or fiscal test is authorized by this document.

## Accepted workflow

Both modes are retained, not mutually replacing designs. In local_quantity mode,
the extension accumulates inside intervals and sends a fixed quantity once the
operator finishes, rounded up ONCE to a minute. This uses a non-timed hour-priced
article. In barsy_timer mode, each inside interval uses a separate timed Barsy
row; stop capability and rounding must be verified before activation. Each mode
has a separate administrator-selected article. Profiles never silently convert
open stays or uncertain historical commands. The common target for BOTH modes is
one allocated account from entry until operator-confirmed payment/closure.

- First entry: choose an available configured Barsy place, create the parent's
  account and include the child's name on the visit/account. Local mode opens an
  empty account and starts local timing only after confirmed admission. The future
  Barsy timer mode will start a timed article instead.
  A new stay cannot be admitted without confirmed capacity/account allocation.
- Exit: pause the local interval; keep the account and place allocated. In the
  future Barsy timer mode, stop the current order row's timer instead.
- Re-entry: resume a new local interval on the SAME account. Future Barsy timer
  mode will add a NEW timed row, never resume or overwrite a stopped row.
- Operator sees the child's allowed consumption. An explicit article/quantity
  action adds consumption to the account; permission alone is not a sale.
- Finish game: operator stops the active interval and prevents further entry on
  this stay. In local mode send the total rounded duration as a fixed article
  quantity to the existing account. Account remains open for payment.
- Close account: operator selects a Barsy payment method, reviews the current
  Barsy total/currency, then explicitly confirms payment and fiscal closure.
  Release the place only after verified remote completion. No automatic repeat
  of a payment, row insertion or fiscal action after an uncertain response.
- Administrator configures the timed article, places, connector and permissions.
  Barsy owns prices. Preserve the requested upward-minute rounding only through
  a verified Barsy timer configuration/contract, not a second local charge.

## Evidence checked on 2026-09-08

- `Accounts_create`: creates an open account, accepts place/client and initial rows.
  https://docs.lukanet.com/barsy.api/methods/accounts/create.html
- `Accounts_place`: explicitly supports an existing account_id and additional
  orders, with flag_close_account=0. This is the documented candidate for both
  consumption and new timed intervals. Its UUID guarantee concerns account
  creation, NOT proven idempotency for adding another row to an existing account.
  https://docs.lukanet.com/barsy.api/methods/accounts/place.html
- `Paymentmethods_getlist`: available payment methods include currency/provider
  requirements; do not treat every method as a simple cash/card boolean.
  https://docs.lukanet.com/barsy.api/methods/paymentmethods/getlist.html
- `Accounts_close`: includes payments and fiscal printing; never use for pause.
  The close page describes payments as an array without a complete worked example.
  https://docs.lukanet.com/barsy.api/methods/accounts/close.html
- Public Orders documentation and the linked official PHP library currently list
  only Orders_getlist. Neither yielded a documented single-row timer-stop method.
  This does NOT establish that the Barsy server lacks that capability.
  https://docs.lukanet.com/barsy.api/methods/orders/index.html
  https://docs.lukanet.com/barsy.api/usage/barsy_api_client.html
- Previously verified UI: stopping the hourglass changes the order's
  active_time_orders to 0 while the account remains open. Account-level
  time_calculation=0 does NOT establish that all order timers are stopped.

## Exact missing contract to request from Barsy

1. Supported API method and input/output example for stopping one timed order_id
   without closing/paying its account, including repeated calls and failures.
2. How Accounts_place returns/identifies the newly created timed row, whether same
   article rows remain separate, and whether a durable external row identifier is
   supported for recovery after a lost response.
3. Timer start semantics, upward-minute rounding configuration, and authoritative
   read-back fields for active/stopped time and final quantity.
4. Payment/fiscal completion read-back: distinguishing paid/closed from a failed
   or still-pending fiscal print; safe recovery after a lost close response.

Do not guess endpoint names, use account closure as pause, or implement browser
click automation as the production connector. Never silently switch timing modes.

## Remaining work for Barsy timer mode after verification

1. Extension-owned forward migration: per-interval remote row identity and durable
   command outcomes; preserve historical 0.6.x accounts and prevent rebilling.
2. Restore allocation at first entry; retain allocation across pauses; serialize
   start/stop/add/finish/payment commands for each account. Reconcile unknown
   outcomes through reads or operator review, never blind retry.
3. Add strict operator contracts for consumption, finish, payment preview/confirm
   and status. Separate financial permission; kiosk/internal cannot invoke them.
4. Operator UI: consumption, intervals, game completion, payment confirmation and
   actionable pending/review states. Keep configuration in Administration.
5. Test capacity, pause/re-entry, duplicate scans, unknown replies, crash recovery,
   concurrent operators, disabled/restored extension and legacy data; then frontend
   build and light/dark/mobile review. Fiscal end-to-end test requires confirmation.

## Folder delivery (no outer ZIP)

The builder now accepts `--output-dir <new-folder>` and creates the reviewed wheel,
matching SHA-256 contract, manifests and frontend sources. It refuses all existing
targets. Zip the CONTENTS so manifest.json is at the archive root, not a containing
folder. Never zip modules/child-center directly: that is a source/test directory,
not a staged installer payload. Prepare the release folder only once the new
workflow is implemented and tested. See RELEASE_NOTES_0.6.3.md for the implemented
local-account workflow, supported payment methods and verification limitations.
