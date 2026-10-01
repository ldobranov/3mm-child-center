"""Temporary extension storage and synthetic subjects/POS only."""
import json
from datetime import timedelta

import pytest
from child_center_application.access_runtime import create_service
from test_operator_accounts import setup as commercial_setup, start, tick
from child_center_application.migrations import get_migrations
from test_stays import invoke
from test_cc4_barsy_pool import _context


@pytest.fixture
def setup(tmp_path):
    storage, old, clock, remote, children = commercial_setup(tmp_path)
    storage.migrate(get_migrations(), '0016')
    service = create_service(old.application)
    with storage.transaction() as c:
        guardian = c.execute('SELECT guardian_id FROM guardian_children WHERE child_id=?', (children[0],)).fetchone()[0]
    return storage, service, clock, remote, children, guardian


def subject(setup, kind='child'):
    return {'subject_kind': kind, 'subject_id': setup[4][0] if kind == 'child' else setup[5]}


def export(setup, key='export', kind='child'):
    return invoke(setup[1], 'export_personal_data', subject(setup, kind), 'administrator', key)


def erase(setup, key='erase', kind='child'):
    return invoke(setup[1], 'erase_personal_data', {**subject(setup, kind), 'scope': 'erase_where_permitted',
        'reason': 'Synthetic confidential erasure reason'}, 'administrator', key)


def closed_paid_visit(setup):
    _, s, clock, _, children, _ = setup
    visit = start(s, clock, children[0])
    tick(s)
    clock.current += timedelta(seconds=61)
    invoke(s, 'close_visit', {'visit_id': visit, 'occurred_at': clock.now().isoformat()}, key='finish')
    tick(s)
    quote = invoke(s, 'preview_account_payment', {'visit_id': visit}, key='quote')
    invoke(s, 'pay_account', {'quote_id': quote['quote_id'], 'paymethod_id': 1, 'confirmed': True}, key='pay')
    tick(s)
    return visit


def test_export_is_complete_within_declared_scope_and_not_in_command_cache(setup):
    result = export(setup)
    assert export(setup) == result
    document = json.loads(result['document_json'])
    assert document['subject']['child_id'] == setup[4][0]
    assert setup[4][1] not in result['document_json']
    assert 'connector' not in document
    with setup[0].transaction() as c:
        stored = json.loads(c.execute("SELECT result_json FROM command_results WHERE operation_id='export_personal_data'").fetchone()[0])
        assert set(stored) == {'export_id','status'}


def test_erasure_revokes_exports_and_cached_replies_but_preserves_tombstones(setup):
    storage, s, _, _, children, guardian = setup
    prior = export(setup)
    key = _context('administrator', 'synthetic-cache')
    s._idempotent('synthetic_result', {}, key, lambda c: {'child_id': children[0], 'display_name': 'Synthetic cached name'})
    result = erase(setup)
    assert result['status'] == 'erased'
    assert erase(setup) == result
    with pytest.raises(ValueError, match='expired or was revoked'):
        export(setup)
    with pytest.raises(ValueError, match='privacy processing'):
        s._idempotent('synthetic_result', {}, key, lambda c: pytest.fail('Privacy caused command replay'))
    with storage.transaction() as c:
        assert c.execute('SELECT status FROM children WHERE child_id=?', (children[0],)).fetchone()[0] == 'erased'
        assert c.execute('SELECT status FROM children WHERE child_id=?', (children[1],)).fetchone()[0] == 'active'
        assert c.execute('SELECT status FROM guardians WHERE guardian_id=?', (guardian,)).fetchone()[0] == 'active'
        assert not c.execute('SELECT 1 FROM privacy_exports WHERE export_id=?', (prior['export_id'],)).fetchone()
        assert 'Synthetic confidential erasure reason' not in str([tuple(r) for r in c.execute('SELECT metadata_json FROM domain_audit_events')])


def test_measured_financial_history_is_not_deleted_or_replayed(setup):
    visit = closed_paid_visit(setup)
    posts = len(setup[3].posts)
    erase(setup)
    with setup[0].transaction() as c:
        assert c.execute('SELECT duration_seconds FROM visits WHERE visit_id=?', (visit,)).fetchone()[0] == 61
        assert c.execute('SELECT COUNT(*) FROM account_commands').fetchone()[0] == 2
        assert c.execute('PRAGMA foreign_key_check').fetchall() == []
    tick(setup[1])
    assert len(setup[3].posts) == posts


@pytest.mark.parametrize('kind', ['child','guardian'])
def test_active_visit_blocks_erasure_without_partial_changes(setup, kind):
    start(setup[1], setup[2], setup[4][0])
    before = export(setup, kind=kind)
    with pytest.raises(ValueError, match='active visits'):
        erase(setup, kind=kind)
    assert export(setup, kind=kind) == before


def test_allocated_account_blocks_erasure_after_operator_finish(setup):
    _, s, clock, _, children, _ = setup
    visit = start(s, clock, children[0])
    tick(s)
    clock.current += timedelta(seconds=61)
    invoke(s, 'close_visit', {'visit_id': visit, 'occurred_at': clock.now().isoformat()}, key='finish')
    tick(s)
    with pytest.raises(ValueError, match='allocated accounts'):
        erase(setup)


@pytest.mark.parametrize('audience', ['operator','kiosk','internal'])
def test_privacy_commands_require_admin(setup, audience):
    for operation, payload in [('export_personal_data', subject(setup)),
            ('erase_personal_data', {**subject(setup), 'scope':'anonymize', 'reason':'synthetic'})]:
        with pytest.raises(ValueError, match='audience'):
            setup[1].handle(operation, payload, _context(audience, 'denied'))


def test_strict_schema_and_required_idempotency(setup):
    s = setup[1]
    with pytest.raises(ValueError):
        s.handle('export_personal_data', {**subject(setup), 'extra':True}, _context('administrator','bad'))
    with pytest.raises(ValueError, match='idempotency'):
        s.handle('export_personal_data', subject(setup), _context('administrator'))
    with pytest.raises(ValueError, match='audience'):
        s.handle('apply_retention', {}, _context('administrator','bad-job'))


def test_expired_export_is_never_regenerated_by_replay(setup):
    result = export(setup)
    setup[2].current += timedelta(minutes=15)
    with pytest.raises(ValueError, match='expired'):
        export(setup)
    assert export(setup, key='new-export')['export_id'] != result['export_id']


def test_retention_uses_last_closed_visit_and_erases_retired_identifiers(setup):
    storage, s, clock, _, children, guardian = setup
    invoke(s, 'assign_identifier', {'child_id': children[0], 'opaque_identifier':'SYNTHETIC-RETENTION', 'expected_assignment_id':None}, key='assign')
    closed_paid_visit(setup)
    clock.current += timedelta(days=8)
    first = invoke(s, 'apply_retention', {}, 'internal', 'retention-1')
    assert first == {'anonymized':0, 'identifiers_erased':1, 'deleted':0}
    assert invoke(s, 'apply_retention', {}, 'internal', 'retention-1') == first
    with storage.transaction() as c:
        assert c.execute('SELECT opaque_identifier FROM identifier_assignments').fetchone()[0].startswith('erased_')
    clock.current += timedelta(days=23)
    # Cursor rotates after a page, including ineligible or blocked subjects.
    invoke(s, 'apply_retention', {}, 'internal', 'rotate')
    result = invoke(s, 'apply_retention', {}, 'internal', 'retention-2')
    assert result['anonymized'] == 1
    with storage.transaction() as c:
        assert c.execute('SELECT status FROM guardians WHERE guardian_id=?', (guardian,)).fetchone()[0] == 'anonymized'
        assert c.execute('SELECT duration_seconds FROM visits').fetchone()[0] == 61


def test_redacted_family_cannot_be_repopulated_by_legacy_update(setup):
    storage, s, _, _, children, _ = setup
    with storage.transaction() as c:
        registration = c.execute('SELECT registration_id FROM children WHERE child_id=?', (children[0],)).fetchone()[0]
    erase(setup)
    with pytest.raises(ValueError, match='cannot be restored'):
        s._idempotent('update_client', {'registration_id': registration}, _context('administrator','update'),
            lambda c: pytest.fail('Repopulated erased data'))


def test_delete_client_revokes_family_exports_in_same_transaction(setup):
    storage, s, _, _, children, _ = setup
    export(setup)
    export(setup, key='guardian-export', kind='guardian')
    with storage.transaction() as c:
        registration = c.execute('SELECT registration_id FROM children WHERE child_id=?', (children[0],)).fetchone()[0]
    payload = {'registration_id': registration, 'reason':'administrator_request'}
    result = invoke(s, 'delete_client', payload, 'administrator', 'delete')
    assert result == {'status':'deleted', 'retained_visit_count':0}
    assert invoke(s, 'delete_client', payload, 'administrator', 'delete') == result
    with storage.transaction() as c:
        assert c.execute('SELECT COUNT(*) FROM privacy_exports').fetchone()[0] == 0
        assert c.execute("SELECT COUNT(*) FROM children WHERE status!='erased'").fetchone()[0] == 0
        assert c.execute('PRAGMA foreign_key_check').fetchall() == []


def test_expired_artifacts_removed_with_count_and_no_replay(setup):
    export(setup)
    setup[2].current += timedelta(minutes=15)
    result = invoke(setup[1], 'apply_retention', {}, 'internal', 'expire-artifacts')
    assert result == {'anonymized':0,'identifiers_erased':0,'deleted':1}
    with pytest.raises(ValueError, match='expired or was revoked'):
        export(setup)


def test_oversized_export_fails_without_partial_artifact(setup):
    with setup[0].transaction() as c:
        c.execute('UPDATE children SET notes=? WHERE child_id=?', ('x' * 1048576, setup[4][0]))
    with pytest.raises(ValueError, match='inline limit'):
        export(setup)
    with setup[0].transaction() as c:
        assert c.execute('SELECT COUNT(*) FROM privacy_exports').fetchone()[0] == 0


def test_unresolved_access_intent_blocks_child_erasure(setup):
    visit = closed_paid_visit(setup)
    s = setup[1]
    with setup[0].transaction() as c:
        c.execute("INSERT INTO access_points VALUES ('synthetic','{}')")
        c.execute("""INSERT INTO access_intents(request_id,point_id,visit_id,payload_json,state,created_at,expires_at)
            VALUES ('access_pending','synthetic',?,'{}','review',?,?)""", (visit,s._now(),s._now()))
    with pytest.raises(ValueError, match='physical commands'):
        erase(setup)
