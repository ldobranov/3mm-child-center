# Child Center CC-4A Barsy table-pool decisions

Status: implemented as the safe `0.4.0` mapping and mock-lifecycle boundary.
It contains no production Barsy mutation and no credential value.

## Verified API facts

- `Places_getlist` is the read-only Barsy method for configured places such as
  tables and rooms. Its place identity is the positive integer `place_id`.
- Barsy timing starts operationally by opening an account on a configured
  place and adding its timed article. `Accounts_create` accepts a durable
  request `uuid` and a `place_id`.
- `Accounts_close` is not a safe synonym for stopping measured time. It closes
  the account and may perform payments, fiscal printing and stock updates.
- The reviewed API method catalog and official Postman collection do not expose
  a separately documented timer-only stop mutation.

Therefore `Accounts_close` is excluded from Child Center timing delivery. A
production stop adapter remains blocked until Lukanet confirms a non-fiscal
request and response contract for the installed Barsy version.

## Selected pool policy

1. An administrator records positive Barsy `place_id` values that already
   exist in Barsy, with an operator label, priority and enabled state.
2. The extension never creates or edits Barsy tables, articles, tariffs,
   prices, bills or fiscal settings.
3. With no enabled mappings, the existing local visit workflow remains active
   and creates no Barsy binding.
4. With at least one enabled mapping, entry atomically claims the first free
   slot by priority and Barsy place ID. If all enabled slots are occupied, the
   entry transaction fails and creates no visit.
5. A visit has at most one binding. A slot has at most one allocated visit.
6. Exit releases the same slot. An allocated mapping cannot be edited or
   disabled.
7. CC-4A creates one durable local start identity and one durable local stop
   identity per bound visit. Their state is `mock_confirmed`; no network call
   or transactional outbox delivery occurs in this version.
8. The schema already reserves distinct `prepared`, `confirmed`, `retryable`,
   `ambiguous` and `manual_review` states for the later verified adapter.

## Acceptance examples

Given enabled mappings for Barsy places `101` and `102`, both at the same
priority, the first entry receives `101` and the second receives `102`. A third
entry fails atomically while both are allocated. Closing the first visit frees
`101`, which can then be claimed by the next entry.

Replaying a visit command with the same idempotency key returns the stored
result and does not create another visit, binding or timing identity. Direct
database uniqueness also prevents a visit from receiving two slots and a slot
from serving two active visits.

No operation contract or stored timing command contains a price, tariff,
currency, payment, receipt or fiscal field.
