"""Remote business refusals are observable but never silently replayed."""
import base64
from dataclasses import replace
from datetime import timedelta
import pytest

from child_center_application.reliable_runtime import create_service, get_migrations
from child_center_application.commerce import write_failure_code
from test_operator_accounts import setup as previous_setup, start, tick
from test_billing_units import invoke


@pytest.fixture
def setup(tmp_path):
    storage, old, clock, remote, children = previous_setup(tmp_path)
    storage.migrate(get_migrations(), '0020')
    return storage, create_service(replace(old.application, version='0.7.1')), clock, remote, children


@pytest.mark.parametrize('known', [False, True])
def test_501_is_specific_private_and_not_replayed(setup, known):
    storage, service, clock, remote, children = setup
    visit = start(service, clock, children[0]); tick(service)
    clock.current += timedelta(minutes=93)
    invoke(service, 'close_visit', {'visit_id': visit, 'occurred_at': clock.now().isoformat()}, key='finish')
    original = remote.connector_request
    attempts = []
    text = 'SYNTHETIC_PRIVATE_NAME няма зададена продажна цена и не може да бъде продаден' if known else 'SYNTHETIC_PRIVATE_NAME other remote error'
    def connector(*args, **kwargs):
        if kwargs['path'].endswith('Accounts_place'):
            attempts.append(kwargs)
            return {'outcome': 'retryable', 'http_status': 501, 'body_base64': base64.b64encode(text.encode()).decode()}
        return original(*args, **kwargs)
    remote.connector_request = connector
    tick(service); tick(create_service(service.application))
    assert len(attempts) == 1
    command = invoke(service, 'get_operator_account', {'visit_id': visit})['commands'][0]
    assert command['state'] == ('failed' if known else 'ambiguous')
    assert command['error_code'] == ('barsy_article_price_missing' if known else 'barsy_http_501')
    if known:
        assert invoke(service, 'retry_account_command', {'command_id': command['command_id']}, key='retry')['state'] == 'prepared'
        assert len(attempts) == 1  # explicit retry is queued, never sent in the request path
    else:
        with pytest.raises(ValueError, match='definitely unsent'):
            invoke(service, 'retry_account_command', {'command_id': command['command_id']}, key='retry')
    with storage.transaction() as c:
        for row in c.execute('SELECT * FROM account_commands'):
            assert 'SYNTHETIC_PRIVATE_NAME' not in str(dict(row))
        assert c.execute('SELECT state FROM visit_barsy_bindings WHERE visit_id=?', (visit,)).fetchone()[0] == 'allocated'


@pytest.mark.parametrize('value', [None, True, '501', 200, 999])
def test_http_code_is_not_arbitrary_remote_text(value):
    assert write_failure_code({'http_status': value, 'body_base64': 'invalid'}) == 'confirmation_required_no_retry'


def test_one_blocked_admission_does_not_starve_later_child(setup):
    _, service, clock, remote, children = setup
    original = remote.connector_request
    def connector(*args, **kwargs):
        result = original(*args, **kwargs)
        if kwargs['path'].endswith('Accounts_create'):
            remote.accounts[501]['time_calculation'] = 1
        return result
    remote.connector_request = connector
    first = start(service, clock, children[0]); tick(service)
    second = start(service, clock, children[1]); tick(service, 20)
    accounts = {r['visit_id']: r for r in invoke(service, 'list_operator_accounts', {'offset': 0})['items']}
    assert accounts[first]['admitted'] is False
    assert accounts[first]['error_code'] == 'barsy_place_timing_enabled'
    assert accounts[second]['admitted'] is True
    assert len(remote.posts) == 2
