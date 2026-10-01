# Child Center 0.6.3

Extension-only release. No Core, Agent or Application Reference modifications.
No deployment, installation, commit, push or outer ZIP is part of this delivery.

## Operator workflow

1. First entry checks the configured place pool against open Barsy accounts and
   reserves one locally. It opens the parent's account with the child's name in
   the account title. The child is pending admission until opening is confirmed;
   local time does not accumulate while waiting. Do not admit a pending child.
2. Exit pauses time; re-entry resumes the same stay and account. The table stays
   allocated. Total inside time is rounded UP ONCE to a minute when the operator
   finishes the game, then converted to the configured article's hour quantity.
3. Operator -> Stays and Barsy -> Accounts and consumption shows the child's
   allowed articles. Operators explicitly select child/parent, article and quantity.
   Articles and all prices come from Barsy; permissions do not create sales.
4. Finish sends time to the SAME account. Payment preview is available only after
   finishing and confirming delivery. Operator selects a payment method and
   explicitly confirms received payment and fiscal closure. A confirmed closed,
   paid fiscal account releases the table. No second account is created at finish.

## Configuration and supported scope

- Enable live delivery, configure the connector, place pool and local hourly
  article in Administration. The hour article must NOT start an automatic timer;
  its quantity unit needs at least three decimal places. Prices stay in Barsy.
- Both timing profiles remain configurable. Barsy timer activation is deliberately
  unavailable until a reviewed row-stop API exists. Local quantity is operational.
- Existing operator roles need the new extension permission `payments_manage` for
  payment preview, confirmation and manual closure verification. Other account
  operations use `visits_manage`. Kiosk/internal cannot invoke operator actions.
- This release supports fiscal cash and manually confirmed card methods without
  a payment provider, extra required details or currency restrictions. It supports
  positive account balances in base currency (rate 1), with at most two decimals.
  Card-terminal authorization is NOT initiated by this extension. Mixed payments,
  credit, vouchers, refunds, zero-value closures and other currencies stay in Barsy.
- Use a dedicated configured table pool. The extension serializes its own writes;
  the API does not provide an atomic lock against another external Barsy operator
  changing the same account between checking and sending.

## Recovery and compatibility

- Unknown article/payment POST results are persisted BEFORE sending and are never
  automatically replayed, including after a service restart. The table remains
  allocated and the operator sees a review warning.
- Only definitely unsent article requests offer retry. A rejected payment preflight
  requires a fresh amount preview. A changed or expired preview does not send money.
- A browser transport failure preserves the local action's idempotency identity
  in session storage. Use Recover the previous action result, not a new action.
- For an uncertain result, inspect and resolve the full bill in Barsy, including
  quantities and the fiscal receipt. Operator can then explicitly verify an already
  paid fiscal account and release the table without sending another payment.
- An unsent pending admission can be cancelled. An unknown account opening cannot
  be cancelled as if nothing happened; use existing Barsy opening reconciliation.
- Migration 0015 only adds extension-owned tables. Historical visits/bills are not
  converted or rebilled. Existing backup/restore and lifecycle contracts remain.
  Restore/rollback cannot undo an external sale or fiscal receipt: reconcile open
  accounts in Barsy before resuming delivery from a restored older snapshot.

## Validation and delivery

Synthetic tests cover account capacity, pause/re-entry, total rounding, consumption
permission, payment confirmation, lost responses, process interruption, explicit
reconciliation and forward migration. The local browser harness covers Operator
consumption and payment, light/dark themes and mobile layout. Package tests invoke
the real installer compiler against temporary local artifacts, not a deployment.

No real payment or fiscal receipt was triggered. A supervised end-to-end test with
the configured Barsy instance and fiscal device is still required before real use.

Prepared folder: `.runtime/child-center-0.6.3` at the repository root. ZIP its
CONTENTS, with `manifest.json` at the archive root. Do not ZIP the source module
directory. The included service wheel is required and is not an outer installer ZIP.
