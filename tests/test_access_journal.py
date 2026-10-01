"""Real extension SQLite and broker-shaped mock; no network or hardware."""
from copy import deepcopy
from datetime import UTC, datetime, timedelta
import sqlite3

import pytest
from three_mm_application_sdk import ApplicationMigration, ApplicationStorage
from child_center_application.access_points import AccessJournal
from child_center_application.migrations import get_migrations


VISIT = 'visit_' + '1' * 32
REQUEST = 'access_' + '2' * 32
COMMAND = 'cmd_' + '3' * 32
EVENT = 'evt_' + '4' * 32
DEVICE = 'dev_' + '5' * 32
SENSOR = 'dev_' + '6' * 32
GENERATION = '7' * 32


class Clock:
    value = datetime(2026, 1, 1, tzinfo=UTC)

    def now(self):
        return self.value


class Platform:
    def __init__(self):
        self.calls = []
        self.result = dict(command_id=COMMAND, generation=GENERATION,
                           status='succeeded', claimed=True, passage_event_id=EVENT,
                           expires_at=(Clock.value + timedelta(seconds=10)).isoformat())
        self.failure = None

    def submit_command(self, binding_id, **kwargs):
        self.calls.append((binding_id, kwargs))
        if self.failure:
            raise self.failure
        return self.result.copy()

    def command_status(self, command_id):
        assert command_id == COMMAND
        return self.result.copy()


@pytest.fixture
def setup(tmp_path):
    storage = ApplicationStorage(tmp_path)
    storage.migrate(get_migrations(), '0016')
    with storage.transaction() as c:
        c.execute("INSERT INTO registrations(registration_id,kiosk_terminal_id,submission_idempotency_key,status,consent_version,submitted_at,created_at,updated_at) VALUES ('r','k','i','approved','v1','t','t','t')")
        c.execute("INSERT INTO children(child_id,registration_id,display_name,allowed_consumption_codes_json,status,created_at,updated_at) VALUES ('c','r','Synthetic','[]','active','t','t')")
        c.execute("INSERT INTO visits(visit_id,child_id,state,entered_at,display_timezone,created_at,updated_at) VALUES (?,'c','active','t','UTC','t','t')", (VISIT,))
        c.execute("INSERT INTO stay_sessions VALUES (?,NULL,0,?)", (VISIT, Clock.value.isoformat()))
    clock, platform = Clock(), Platform()
    journal = AccessJournal(storage, platform, clock)
    point = dict(point_id='entrance', reader_device=DEVICE, reader_id='reader.synthetic',
                 binding_id='passage_output', sensor_device=SENSOR, sensor_id='sensor.synthetic',
                 entry_direction='forward')
    journal.register_point(point)
    request = dict(request_id=REQUEST, point_id='entrance', visit_id=VISIT,
                   direction='entry', reader_device=DEVICE, reader_id='reader.synthetic')
    return journal, request, point


def event(journal):
    return dict(event_id=EVENT, device_id=SENSOR, occurred_at=journal.clock.now().isoformat(),
                payload=dict(direction='forward', command_id=COMMAND, generation=GENERATION,
                             sensor_id='sensor.synthetic', binding_id='passage_output', device_health='ok'))


def transition(c, visit_id, direction, occurred_at, event_id):
    # The production stay adapter will supply the actual interval/audit mutation.
    c.execute('UPDATE stay_sessions SET inside_since=? WHERE visit_id=?',
              (occurred_at.isoformat() if direction == 'entry' else None, visit_id))


def test_prepare_does_not_start_time_and_confirm_is_atomic_replay_safe(setup):
    journal, request, point = setup
    journal.register_point(point)  # exact immutable configuration replay
    assert journal.prepare(request, admission_ready=True)['state'] == 'prepared'
    assert journal.prepare(request, admission_ready=True)['state'] == 'prepared'
    assert journal.dispatch(REQUEST)['state'] == 'submitted'
    assert journal.dispatch(REQUEST)['state'] == 'submitted'
    assert len(journal.platform.calls) == 1
    with journal.storage.transaction() as c:
        assert c.execute('SELECT inside_since FROM stay_sessions').fetchone()[0] is None
    journal.clock.value += timedelta(seconds=1)
    evidence = event(journal)
    assert journal.confirm(evidence, transition)
    assert not journal.confirm(evidence, lambda *args: pytest.fail('Replayed passage'))
    with journal.storage.transaction() as c:
        assert c.execute('SELECT inside_since FROM stay_sessions').fetchone()[0] == journal.clock.value.isoformat()
    conflict = deepcopy(evidence)
    conflict['payload']['direction'] = 'reverse'
    with pytest.raises(ValueError, match='identity conflict'):
        journal.confirm(conflict, transition)


@pytest.mark.parametrize('failure', [TimeoutError(), KeyboardInterrupt()])
def test_submission_attempt_survives_restart_without_retry(setup, failure):
    journal, request, _ = setup
    journal.prepare(request, admission_ready=True)
    journal.platform.failure = failure
    if isinstance(failure, KeyboardInterrupt):
        with pytest.raises(KeyboardInterrupt):
            journal.dispatch(REQUEST)
    else:
        journal.dispatch(REQUEST)
    restarted = AccessJournal(journal.storage, journal.platform, journal.clock)
    assert restarted.dispatch(REQUEST)['state'] == 'review'
    assert len(journal.platform.calls) == 1
    with pytest.raises(sqlite3.IntegrityError):
        restarted.prepare({**request, 'request_id': 'access_' + 'a' * 32}, admission_ready=True)


@pytest.mark.parametrize('dispatched', [False, True])
def test_invalidation_prevents_old_intents_and_passages(setup, dispatched):
    journal, request, _ = setup
    journal.prepare(request, admission_ready=True)
    if dispatched:
        journal.dispatch(REQUEST)
    journal.invalidate()
    assert journal.dispatch(REQUEST)['state'] == 'invalidated'
    assert len(journal.platform.calls) == int(dispatched)
    with pytest.raises(ValueError):
        journal.confirm(event(journal), transition)
    with pytest.raises(sqlite3.IntegrityError):
        journal.prepare({**request, 'request_id': 'access_' + 'a' * 32}, admission_ready=True)


def test_expired_prepared_intent_never_submits(setup):
    journal, request, _ = setup
    journal.prepare(request, admission_ready=True)
    journal.clock.value += timedelta(seconds=10)
    assert journal.dispatch(REQUEST)['state'] == 'review'
    assert not journal.platform.calls


@pytest.mark.parametrize('dispatched', [False, True])
def test_operator_finishing_visit_prevents_later_admission(setup, dispatched):
    journal, request, _ = setup
    journal.prepare(request, admission_ready=True)
    if dispatched:
        journal.dispatch(REQUEST)
    with journal.storage.transaction() as c:
        c.execute("UPDATE visits SET state='closed' WHERE visit_id=?", (VISIT,))
    if dispatched:
        with pytest.raises(ValueError, match='Visit changed'):
            journal.confirm(event(journal), transition)
    else:
        assert journal.dispatch(REQUEST)['error_code'] == 'visit_changed_before_submit'
        assert not journal.platform.calls


@pytest.mark.parametrize('change', [
    {'direction': 'invalid'}, {'reader_device': SENSOR}, {'reader_id': 'other'},
    {'extra': 'forbidden'}, {'visit_id': 'visit_' + 'f' * 32},
])
def test_invalid_or_wrong_source_request_denied(setup, change):
    journal, request, _ = setup
    with pytest.raises(ValueError):
        journal.prepare({**request, **change}, admission_ready=True)
    assert not journal.platform.calls


def test_readiness_identity_and_configuration_are_strict(setup):
    journal, request, point = setup
    for ready in (False, None, 1, 'true'):
        with pytest.raises(ValueError):
            journal.prepare(request, admission_ready=ready)
    journal.prepare(request, admission_ready=True)
    with pytest.raises(ValueError, match='identity conflict'):
        journal.prepare({**request, 'direction': 'exit'}, admission_ready=True)
    with pytest.raises(ValueError, match='configuration conflict'):
        journal.register_point({**point, 'sensor_device': DEVICE})


@pytest.mark.parametrize('change', ['sensor', 'direction', 'binding', 'generation', 'health', 'expired', 'unclaimed', 'unaccepted', 'invalidated'])
def test_invalid_passage_never_changes_visit(setup, change):
    journal, request, _ = setup
    journal.prepare(request, admission_ready=True)
    journal.dispatch(REQUEST)
    evidence = event(journal)
    if change == 'sensor':
        evidence['device_id'] = DEVICE
    elif change == 'direction':
        evidence['payload']['direction'] = 'reverse'
    elif change == 'binding':
        evidence['payload']['binding_id'] = 'other'
    elif change == 'generation':
        evidence['payload']['generation'] = 'a' * 32
    elif change == 'health':
        evidence['payload']['device_health'] = 'degraded'
    elif change == 'expired':
        journal.clock.value += timedelta(seconds=10)
    elif change == 'unclaimed':
        journal.platform.result['claimed'] = False
    elif change == 'unaccepted':
        journal.platform.result['passage_event_id'] = None
    else:
        journal.platform.result['status'] = 'invalidated'
    with pytest.raises(ValueError):
        journal.confirm(evidence, lambda *args: pytest.fail('Invalid passage applied'))


def test_failed_business_transition_rolls_back_receipt_and_changes(setup):
    journal, request, _ = setup
    journal.prepare(request, admission_ready=True)
    journal.dispatch(REQUEST)
    def fail(c, *args):
        transition(c, *args)
        raise RuntimeError('Synthetic transaction failure')
    with pytest.raises(RuntimeError):
        journal.confirm(event(journal), fail)
    with journal.storage.transaction() as c:
        assert c.execute('SELECT inside_since FROM stay_sessions').fetchone()[0] is None
        assert c.execute('SELECT COUNT(*) FROM access_passages').fetchone()[0] == 0
    assert journal.get(REQUEST)['state'] == 'submitted'
    assert journal.confirm(event(journal), transition)


def test_exit_direction_is_mapped_and_not_blocked_by_commercial_readiness(setup):
    journal, request, _ = setup
    with journal.storage.transaction() as c:
        c.execute('UPDATE stay_sessions SET inside_since=?', (journal.clock.now().isoformat(),))
    journal.prepare({**request, 'direction': 'exit'}, admission_ready=False)
    journal.dispatch(REQUEST)
    assert journal.platform.calls[0][1]['direction'] == 'reverse'
    evidence = event(journal)
    evidence['payload']['direction'] = 'reverse'
    assert journal.confirm(evidence, transition)


def test_additive_migration_is_repeatable_and_preserves_existing_data(tmp_path):
    storage = ApplicationStorage(tmp_path)
    storage.migrate(get_migrations(), '0015')
    with storage.transaction() as c:
        before = [tuple(r) for r in c.execute('SELECT * FROM reader_configurations')]
    storage.migrate(get_migrations(), '0016')
    storage.migrate(get_migrations(), '0016')
    with storage.transaction() as c:
        assert [tuple(r) for r in c.execute('SELECT * FROM reader_configurations')] == before
        assert c.execute('PRAGMA foreign_key_check').fetchall() == []
        assert c.execute('SELECT COUNT(*) FROM access_intents').fetchone()[0] == 0
    with pytest.raises(ValueError, match='forward-compatible'):
        storage.migrate(get_migrations(), '0015')


def test_migration_failure_rolls_back_new_tables(tmp_path):
    storage = ApplicationStorage(tmp_path)
    migrations = get_migrations()
    storage.migrate(migrations, '0015')
    def fail(c):
        migrations[-1].apply(c)
        raise RuntimeError('Synthetic migration failure')
    with pytest.raises(RuntimeError):
        storage.migrate([*migrations[:-1], ApplicationMigration('0016', fail)], '0016')
    with storage.transaction() as c:
        assert c.execute("SELECT name FROM sqlite_master WHERE name LIKE 'access_%'").fetchall() == []
    assert storage.status()['revision'] == '0015'
