# Child Center CC-4B verified Barsy discovery boundary

Status: implemented in `0.4.1` without production Barsy mutations.

## Verified transport

Barsy uses HTTP Basic authentication and exposes a single-method endpoint at
`/endpoints/json/{method}`. `Places_getlist` is documented as a read-only list
of configured places and returns positive integer `place_id` values. The Child
Center extension calls it with `GET` through the destination-restricted 3mm
connector. The credential remains an opaque platform secret reference.

The extension accepts only a bounded array of place objects, normalizes the
documented identifier and display fields, and returns at most 256 entries. It
does not persist or expose the raw response. Timeout, rejection, unavailable
connector and invalid response remain distinct results.

## Safe mutation boundary

The reviewed documentation confirms that starting timed use requires an open
account on the place with the configured timed article. It also confirms a UI
action that stops the timed article while leaving the account open. The public
API catalog does not document that timer-only stop action.

`Accounts_close` is explicitly excluded: it closes the commercial account and
may record payment, print a fiscal receipt and update stock. Child Center must
not substitute it for timer-only stop.

For `0.4.1`:

- `production_mutations_enabled` is always `false`;
- local start and stop identities remain `mock_confirmed`;
- the administrator can inspect bounded command counts and review-state counts;
- no `Accounts_create`, `Accounts_close` or other Barsy mutation is sent;
- Core and Agent remain vendor-neutral.

Production timing delivery requires a version-specific Lukanet contract for
both start and non-fiscal stop, including request, response, idempotency and
reconciliation behavior.

## Acceptance examples

When the connector returns two valid Barsy places, discovery returns only their
IDs, labels, salon/type labels, optional open-account counts and existing local
mapping identity. Unknown fields are discarded.

A retryable connector result returns no places and a bounded retryable status.
A malformed, oversized or duplicate-ID response returns `invalid_response` and
does not alter the configured table pool.

Reading the Barsy catalog never creates a local visit, table binding, timing
command or connector mutation attempt.
