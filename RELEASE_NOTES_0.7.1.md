# Child Center 0.7.1 — reliable account status and closure review

## Corrections to 0.7.0

- The extension now checks allocated live Barsy accounts in the background and
  shows an externally closed account in Operator as **Closed in Barsy — review
  required**. This is a read-only check; it never closes, pays or changes the
  remote account.
- External closure no longer disappears behind stale local state. While the
  account is observed closed, Operator blocks new consumption, retries and a
  second payment attempt. The existing manual verification action remains
  available after the local stay is finished.
- Manual verification no longer treats remote `status=closed` as sufficient.
  It requires paid fiscal closure and exact remote quantities for the locally
  measured playing-time article and every queued consumption article. Missing
  or partial rows do not release the table and are not marked confirmed.
- A failing or malformed read produces a bounded `unknown` observation and does
  not preserve stale closed evidence. Checks rotate fairly and are throttled to
  one account every 15 seconds.
- HTTP 501 write results stay ambiguous and are never replayed automatically,
  except for the exact Barsy business refusal stating that the sole article has
  no sale price and cannot be sold. That refusal is definitely unsent and allows
  an explicit operator retry after the price is corrected; it is never retried
  by a job. The bounded reason is stored without the remote response text.
- Capacity scan failures distinguish missing enabled tables from a fully
  occupied table pool. One blocked admission no longer starves later stays.

## Storage and safety

Forward-only migration `0020` extends bounded scan diagnostics and adds the
extension-owned `account_observations` cache. Observation rows cascade with the
owning stay. Upgrade keeps visits, bills, account identities, commands and table
bindings. Rollback requires the platform's matching pre-upgrade snapshot.

Account observation never changes visits, bindings, bills or command states and
never sends a POST. A closed observation is not proof that time, consumption,
payment or fiscalization succeeded. The explicit verification operation is the
only recovery path and is intentionally strict.

## Installation and acceptance

The staged folder is `.runtime/child-center-0.7.1`. Zip its **contents**, keeping
`manifest.json` at the archive root. Upgrade the installed extension without
deleting its existing data.

After installation, use a controlled account and verify:

1. first entry opens one account and allocates one configured table;
2. operator finish adds the rounded playing time exactly once;
3. payment closes the account and releases the table only after confirmation;
4. if the account is closed manually in Barsy, Operator shows the review state
   after the background check and does not offer another payment;
5. manual verification refuses an empty or incomplete account.

No Raspberry deployment, live Barsy mutation, Core/Agent edit, commit, push or
outer ZIP is performed while preparing this release.

Verification on 2026-09-22: all 341 extension tests passed; after the final
definitely-unsent price-refusal classification, its 33 focused commerce,
reconciliation, observation and package tests passed again. Five isolated browser
suites passed, covering EN/BG, light/dark/mobile, external-closure polling and
action gating without remote mutations. The 25 staged files exactly match the
deterministic builder output; installer compilation and aarch64 package validation
passed. Wheel SHA256:
`1140b412dc1e1cd6c3d4e13157c97322274670ac8589a8dadc5b7efca36f9156`.
