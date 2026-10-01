"""All commercial calls are synthetic; no real account or payment is created."""
from dataclasses import replace
from datetime import timedelta
from decimal import Decimal
import json

import pytest
from three_mm_application_sdk import ApplicationMigration, ApplicationStorage
from backend.services.application_extensions import validate_operation_payload, ApplicationGatewayError
from child_center_application.billing_units import create_service, get_migrations
from test_operator_accounts import setup as previous_setup, start, tick
from test_cc4_barsy_pool import _context
from test_live_barsy import response
from test_package import _builder_module


def invoke(service, operation, payload, audience='operator', key=None):
    contract = json.loads(_builder_module().package_files()['application-extension.json'])
    op = next(o for o in contract['operations'] if o['operation_id'] == operation)
    validate_operation_payload(payload, op['input_schema'])
    result = service.handle(operation, payload, _context(audience, key))
    validate_operation_payload(result, op['output_schema'])
    return result


@pytest.fixture
def setup(tmp_path):
    storage, old, clock, remote, children = previous_setup(tmp_path)
    storage.migrate(get_migrations(), '0019')
    return storage, create_service(replace(old.application, version='0.7.0')), clock, remote, children


def configure(s, unit, key='units'):
    return invoke(s, 'set_timing_profile', {'mode': 'local_quantity', 'article_id': 26, 'billing_unit': unit}, 'administrator', key)


@pytest.mark.parametrize('unit,precision,seconds,expected', [
    ('minutes', 0, 303, '6'), ('minutes', 3, 303, '6.000'),
    ('hours', 3, 303, '0.100'), ('hours', 3, 60, '0.017'),
    ('minutes', 0, 60, '1'), ('minutes', 0, 61, '2'),
    ('minutes', 0, 0, '0'),
])
def test_fixed_quantity_sent_once_and_snapshot_survives_restart(setup, unit, precision, seconds, expected):
    storage, s, clock, remote, children = setup
    original = remote.connector_request
    def connector(*a, **kw):
        if kw['path'].endswith('Amounttypes_getlist'):
            return response([{'amount_type_id': 4, 'time_interval': None, 'value_precision': precision}])
        return original(*a, **kw)
    remote.connector_request = connector
    assert configure(s, unit) == configure(s, unit)
    visit = start(s, clock, children[0]); tick(s)
    clock.current += timedelta(seconds=seconds)
    payload = {'visit_id': visit, 'occurred_at': clock.now().isoformat()}
    result = invoke(s, 'close_visit', payload, key='finish')
    assert invoke(s, 'close_visit', payload, key='finish') == result
    with storage.transaction() as c:
        bill = dict(c.execute('SELECT * FROM stay_bills WHERE visit_id=?', (visit,)).fetchone())
    assert bill['quantity'] == expected
    assert bill['billing_unit'] == unit
    assert bill['quantity_precision'] == precision
    tick(create_service(s.application))
    writes = [body for method, body in remote.posts if method == 'Accounts_place']
    assert len(writes) == (1 if seconds else 0)
    if seconds:
        assert Decimal(str(writes[0]['orders'][0]['amount'])) == Decimal(expected)
        detail = invoke(s, 'get_operator_account', {'visit_id': visit})
        assert detail['commands'][0]['billing_unit'] == unit
        contract = json.loads(_builder_module().package_files()['application-extension.json'])
        op = next(o for o in contract['operations'] if o['operation_id'] == 'get_operator_account')
        validate_operation_payload(detail, op['output_schema'])
    count = len(remote.posts); tick(create_service(s.application))
    assert len(remote.posts) == count


def test_unit_change_locked_during_visit_and_unsettled_account(setup):
    _, s, clock, _, children = setup
    visit = start(s, clock, children[0])
    assert configure(s, 'minutes')['error_code'] == 'settings_locked'
    tick(s); clock.current += timedelta(seconds=303)
    invoke(s, 'close_visit', {'visit_id': visit, 'occurred_at': clock.now().isoformat()}, key='finish')
    tick(s)
    assert configure(s, 'minutes', 'after-finish')['error_code'] == 'settings_locked'


def test_timer_and_invalid_precision_are_rejected_atomically(setup):
    _, s, _, remote, _ = setup
    original = remote.connector_request
    timer, precision = 60, 0
    def connector(*a, **kw):
        if kw['path'].endswith('Amounttypes_getlist'):
            return response([{'amount_type_id': 4, 'time_interval': timer, 'value_precision': precision}])
        return original(*a, **kw)
    remote.connector_request = connector
    assert configure(s, 'minutes')['error_code'] == 'unit_mismatch'
    timer = None
    assert configure(s, 'hours', 'precision')['error_code'] == 'precision_incompatible'
    assert invoke(s, 'get_timing_configuration', {}, 'administrator')['local_quantity']['billing_unit'] == 'hours'
    assert configure(s, 'minutes', 'corrected')['status'] == 'updated'


def test_strict_contract_permissions_and_idempotency(setup):
    _, s, _, _, _ = setup
    contract = json.loads(_builder_module().package_files()['application-extension.json'])
    operations = {o['operation_id']: o for o in contract['operations']}
    op = operations['set_timing_profile']
    assert op['audiences'] == ['administrator'] and op['idempotency'] == 'required'
    for unit in ['minutes', 'hours']:
        validate_operation_payload({'mode': 'local_quantity', 'article_id': 26, 'billing_unit': unit}, op['input_schema'])
    with pytest.raises(ApplicationGatewayError):
        validate_operation_payload({'mode': 'local_quantity', 'article_id': 26, 'billing_unit': 'seconds'}, op['input_schema'])
    for audience in ['operator', 'kiosk', 'internal']:
        with pytest.raises(ValueError, match='audience'):
            invoke(s, 'set_timing_profile', {'mode': 'local_quantity', 'article_id': 26, 'billing_unit': 'minutes'}, audience, 'denied')
    configure(s, 'minutes')
    with pytest.raises(ValueError, match='reused'):
        configure(s, 'hours')
    for name, payload in [('get_timing_configuration', {}), ('get_stay_billing', {'offset': 0}), ('list_stay_bills', {'offset': 0})]:
        result = invoke(s, name, payload, 'administrator')
        validate_operation_payload(result, operations[name]['output_schema'])


def test_upgrade_preserves_old_amounts_and_atomic_migration(tmp_path):
    storage, old, clock, remote, children = previous_setup(tmp_path)
    visit = start(old, clock, children[0]); tick(old)
    clock.current += timedelta(seconds=303)
    invoke(old, 'close_visit', {'visit_id': visit, 'occurred_at': clock.now().isoformat()}, key='finish')
    migrations = get_migrations()
    storage.migrate(migrations, '0018')
    with storage.transaction() as c:
        old_bill = dict(c.execute('SELECT * FROM stay_bills').fetchone())
        old_command = dict(c.execute("SELECT * FROM account_commands WHERE kind='time'").fetchone())
    def fail(c):
        migrations[-1].apply(c)
        raise RuntimeError('synthetic interruption')
    with pytest.raises(RuntimeError):
        storage.migrate([*migrations[:-1], ApplicationMigration('0019', fail)], '0019')
    with storage.transaction() as c:
        assert dict(c.execute('SELECT * FROM stay_bills').fetchone()) == old_bill
    storage.migrate(migrations, '0019'); storage.migrate(migrations, '0019')
    with storage.transaction() as c:
        assert dict(c.execute('SELECT * FROM stay_bills').fetchone()) == {**old_bill, 'billing_unit': 'hours'}
        assert dict(c.execute("SELECT * FROM account_commands WHERE kind='time'").fetchone()) == old_command
        assert not c.execute('PRAGMA foreign_key_check').fetchall()


def test_activation_and_legacy_article_selector_preserve_minutes(setup):
    _, s, _, _, _ = setup
    configure(s, 'minutes')
    assert invoke(s, 'activate_timing_mode', {'mode': 'local_quantity'}, 'administrator', 'activate')['status'] == 'updated'
    assert invoke(s, 'set_stay_article', {'article_id': 27}, 'administrator', 'legacy-selector')['status'] == 'updated'
    profile = invoke(s, 'get_timing_configuration', {}, 'administrator')['local_quantity']
    assert profile['billing_unit'] == 'minutes' and profile['article_id'] == 27
    with pytest.raises(ValueError, match='unavailable'):
        invoke(s, 'activate_timing_mode', {'mode': 'barsy_timer'}, 'administrator', 'timer')


def test_old_unsent_bill_retry_remains_hours(tmp_path):
    from test_stays import setup as legacy_setup, scan
    storage, old, clock, remote, _ = legacy_setup(tmp_path)
    visit = scan(old, clock, 1, '2026-08-30T21:00:00+00:00')['visit_id']
    old.handle('close_visit', {'visit_id': visit, 'occurred_at': '2026-08-30T21:05:03+00:00'}, _context('operator', 'finish'))
    with storage.transaction() as c:
        c.execute("UPDATE stay_bills SET state='retryable'")
        bill_id = c.execute('SELECT bill_id FROM stay_bills').fetchone()[0]
    storage.migrate(get_migrations(), '0019')
    s = create_service(replace(old.application, version='0.7.0'))
    payload = {'bill_id': bill_id}
    assert invoke(s, 'retry_stay_bill', payload, key='retry') == invoke(s, 'retry_stay_bill', payload, key='retry')
    tick(s)
    bill = invoke(s, 'list_stay_bills', {'offset': 0})['items'][0]
    assert bill['billing_unit'] == 'hours' and bill['quantity'] == '0.100' and bill['state'] == 'confirmed'
    assert len(remote.posts) == 1


def test_minutes_unknown_delivery_is_not_resent(setup):
    _, s, clock, remote, children = setup
    configure(s, 'minutes')
    visit = start(s, clock, children[0]); tick(s)
    clock.current += timedelta(seconds=303)
    invoke(s, 'close_visit', {'visit_id': visit, 'occurred_at': clock.now().isoformat()}, key='finish')
    remote.outcome = 'timeout'
    tick(s)
    before = len(remote.posts)
    tick(create_service(s.application))
    assert len(remote.posts) == before
    detail = invoke(s, 'get_operator_account', {'visit_id': visit})
    assert detail['commands'][0]['state'] == 'ambiguous'
    assert detail['commands'][0]['quantity'] == '6.000'
    assert detail['commands'][0]['billing_unit'] == 'minutes'


@pytest.mark.parametrize('scenario', ['pause', 'payment', 'lost_payment', 'lost_consumption', 'crash'])
def test_current_runtime_commercial_regressions(tmp_path, monkeypatch, scenario):
    import test_operator_accounts as scenarios
    original = scenarios.setup
    def upgraded(path):
        storage, old, clock, remote, children = original(path)
        storage.migrate(get_migrations(), '0019')
        return storage, create_service(replace(old.application, version='0.7.0')), clock, remote, children
    monkeypatch.setattr(scenarios, 'setup', upgraded)
    if scenario == 'pause':
        scenarios.test_pause_and_reentry_keep_one_account_and_round_total_once(tmp_path)
    elif scenario == 'payment':
        scenarios.test_first_entry_capacity_pause_consumption_finish_and_payment(tmp_path)
    elif scenario == 'crash':
        scenarios.test_crash_after_payment_and_manual_verification_do_not_repeat_post(tmp_path)
    else:
        scenarios.test_lost_reply_never_replays_or_releases_table(tmp_path, scenario.removeprefix('lost_'))
