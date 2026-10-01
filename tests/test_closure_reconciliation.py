"""Manual reconciliation cannot erase missing time or consumption evidence."""
from datetime import timedelta

import pytest
from test_account_observation import setup, accounts, financial_state
from test_operator_accounts import start, tick
from test_cc4_barsy_pool import _context


def verify(service, visit, key='verify'):
    return service.handle('verify_account_closure', {'visit_id': visit, 'reviewed': True}, _context('operator', key))


@pytest.mark.parametrize('fx', [None, 1])
def test_empty_closed_account_cannot_confirm_93_minutes(setup, fx):
    storage, service, clock, remote, children = setup
    service.handle('set_timing_profile', {'mode': 'local_quantity', 'article_id': 26, 'billing_unit': 'minutes'}, _context('administrator', 'minutes'))
    visit = start(service, clock, children[0]); tick(service)
    clock.current += timedelta(minutes=93)
    service.handle('close_visit', {'visit_id': visit, 'occurred_at': clock.now().isoformat()}, _context('operator', 'finish'))
    remote.outcome = 'timeout'; tick(service)
    remote.accounts[501].update(status=1, orders=[], total_real=0, total_paid=0, total_remain=0, fx=fx)
    before = financial_state(storage); writes = len(remote.posts)
    with pytest.raises(ValueError, match='paid fiscal|expected playing time'):
        verify(service, visit)
    assert financial_state(storage) == before
    assert before['stay_bills'][0]['quantity'] == '93.000'
    assert len(remote.posts) == writes


def test_full_time_and_consumption_fiscal_closure_releases_without_reposting(setup):
    storage, service, clock, remote, children = setup
    visit = start(service, clock, children[0]); tick(service)
    for index in range(2):
        service.handle('add_account_consumption', {'visit_id': visit, 'article_id': 11,
            'quantity': '1', 'consumer': 'child'}, _context('operator', 'drink-' + str(index)))
        tick(service)
    clock.current += timedelta(seconds=61)
    service.handle('close_visit', {'visit_id': visit, 'occurred_at': clock.now().isoformat()}, _context('operator', 'finish'))
    tick(service)
    account = remote.accounts[501]
    account.update(status=1, total_paid=account['total_real'], total_remain=0, fx=1)
    writes = len(remote.posts)
    assert verify(service, visit) == {'status': 'released'}
    assert verify(service, visit) == {'status': 'released'}
    tick(service)
    assert accounts(service)['items'] == []
    assert len(remote.posts) == writes
    with storage.transaction() as c:
        assert c.execute('SELECT state FROM stay_bills WHERE visit_id=?', (visit,)).fetchone()[0] == 'confirmed'
        assert not c.execute("SELECT 1 FROM account_commands WHERE visit_id=? AND state!='confirmed'", (visit,)).fetchone()
        assert not c.execute('PRAGMA foreign_key_check').fetchall()


@pytest.mark.parametrize('state,remote_amount', [('confirmed', 0), ('ambiguous', 0), ('failed', 0), ('prepared', 0), ('ambiguous', 1)])
def test_missing_or_partial_consumption_cannot_be_blanket_confirmed(setup, state, remote_amount):
    storage, service, clock, remote, children = setup
    visit = start(service, clock, children[0]); tick(service)
    service.handle('add_account_consumption', {'visit_id': visit, 'article_id': 11,
        'quantity': '2', 'consumer': 'child'}, _context('operator', 'drink'))
    tick(service)
    clock.current += timedelta(seconds=61)
    service.handle('close_visit', {'visit_id': visit, 'occurred_at': clock.now().isoformat()}, _context('operator', 'finish'))
    tick(service)
    account = remote.accounts[501]
    account['orders'] = [r for r in account['orders'] if r['article_id'] != 11]
    if remote_amount:
        account['orders'].append({'article_id': 11, 'amount': remote_amount, 'active_time_orders': 0})
    account.update(status=1, total_paid=account['total_real'], total_remain=0, fx=1)
    with storage.transaction() as c:
        c.execute("UPDATE account_commands SET state=? WHERE visit_id=? AND kind='consumption'", (state, visit))
    before = financial_state(storage); writes = len(remote.posts)
    with pytest.raises(ValueError, match='consumption|article|quantit'):
        verify(service, visit)
    assert financial_state(storage) == before
    assert len(remote.posts) == writes
