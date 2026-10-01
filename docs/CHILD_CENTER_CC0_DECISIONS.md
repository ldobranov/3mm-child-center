# Child Center CC-0 business decisions

Status: updated through the `0.4.1` CC-4B package. Items marked **provisional** are
reversible test defaults and require operator acceptance before a production
package.

This document records extension-owned policy. It does not add child-center or
external-system concepts to Core or Agent.

## Selected workflow policies

1. **Scan meaning — selected.** The default reader mode is automatic toggle.
   A scan without an active visit means entry; the next scan of the same active
   bracelet means exit. Duplicate delivery of the same stable event ID cannot
   reverse the transition. Dedicated entry/exit readers remain configurable.
2. **Measured time — selected.** Event timestamps are persisted in UTC and
   displayed in `Europe/Sofia`. Child Center stores the entry, exit and elapsed
   seconds for operational continuity and audit. It owns no tariff, currency,
   price, rounding rule or checkout total.
3. **Barsy timing — selected.** A later integration step maps each timing
   workflow to a table that is already configured in Barsy. Entry starts time
   and exit stops time through the Barsy API. Child Center does not create or
   edit Barsy pricing rules.
4. **Commercial and fiscal authority — selected.** Barsy is the sole authority
   for time-based prices, consumption, bills, payment, fiscal calculation,
   receipt printing, reversal and fiscal closure.
5. **Retention — provisional.** Guardian contact data is anonymized 30 days
   after the last closed visit. A retired opaque identifier is erased after 7
   days. Closed visit records may retain non-personal timestamps and elapsed
   seconds for 24 months and are then deleted or aggregated. A valid erasure
   request may anonymize personal fields earlier while preserving a redacted
   audit record.

## Minimum personal data

The kiosk may collect only:

- guardian display name;
- separate optional phone and email fields, with at least one of them required;
- consent version and acceptance timestamp;
- child display name;
- allowed consumption preferences represented by administrator-approved codes.

The MVP does not collect an address, full date of birth, payment-card data,
government identifier, medical diagnosis or biometric data. Tags contain only
opaque identifiers. Raw identifiers, names, contacts and connector payloads
must not appear in logs, diagnostics, package defaults or test fixtures.

## Acceptance examples

### Registration and idempotency

Given an enrolled kiosk submits one guardian, one child and consent version
`test-v1` with idempotency key `registration-command-1`, the result is one
registration in `submitted` state. Repeating the same payload and key returns
the stored result. Reusing the key with a different payload fails and creates
no additional rows. The kiosk can read that submission result but cannot list
or open another registration.

### Contact fields and language

The kiosk and operator registration forms show phone and email as separate
fields. A guardian may provide either one or both, but a submission with both
empty fails without creating domain records. The extension initially follows
the saved `preferredLanguage` value and provides a small BG/EN control on each
route. With no saved preference it starts in English, and a language change is
shared across the extension routes without requiring a Core-specific change.

### Tablet fullscreen registration

Given a tablet opens `/child-center/register`, the public bootstrap surface is
available without an operator or administrator session. Before personal data
can be submitted, the tablet must claim a short-lived, one-time enrollment code
created from the administrator route. The extension retains the terminal
identity locally and renews short-lived kiosk access tokens without exposing
the administrator session. Pressing the localized Fullscreen control requests
browser fullscreen for the Child Center registration surface itself. While
active, only the registration UI, language control and explicit Exit action are
visible. If the browser denies the request, the route remains usable and shows
a localized error.

### Entry

Given a currently active identifier assignment, reader mode `entry`, event
time `2026-08-30T09:00:00Z`, processing the scan creates exactly one active
visit. The visit stores the UTC entry time and display timezone, with no price
or tariff snapshot.

### Duplicate scan

Redelivering the same event ID and idempotency key returns the original entry
result. It creates no second visit or visit event. A different event received
while the reader remains in `entry` mode is rejected as an already-active
visit; it is not interpreted as an exit.

### Exit and measured duration

Given the visit above and an `exit` scan at `2026-08-30T10:02:00Z`, elapsed
time is 62 minutes. The visit closes once and stores `3720` elapsed seconds.
No monetary value is calculated or persisted by Child Center.

A visit from `2026-08-30T20:50:00Z` to `2026-08-30T21:20:00Z` crosses local
midnight in `Europe/Sofia` and remains 30 elapsed minutes.

### Connector outage

When Barsy delivery is implemented, a start/stop command that cannot be sent
must remain durable and retryable. Restart, disable/re-enable and backup/restore
must not reopen a visit or discard pending integration work.

### Ambiguous Barsy mutation

If Barsy may have accepted a start/stop mutation but the response is lost, the
operation enters `ambiguous`/manual-review state. The extension does not blindly
replay it. Reconciliation or an explicit operator decision is required.

### Privacy lifecycle

An administrator export request is scoped to one guardian or child and returns
only extension-owned data. Erasure anonymizes the selected personal fields and
retired identifiers without changing persisted measured-time events.
The retention job applies the same rules in bounded batches and records only
counts and correlation metadata in its operational result.

## Frozen MVP exclusions

Version `0.4.1` does not implement continuous tracking, a physical reader driver
or Barsy API mutations. It adds administrator-managed table mapping, a local
mock allocation lifecycle and bounded read-only discovery of Barsy places.
Pricing, payment, fiscal operations, receipt printing and reversals are
intentionally outside the Child Center domain.
