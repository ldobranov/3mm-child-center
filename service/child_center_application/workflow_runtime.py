"""0.6.9: bounded delivery selection and durable, non-replayed admission failures."""
import base64
import json

from three_mm_application_sdk import ApplicationMigration, ApplicationPlatformError
from three_mm_protocol.identifier_scan import IdentifierScanEventV1
from child_center_application.access_control import get_migrations as previous_migrations
from child_center_application.access_runtime import AccessRuntime
from child_center_application.service import _canonical, _digest


class AdmissionReadError(ValueError):
    def __init__(self, code):
        self.code = code
        super().__init__('Barsy admission check failed: ' + code)


def migration(connection):
    connection.execute('''CREATE TABLE scan_failures (
        event_id TEXT PRIMARY KEY REFERENCES identifier_scan_activity(event_id),
        error_code TEXT NOT NULL CHECK(error_code IN (
            'barsy_credentials_unavailable','barsy_unavailable','barsy_rejected','barsy_invalid_response'))
    )''')


def get_migrations():
    return [*previous_migrations(), ApplicationMigration('0018', migration)]


class WorkflowRuntime(AccessRuntime):
    def _health(self, payload, context):
        self._require_audience(context, 'internal')
        if payload:
            raise ValueError('Health operation requires an empty request')
        if self.application.storage.status().get('revision') != '0018':
            raise RuntimeError('Application storage is not ready')
        return dict(status='ready', schema_revision='0018', service_version=self.application.version)

    def _barsy_read(self, path, parameters=None):
        if self.application.platform is None:
            raise AdmissionReadError('barsy_unavailable')
        try:
            response = self.application.platform.connector_request('barsy_api', method='GET', path=path,
                body=_canonical(parameters or {}).encode(), headers={'Content-Type': 'application/json'})
        except ApplicationPlatformError as exc:
            # Classify locally; never persist or return arbitrary platform messages.
            code = 'barsy_credentials_unavailable' if str(exc) in {
                'Application credential cannot be decrypted', 'Connector credential is unavailable',
                'Connector credential is unavailable or incompatible'} else 'barsy_unavailable'
            raise AdmissionReadError(code) from None
        if response.get('outcome') != 'succeeded':
            raise AdmissionReadError('barsy_rejected')
        try:
            return json.loads(base64.b64decode(response['body_base64'], validate=True))
        except (ValueError, KeyError, TypeError, UnicodeError):
            raise AdmissionReadError('barsy_invalid_response') from None

    def _scan_failure_code(self, error):
        return error.code if isinstance(error, AdmissionReadError) else None

    def _process_identifier_scan(self, payload, context):
        self._require_audience(context, 'internal')
        IdentifierScanEventV1.model_validate(payload)
        if not context.idempotency_key:
            raise ValueError('An idempotency key is required')
        try:
            return super()._process_identifier_scan(payload, context)
        except ValueError as exc:
            code = self._scan_failure_code(exc)
            if code is None:
                raise
            # The failed admission transaction has rolled back. Persist a terminal
            # denial separately; broker retries must never admit someone later.
            def denied(c):
                event_id, digest = payload['event_id'], _digest(_canonical(payload))
                old = c.execute('SELECT * FROM identifier_event_results WHERE event_id=?', (event_id,)).fetchone()
                if old:
                    if old['payload_hash'] != digest:
                        raise ValueError('Identifier event ID was reused with another payload')
                    return json.loads(old['result_json'])
                assignment = c.execute('SELECT child_id FROM identifier_assignments WHERE opaque_identifier=? AND retired_at IS NULL',
                    (payload['payload']['opaque_identifier'],)).fetchone()
                result = self._store_identifier_event_result(c, event_id=event_id, payload_hash=digest,
                    occurred_at=self._parse_time(payload['occurred_at']).isoformat(),
                    result={'status': 'ignored', 'visit_id': None}, scan=payload['payload'],
                    child_id=assignment['child_id'] if assignment else None)
                c.execute('INSERT INTO scan_failures VALUES (?,?)', (event_id, code))
                return result
            return self._idempotent('process_identifier_scan', payload, context, denied)

    def handle(self, operation_id, payload, context):
        if operation_id == 'list_scan_outcomes':
            self._require_audience(context, 'operator', 'administrator')
            if payload:
                raise ValueError('Scan outcomes require an empty request')
            with self.application.storage.transaction() as c:
                rows = c.execute('''SELECT a.event_id,a.occurred_at,a.status,
                    f.error_code,c.display_name child_name FROM identifier_scan_activity a
                    LEFT JOIN scan_failures f ON f.event_id=a.event_id
                    LEFT JOIN children c ON c.child_id=a.child_id
                    ORDER BY a.occurred_at DESC,a.event_id DESC LIMIT 10''').fetchall()
            return {'items': [dict(r) for r in rows]}
        return super().handle(operation_id, payload, context)

    def _deliver_barsy_commands(self, payload, context):
        self._require_audience(context, 'internal')
        if payload or not context.idempotency_key:
            raise ValueError('Delivery requires an empty request and idempotency identity')
        if not self._integration_lock.acquire(blocking=False):
            return {'processed': 0}
        try:
            with self.application.storage.transaction() as c:
                if not self._live_start(c):
                    return {'processed': 0}
                # Readiness must match each handler's ownership predicates. New
                # accounts are not work for legacy release/billing handlers.
                queries = [
                    "SELECT 1 FROM barsy_parent_links l JOIN guardians g ON g.guardian_id=l.guardian_id WHERE l.state IN ('prepared','ambiguous') AND g.status='active' LIMIT 1",
                    "SELECT 1 FROM visits v JOIN visit_barsy_bindings b ON b.visit_id=v.visit_id JOIN barsy_timing_commands cmd ON cmd.command_id=b.start_command_id WHERE v.state='closed' AND b.state='allocated' AND cmd.state='confirmed' AND cmd.remote_account_id IS NOT NULL AND NOT EXISTS (SELECT 1 FROM stay_accounts a WHERE a.visit_id=v.visit_id) LIMIT 1",
                    "SELECT 1 FROM barsy_timing_commands WHERE command_kind='start' AND state IN ('prepared','retryable') AND remote_place_id IS NOT NULL LIMIT 1",
                    "SELECT 1 FROM stay_bills bill WHERE state IN ('prepared','retryable') AND NOT EXISTS (SELECT 1 FROM stay_accounts a WHERE a.visit_id=bill.visit_id) LIMIT 1",
                    "SELECT 1 FROM account_commands cmd WHERE state='prepared' AND NOT EXISTS (SELECT 1 FROM account_commands older WHERE older.visit_id=cmd.visit_id AND older.sequence<cmd.sequence AND older.state IN ('prepared','ambiguous')) LIMIT 1",
                    "SELECT 1 FROM stay_accounts a JOIN visits v ON v.visit_id=a.visit_id JOIN visit_barsy_bindings b ON b.visit_id=a.visit_id JOIN barsy_timing_commands cmd ON cmd.command_id=b.start_command_id WHERE a.admitted=0 AND v.state='active' AND cmd.state='confirmed' LIMIT 1",
                ]
                ready = [c.execute(q).fetchone() is not None for q in queries]
                additional = self._additional_delivery_work(c)
            actions = [self._deliver_one_parent, self._release_completed_barsy_accounts,
                self._deliver_one_barsy_start, self._deliver_one_stay_bill,
                self._commerce.deliver, self._commerce.admit_next]
            ready.extend(item[0] for item in additional)
            actions.extend(item[1] for item in additional)
            processed = 0
            for offset in range(len(actions)):
                phase = (self._integration_phase + offset) % len(actions)
                if ready[phase]:
                    self._integration_phase = (phase + 1) % len(actions)
                    processed = actions[phase]()
                    break  # At most one external workflow, retaining fair rotation.
        finally:
            self._integration_lock.release()
        if self.access_control is not None:
            self.access_control.work({}, context)
        return {'processed': processed}

    def _additional_delivery_work(self, connection):
        return []


def create_service(application):
    return WorkflowRuntime(application)
