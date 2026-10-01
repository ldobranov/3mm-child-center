"""0.6.8 entrypoint: one journal per instance, opt-in sensor admission and privacy.

Schema 0017 exposes configured access workflows. Older-schema fallback is kept
for compatibility tests; production uses the builder's matched entrypoint/schema.
"""
import json
from child_center_application.service import ChildCenterService, _canonical, _digest
from child_center_application.access_points import AccessJournal
from child_center_application.sensor_admission import SensorAdmission
from child_center_application.access_review import AccessReview
from child_center_application.privacy import PrivacyWorkflow


class AccessRuntime(ChildCenterService):
    def __init__(self, application):
        super().__init__(application)
        self.access_journal = None
        self.sensor_admission = None
        self.access_review = None
        self.privacy = None
        self.access_control = None
        if application.storage.status().get('revision', '') >= '0016':
            self.access_journal = AccessJournal(application.storage, application.platform, application.clock)
            self.sensor_admission = SensorAdmission(self, self.access_journal)
            self.access_review = AccessReview(self, self.access_journal)
            self.privacy = PrivacyWorkflow(self)
        if application.storage.status().get('revision', '') >= '0017':
            from child_center_application.access_control import AccessControl
            self.access_control = AccessControl(self)

    def handle(self, operation_id, payload, context):
        if self.access_control is not None:
            operations = {
                'get_access_settings': self.access_control.settings,
                'configure_access_point': self.access_control.configure,
                'get_access_status': self.access_control.status,
                'process_access_work': self.access_control.work,
                'process_access_passage': self.access_control.passage,
                'reconcile_access': self.access_control.reconcile,
                'resolve_unsent_access': self.access_review.resolve_unsent,
            }
            if operation_id in operations:
                return operations[operation_id](payload, context)
        if self.privacy is not None and operation_id in {'export_personal_data', 'erase_personal_data', 'apply_retention', 'delete_client'}:
            return {'export_personal_data': self.privacy.export,
                    'erase_personal_data': self.privacy.erase,
                    'apply_retention': self.privacy.retention,
                    'delete_client': self.privacy.delete_client}[operation_id](payload, context)
        return super().handle(operation_id, payload, context)

    def _health(self, payload, context):
        if self.access_control is not None:
            self._require_audience(context, 'internal')
            if payload:
                raise ValueError('Health operation requires an empty request')
            if self.application.storage.status().get('revision') != '0017':
                raise RuntimeError('Application storage is not ready')
            return {'status': 'ready', 'schema_revision': '0017', 'service_version': self.application.version}
        return super()._health(payload, context)

    def _process_identifier_scan(self, payload, context):
        if self.access_control is not None:
            result = self.access_control.scan(payload, context)
            if result is not None:
                return result
        return super()._process_identifier_scan(payload, context)

    def _deliver_barsy_commands(self, payload, context):
        result = super()._deliver_barsy_commands(payload, context)
        if self.access_control is not None:
            # Do not wait another five-second scheduler interval after account
            # confirmation: the original physical-request deadline still applies.
            self.access_control.work({}, context)
        return result

    def _idempotent(self, operation_id, payload, context, mutation, *, decorate=None):
        if self.privacy is None:
            return super()._idempotent(operation_id, payload, context, mutation, decorate=decorate)
        if not context.idempotency_key:
            raise ValueError('An idempotency key is required')
        key = self._command_key(context.idempotency_key)
        digest = _digest(_canonical(payload))
        with self.application.storage.transaction() as c:
            if c.execute('SELECT 1 FROM privacy_redacted_commands WHERE idempotency_key=?', (key,)).fetchone():
                raise ValueError('This command result was revoked by privacy processing; it cannot be replayed')
            previous = c.execute('SELECT * FROM command_results WHERE idempotency_key=?', (key,)).fetchone()
            if previous:
                if previous['operation_id'] != operation_id or previous['payload_hash'] != digest:
                    raise ValueError('Idempotency key was reused with another request')
                result = json.loads(previous['result_json'])
            else:
                if operation_id in {'update_client','correct_registration','approve_registration'}:
                    registration = payload['registration_id']
                    if (c.execute("SELECT 1 FROM guardians WHERE registration_id=? AND status IN ('erased','anonymized')", (registration,)).fetchone()
                            or c.execute("SELECT 1 FROM children WHERE registration_id=? AND status IN ('erased','anonymized')", (registration,)).fetchone()):
                        raise ValueError('Redacted subjects cannot be restored by an old registration update')
                result = mutation(c)
                c.execute('INSERT INTO command_results VALUES (?,?,?,?,?)', (key,operation_id,digest,_canonical(result),self._now()))
        return decorate(result, context.idempotency_key) if decorate else result

    def _finish_stay(self, connection, visit, occurred_at, context):
        if self.access_journal is not None:
            # The same SQLite write transaction serializes finish with the
            # durable pre-submit claim, even across service instances. Never
            # infer cancellation from timeout or from a lost submit response.
            pending = connection.execute("""SELECT 1 FROM access_intents
                WHERE visit_id=? AND state NOT IN ('confirmed','resolved','prepared')
                AND NOT (state='review' AND COALESCE(error_code,'') IN
                    ('expired_before_submit','visit_changed_before_submit')
                    AND command_id IS NULL AND generation IS NULL
                    AND passage_event_id IS NULL) LIMIT 1""", (visit['visit_id'],)).fetchone()
            if pending:
                raise ValueError('Resolve the pending physical passage before finishing this stay')
            connection.execute("""UPDATE access_intents SET state='review',
                error_code='visit_changed_before_submit'
                WHERE visit_id=? AND state='prepared'""", (visit['visit_id'],))
        return super()._finish_stay(connection, visit, occurred_at, context)

    def _start_visit_mutation(self, connection, **request):
        if (self.access_control is not None and self.access_control.current(connection) is not None
                and (request['context'].audience != 'internal'
                     or request['details'].get('source') != 'sensor_reservation')):
            raise ValueError('Sensor mode requires a fresh bracelet scan, not manual start')
        return super()._start_visit_mutation(connection, **request)

    def _transition_stay(self, connection, visit_id, occurred_at, inside, context, source_event_id, details):
        if (self.access_journal is not None and self._commerce.sensor_managed(connection, visit_id)
                and (context.audience != 'internal' or not source_event_id
                     or details.get('source') != 'confirmed_passage')):
            raise ValueError('This stay requires confirmed sensor passage, not a legacy scan or resume')
        return super()._transition_stay(connection, visit_id, occurred_at, inside,
            context, source_event_id, details)


def create_service(application):
    return AccessRuntime(application)
