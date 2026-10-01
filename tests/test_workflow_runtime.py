from dataclasses import replace
from datetime import timedelta
import json
import uuid

import pytest
from three_mm_application_sdk import ApplicationPlatformError, ApplicationMigration, ApplicationStorage
from child_center_application.workflow_runtime import create_service, get_migrations
from test_access_control import setup as previous_setup, configure
from test_cc4_barsy_pool import _context
from test_operator_accounts import tick, start
from test_package import _builder_module
from backend.services.application_extensions import validate_operation_payload


@pytest.fixture
def setup(previous_setup):
    old, clock, remote, children = previous_setup
    old.application.storage.migrate(get_migrations(), '0018')
    return create_service(replace(old.application, version='0.6.9')), clock, remote, children


def scan(s, clock):
    event = {'event_id': 'evt_' + uuid.uuid4().hex, 'device_id': 'dev_' + '1' * 32,
        'event_type': 'identifier.scan.v1', 'occurred_at': clock.now().isoformat(),
        'payload': {'schema_version': 1, 'capability_id': 'identifier.scan.v1',
            'opaque_identifier': 'SYNTHETIC-SENSOR-ONLY', 'reader_id': 'reader.synthetic',
            'adapter_kind': 'mock', 'sequence': 1, 'device_health': 'ok', 'scan_metadata': {}}}
    return event, s.handle('process_identifier_scan', event, _context('internal', event['event_id']))


@pytest.mark.parametrize('sensor', [False, True])
def test_read_failure_is_visible_terminal_and_never_replayed(setup, sensor):
    s, clock, remote, _ = setup
    if sensor:
        configure(s)
    original = remote.connector_request
    def fail(*a, **kw):
        raise ApplicationPlatformError('Application credential cannot be decrypted')
    remote.connector_request = fail
    clock.current += timedelta(seconds=1)
    event, result = scan(s, clock)
    assert result == {'status': 'ignored', 'visit_id': None}
    rows = s.handle('list_scan_outcomes', {}, _context('operator'))['items']
    assert rows[0]['error_code'] == 'barsy_credentials_unavailable'
    assert rows[0]['child_name'] is not None
    remote.connector_request = original
    assert s.handle('process_identifier_scan', event, _context('internal', event['event_id'])) == result
    with s.application.storage.transaction() as c:
        assert c.execute('SELECT COUNT(*) FROM visits').fetchone()[0] == 0
        assert c.execute('SELECT COUNT(*) FROM scan_failures').fetchone()[0] == 1
        assert 'SYNTHETIC-SENSOR-ONLY' not in json.dumps([dict(r) for r in c.execute('SELECT * FROM scan_failures')])
    changed = {**event, 'device_id': 'dev_' + '9' * 32}
    with pytest.raises(ValueError, match='reused|conflict'):
        s.handle('process_identifier_scan', changed, _context('internal', 'different-attempt'))
    clock.current += timedelta(seconds=1)
    _, fresh = scan(s, clock)
    assert fresh['visit_id'] is not None


def test_unknown_is_not_reported_as_connection_failure(setup):
    s, clock, _, _ = setup
    with s.application.storage.transaction() as c:
        c.execute('UPDATE identifier_assignments SET retired_at=?', (clock.now().isoformat(),))
    _, result = scan(s, clock)
    assert result['status'] == 'unknown_identifier'
    assert s.handle('list_scan_outcomes', {}, _context('operator'))['items'][0]['error_code'] is None


def test_empty_legacy_phases_do_not_delay_current_bill(setup):
    s, clock, remote, children = setup
    visit = start(s, clock, children[0])
    tick(s)
    clock.current += timedelta(seconds=61)
    s.handle('close_visit', {'visit_id': visit, 'occurred_at': clock.now().isoformat()}, _context('operator', 'finish'))
    s._integration_phase = 1  # legacy release and legacy bill both used to waste a tick
    before = len(remote.posts)
    assert s.handle('deliver_barsy_commands', {}, _context('internal', 'deliver')) == {'processed': 1}
    assert len(remote.posts) == before + 1
    with s.application.storage.transaction() as c:
        assert c.execute("SELECT state FROM account_commands WHERE kind='time'").fetchone()[0] == 'confirmed'
    tick(s)
    assert len(remote.posts) == before + 1


def test_scan_query_contract_and_permissions(setup):
    s = setup[0]
    contract = json.loads(_builder_module().package_files()['application-extension.json'])
    op = next(o for o in contract['operations'] if o['operation_id'] == 'list_scan_outcomes')
    assert op['required_permission'] == 'visits_manage'
    validate_operation_payload(s.handle('list_scan_outcomes', {}, _context('operator')), op['output_schema'])
    for audience in ['kiosk', 'internal']:
        with pytest.raises(ValueError):
            s.handle('list_scan_outcomes', {}, _context(audience))
    with pytest.raises(ValueError):
        s.handle('list_scan_outcomes', {'extra': True}, _context('operator'))


def test_migration_0018_atomic_and_repeatable(tmp_path):
    storage = ApplicationStorage(tmp_path)
    migrations = get_migrations()
    storage.migrate(migrations, '0017')
    def fail(c):
        migrations[-1].apply(c)
        raise RuntimeError('synthetic failure')
    with pytest.raises(RuntimeError):
        storage.migrate([*migrations[:-1], ApplicationMigration('0018', fail)], '0018')
    with storage.transaction() as c:
        assert not c.execute("SELECT 1 FROM sqlite_master WHERE name='scan_failures'").fetchone()
    storage.migrate(migrations, '0018')
    storage.migrate(migrations, '0018')
    with storage.transaction() as c:
        assert not c.execute('PRAGMA foreign_key_check').fetchall()


@pytest.mark.parametrize('scenario', ['payment', 'lost_payment', 'lost_consumption', 'crash'])
def test_current_runtime_preserves_commercial_guarantees(tmp_path, monkeypatch, scenario):
    import test_operator_accounts as scenarios
    original = scenarios.setup
    def upgraded(path):
        storage, old, clock, remote, children = original(path)
        storage.migrate(get_migrations(), '0018')
        return storage, create_service(replace(old.application, version='0.6.9')), clock, remote, children
    monkeypatch.setattr(scenarios, 'setup', upgraded)
    if scenario == 'payment':
        scenarios.test_first_entry_capacity_pause_consumption_finish_and_payment(tmp_path)
    elif scenario == 'crash':
        scenarios.test_crash_after_payment_and_manual_verification_do_not_repeat_post(tmp_path)
    else:
        scenarios.test_lost_reply_never_replays_or_releases_table(tmp_path, scenario.removeprefix('lost_'))
