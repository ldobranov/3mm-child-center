# 0.7.5 — remove unreliable row-timer gate

Removed `active_time_orders` from commercial and historical bill verification.
It no longer blocks confirmation, reconciliation or checkout. Account identity,
place timing (`time_calculation = 0`), expected quantities, payment verification
and protection against replaying uncertain writes remain in place.

Existing `barsy_order_timer_active` errors are retained for audit, but the UI
explains that they came from an obsolete check instead of asserting an active
timer. Upgrade does not resend or automatically confirm these commands.

After upgrading without deleting data, use **Check rows in Barsy** on the blocked
time command. If the actual quantity matches, the existing command is confirmed
without another article POST. Then proceed to payment. Do not add replacement
rows or retry a command whose delivery is uncertain.

Schema remains 0020. No Core/Agent edits, deployment, live payment or outer ZIP.
