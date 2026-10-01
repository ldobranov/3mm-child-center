"""Real stay/commerce/journal code; simulated Barsy and command broker only."""
from datetime import timedelta
import uuid

import pytest
from child_center_application.access_points import AccessJournal
from child_center_application.sensor_admission import SensorAdmission
from child_center_application.migrations import get_migrations
from test_operator_accounts import setup as commercial_setup, tick, start
from test_stays import invoke
from test_cc4_barsy_pool import _context


DEVICE = 'dev_' + '1' * 32
SENSOR = 'dev_' + '2' * 32


class Broker:
    def __init__(self):
        self.commands = {}

    def submit_command(self, binding_id, **payload):
        command = 'cmd_' + uuid.uuid4().hex
        result = dict(command_id=command, generation='3' * 32, status='succeeded',
                      claimed=True, passage_event_id=None, expires_at=payload['not_after'].isoformat())
        self.commands[command] = (result, payload)
        return result.copy()

    def command_status(self, command_id):
        return self.commands[command_id][0].copy()


def setup(tmp_path):
    storage, service, clock, remote, children = commercial_setup(tmp_path)
    storage.migrate(get_migrations(), '0016')
    assignment = invoke(service, 'assign_identifier', dict(child_id=children[0],
        opaque_identifier='SYNTHETIC-SENSOR-ONLY', expected_assignment_id=None), key='attach')['assignment_id']
    broker = Broker()
    journal = AccessJournal(storage, broker, clock)
    journal.register_point(dict(point_id='entrance', reader_device=DEVICE, reader_id='reader.synthetic',
        binding_id='passage_output', sensor_device=SENSOR, sensor_id='sensor.synthetic', entry_direction='forward'))
    workflow = SensorAdmission(service, journal)
    payload = dict(child_id=children[0], assignment_id=assignment, point_id='entrance',
                   reader_device=DEVICE, reader_id='reader.synthetic')
    return workflow, payload, service, clock, remote, children


def reserve(workflow, payload):
    return workflow.reserve(payload, _context('internal', 'reserve'))['visit_id']


def prepare(workflow, visit, direction='entry'):
    return workflow.prepare(dict(request_id='access_' + uuid.uuid4().hex, visit_id=visit,
        point_id='entrance', direction=direction, reader_device=DEVICE,
        reader_id='reader.synthetic'), _context('internal'))


def passage(workflow, intent, clock):
    submitted = workflow.dispatch(intent['request_id'], _context('internal'))
    command = submitted['command_id']
    broker = workflow.journal.platform
    status, request = broker.commands[command]
    event_id = 'evt_' + uuid.uuid4().hex
    status['passage_event_id'] = event_id
    clock.current += timedelta(seconds=1)
    payload = dict(event_id=event_id, device_id=SENSOR, occurred_at=clock.now().isoformat(),
        payload=dict(direction=request['direction'], command_id=command, generation=status['generation'],
        sensor_id='sensor.synthetic', binding_id='passage_output', device_health='ok'))
    assert workflow.confirm(payload, _context('internal'))
    assert not workflow.confirm(payload, _context('internal'))


def test_ready_account_does_not_start_time_then_pause_resume_and_bill_once(tmp_path):
    w, payload, s, clock, remote, _ = setup(tmp_path)
    visit = reserve(w, payload)
    assert reserve(w, payload) == visit
    with pytest.raises(ValueError, match='not ready'):
        prepare(w, visit)
    tick(s)
    clock.current += timedelta(minutes=2)
    with w.journal.storage.transaction() as c:
        assert c.execute('SELECT admitted FROM stay_accounts').fetchone()[0] == 1
        assert c.execute('SELECT inside_since FROM stay_sessions').fetchone()[0] is None
        assert c.execute('SELECT COUNT(*) FROM stay_intervals').fetchone()[0] == 0
    assert len(remote.posts) == 1
    passage(w, prepare(w, visit), clock)
    clock.current += timedelta(seconds=60)
    passage(w, prepare(w, visit, 'exit'), clock)  # 61 seconds inside
    clock.current += timedelta(minutes=5)  # pause is never billed
    passage(w, prepare(w, visit), clock)
    clock.current += timedelta(seconds=29)
    passage(w, prepare(w, visit, 'exit'), clock)  # another 30 seconds
    clock.current += timedelta(seconds=1)
    invoke(s, 'close_visit', dict(visit_id=visit, occurred_at=clock.now().isoformat()), key='finish')
    tick(s)
    with w.journal.storage.transaction() as c:
        assert c.execute('SELECT duration_seconds FROM visits').fetchone()[0] == 91
        assert tuple(c.execute('SELECT rounded_minutes,quantity FROM stay_bills').fetchone()) == (2, '0.033')
        assert c.execute('SELECT COUNT(*) FROM stay_intervals').fetchone()[0] == 2
        assert c.execute('SELECT COUNT(*) FROM access_passages').fetchone()[0] == 4
        assert c.execute('SELECT retired_at FROM identifier_assignments').fetchone()[0] is not None
        assert c.execute('PRAGMA foreign_key_check').fetchall() == []
    assert len(remote.accounts) == 1
    assert [p[0] for p in remote.posts] == ['Accounts_create', 'Accounts_place']
    assert remote.posts[-1][1]['orders'] == [{'article_id': 26, 'amount': 0.033}]


def test_scan_only_visit_still_starts_after_account_ready_on_new_schema(tmp_path):
    w, payload, s, clock, remote, children = setup(tmp_path)
    sensor_visit = reserve(w, payload)
    scan_visit = start(s, clock, children[1])
    tick(s)
    with w.journal.storage.transaction() as c:
        rows = {r[0]: r[1] for r in c.execute('SELECT visit_id,inside_since FROM stay_sessions')}
        assert rows[sensor_visit] is None
        assert rows[scan_visit] is not None


def test_restart_preserves_pending_passage_without_starting_time(tmp_path):
    w, payload, s, clock, remote, _ = setup(tmp_path)
    visit = reserve(w, payload)
    tick(s)
    intent = prepare(w, visit)
    w.dispatch(intent['request_id'], _context('internal'))
    restarted = type(s)(s.application)
    journal = AccessJournal(w.journal.storage, w.journal.platform, clock)
    next_workflow = SensorAdmission(restarted, journal)
    tick(restarted)
    assert next_workflow.dispatch(intent['request_id'], _context('internal'))['state'] == 'submitted'
    assert len(journal.platform.commands) == 1
    with journal.storage.transaction() as c:
        assert c.execute('SELECT inside_since FROM stay_sessions').fetchone()[0] is None
    passage(next_workflow, intent, clock)
    assert len(remote.posts) == 1


@pytest.mark.parametrize('failure', ['busy', 'ambiguous'])
def test_capacity_and_unknown_account_never_grant_entry(tmp_path, failure):
    w, payload, s, clock, remote, _ = setup(tmp_path)
    if failure == 'busy':
        remote.busy_places.update({6, 7})
        with pytest.raises(ValueError, match='free in Barsy'):
            reserve(w, payload)
        assert not remote.posts
    else:
        visit = reserve(w, payload)
        remote.outcome = 'timeout'
        tick(s)
        with pytest.raises(ValueError, match='not ready'):
            prepare(w, visit)
        tick(s)
        assert len(remote.posts) == 1
    assert not w.journal.platform.commands


@pytest.mark.parametrize('change', ['closed', 'moved', 'invalid_orders', 'detached'])
def test_rechecks_readiness_before_dispatch(tmp_path, change):
    w, payload, s, clock, remote, _ = setup(tmp_path)
    visit = reserve(w, payload)
    tick(s)
    intent = prepare(w, visit)
    account = next(iter(remote.accounts.values()))
    if change == 'closed':
        account['status'] = 1
    elif change == 'moved':
        account['place_id'] = 999
    elif change == 'invalid_orders':
        account['orders'] = [None]
    else:
        with w.journal.storage.transaction() as c:
            c.execute('UPDATE identifier_assignments SET retired_at=?', (clock.now().isoformat(),))
    with pytest.raises(ValueError):
        w.dispatch(intent['request_id'], _context('internal'))
    assert not w.journal.platform.commands


def test_unused_grant_does_not_free_account_or_create_time(tmp_path):
    w, payload, s, clock, remote, _ = setup(tmp_path)
    visit = reserve(w, payload)
    tick(s)
    intent = prepare(w, visit)
    w.dispatch(intent['request_id'], _context('internal'))
    clock.current += timedelta(minutes=1)
    tick(s)
    with w.journal.storage.transaction() as c:
        assert c.execute('SELECT inside_since FROM stay_sessions').fetchone()[0] is None
        assert c.execute('SELECT state FROM visit_barsy_bindings').fetchone()[0] == 'allocated'
    assert len(remote.posts) == 1


@pytest.mark.parametrize('audience', ['kiosk', 'operator', 'administrator'])
def test_internal_adapter_rejects_other_audiences(tmp_path, audience):
    w, payload, *_ = setup(tmp_path)
    with pytest.raises(ValueError, match='audience'):
        w.reserve(payload, _context(audience, 'forbidden'))


def test_exit_does_not_require_open_barsy_account(tmp_path):
    w, payload, s, clock, remote, _ = setup(tmp_path)
    visit = reserve(w, payload)
    tick(s)
    passage(w, prepare(w, visit), clock)
    next(iter(remote.accounts.values()))['status'] = 1
    passage(w, prepare(w, visit, 'exit'), clock)
    with w.journal.storage.transaction() as c:
        assert c.execute('SELECT inside_since FROM stay_sessions').fetchone()[0] is None
