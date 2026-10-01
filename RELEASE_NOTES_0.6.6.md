# Child Center 0.6.6 — first permission-aware staff screens

Uses the Core `/api/v1/application-extensions/{module_id}/access` contract
available in local Core commit b3154f9. Only this extension was changed.
No Core/Agent patch, deployment, installation, ZIP, commit or push.

## Included

- Operator and standalone Visits load only after a valid server access snapshot.
  The wrapper checks the permitted route and supplies permitted operations to
  child components; it never infers privileges from a role name or JWT payload.
- Operator now requires registrations_manage, not the former conjunction of
  registrations, children and visits. This preserves existing fully granted
  users and lets reception open the desk without giving it visit/payment powers.
  Anonymous users and users without that grant still cannot open this route.
- Clients, assignment buttons and visit/account sections follow allowed operations.
  Unavailable sections do not mount or fetch hidden data. Visits-only staff use
  `/child-center/visits`; combined staff can use the Operator sections.
- Payment preview, payment submission and paid-account verification are absent
  without their permissions. Server authorization remains authoritative on every
  request; frontend checks are only presentation and accidental-action guards.
- The snapshot is refreshed on focus, storage/visibility changes and every
  15 seconds. A 401/403 from an operator operation invalidates it immediately.
  Changed identity, version or permissions remount the workspace and clear its
  loaded data/forms. A failed snapshot closes the workspace with a retry message.
  In-flight stale snapshot replies are ignored; requests have an 8-second abort.
- New uncertain commercial browser attempts retain their initiating platform user
  ID. Another user cannot replay them. Legacy saved attempts without an owner,
  or attempts for which permission was revoked, remain blocked for responsible
  staff review rather than being discarded or silently retried.

## Recommended current grants (not new roles or automatic grants)

| Staff use | Existing permissions | Entry |
| --- | --- | --- |
| Reception and bracelets | registrations_manage + children_manage | /child-center/operator |
| Play area and consumption, no payments | visits_manage | /child-center/visits |
| Combined daily operator, no payments | registrations_manage + children_manage + visits_manage | /child-center/operator |
| Combined operator with checkout | Above + payments_manage | /child-center/operator |

Existing permission groups remain broad: visits_manage includes account reads,
consumption and finishing a stay. A cashier-only account-reader permission and
delegated center administrator are not part of this increment. Administration
retains the Core's global-admin boundary. No new users, roles or grants are created.
Standalone History and Administration have not been converted to the new
snapshot wrapper in this increment; their existing Core authorization remains.

## Verification and upgrade

Tests use a temporary Core database and simulated connector responses. They verify
real access snapshot/grant/revoke decisions, installer compilation, no hidden
reception queries, no-payment buttons, revocation data clearing, snapshot outage,
and the previous registration/consumption/finish/payment browser flow.
No live Barsy payment or Raspberry modification was used for validation.

SQLite remains 0015; no database reset or migration is needed. Back up and upgrade
through the extension installer. The new Core access endpoint is required; older
Core versions intentionally show an unavailable-access screen, not an allow-all
fallback. Package folder, if prepared: `.runtime/child-center-0.6.6`.
