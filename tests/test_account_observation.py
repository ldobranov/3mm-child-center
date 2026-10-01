"""Synthetic external closure is observation, never payment/delivery confirmation."""
from dataclasses import replace
from datetime import timedelta
import json

import pytest
from three_mm_application_sdk import ApplicationMigration, ApplicationPlatformError
from backend.services.application_extensions import validate_operation_payload
from child_center_application.reliable_runtime import create_service, get_migrations
from test_operator_accounts import setup as previous_setup, start, tick
from test_cc4_barsy_pool import _context
from test_package import _builder_module


@pytest.fixture
def setup(tmp_path):
    storage, old, clock, remote, children = previous_setup(tmp_path)
    storage.migrate(get_migrations(), '0020')
    return storage, create_service(replace(old.application, version='0.7.1')), clock, remote, children


def accounts(service, operation='list_operator_accounts'):
    return service.handle(operation, {'offset': 0}, _context('operator'))


def financial_state(storage):
    with storage.transaction() as c:
        return {name: [dict(row) for row in c.execute('SELECT * FROM ' + name)]
                for name in ['account_commands', 'stay_bills', 'stay_accounts', 'visits',
                             'stay_sessions', 'stay_intervals', 'visit_barsy_bindings']}


def test_background_observes_manual_closure_without_claiming_missing_time(setup):
    storage, service, clock, remote, children = setup
    visit = start(service, clock, children[0]); tick(service)
    assert accounts(service)['items'][0]['remote_observation']['status'] == 'open'
    clock.current += timedelta(minutes=93)
    service.handle('close_visit', {'visit_id': visit, 'occurred_at': clock.now().isoformat()}, _context('operator', 'finish'))
    remote.outcome = 'timeout'; tick(service)
    remote.accounts[501].update(status=1, orders=[], total_real=0, total_paid=0, total_remain=0, fx=None)
    before = financial_state(storage); writes = len(remote.posts)
    clock.current += timedelta(seconds=15); tick(service)
    observed = accounts(service)['items'][0]['remote_observation']
    assert observed == {'status': 'closed', 'checked_at': service._now(), 'error_code': 'closed_external_review'}
    assert financial_state(storage) == before
    assert before['stay_bills'][0]['rounded_minutes'] == 93
    assert before['stay_bills'][0]['state'] == before['account_commands'][0]['state'] == 'ambiguous'
    assert before['visit_barsy_bindings'][0]['state'] == 'allocated'
    restarted = create_service(service.application); tick(restarted)
    assert accounts(restarted)['items'][0]['remote_observation'] == observed
    assert len(remote.posts) == writes


def test_external_closure_never_stops_an_active_local_stay(setup):
    storage, service, clock, remote, children = setup
    start(service, clock, children[0]); tick(service)
    before = financial_state(storage); writes = len(remote.posts)
    # Timer metadata is irrelevant to observation, but still rejects live writes.
    remote.accounts[501].update(status=1, time_calculation=1)
    clock.current += timedelta(seconds=15); tick(service)
    assert accounts(service)['items'][0]['remote_observation']['status'] == 'closed'
    assert financial_state(storage) == before
    assert len(remote.posts) == writes


def test_paid_fiscal_closure_does_not_confirm_an_ambiguous_payment(setup):
    storage, service, clock, remote, children = setup
    visit = start(service, clock, children[0]); tick(service)
    clock.current += timedelta(seconds=61)
    service.handle('close_visit', {'visit_id': visit, 'occurred_at': clock.now().isoformat()}, _context('operator', 'finish'))
    tick(service)
    quote = service.handle('preview_account_payment', {'visit_id': visit}, _context('operator', 'quote'))
    service.handle('pay_account', {'quote_id': quote['quote_id'], 'paymethod_id': 1, 'confirmed': True}, _context('operator', 'payment'))
    remote.outcome = 'timeout'; tick(service)
    assert remote.accounts[501]['status'] == remote.accounts[501]['fx'] == 1
    before = financial_state(storage); writes = len(remote.posts)
    assert before['account_commands'][-1]['kind'] == 'payment'
    assert before['account_commands'][-1]['state'] == 'ambiguous'
    clock.current += timedelta(seconds=15); tick(create_service(service.application))
    assert accounts(service)['items'][0]['remote_observation']['status'] == 'closed'
    assert financial_state(storage) == before
    assert len(remote.posts) == writes


@pytest.mark.parametrize('change', [
    {'account_id': 999}, {'place_id': 999}, {'account_alias': 'synthetic-unrelated'},
    {'status': True}, {'status': None}, {'status': 'invalid'},
])
def test_invalid_identity_or_status_clears_stale_observation(setup, change):
    storage, service, clock, remote, children = setup
    start(service, clock, children[0]); tick(service)
    remote.accounts[501].update(status=1)
    clock.current += timedelta(seconds=15); tick(service)
    assert accounts(service)['items'][0]['remote_observation']['status'] == 'closed'
    before = financial_state(storage); writes = len(remote.posts)
    remote.accounts[501].update(change)
    clock.current += timedelta(seconds=15); tick(service)
    observed = accounts(service)['items'][0]['remote_observation']
    assert observed == {'status': 'unknown', 'checked_at': service._now(), 'error_code': 'barsy_unavailable'}
    assert financial_state(storage) == before
    assert len(remote.posts) == writes


def test_failed_read_cannot_starve_the_next_account_or_leak_remote_text(setup):
    storage, service, clock, remote, children = setup
    visits = []
    for child in children:
        visits.append(start(service, clock, child))
        tick(service)  # Establish deterministic account IDs before the next start.
    original = remote.connector_request
    reads = []
    def connector(*args, **kwargs):
        if kwargs['path'].endswith('Accounts_get'):
            identity = json.loads(kwargs['body'])['account_id']; reads.append(identity)
            if identity == 501:
                raise ApplicationPlatformError('synthetic-secret-must-not-be-persisted')
        return original(*args, **kwargs)
    remote.connector_request = connector
    remote.accounts[502]['status'] = 1
    clock.current += timedelta(seconds=15); tick(service)
    items = {item['visit_id']: item['remote_observation'] for item in accounts(service)['items']}
    assert items[visits[0]]['status'] == 'unknown'
    assert items[visits[1]]['status'] == 'closed'
    assert reads == [501, 502]
    with storage.transaction() as c:
        assert 'synthetic-secret' not in json.dumps([dict(r) for r in c.execute('SELECT * FROM account_observations')])
    clock.current += timedelta(seconds=14); tick(service)
    assert reads == [501, 502]


def test_cached_operator_and_cashier_query_remain_read_only_and_strict(setup):
    _, service, clock, remote, children = setup
    start(service, clock, children[0]); tick(service)
    def forbidden(*args, **kwargs):
        raise AssertionError('A UI query must not access Barsy')
    remote.connector_request = forbidden
    contract = json.loads(_builder_module().package_files()['application-extension.json'])
    operations = {op['operation_id']: op for op in contract['operations']}
    for operation in ['list_operator_accounts', 'list_checkout_accounts']:
        validate_operation_payload(accounts(service, operation), operations[operation]['output_schema'])
        for audience in ['kiosk', 'internal']:
            with pytest.raises(ValueError):
                service.handle(operation, {'offset': 0}, _context(audience))


def test_unreleased_migration_adds_observations_atomically_without_touching_stays(tmp_path):
    storage, old, clock, remote, children = previous_setup(tmp_path)
    start(old, clock, children[0]); tick(old)
    migrations = get_migrations(); storage.migrate(migrations, '0019')
    before = financial_state(storage)
    def fail(c):
        migrations[-1].apply(c)
        raise RuntimeError('synthetic interruption')
    with pytest.raises(RuntimeError, match='synthetic interruption'):
        storage.migrate([*migrations[:-1], ApplicationMigration('0020', fail)], '0020')
    with storage.transaction() as c:
        assert not c.execute("SELECT 1 FROM sqlite_master WHERE name='account_observations'").fetchone()
    assert financial_state(storage) == before
    storage.migrate(migrations, '0020'); storage.migrate(migrations, '0020')
    assert financial_state(storage) == before
    service = create_service(replace(old.application, version='0.7.1'))
    assert accounts(service)['items'][0]['remote_observation'] == {'status': 'unknown', 'checked_at': None, 'error_code': None}
    with storage.transaction() as c:
        assert not c.execute('PRAGMA foreign_key_check').fetchall()


def test_observation_cascades_if_its_owning_account_is_deleted(setup):
    storage, service, clock, _, children = setup
    visit = start(service, clock, children[0]); tick(service)
    with storage.transaction() as c:
        assert c.execute('SELECT 1 FROM account_observations WHERE visit_id=?', (visit,)).fetchone()
        c.execute('DELETE FROM stay_accounts WHERE visit_id=?', (visit,))
        assert not c.execute('SELECT 1 FROM account_observations WHERE visit_id=?', (visit,)).fetchone()
        assert not c.execute('PRAGMA foreign_key_check').fetchall()


def test_personal_erasure_preserves_only_technical_observation(setup):
    storage, service, clock, remote, children = setup
    visit = start(service, clock, children[0]); tick(service)
    clock.current += timedelta(seconds=61)
    service.handle('close_visit', {'visit_id': visit, 'occurred_at': clock.now().isoformat()}, _context('operator', 'finish'))
    tick(service)
    quote = service.handle('preview_account_payment', {'visit_id': visit}, _context('operator', 'quote'))
    service.handle('pay_account', {'quote_id': quote['quote_id'], 'paymethod_id': 1, 'confirmed': True}, _context('operator', 'payment'))
    tick(service)
    with storage.transaction() as c:
        observation = dict(c.execute('SELECT * FROM account_observations WHERE visit_id=?', (visit,)).fetchone())
    writes = len(remote.posts)
    result = service.handle('erase_personal_data', {'subject_kind': 'child', 'subject_id': children[0],
        'scope': 'erase_where_permitted', 'reason': 'Synthetic erasure test'}, _context('administrator', 'erase'))
    assert result['status'] == 'erased'
    assert len(remote.posts) == writes
    with storage.transaction() as c:
        assert c.execute('SELECT display_name FROM children WHERE child_id=?', (children[0],)).fetchone()[0] == 'Removed child'
        assert dict(c.execute('SELECT * FROM account_observations WHERE visit_id=?', (visit,)).fetchone()) == observation
        assert set(observation) == {'visit_id', 'status', 'checked_at', 'error_code'}
        assert not c.execute('PRAGMA foreign_key_check').fetchall()
