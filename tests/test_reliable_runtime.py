"""Synthetic admission checks only; no live account or physical access calls."""
from dataclasses import replace
from datetime import timedelta
import sqlite3

import pytest
from three_mm_application_sdk import ApplicationMigration, ApplicationPlatformError

from child_center_application.billing_units import create_service as previous_service
from child_center_application.reliable_runtime import create_service, get_migrations
from test_access_control import setup as previous_setup, configure
from test_cc4_barsy_pool import _context
from test_workflow_runtime import scan


@pytest.fixture
def setup(previous_setup):
    old, clock, remote, children = previous_setup
    old.application.storage.migrate(get_migrations(), '0020')
    return create_service(replace(old.application, version='0.7.3')), clock, remote, children


@pytest.mark.parametrize('sensor', [False, True])
@pytest.mark.parametrize('reason', ['no_enabled_tables', 'no_free_tables'])
def test_capacity_denial_is_visible_terminal_and_new_scan_can_enter(setup, sensor, reason):
    service, clock, remote, _ = setup
    if sensor:
        configure(service)
    with service.application.storage.transaction() as connection:
        if reason == 'no_enabled_tables':
            connection.execute('UPDATE barsy_table_slots SET enabled=0')
    if reason == 'no_free_tables':
        remote.busy_places.update((6, 7))
    clock.current += timedelta(seconds=1)
    event, denied = scan(service, clock)
    assert denied == {'status': 'ignored', 'visit_id': None}
    outcome = service.handle('list_scan_outcomes', {}, _context('operator'))['items'][0]
    assert outcome['event_id'] == event['event_id'] and outcome['error_code'] == reason
    assert outcome['child_name'] is not None
    with service.application.storage.transaction() as connection:
        assert connection.execute('SELECT COUNT(*) FROM visits').fetchone()[0] == 0
        connection.execute('UPDATE barsy_table_slots SET enabled=1')
    remote.busy_places.clear()
    restarted = create_service(service.application)
    assert restarted.handle('process_identifier_scan', event, _context('internal', 'retry-after-config')) == denied
    with service.application.storage.transaction() as connection:
        assert connection.execute('SELECT COUNT(*) FROM visits').fetchone()[0] == 0
        assert connection.execute('SELECT COUNT(*) FROM scan_failures').fetchone()[0] == 1
        assert connection.execute('SELECT COUNT(*) FROM barsy_timing_commands').fetchone()[0] == 0
    assert not remote.posts
    clock.current += timedelta(seconds=1)
    _, fresh = scan(restarted, clock)
    assert fresh['visit_id'] is not None
    changed = {**event, 'device_id': 'dev_' + '9' * 32}
    with pytest.raises(ValueError, match='reused|conflict'):
        restarted.handle('process_identifier_scan', changed, _context('internal', 'conflicting-retry'))


def test_only_exact_known_capacity_errors_are_classified(setup):
    service, _, _, _ = setup
    assert service._scan_failure_code(ValueError('No Barsy table is currently available')) == 'no_free_tables'
    assert service._scan_failure_code(ValueError('Barsy capacity could not be checked')) is None
    assert service._scan_failure_code(ValueError('Configure at least one Barsy table before entry extra')) is None
    class ValidationError(ValueError):
        pass
    assert service._scan_failure_code(ValidationError('No Barsy table is currently available')) is None


def test_malformed_scan_and_unexpected_validation_are_not_acknowledged(setup, monkeypatch):
    service, clock, _, _ = setup
    with pytest.raises(ValueError):
        service.handle('process_identifier_scan', {'invalid': True}, _context('internal', 'malformed'))
    def fail(_connection):
        raise ValueError('Synthetic strict capacity response validation')
    monkeypatch.setattr(service._commerce, 'choose_table', fail)
    with pytest.raises(ValueError, match='strict capacity response validation'):
        scan(service, clock)
    with service.application.storage.transaction() as connection:
        assert connection.execute('SELECT COUNT(*) FROM scan_failures').fetchone()[0] == 0
        assert connection.execute('SELECT COUNT(*) FROM identifier_scan_activity').fetchone()[0] == 0
        assert connection.execute('SELECT COUNT(*) FROM visits').fetchone()[0] == 0


def test_0020_migration_is_atomic_repeatable_and_preserves_0019_data(previous_setup):
    old, clock, remote, _ = previous_setup
    storage = old.application.storage
    migrations = get_migrations()
    storage.migrate(migrations, '0019')
    old = previous_service(replace(old.application, version='0.7.0'))
    def fail_read(*args, **kwargs):
        raise ApplicationPlatformError('Application credential cannot be decrypted')
    remote.connector_request = fail_read
    event, denied = scan(old, clock)
    assert denied['status'] == 'ignored'
    def snapshot():
        with storage.transaction() as connection:
            return {name: [dict(row) for row in connection.execute('SELECT * FROM ' + name)]
                    for name in ('scan_failures', 'identifier_event_results', 'identifier_scan_activity',
                                 'children', 'guardians', 'stay_billing_settings', 'billing_unit_settings')}
    before = snapshot()
    def fail_migration(connection):
        migrations[-1].apply(connection)
        raise RuntimeError('Synthetic interrupted migration')
    with pytest.raises(RuntimeError, match='interrupted'):
        storage.migrate([*migrations[:-1], ApplicationMigration('0020', fail_migration)], '0020')
    assert storage.status()['revision'] == '0019'
    assert snapshot() == before
    storage.migrate(migrations, '0020')
    storage.migrate(migrations, '0020')
    assert snapshot() == before
    with storage.transaction() as connection:
        assert not connection.execute('PRAGMA foreign_key_check').fetchall()
        assert not connection.execute("SELECT 1 FROM sqlite_master WHERE name='scan_failures_new'").fetchone()
        with pytest.raises(sqlite3.IntegrityError):
            connection.execute('UPDATE scan_failures SET error_code=? WHERE event_id=?', ('arbitrary_message', event['event_id']))
        for code in ('no_enabled_tables', 'no_free_tables'):
            connection.execute('UPDATE scan_failures SET error_code=? WHERE event_id=?', (code, event['event_id']))
    latest = create_service(replace(old.application, version='0.7.3'))
    assert latest.handle('health', {}, _context('internal')) == {
        'status': 'ready', 'schema_revision': '0020', 'service_version': '0.7.3'}
    for audience in ('operator', 'administrator', 'kiosk'):
        with pytest.raises(ValueError):
            latest.handle('health', {}, _context(audience))
    with pytest.raises(ValueError):
        latest.handle('health', {'invalid': True}, _context('internal'))
