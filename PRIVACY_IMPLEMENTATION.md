# Prepared runtime privacy — 2026-09-14

Implemented in extension-owned SQLite, draft schema 0016 and
`access_runtime:create_service`. The released 0.6.7 manifest still selects the old
entrypoint/schema 0015. Do not rebuild this intermediate source as 0.6.7.
No real customer data, deployed installation or Barsy account was changed.

## Export

- Existing strict administrator / privacy_manage contract; real Core authorization
  is covered by tests with a stubbed service transport. Internal implementation
  also checks audience and authenticated administrator identity.
- One guardian or child, never another person's full profile. Relationships use
  identifiers, not other family members' names/contact fields. Guardian export
  contains its profile, relationships and external client linkage. Child export
  contains its profile, relationships, bracelet assignments, visits, intervals,
  events, billing/consumption and access journal. Device topology and platform
  authorization generations are excluded. This is the defined structured scope,
  not a database dump, remote-system export or financial receipt export.
- At most 5000 rows per section; final transport envelope must fit the inline
  contract limit. Oversize fails atomically without a partial document. Larger
  exports require a separate reviewed workflow; no silent truncation.
- A separate artifact table contains the document for a provisional 15 minutes.
  Permanent command results contain only export ID/status. Replay before expiry
  returns the same document. Expiry or erasure revokes it; replay never recreates
  an old artifact. A fresh request is required for a new export.

## Selected-field redaction / erasure where permitted

- Guardian: name/contact fields. Child: name, notes, preferences and raw bracelet
  values. Consent evidence, stable subject/relationship identifiers, measured-time
  history, remote mappings and financial/idempotency records remain. Therefore
  these are redacted/pseudonymized records, not a claim of irreversible anonymity.
- Both scope variants preserve necessary history and differ in the recorded
  subject status. Neither performs remote erasure or fiscal actions.
- Active visits, allocated places/accounts, pending/ambiguous financial commands,
  unresolved access intents, and ambiguous guardian synchronization block the
  relevant operation. Family deletion is atomic; partial redaction rolls back.
- Existing exports are revoked. Cached responses that structurally reference the
  selected subject/registration are replaced and marked unusable. Their keys and
  request digests remain to prevent duplicate mutations. Later legacy updates of
  a redacted family are refused; a new registration/consent flow is required.
- Audit records contain scope, identifiers and counts, not free-text erasure
  reasons, original contacts or export bodies. The request digest preserves
  idempotency checks without storing the reason itself.

## Automatic retention

- Provisional CC-0: guardian personal fields after 30 days from the latest closed
  related visit, provided all safety checks pass. No closed visit means no inferred
  expiry date. Active visits or unresolved accounts prevent redaction.
- Provisional CC-0: raw retired identifier values after 7 days. Technical assignment
  identities remain. This does not detach an active bracelet.
  An explicit `identifier_erased` flag tracks completion, not the bracelet's
  prefix. Draft migration 0016 recognizes exact legacy assignment tombstones.
  Scrubbing revokes that child's existing export artifacts in the same transaction;
  replay cannot recover the old raw value. Guardian/other-child exports are kept.
- Up to 50 guardian candidates, 50 retired identifiers and 50 expired artifacts
  per invocation. A rotating guardian cursor prevents blocked subjects from
  permanently starving subsequent pages. Cached reply matching may still scan
  existing command results; very large datasets require further indexing/work jobs.
- Job receipt is idempotent. Output `anonymized` counts guardian subjects,
  `identifiers_erased` counts retired identifiers, `deleted` counts expired export
  artifacts. Visit history is NOT deleted by this implementation.

## Remaining gates before production acceptance

1. Reviewed 24-month history aggregation/purge preserving financial and physical
   replay protection; no indiscriminate cascade deletes.
2. Backup/restore privacy procedure: restoring an old backup can restore personal
   fields erased after it was taken. Local SQLite tombstones alone cannot prevent
   this. Recovery must include the subsequent erasure obligations before use.
3. Independent Barsy data, Core connector storage/audit, downloaded exports and
   existing backups have separate handling; this extension cannot silently erase
   them. SQLite row updates/deletes do not promise forensic removal from disk/WAL.
4. UI for clear scope, short-lived download and blocked-operation explanations;
   real installation/restore acceptance and the remaining access-point contracts.

Tests use synthetic profiles, temporary SQLite and mocked POS. They verify existing
authorization boundaries, replay/revocation, inline limits, subject isolation,
financial/physical guards, legacy family deletion, retention and unchanged time.
