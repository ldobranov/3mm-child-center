"""Durable admission denials for unavailable configured capacity."""
from three_mm_application_sdk import ApplicationMigration

from child_center_application.billing_units import BillingRuntime, get_migrations as previous_migrations
from child_center_application.account_observation import AccountObservation, migrate as migrate_observations


def migration(connection):
    # Add bounded diagnostic codes without changing an already shipped migration.
    connection.execute('''CREATE TABLE scan_failures_new (
        event_id TEXT PRIMARY KEY REFERENCES identifier_scan_activity(event_id),
        error_code TEXT NOT NULL CHECK(error_code IN (
            'barsy_credentials_unavailable','barsy_unavailable','barsy_rejected','barsy_invalid_response',
            'no_enabled_tables','no_free_tables'))
    )''')
    connection.execute('INSERT INTO scan_failures_new SELECT * FROM scan_failures')
    connection.execute('DROP TABLE scan_failures')
    connection.execute('ALTER TABLE scan_failures_new RENAME TO scan_failures')
    migrate_observations(connection)


def get_migrations():
    return [*previous_migrations(), ApplicationMigration('0020', migration)]


class ReliableRuntime(BillingRuntime):
    def __init__(self, application):
        super().__init__(application)
        self.account_observation = AccountObservation(self)

    def handle(self, operation_id, payload, context):
        result = super().handle(operation_id, payload, context)
        if operation_id in {'list_operator_accounts', 'list_checkout_accounts'}:
            with self.application.storage.transaction() as c:
                for item in result['items']:
                    item['remote_observation'] = self.account_observation.cached(c, item['visit_id'])
        return result

    def _additional_delivery_work(self, connection):
        return [*super()._additional_delivery_work(connection),
                (self.account_observation.ready(connection), self.account_observation.observe)]

    def _health(self, payload, context):
        self._require_audience(context, 'internal')
        if payload:
            raise ValueError('Health operation requires an empty request')
        if self.application.storage.status().get('revision') != '0020':
            raise RuntimeError('Application storage is not ready')
        return dict(status='ready', schema_revision='0020', service_version=self.application.version)

    def _scan_failure_code(self, error):
        inherited = super()._scan_failure_code(error)
        if inherited is not None:
            return inherited
        # Do not turn schema, payload, conflict or unexpected application errors
        # into successful acknowledgements. Only these known capacity denials
        # represent terminal decisions about the original physical scan.
        if type(error) is ValueError:
            return {
                'Configure at least one Barsy table before entry': 'no_enabled_tables',
                'No Barsy table is currently available': 'no_free_tables',
                'No configured table is free in Barsy': 'no_free_tables',
            }.get(str(error))
        return None


def create_service(application):
    return ReliableRuntime(application)
