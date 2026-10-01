"""Native temporal units on non-timed places; synthetic financial writes only."""
from datetime import timedelta
import pytest
from test_billing_units import setup, configure, invoke
from test_operator_accounts import start, tick
from test_live_barsy import response
from child_center_application.billing_units import create_service


@pytest.mark.parametrize('unit,interval,precision,amount', [('minutes', 1, 0, 6), ('minutes', 1, 3, 6), ('hours', 60, 3, 0.1)])
def test_native_units_deliver_fixed_quantity(setup, unit, interval, precision, amount):
    _, s, clock, remote, children = setup
    original = remote.connector_request
    def connector(*a, **kw):
        if kw['path'].endswith('Amounttypes_getlist'):
            return response([{'amount_type_id': 4, 'time_interval': str(interval), 'value_precision': precision}])
        return original(*a, **kw)
    remote.connector_request = connector
    assert configure(s, unit)['status'] == 'updated'
    visit = start(s, clock, children[0]); tick(s)
    clock.current += timedelta(seconds=303)
    invoke(s, 'close_visit', {'visit_id': visit, 'occurred_at': clock.now().isoformat()}, key='finish')
    tick(s)
    assert remote.posts[-1][1]['orders'] == [{'article_id': 26, 'amount': amount}]
    assert invoke(s, 'get_operator_account', {'visit_id': visit})['commands'][0]['state'] == 'confirmed'
    count = len(remote.posts); tick(create_service(s.application))
    assert len(remote.posts) == count


@pytest.mark.parametrize('flag', [1, '1', None, True, 'invalid'])
def test_timed_or_unverified_place_blocks_before_write(setup, flag):
    _, s, clock, remote, children = setup
    visit = start(s, clock, children[0]); tick(s)
    clock.current += timedelta(seconds=303)
    invoke(s, 'close_visit', {'visit_id': visit, 'occurred_at': clock.now().isoformat()}, key='finish')
    remote.accounts[501]['time_calculation'] = flag
    count = len(remote.posts); tick(s)
    assert len(remote.posts) == count
    assert invoke(s, 'get_operator_account', {'visit_id': visit})['commands'][0]['state'] == 'failed'


def test_row_timer_metadata_does_not_block_fixed_quantity_or_payment(setup):
    _, s, clock, remote, children = setup
    visit = start(s, clock, children[0]); tick(s)
    clock.current += timedelta(seconds=303)
    invoke(s, 'close_visit', {'visit_id': visit, 'occurred_at': clock.now().isoformat()}, key='finish')
    remote.timed = True
    tick(s)
    assert invoke(s, 'get_operator_account', {'visit_id': visit})['commands'][0]['state'] == 'confirmed'
    count = len(remote.posts); tick(create_service(s.application))
    assert len(remote.posts) == count
    quote = invoke(s, 'preview_account_payment', {'visit_id': visit}, key='quote')
    invoke(s, 'pay_account', {'quote_id': quote['quote_id'], 'paymethod_id': 1, 'confirmed': True}, key='pay')
    tick(s)
    assert invoke(s, 'list_operator_accounts', {'offset': 0})['items'] == []
    assert len(remote.posts) == count + 1


def test_changed_native_unit_is_not_silently_converted(setup):
    _, s, clock, remote, children = setup
    assert configure(s, 'minutes')['status'] == 'updated'
    visit = start(s, clock, children[0]); tick(s)
    clock.current += timedelta(seconds=303)
    invoke(s, 'close_visit', {'visit_id': visit, 'occurred_at': clock.now().isoformat()}, key='finish')
    original = remote.connector_request
    def connector(*a, **kw):
        if kw['path'].endswith('Amounttypes_getlist'):
            return response([{'amount_type_id': 4, 'time_interval': 60, 'value_precision': 3}])
        return original(*a, **kw)
    remote.connector_request = connector
    count = len(remote.posts); tick(s)
    assert len(remote.posts) == count
    command = invoke(s, 'get_operator_account', {'visit_id': visit})['commands'][0]
    assert command['state'] == 'failed' and command['quantity'] == '6.000'


def test_timed_place_cannot_admit_even_when_account_has_no_rows(setup):
    _, s, clock, remote, children = setup
    original = remote.connector_request
    def connector(*a, **kw):
        result = original(*a, **kw)
        if kw['path'].endswith('Accounts_create'):
            remote.accounts[501]['time_calculation'] = '1'
        return result
    remote.connector_request = connector
    start(s, clock, children[0]); tick(s)
    item = invoke(s, 'list_operator_accounts', {'offset': 0})['items'][0]
    assert item['admitted'] is False and item['error_code'] == 'barsy_place_timing_enabled'
    assert len(remote.posts) == 1  # Empty account is retained for review, never duplicated.
