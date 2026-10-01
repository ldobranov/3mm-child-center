# Child Center Barsy connector boundary

Status: default mock lifecycle with opt-in live integration in 0.5.0.

The extension declares one destination-restricted connector named
`barsy_api`. The administrator binds its URL and opaque Basic credential
reference through the platform. No credential value reaches the package,
service state, browser, logs or diagnostics.

The integration boundary is intentionally narrow:

- Child Center registers clients and records opaque identifier assignments;
- entry and exit transitions produce measured UTC timestamps;
- a singleton job opens accounts on preconfigured Barsy places after entry;
- exit remains local; remote completion is manual, verification/release automatic;
- approved parents are synchronized and their client IDs identify new accounts;
- administrator-selected sale articles supply consumption permission choices;
- Barsy alone determines prices, bill totals and fiscal actions.

The authenticated documentation verifies `Places_getlist` as the read-only
source for configured places and its integer `place_id`. It also verifies that
`Accounts_close` closes the account and participates in payment/fiscal work, so
Child Center must not use it as a timer-only stop. Live opening does not imply
automatic stop, timed-article insertion, payment or fiscal closure.
Mutating calls must use a durable local identity; an ambiguous
response cannot be replayed blindly and must be reconciled or surfaced for
operator review.

Version `0.5.0` uses GET `Places_getlist`, `Poses_getcurrent`, `Articles_getlist`,
`Clients_getlist`, `Clients_get`, `Accounts_getlist`, and `Accounts_get` under
`/endpoints/json/`. JSON reads send
parameter objects or `{}`, not empty bodies; paths contain no query strings.
POST is restricted to `Clients_createsmart` (parent name, supplied contacts and
an opaque client code) and `Accounts_create` (durable UUID, place ID, verified
parent client ID, child name in the identity-prefixed alias, empty rows).
Before POST, ambiguous state is
persisted. The demo rejects duplicate UUIDs, so an uncertain outcome must not be
replayed. Reconciliation verifies account ID, place and alias; local exit only
releases the place after remote status confirms closure. Definitely unsent
commands can be cancelled after local exit. Reserve the pool for this extension:
occupancy reads cannot prevent concurrent use by another client. Do not rebind
the connector while accounts are outstanding. Elapsed account time alone is
not proof of a configured chargeable timed article.

Client creation conflicts are never resolved by name alone: all supplied contacts
must also match. Unknown results use read-only marker lookup or manual client-ID
verification, never automatic POST replay. Directory operations are admin-only;
the kiosk receives only enabled article IDs/names through a bounded local query.
Local deletion does not imply deletion of independently held Barsy records.

Reviewed method references:
- https://docs.lukanet.com/barsy.api/methods/clients/createsmart.html
- https://docs.lukanet.com/barsy.api/methods/clients/getlist.html
- https://docs.lukanet.com/barsy.api/methods/articles/getlist.html
- https://docs.lukanet.com/barsy.api/methods/accounts/create.html

No real Barsy credential, customer data, table identifier or fiscal data is embedded
in the package, defaults, logs or fixtures. Core and Agent remain vendor-neutral.
