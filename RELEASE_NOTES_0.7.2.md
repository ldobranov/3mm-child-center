# Child Center 0.7.2 — recover incomplete and ambiguous accounts

## Live diagnosis addressed

The installed 0.7.1 correctly observed Barsy account 35 as closed and account 37
as open, but both local table bindings remained allocated because their historic
playing-time writes were ambiguous. Account 35 is closed and empty. Account 37
contains its confirmed consumption but no playing-time row. Barsy article 28
(`Зала Мин.`) currently reports `current_price: n/a`, so Barsy cannot sell that
time article until its sale price is configured.

## Recovery workflow

- An operator can use **Check rows in Barsy** for an ambiguous time or
  consumption request. This performs an identity-checked GET and no POST.
- If the account is open and the requested article is proven absent relative to
  all locally confirmed quantities, the command becomes definitely unsent. After
  correcting the article/price in Barsy, the operator can explicitly retry it.
- Before the retry POST, an explicit Barsy `current_price: n/a` is rejected
  locally as `barsy_article_price_missing`; no write is sent until the sale price
  is configured.
- If the exact expected row is already present, the command and time bill are
  confirmed locally without resending anything.
- Partial, conflicting or multiple unresolved quantities remain in review.
- A closed account with missing charges cannot be retried. An administrator with
  configuration rights can explicitly **Release incomplete closed account**.
  This releases only the local table binding. The command and bill remain
  ambiguous, the missing charges are not represented as paid, and an audit event
  records the accepted incomplete closure.
- Open accounts cannot use the administrative release action.

The existing strict paid-account verification is unchanged: normal release still
requires paid fiscal closure plus exact playing-time and consumption quantities.

## Packaging

This is extension version 0.7.2 and keeps forward-only schema revision 0020; no
database migration is needed from 0.7.1. Upgrade in place without deleting the
extension data. No Core/Agent changes, live writes, deployment, commit or push
are part of package preparation.

Verification on 2026-09-22: 345 full extension tests passed. After the final
sale-price preflight, 27 focused recovery, billing-unit and package tests passed
again. All five isolated UI suites passed in EN/BG, light/dark and responsive
layouts. The 25 staged files exactly match the deterministic builder; installer
compilation and aarch64 validation passed. Wheel SHA256:
`a557fc98317899bfaceecd8ab2dc49f645a3961335d78476e10b125e27310e70`.
