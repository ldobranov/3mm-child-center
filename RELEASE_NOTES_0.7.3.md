# Child Center 0.7.3 — administrator release routing

Version 0.7.2 exposed an administrator-only action in the Operator screen but
sent it to the operator API route. The request was rejected before reaching the
extension service. Version 0.7.3 sends **Release incomplete closed account** to
the administrator route. The existing administrator permission check, explicit
confirmation, Barsy identity/status check and audit record remain in force.

The installed data was inspected read-only on 2026-09-22. Barsy account 35 is
closed and empty; its local 93-minute command remains ambiguous. An administrator
may release this incomplete account without marking the time as charged or paid.
Barsy account 37 is still open with one consumption row and no playing-time row.
Its time command was reconciled as absent. Article 28 (`Зала Мин.`) still reports
`current_price: n/a`, so the time cannot be sold until a price is configured in
Barsy. After correcting the price, the operator can retry the time command, then
take payment. If the account is closed separately in Barsy, the administrator
can release it as incomplete and keep the missing charge visible for audit.

Schema revision remains 0020. Upgrade in place and keep the extension data.
Zip the contents of `.runtime/child-center-0.7.3` with `manifest.json` at the
archive root.

Verification: 23 focused backend, reconciliation and package tests passed.
The isolated Operator browser test exercised the administrator API address and
confirmed that a released account leaves the active list. The staged 25 files
match the deterministic builder exactly; wheel SHA256:
`1695e8da6a90f890da7d3029aaf55477ca1c12d2eda7a4d41db6260758352ad3`.
