# Child Center 0.7.0 — native Barsy time units, fixed quantities

## Correction to 0.6.10

A temporal amount unit does not, by itself, mean that an order timer is
running. Barsy also requires automatic timing on the place type. The previous
blanket rejection of Minute/Hour units was incorrect.

References:
- https://docs.lukanet.com/barsy.help/110-admin/100-catalog/articles/timearticles.html
- https://docs.lukanet.com/barsy.api/methods/accounts/get.html

## Configuration and operation

1. In Barsy, use a place type with automatic timing disabled for local measurement.
2. In Child Center administration select Minutes, then select the desired minute
   article under billing articles. Article and unit are saved together. For an
   Hour article, select Hours instead. Ordinary units retain explicit mapping
   for compatibility; the administrator must verify their price basis.
3. Open stays and unresolved accounts still lock configuration changes.
4. First entry opens the account and reserves the place. Local measurement
   pauses/resumes with the established access workflow. Operator finish sums
   intervals and rounds up once to a minute. Example: 303 seconds => 6 minutes
   => quantity 6 with Minutes, or 0.100 with Hours. Barsy owns prices and taxes.
5. Consumption and payment remain in Operator. No undocumented timer-stop API
   is used; Barsy timer mode remains unavailable.

Before admission and commercial writes, verify the account's documented
`time_calculation` is zero and every existing row's `active_time_orders` is zero.
Missing/malformed values fail closed. After a write, both are checked again.
An uncertain or unexpectedly timed write remains ambiguous and is never resent
automatically. An empty account on an unsafe place is retained for review,
not silently cancelled or duplicated.

The delivery worker validates the native unit against the bill's saved unit,
not a newly selected global preference. Changed remote units cannot silently
reinterpret a queued amount. Historical pre-account-workflow bills retain their
conservative fixed-unit validation and are not automatically converted.

Configuration failures now return bounded, translated reasons for mismatched
units, unsupported units, insufficient precision, unavailable articles and locked
settings. No raw connector errors or credentials are displayed.

## Packaging and compatibility

- Extension-owned changes only; no Core, Agent or Application Reference edits.
- Storage remains schema 0019. Upgrade from 0.6.10 needs no new migration;
  earlier installations use the existing forward migrations. Existing bill
  snapshots and idempotency records are preserved.
- No deployment, remote database edits, commit, push or outer ZIP.
- Staged folder: `.runtime/child-center-0.7.0`. Zip its contents so that
  `manifest.json` is at the archive root. Do not uninstall or erase the old data.
- Synthetic regression tests cover units, pause/resume, admission, consumption,
  payment, lost replies, restart, migration, contracts and deterministic packaging.
  Installer compilation and isolated EN/BG light/dark/mobile UI checks are included.
- Real account/fiscal writes are not part of this release verification; a controlled
  acceptance stay on the configured non-timed Barsy place is still required after installation.

Verification on 2026-09-16: full suite 302 passed (125 existing dependency
warnings); final native-unit suite 11 passed, including 2 cases added after full
suite collection: 304 distinct passing tests. UI regression passed, including
changing the article and unit, translated rejection, saved-value preservation,
locked settings and responsive layout. Staged 25 files match the builder exactly;
aarch64 validation and repeat-build equality passed. Wheel SHA256:
`8a552676317759dc2e270edacc3c39d4961922fe0d4b98a116f0108c18f41b40`.
