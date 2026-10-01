# 0.7.6 — single payment confirmation

Removed the payment checkbox from Operator and Cashier. The operator selects
a payment method and clicks Pay and close account. A single final dialog shows
the account, amount, currency and method and asks whether payment was received.
Cancelling the dialog sends nothing. The strict backend confirmed=true contract
and idempotency protections remain unchanged.

This UI release does NOT resolve the quarantined scheduler claim or the timeout
budget issue. See INCIDENT_2026_09_23_JOB_TIMEOUT.md for verified findings and the
existing recovery API. No Core changes, live recovery, payment or deployment.

Schema remains 0020. Upgrade without deleting data; archive the staged folder's
contents manually. No outer ZIP is generated.
