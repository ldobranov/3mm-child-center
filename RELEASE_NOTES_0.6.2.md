# 0.6.2 — timing profiles (incremental release)

Implemented:
- Administration / Barsy shows Local measurement and Barsy timer profiles.
- Each profile has an independent article selection, verified read-only against
  Barsy article/unit metadata. Local quantity rejects automatic timers; the Barsy
  draft requires a timed unit. Selecting a profile for editing does not activate it.
- Local measurement remains active, including pause/resume, one upward-minute
  rounding at operator finish and fixed-quantity delivery without extension prices.
- Remote timing is explicitly unavailable pending a verified stop API. This is
  enforced server-side; saving a timed article does not enable network mutations.
- Active profile changes are locked while stays, allocated accounts or uncertain
  deliveries are outstanding. Inactive remote draft configuration remains editable.
- Forward migration 0014 preserves existing stays, selected local article and bills.
- No Core/Agent changes, deployment, fiscal testing, commit or push.

Not included yet (do not mistake this for the complete requested workflow):
- Account/table allocation at FIRST entry for the local-quantity mode, with final
  quantity appended to that same account. Existing local mode still opens its
  account at operator finish.
- Operator consumption ordering and payment/fiscal closure.
- Operational Barsy row start/stop mode (configuration draft only).

The missing stop API blocks only operational Barsy timers, not these remaining
local-mode/account/Operator tasks. See OPERATOR_BARSY_IMPLEMENTATION.md.

For manual packaging use the staged folder's CONTENTS; manifest.json must be at
the ZIP root. The source folder itself is not an installer package.
