"""Explicit recovery resolves legacy ambiguity without guessing or reposting."""
from datetime import timedelta

import pytest

from test_account_observation import setup
from test_cc4_barsy_pool import _context
from test_operator_accounts import start, tick
from test_live_barsy import response


def ambiguous_time(service, clock, remote, child):
    visit = start(service, clock, child); tick(service)
    clock.current += timedelta(minutes=3)
    service.handle('close_visit', {'visit_id': visit, 'occurred_at': clock.now().isoformat()},
                   _context('operator', 'finish'))
    remote.outcome = 'timeout'; tick(service); remote.outcome = 'succeeded'
    detail = service.handle('get_operator_account', {'visit_id': visit}, _context('operator'))
    command = next(item for item in detail['commands'] if item['kind'] == 'time')
    assert command['state'] == 'ambiguous'
    return visit, command


def test_missing_open_row_becomes_explicit_manual_retry_without_post(setup):
    storage, service, clock, remote, children = setup
    visit, command = ambiguous_time(service, clock, remote, children[0])
    remote.accounts[501]['orders'] = []
    writes = len(remote.posts)
    result = service.handle('reconcile_account_command', {'command_id': command['command_id']},
                            _context('operator', 'check'))
    assert result == {'status': 'retry_available'}
    assert len(remote.posts) == writes
    with storage.transaction() as c:
        assert c.execute('SELECT state,error_code FROM account_commands WHERE command_id=?',
                         (command['command_id'],)).fetchone()[:] == ('failed', 'operator_verified_absent_in_barsy')
        assert c.execute('SELECT state FROM stay_bills WHERE visit_id=?', (visit,)).fetchone()[0] == 'retryable'
    assert service.handle('retry_account_command', {'command_id': command['command_id']},
                          _context('operator', 'retry'))['state'] == 'prepared'
    assert len(remote.posts) == writes


def test_catalogue_na_price_does_not_prevent_time_delivery(setup):
    storage, service, clock, remote, children = setup
    visit = start(service, clock, children[0]); tick(service)
    clock.current += timedelta(minutes=4)
    service.handle('close_visit', {'visit_id': visit, 'occurred_at': clock.now().isoformat()},
                   _context('operator', 'finish'))
    # Reproduce the persisted 0.7.3 preflight failure: no article POST happened.
    with storage.transaction() as c:
        command = c.execute("SELECT * FROM account_commands WHERE visit_id=? AND kind='time'", (visit,)).fetchone()
        service._commerce.state(c, command, 'failed', 'barsy_article_price_missing')
    writes = len(remote.posts)
    tick(service)
    assert len(remote.posts) == writes  # upgrade/job never requeues it automatically
    service.handle('retry_account_command', {'command_id': command['command_id']},
                   _context('operator', 'retry'))
    original = remote.connector_request
    def no_price(connector_id, **request):
        if request['path'].endswith('Articles_getlist'):
            return response([{'article_id': 26, 'article_name': 'Synthetic time',
                              'amount_type_id': 4, 'article_type': 1, 'current_price': 'n/a'}])
        return original(connector_id, **request)
    remote.connector_request = no_price
    writes = len(remote.posts); tick(service)
    assert len(remote.posts) == writes + 1
    with storage.transaction() as c:
        assert c.execute('SELECT state,error_code FROM account_commands WHERE command_id=?',
                         (command['command_id'],)).fetchone()[:] == ('confirmed', None)
        assert c.execute('SELECT state FROM stay_bills WHERE visit_id=?', (visit,)).fetchone()[0] == 'confirmed'


def test_catalogue_na_price_does_not_prevent_consumption_delivery(setup):
    _, service, clock, remote, children = setup
    visit = start(service, clock, children[0]); tick(service)
    original = remote.connector_request
    def catalogue(connector_id, **request):
        if request['path'].endswith('Articles_getlist'):
            return response([{'article_id': 11, 'article_name': 'Synthetic drink',
                              'amount_type_id': 4, 'article_type': 1, 'current_price': 'n/a'}])
        return original(connector_id, **request)
    remote.connector_request = catalogue
    service.handle('add_account_consumption', {'visit_id': visit, 'article_id': 11,
                   'quantity': '1', 'consumer': 'child'}, _context('operator', 'drink'))
    writes = len(remote.posts); tick(service)
    assert len(remote.posts) == writes + 1
    assert service.handle('get_operator_account', {'visit_id': visit},
                          _context('operator'))['commands'][0]['state'] == 'confirmed'


def test_failed_consumption_blocks_payment_even_after_time_confirmed(setup):
    storage, service, clock, remote, children = setup
    visit = start(service, clock, children[0]); tick(service)
    from test_operator_accounts import finish
    finish(service, clock, visit)
    with storage.transaction() as c:
        command = service._commerce.insert(c, visit, 'consumption', article_id=11,
                                            quantity='1', consumer='child')
        c.execute("UPDATE account_commands SET state='failed' WHERE command_id=?",
                  (command['command_id'],))
    writes = len(remote.posts)
    with pytest.raises(ValueError, match='Confirm all article deliveries'):
        service.handle('preview_account_payment', {'visit_id': visit}, _context('operator', 'quote'))
    assert len(remote.posts) == writes


@pytest.mark.parametrize('row_flag', ['1', None, 'missing'])
def test_present_row_is_confirmed_without_post(setup, row_flag):
    storage, service, clock, remote, children = setup
    visit, command = ambiguous_time(service, clock, remote, children[0])
    for row in remote.accounts[501]['orders']:
        if row_flag == 'missing':
            row.pop('active_time_orders', None)
        else:
            row['active_time_orders'] = row_flag
    with storage.transaction() as c:
        c.execute("UPDATE account_commands SET error_code='barsy_order_timer_active' WHERE command_id=?", (command['command_id'],))
    writes = len(remote.posts)
    service = type(service)(service.application)
    tick(service)
    assert service.handle('get_operator_account', {'visit_id': visit}, _context('operator'))['commands'][0]['state'] == 'ambiguous'
    assert service.handle('reconcile_account_command', {'command_id': command['command_id']},
                          _context('operator', 'check')) == {'status': 'confirmed'}
    assert service.handle('reconcile_account_command', {'command_id': command['command_id']},
                          _context('operator', 'check')) == {'status': 'confirmed'}
    assert len(remote.posts) == writes
    with storage.transaction() as c:
        assert c.execute('SELECT state FROM account_commands WHERE command_id=?', (command['command_id'],)).fetchone()[0] == 'confirmed'
        assert c.execute('SELECT state,remote_account_id FROM stay_bills WHERE visit_id=?', (visit,)).fetchone()[:] == ('confirmed', 501)


def test_closed_missing_row_requires_explicit_administrator_release(setup):
    storage, service, clock, remote, children = setup
    visit, command = ambiguous_time(service, clock, remote, children[0])
    remote.accounts[501].update(status=1, orders=[], total_real=0, total_paid=0, total_remain=0, fx=None)
    writes = len(remote.posts)
    assert service.handle('reconcile_account_command', {'command_id': command['command_id']},
                          _context('operator', 'check')) == {'status': 'closed_incomplete'}
    with pytest.raises(ValueError, match='audience'):
        service.handle('release_incomplete_closed_account',
                       {'visit_id': visit, 'accepted_missing_charges': True}, _context('operator', 'release'))
    result = service.handle('release_incomplete_closed_account',
                            {'visit_id': visit, 'accepted_missing_charges': True},
                            _context('administrator', 'admin-release'))
    assert result == {'status': 'released_incomplete'}
    assert len(remote.posts) == writes
    with storage.transaction() as c:
        assert c.execute('SELECT state FROM visit_barsy_bindings WHERE visit_id=?', (visit,)).fetchone()[0] == 'released'
        assert c.execute('SELECT state FROM account_commands WHERE command_id=?', (command['command_id'],)).fetchone()[0] == 'ambiguous'
        assert c.execute('SELECT state FROM stay_bills WHERE visit_id=?', (visit,)).fetchone()[0] == 'ambiguous'
        assert c.execute('SELECT last_error FROM stay_accounts WHERE visit_id=?', (visit,)).fetchone()[0] == 'administrator_released_incomplete_account'
        assert c.execute("SELECT 1 FROM domain_audit_events WHERE event_type='account.incomplete_closure_accepted'").fetchone()


def test_open_account_cannot_be_force_released(setup):
    storage, service, clock, remote, children = setup
    visit, _ = ambiguous_time(service, clock, remote, children[0])
    with pytest.raises(ValueError, match='still open'):
        service.handle('release_incomplete_closed_account',
                       {'visit_id': visit, 'accepted_missing_charges': True},
                       _context('administrator', 'release'))
    with storage.transaction() as c:
        assert c.execute('SELECT state FROM visit_barsy_bindings WHERE visit_id=?', (visit,)).fetchone()[0] == 'allocated'
