"""Configured single bidirectional access point; scan-only remains the default.

The installed driver binding supplies a bounded pulse. Only its correlated sensor
establishes passage. Device identities come from installation configuration.
"""
from datetime import timedelta
import json
import uuid

from pydantic import BaseModel, ConfigDict, Field
from three_mm_application_sdk import ApplicationMigration
from three_mm_protocol.identifier_scan import IdentifierScanEventV1
from three_mm_protocol.passage import PassageEventV1
from child_center_application.access_points import SensorPoint, PulseArguments, canonical
from child_center_application.service import ChildCenterService, _digest, _canonical
from child_center_application.migrations import get_migrations as previous_migrations


class Configure(BaseModel):
    model_config = ConfigDict(extra='forbid', strict=True)
    expected_point_id: str | None = Field(pattern=r'^point_[0-9a-f]{32}$')
    enabled: bool
    reader_id: str = Field(pattern=r'^[A-Za-z0-9][A-Za-z0-9_.:-]{0,95}$')
    channel: str = Field(pattern=r'^[A-Za-z0-9][A-Za-z0-9_.:-]{0,31}$')
    duration_ms: int = Field(ge=50, le=500)
    safety_confirmed: bool


class ReviewRequest(BaseModel):
    model_config = ConfigDict(extra='forbid', strict=True)
    request_id: str = Field(pattern=r'^access_[0-9a-f]{32}$')
    expected_state: str = Field(pattern=r'^(review|invalidated)$')
    observed_inside: bool
    hardware_isolated: bool
    confirmed: bool


class Empty(BaseModel):
    model_config = ConfigDict(extra='forbid', strict=True)


def migration(connection):
    connection.execute('''CREATE TABLE access_control_settings (
        singleton INTEGER PRIMARY KEY CHECK(singleton=1),
        point_id TEXT REFERENCES access_points(point_id), output_device TEXT)''')
    connection.execute('INSERT INTO access_control_settings VALUES (1,NULL,NULL)')


def get_migrations():
    return [*previous_migrations(), ApplicationMigration('0017', migration)]


class AccessControl:
    def __init__(self, service):
        self.s, self.j = service, service.access_journal

    def current(self, c):
        row = c.execute('SELECT * FROM access_control_settings WHERE singleton=1').fetchone()
        if row['point_id'] is None:
            return None
        point = SensorPoint.model_validate_json(c.execute('SELECT configuration_json FROM access_points WHERE point_id=?', (row['point_id'],)).fetchone()[0])
        cfg = self.s.application.configuration
        valid = (point.reader_device == cfg.get('READER_DEVICE_ID')
                 and point.sensor_device == cfg.get('ACCESS_SENSOR_DEVICE_ID')
                 and row['output_device'] == cfg.get('ACCESS_OUTPUT_DEVICE_ID'))
        return point, valid

    def settings(self, payload, context):
        self.s.access_review._administrator(context)
        Empty.model_validate(payload)
        with self.j.transaction() as c:
            current = self.current(c)
            saved_output = c.execute('SELECT output_device FROM access_control_settings WHERE singleton=1').fetchone()[0]
        point, valid = current if current else (None, True)
        return {'point_id': point.point_id if point else None, 'enabled': point is not None,
            'binding_valid': valid, 'reader_id': point.reader_id if point else '',
            'channel': point.arguments.channel if point and point.arguments else '',
            'duration_ms': point.arguments.duration_ms if point and point.arguments else 100,
            'sensor_id': 'access.sensor',
            'reader_device': point.reader_device if point else self.s.application.configuration.get('READER_DEVICE_ID', ''),
            'output_device': saved_output if point else self.s.application.configuration.get('ACCESS_OUTPUT_DEVICE_ID', ''),
            'sensor_device': point.sensor_device if point else self.s.application.configuration.get('ACCESS_SENSOR_DEVICE_ID', '')}

    def configure(self, payload, context):
        self.s.access_review._administrator(context)
        request = Configure.model_validate(payload)
        if request.enabled and not request.safety_confirmed:
            raise ValueError('Driver, correlated sensor and independent emergency egress must be verified')
        def mutation(c):
            current = c.execute('SELECT point_id FROM access_control_settings WHERE singleton=1').fetchone()[0]
            if current != request.expected_point_id:
                raise ValueError('Access configuration changed')
            if (c.execute("SELECT 1 FROM visits WHERE state='active' LIMIT 1").fetchone()
                    or c.execute("SELECT 1 FROM access_intents WHERE state NOT IN ('confirmed','resolved') LIMIT 1").fetchone()):
                raise ValueError('Finish visits and resolve physical requests before changing mode')
            point_id = None
            output = None
            if request.enabled:
                if not self.s._live_start(c):
                    raise ValueError('Sensor admission requires live commercial capacity')
                cfg = self.s.application.configuration
                output = cfg.get('ACCESS_OUTPUT_DEVICE_ID')
                # Same strict device syntax as the generic installation contract.
                from re import fullmatch
                if not isinstance(output, str) or not fullmatch(r'dev_[0-9a-f]{32}', output):
                    raise ValueError('Select the output device in extension installation settings')
                point_id = 'point_' + uuid.uuid4().hex
                point = SensorPoint(point_id=point_id, reader_device=cfg.get('READER_DEVICE_ID'),
                    reader_id=request.reader_id, binding_id='access_output',
                    sensor_device=cfg.get('ACCESS_SENSOR_DEVICE_ID'), sensor_id='access.sensor',
                    entry_direction='forward', arguments=PulseArguments(channel=request.channel, duration_ms=request.duration_ms))
                c.execute('INSERT INTO access_points VALUES (?,?)', (point_id, canonical(point.model_dump())))
            c.execute('UPDATE access_control_settings SET point_id=?,output_device=? WHERE singleton=1', (point_id, output))
            self.s._audit(c, event_type='access.configured', entity_type='access_point',
                entity_id=point_id or 'scan_only', context=context, metadata={'enabled': request.enabled})
            return {'status': 'updated', 'point_id': point_id}
        return self.s._idempotent('configure_access_point', request.model_dump(), context, mutation)

    def scan(self, payload, context):
        self.s._require_audience(context, 'internal')
        event = IdentifierScanEventV1.model_validate(payload)
        with self.j.transaction() as c:
            current = self.current(c)
            if current is None:
                return None  # existing scan-only handler
            point, valid = current
            previous = c.execute('SELECT payload_hash,result_json FROM identifier_event_results WHERE event_id=?', (event.event_id,)).fetchone()
            digest = _digest(_canonical(payload))
            if previous:
                if previous['payload_hash'] != digest:
                    raise ValueError('Identifier event ID conflict')
                return json.loads(previous['result_json'])
            scan = payload['payload']
            child = None
            result = {'status': 'ignored', 'visit_id': None}
            if not valid or event.device_id != point.reader_device or event.payload.reader_id != point.reader_id:
                result['status'] = 'wrong_reader_mode'
            elif event.payload.device_health != 'ok':
                result['status'] = 'ignored'
            else:
                assignment = c.execute("""SELECT a.* FROM identifier_assignments a JOIN children ch
                    ON ch.child_id=a.child_id WHERE a.opaque_identifier=? AND a.retired_at IS NULL AND ch.status='active'""",
                    (event.payload.opaque_identifier,)).fetchone()
                now = self.s.application.clock.now()
                deadline = event.occurred_at + timedelta(seconds=point.ttl_seconds)
                if assignment is None:
                    result['status'] = 'unknown_identifier'
                elif event.occurred_at > now or deadline <= now or event.occurred_at < self.s._parse_time(assignment['assigned_at']):
                    result['status'] = 'late_event'
                else:
                    child = assignment['child_id']
                    active = c.execute("SELECT visit_id FROM visits WHERE child_id=? AND state='active'", (child,)).fetchone()
                    if active is None:
                        if not self.s._live_start(c):
                            raise ValueError('Sensor admission requires live mode')
                        started = self.s._start_visit_mutation(c, child_id=child,
                            assignment_id=assignment['assignment_id'], occurred_at=self.s._now(),
                            context=context, source_event_id=None, details={'source': 'sensor_reservation'})
                        visit_id = started['visit_id']
                        c.execute('INSERT INTO access_sensor_stays VALUES (?,?)', (visit_id, point.point_id))
                    else:
                        visit_id = active['visit_id']
                    result['visit_id'] = visit_id
                    owner = c.execute('SELECT point_id FROM access_sensor_stays WHERE visit_id=?', (visit_id,)).fetchone()
                    stay = self.s._stay(c, visit_id)
                    pending = c.execute("SELECT 1 FROM access_intents WHERE visit_id=? AND state NOT IN ('confirmed','resolved')", (visit_id,)).fetchone()
                    if owner is None or owner[0] != point.point_id:
                        result['status'] = 'wrong_reader_mode'
                    elif pending:
                        result['status'] = 'ignored'
                    elif event.occurred_at <= self.s._parse_time(stay['last_transition_at']) and active is not None:
                        result['status'] = 'late_event'
                    elif self.s.application.clock.now() < deadline:
                        identity = 'access_' + _digest(event.event_id)[:32]
                        request = {'request_id': identity, 'point_id': point.point_id, 'visit_id': visit_id,
                            'direction': 'exit' if stay['inside_since'] else 'entry',
                            'reader_device': point.reader_device, 'reader_id': point.reader_id}
                        # Prepared is only a durable request. The worker must pass
                        # commercial and source checks before claiming submission.
                        c.execute('''INSERT INTO access_intents
                            (request_id,point_id,visit_id,payload_json,state,created_at,expires_at)
                            VALUES (?,?,?,?,'prepared',?,?)''', (identity, point.point_id, visit_id,
                            canonical(request), self.s._now(), deadline.isoformat()))
            return self.s._store_identifier_event_result(c, event_id=event.event_id,
                payload_hash=digest, occurred_at=event.occurred_at.isoformat(), result=result,
                scan=scan, child_id=child)

    def status(self, payload, context):
        self.s._require_audience(context, 'administrator', 'operator')
        Empty.model_validate(payload)
        with self.j.transaction() as c:
            rows = c.execute('''SELECT i.request_id,i.visit_id,i.state,i.error_code,i.expires_at,
                ch.display_name child_name,s.inside_since FROM access_intents i
                JOIN visits v ON v.visit_id=i.visit_id JOIN children ch ON ch.child_id=v.child_id
                JOIN stay_sessions s ON s.visit_id=v.visit_id
                WHERE i.state NOT IN ('confirmed','resolved') ORDER BY i.created_at,i.request_id LIMIT 101''').fetchall()
            current = self.current(c)
        return {'enabled': current is not None, 'binding_valid': current[1] if current else True,
                'items': [dict(row) for row in rows[:100]], 'has_more': len(rows) > 100}

    def work(self, payload, context):
        self.s._require_audience(context, 'internal')
        Empty.model_validate(payload)
        if not context.idempotency_key:
            raise ValueError('An idempotency key is required')
        # Every effect has its own durable request identity. Repeated job ticks
        # may inspect the same record but can never submit it a second time.
        self.j.review_pending()
        with self.j.transaction() as c:
            current = self.current(c)
            if current is None or not current[1]:
                return {'processed': 0}
            rows = c.execute("SELECT request_id FROM access_intents WHERE point_id=? AND state='prepared' ORDER BY created_at LIMIT 10", (current[0].point_id,)).fetchall()
        processed = 0
        if rows:
            self.s._commerce.admit_next()
        for row in rows:
            try:
                self.s.sensor_admission.dispatch(row['request_id'], context)
                processed += 1
            except ValueError:
                # Readiness may still be pending; expiry will stop delayed grants.
                continue
        return {'processed': processed}

    def passage(self, payload, context):
        self.s._require_audience(context, 'internal')
        event = PassageEventV1.model_validate(payload)
        with self.j.transaction() as c:
            known = c.execute('SELECT 1 FROM access_intents WHERE command_id=?', (event.payload.command_id,)).fetchone()
            rows = [] if known else c.execute("SELECT request_id FROM access_intents WHERE state='review' AND error_code IN ('submit_outcome_unknown','startup_submit_unknown') LIMIT 10").fetchall()
        for row in rows:
            try:
                self.j.recover(row['request_id'])
            except Exception:
                # An unrelated unresolved command must not prevent acceptance of
                # this event. The journal still requires its exact correlation.
                continue
        return {'accepted': self.s.sensor_admission.confirm(payload, context)}

    def reconcile(self, payload, context):
        self.s.access_review._administrator(context)
        request = ReviewRequest.model_validate(payload)
        if not request.confirmed or not request.hardware_isolated:
            raise ValueError('Explicit observation and physical isolation are required')
        if not self.j.submission_lock.acquire(blocking=False):
            raise ValueError('Submission is still in progress')
        try:
            row = self.j.get(request.request_id)
            with self.j.transaction() as c:
                point = SensorPoint.model_validate_json(c.execute('SELECT configuration_json FROM access_points WHERE point_id=?', (row['point_id'],)).fetchone()[0])
            # Read-only even on an idempotent replay; never use submit to discover.
            evidence = self.s.application.platform.command_lookup(request_id=request.request_id, binding_id=point.binding_id)
            if not isinstance(evidence, dict) or evidence.get('status') not in {'found', 'not_found'}:
                raise ValueError('Platform recovery is unavailable')
            if evidence['status'] == 'found':
                expiry = self.j._command(evidence['command'], row)
                if self.s._parse_time(expiry) > self.s.application.clock.now():
                    raise ValueError('Physical authority has not expired')
            def mutation(c):
                current = self.j._row(c, request.request_id)
                if dict(current) != row or current['state'] != request.expected_state:
                    raise ValueError('Access request changed; refresh before review')
                if self.s._parse_time(row['expires_at']) > self.s.application.clock.now():
                    raise ValueError('Wait for the original deadline')
                visit = c.execute('SELECT state FROM visits WHERE visit_id=?', (row['visit_id'],)).fetchone()
                stay = self.s._stay(c, row['visit_id'])
                if visit['state'] != 'active':
                    raise ValueError('Review requires an active visit')
                if request.observed_inside:
                    account = self.s._commerce.row(c, row['visit_id'])
                    if not account['admitted'] or account['binding_state'] != 'allocated':
                        raise ValueError('Resolve commercial admission before recording presence')
                if (stay['inside_since'] is not None) != request.observed_inside:
                    # Explicit operator observation, not forged sensor evidence.
                    ChildCenterService._transition_stay(self.s, c, row['visit_id'], self.s._now(),
                        request.observed_inside, context, None, {'source': 'administrator_observation'})
                c.execute("UPDATE access_intents SET state='resolved',error_code='physical_observation_reviewed' WHERE request_id=?", (request.request_id,))
                self.s._audit(c, event_type='access.observation_reviewed', entity_type='visit',
                    entity_id=row['visit_id'], context=context,
                    metadata={'request_id': request.request_id, 'observed_inside': request.observed_inside,
                              'hardware_isolated': True, 'no_retrospective_time_correction': True})
                return {'request_id': request.request_id, 'state': 'resolved'}
            return self.s._idempotent('reconcile_access', request.model_dump(), context, mutation)
        finally:
            self.j.submission_lock.release()
