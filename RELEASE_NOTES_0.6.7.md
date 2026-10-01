# Child Center 0.6.7 — separate cashier desk

## Daily use and access

- New route `/child-center/cashier`, labelled Child Center checkout / Каса на
  детския център. Add it to navigation through the application's menu settings;
  the extension does not force a header/menu item.
- Give the platform staff user only `payments_manage` for a cashier-only setup.
  No new users, passwords, roles or grants are created automatically. Existing
  holders of that permission gain the checkout route and its two read queries.
- The cashier sees the account queue, child/table/account identity and delivery
  status. Default filter is Awaiting checkout; search applies to the current page.
  It does not expose parent contacts, bracelet data or consumption preferences.
- Payment amount/methods, explicit confirmation, fiscal submission and manual
  verification reuse the existing Operator workflow. Playing must first be
  finished by an operator, and deliveries confirmed. No automatic timer stop,
  new Barsy API method, pricing or second payment pipeline is introduced.
- No registration, assignment, visit control, consumption, unsent-command retry,
  test-table release or admission cancellation is offered on the cashier screen,
  including when opened by an administrator. Those remain in Operator.
- An uncertain result is not automatically retried. The same-owner recovery
  retains the original request identity even when recovery is rejected.

## Compatibility

`list_checkout_accounts` and `get_checkout_account` are new strict read-only
queries protected by `payments_manage`. Existing Operator queries keep
`visits_manage`, and all existing command permissions remain unchanged.
No grant migration or privilege escalation to visit/configuration management.
The cashier's read projection deliberately returns no consumption choices.

Includes the post-0.6.6 History access wrapper and rejected-recovery correction.
History now clears data when revocation is detected and does not fetch without
access. Administration still has the platform's global-admin boundary;
delegated center management is not implemented.

SQLite remains 0015. Back up and upgrade without deleting data. Disable preserves
state; rollback uses the platform's matching snapshot. Requires the Core current-
user `/access` endpoint already used by 0.6.6. No Core/Agent changes.

Tests use temporary databases and simulated Barsy responses, including payment
completion. No live fiscal request or Raspberry deployment is performed.
Package directory: `.runtime/child-center-0.6.7`; archive its contents, not its
parent directory, with `manifest.json` at the archive root. No outer ZIP is made.
