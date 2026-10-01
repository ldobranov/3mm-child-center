from datetime import timedelta

import pytest
from child_center_application.access_runtime import create_service
from test_access_runtime import runtime_setup
from test_sensor_admission import reserve, prepare
from test_operator_accounts import tick
from test_cc4_barsy_pool import _context


def setup(tmp_path, *, submitted=False, restored=False):
    service, payload, clock, remote, children = runtime_setup(tmp_path)
    visit = reserve(service.sensor_admission, payload)
    tick(service)
    intent = prepare(service.sensor_admission, visit)
    if submitted:
        service.sensor_admission.dispatch(intent['request_id'], _context('internal'))
        clock.current += timedelta(seconds=10)
        service.access_journal.review_pending()
    elif not restored:
        clock.current += timedelta(seconds=10)
        service.access_journal.dispatch(intent['request_id'])
    return create_service(service.application), intent, remote, children


def resolution(intent):
    return dict(request_id=intent['request_id'], expected_error_code='expired_before_submit', confirmed=True)


def test_resolve_proven_unsent_is_idempotent_and_does_not_touch_money_or_time(tmp_path):
    s, intent, remote, _ = setup(tmp_path)
    review = s.access_review
    assert review.list_pending({}, _context('administrator'))['items'][0]['request_id'] == intent['request_id']
    context = _context('administrator', 'resolve')
    result = review.resolve_unsent(resolution(intent), context)
    assert review.resolve_unsent(resolution(intent), context) == result
    assert result['state'] == 'resolved'
    assert s.access_journal.dispatch(intent['request_id'])['state'] == 'resolved'
    s.access_journal.invalidate()
    assert s.access_journal.get(intent['request_id'])['state'] == 'resolved'
    assert not remote.commands
    with s.application.storage.transaction() as c:
        assert c.execute('SELECT inside_since FROM stay_sessions').fetchone()[0] is None
        assert c.execute('SELECT state FROM visit_barsy_bindings').fetchone()[0] == 'allocated'
        assert c.execute("SELECT COUNT(*) FROM domain_audit_events WHERE event_type='access.unsent_resolved'").fetchone()[0] == 1
    assert len(remote.posts) == 1
    assert review.list_pending({}, context)['items'] == []


def test_unknown_execution_cannot_be_cleared_as_unsent(tmp_path):
    s, intent, remote, _ = setup(tmp_path, submitted=True)
    with pytest.raises(ValueError, match='definitely unsubmitted'):
        s.access_review.resolve_unsent(resolution(intent), _context('administrator', 'resolve'))
    assert s.access_journal.get(intent['request_id'])['state'] == 'review'
    assert len(remote.commands) == 1


def test_prepared_backup_is_not_proof_of_never_submitted(tmp_path):
    s, intent, _, _ = setup(tmp_path, restored=True)
    assert s.access_journal.get(intent['request_id'])['error_code'] == 'startup_unsubmitted_review'
    with pytest.raises(ValueError):
        s.access_review.resolve_unsent(resolution(intent), _context('administrator', 'cannot-clear'))


@pytest.mark.parametrize('audience', ['operator','kiosk','internal'])
def test_review_and_export_reject_non_admin(tmp_path, audience):
    s, intent, _, _ = setup(tmp_path)
    for method, payload in ((s.access_review.list_pending, {}),
                            (s.access_review.resolve_unsent, resolution(intent)),
                            (s.access_review.export_registration, {'registration_id': 'not-used'})):
        with pytest.raises(ValueError, match='audience'):
            method(payload, _context(audience, 'denied'))


@pytest.mark.parametrize('change', [{'confirmed': 1}, {'confirmed': False}, {'retry': True}, {'expected_error_code': 'submit_outcome_unknown'}])
def test_strict_resolution_payload(tmp_path, change):
    s, intent, _, _ = setup(tmp_path)
    with pytest.raises(ValueError):
        s.access_review.resolve_unsent({**resolution(intent), **change}, _context('administrator', 'bad'))


def test_export_is_registration_scoped_and_excludes_hardware_identifiers(tmp_path):
    s, intent, _, children = setup(tmp_path)
    with s.application.storage.transaction() as c:
        registration = c.execute('SELECT registration_id FROM children WHERE child_id=?', (children[0],)).fetchone()[0]
        # A genuinely separate registration, rather than a sibling in the same family.
        c.execute("INSERT INTO registrations(registration_id,kiosk_terminal_id,submission_idempotency_key,status,consent_version,submitted_at,created_at,updated_at) VALUES ('other','test','other','approved','v1','t','t','t')")
    result = s.access_review.export_registration({'registration_id': registration}, _context('administrator'))
    assert result['items'][0]['request_id'] == intent['request_id']
    assert set(result['items'][0]) == {'request_id','visit_id','state','requested_at','expires_at','direction','passed_at'}
    assert s.access_review.export_registration({'registration_id': 'other'}, _context('administrator'))['items'] == []
    with pytest.raises(ValueError):
        s.access_review.export_registration({'registration_id': registration, 'limit': 1000}, _context('administrator'))
