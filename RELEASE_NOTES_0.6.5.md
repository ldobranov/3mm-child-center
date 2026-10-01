# Child Center 0.6.5 — everyday operator workflow

Extension-only update. No Core, Agent, application-reference, deployment or
installation changes. No outer ZIP, commit or push. SQLite remains at 0015;
no data reset or new migration is needed. Back up before upgrading, and retain
the platform's matching version/data snapshot for rollback.

## Operator workflow

- Approved clients is the initial tab. Search parent, child, phone or email;
  names support case-insensitive Cyrillic matching. More clients loads the
  next bounded page. Pending approvals remain separate.
- Select a parent, then Give bracelet for the intended child. The focused field
  accepts a typed code or keyboard scanner and Enter confirms assignment only.
  This is NOT an Agent/entrance-reader enrollment mode. Assignment itself does
  not open a visit or Barsy account; the entrance scan does that.
- Replace bracelet asks for confirmation, preserves the stay, and disables the
  old bracelet. An occupied bracelet is never stolen. The assignment snapshot
  rejects stale replacements. Returning to Clients reloads the selected profile.
- Entrance and pause/resume behavior is unchanged. First admission opens the
  existing Barsy-account workflow; pauses retain account and place allocation.
- In the play area combines play/pause, consumption and Finish playing. Quick
  +1 buttons offer only the child's permitted articles; a confirmation names
  the child, article, quantity and consumer. The form retains parent consumption.
  Pending or uncertain delivery blocks duplicate consumption requests.
- Finish playing automatically detaches the currently assigned bracelet in the
  same local transaction, including a replacement bracelet. It does NOT release
  the table or pay the account. Replaying the finish command cannot detach a
  subsequently assigned bracelet. Events older than the current assignment are
  recorded as late instead of admitting the new owner.
- Finishing a new-workflow account moves the operator to Awaiting payment and
  retains the selected account. Existing explicit payment-method selection,
  fiscal confirmation, unknown-outcome recovery and remote closure checks remain.
- Completion notice and Visit history distinguish actual measured duration from
  the stored, once-rounded billable minutes. Example: 16:10 -> 17 min -> 0.283
  hourly units at 3 decimal places. Decimal quantity precision is not a second
  upward rounding of playing time. No extension-owned price calculation.
- Frequent-client details return at most 100 bracelet assignments, always keeping
  the active one. Complete stored history is not deleted by this display bound.

## Deliberate limits

The Barsy `3mm UUID | child` account alias is unchanged: existing remote identity
verification and lost-response recovery still depend on it. The proposed
article/duration alias needs a separately verified safe identity/update path.
This release does not implement an undocumented Barsy timer-stop API. Local
measurement remains the supported active profile; the timer profile capability
gate and the payment limitations documented in 0.6.3 are preserved.

No new global queue counters, automatic family-account merging or physical
scanner enrollment is included. The tab and client-list changes are the bounded
first everyday-workflow increment, not a rewrite of commercial delivery.

## Verification and manual packaging

Synthetic regression coverage includes assignment without entry, replacement
conflicts, stale snapshots, pause preservation, detach before payment, late scans,
finish replay, microsecond rounding, role separation, search and frequent clients.
The full extension suite also checks migration compatibility, deterministic wheel/
package contents and actual installer compilation using temporary local data.
Browser checks cover client search, keyboard assignment/replacement, consumption,
finish-to-payment navigation and one explicit fiscal confirmation, in light/dark
themes and narrow layouts. All connector responses are synthetic; no live Barsy
account, payment or fiscal device was mutated for these checks.

Prepared folder: `.runtime/child-center-0.6.5` at the repository root.
Archive its CONTENTS, with `manifest.json` at the ZIP root. Upgrade using the
extension installer and activate the new version; do not delete existing data.
