# 0.7.4 — remove false missing-price preflight

Only Child Center changes; no Core/Agent changes or deployment.

- Do not treat catalogue `current_price: n/a` as a sale refusal. Time and
  consumption validate article identity and unit precision, then let Barsy
  determine the actual account price. No price is supplied or overridden.
- Preserve the diagnostic for an actual known missing-price POST refusal and
  the no-automatic-replay rule for uncertain writes.
- Operator disables checkout for failed article deliveries and explains how
  to resolve them. Backend also rejects checkout with failed consumption,
  even when playing time has already been confirmed.
- Explain that saved missing-price errors from 0.7.2/0.7.3 may have been local
  preflight failures, not Barsy refusals.

Upgrade without deleting data. Schema remains 0020. Existing failed commands
are not automatically requeued. In Operator, retry each unsent request once,
waiting for confirmation before the next. Do not create replacement consumption
rows. Unknown outcomes still require review, never blind replay.

This release does not assert successful live payment or fiscal closure.
