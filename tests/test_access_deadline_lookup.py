"""beta.16 boundary: deterministic mock deadlines and read-only recovery."""
from datetime import timedelta

import pytest
from test_access_journal import setup, REQUEST, event, transition


def lost_reply(journal, request):
    journal.prepare(request, admission_ready=True)
    journal.platform.failure = TimeoutError()
    assert journal.dispatch(REQUEST)['error_code'] == 'submit_outcome_unknown'


def test_absolute_deadline_is_original_prepare_deadline(setup):
    journal, request, _ = setup
    row = journal.prepare(request, admission_ready=True)
    journal.clock.value += timedelta(seconds=3)
    journal.dispatch(REQUEST)
    wire = journal.platform.calls[0][1]
    assert wire['not_after'].isoformat() == row['expires_at']
    assert wire['ttl_seconds'] == 7


def test_lost_reply_recovered_without_submit_or_clock_transition(setup):
    journal, request, _ = setup
    lost_reply(journal, request)
    lookups = []
    def lookup(**kwargs):
        lookups.append(kwargs)
        return {'status': 'found', 'command': journal.platform.result.copy()}
    journal.platform.command_lookup = lookup
    assert journal.recover(REQUEST)['state'] == 'submitted'
    assert lookups == [{'request_id': REQUEST, 'binding_id': 'passage_output'}]
    assert len(journal.platform.calls) == 1
    with journal.transaction() as c:
        assert c.execute('SELECT inside_since FROM stay_sessions').fetchone()[0] is None
    assert journal.confirm(event(journal), transition)
    assert not journal.confirm(event(journal), transition)


def test_not_found_does_not_reauthorize_or_resolve(setup):
    journal, request, _ = setup
    lost_reply(journal, request)
    journal.platform.command_lookup = lambda **kwargs: {'status': 'not_found'}
    journal.clock.value += timedelta(seconds=20)
    assert journal.recover(REQUEST)['state'] == 'review'
    assert journal.dispatch(REQUEST)['state'] == 'review'
    assert len(journal.platform.calls) == 1


@pytest.mark.parametrize('response', [None, {}, {'status': 'unavailable'}, {'status': 'found', 'command': {}}])
def test_bad_lookup_never_changes_record(setup, response):
    journal, request, _ = setup
    lost_reply(journal, request)
    before = journal.get(REQUEST)
    journal.platform.command_lookup = lambda **kwargs: response
    with pytest.raises(ValueError):
        journal.recover(REQUEST)
    assert journal.get(REQUEST) == before


def test_recovery_refused_while_submit_worker_is_active(setup):
    journal, request, _ = setup
    journal.prepare(request, admission_ready=True)
    def submit(*args, **kwargs):
        journal.clock.value += timedelta(seconds=10)
        journal.review_pending()
        with pytest.raises(ValueError, match='still in progress'):
            journal.recover(REQUEST)
        return journal.platform.result.copy()
    journal.platform.submit_command = submit
    result = journal.dispatch(REQUEST)
    assert result['state'] == 'review'
    assert result['command_id'] == journal.platform.result['command_id']


@pytest.mark.parametrize('invalidated', [False, True])
def test_expired_or_invalidated_found_command_never_rearms(setup, invalidated):
    journal, request, _ = setup
    lost_reply(journal, request)
    journal.clock.value += timedelta(seconds=10)
    if invalidated:
        journal.platform.result['status'] = 'invalidated'
    journal.platform.command_lookup = lambda **kwargs: {'status': 'found', 'command': journal.platform.result.copy()}
    assert journal.recover(REQUEST)['state'] == ('invalidated' if invalidated else 'review')
    assert len(journal.platform.calls) == 1


def test_submit_reply_cannot_extend_original_deadline(setup):
    journal, request, _ = setup
    journal.prepare(request, admission_ready=True)
    journal.platform.result['expires_at'] = (journal.clock.now() + timedelta(seconds=11)).isoformat()
    assert journal.dispatch(REQUEST)['error_code'] == 'submit_outcome_unknown'


def test_authoritative_shorter_expiry_is_used(setup):
    journal, request, _ = setup
    journal.prepare(request, admission_ready=True)
    expiry = (journal.clock.now() + timedelta(seconds=5)).isoformat()
    journal.platform.result['expires_at'] = expiry
    assert journal.dispatch(REQUEST)['expires_at'] == expiry
    journal.clock.value += timedelta(seconds=5)
    with pytest.raises(ValueError):
        journal.confirm(event(journal), transition)


def test_lookup_error_is_not_not_found(setup):
    journal, request, _ = setup
    lost_reply(journal, request)
    before = journal.get(REQUEST)
    def fail(**kwargs):
        raise TimeoutError('synthetic lookup timeout')
    journal.platform.command_lookup = fail
    with pytest.raises(TimeoutError):
        journal.recover(REQUEST)
    assert journal.get(REQUEST) == before
