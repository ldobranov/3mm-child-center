"""Regression cases from the draft runtime review; temporary storage/mock peers."""
from datetime import timedelta
import hashlib
import sqlite3

import pytest
from three_mm_application_sdk import ApplicationMigration
from child_center_application.migrations import get_migrations
from test_access_runtime import runtime_setup
from test_sensor_admission import reserve, prepare
from test_operator_accounts import tick, setup as commercial_setup
from test_privacy import setup, export, erase
from test_stays import invoke
from test_cc4_barsy_pool import _context


def ready(tmp_path):
    service, payload, clock, remote, _ = runtime_setup(tmp_path)
    visit = reserve(service.sensor_admission, payload)
    tick(service)
    intent = prepare(service.sensor_admission, visit)
    clock.current += timedelta(seconds=1)
    return service, visit, intent, clock, remote


def finish(service, visit, clock):
    return invoke(service, 'close_visit', {'visit_id': visit,
        'occurred_at': clock.now().isoformat()}, key='finish-race')


def test_dispatch_claim_blocks_concurrent_operator_finish(tmp_path):
    service, visit, intent, clock, remote = ready(tmp_path)
    original = remote.submit_command

    def interleaved(*args, **kwargs):
        # Claim has committed; finish runs through a separate SQLite transaction
        # precisely before the external submission, not a synthetic row update.
        with pytest.raises(ValueError, match='pending physical passage'):
            finish(service, visit, clock)
        with service.application.storage.transaction() as c:
            assert c.execute('SELECT state FROM visits WHERE visit_id=?', (visit,)).fetchone()[0] == 'active'
            assert c.execute('SELECT COUNT(*) FROM stay_bills').fetchone()[0] == 0
            assert c.execute('SELECT retired_at FROM identifier_assignments').fetchone()[0] is None
        return original(*args, **kwargs)

    remote.submit_command = interleaved
    service.sensor_admission.dispatch(intent['request_id'], _context('internal'))
    assert len(remote.commands) == 1


def test_operator_finish_wins_before_dispatch_and_old_intent_cannot_send(tmp_path):
    service, visit, intent, clock, remote = ready(tmp_path)
    assert finish(service, visit, clock)['state'] == 'closed'
    result = service.sensor_admission.dispatch(intent['request_id'], _context('internal'))
    assert result['error_code'] == 'visit_changed_before_submit'
    assert not remote.commands


@pytest.mark.parametrize('state,error', [
    ('submitting', None), ('submitted', None), ('review', None),
    ('review', 'submit_outcome_unknown'), ('review', 'passage_timeout_review'),
    ('review', 'startup_submit_unknown'), ('review', 'startup_unsubmitted_review'),
    ('invalidated', 'lifecycle_review')])
def test_unknown_physical_outcome_blocks_finish_even_after_local_expiry(tmp_path, state, error):
    service, visit, intent, clock, _ = ready(tmp_path)
    with service.application.storage.transaction() as c:
        c.execute('UPDATE access_intents SET state=?,error_code=? WHERE request_id=?',
                  (state, error, intent['request_id']))
    clock.current += timedelta(seconds=20)
    with pytest.raises(ValueError, match='pending physical passage'):
        finish(service, visit, clock)


def test_job_expired_unsent_can_be_reviewed_without_resubmission(tmp_path):
    service, visit, intent, clock, remote = ready(tmp_path)
    clock.current += timedelta(seconds=10)
    assert service.access_journal.review_pending() == 1
    result = service.access_review.resolve_unsent({
        'request_id': intent['request_id'], 'expected_error_code': 'expired_before_submit',
        'confirmed': True}, _context('administrator', 'resolve-job-expiry'))
    assert result['state'] == 'resolved'
    assert finish(service, visit, clock)['state'] == 'closed'
    assert service.access_journal.dispatch(intent['request_id'])['state'] == 'resolved'
    assert not remote.commands


def retired_assignment(setup, raw):
    storage, service, clock, _, children, _ = setup
    invoke(service, 'assign_identifier', {'child_id': children[0],
        'opaque_identifier': raw, 'expected_assignment_id': None}, key='assign-review')
    with storage.transaction() as c:
        c.execute("UPDATE identifier_assignments SET retired_at=?,retire_reason='manual'",
                  ((clock.now() - timedelta(days=8)).isoformat(),))


@pytest.mark.parametrize('raw', ['erased-SYNTHETIC-RAW', 'erased_SYNTHETIC-RAW', 'ERASED_SYNTHETIC-RAW'])
def test_retention_does_not_trust_identifier_prefix(setup, raw):
    retired_assignment(setup, raw)
    result = invoke(setup[1], 'apply_retention', {}, 'internal', 'retention-review')
    assert result['identifiers_erased'] == 1
    with setup[0].transaction() as c:
        row = c.execute('SELECT * FROM identifier_assignments').fetchone()
        assert row['identifier_erased'] == 1
        assert row['opaque_identifier'] == 'erased_' + hashlib.sha256(row['assignment_id'].encode()).hexdigest()
        assert row['retire_reason'] == 'manual'
    assert invoke(setup[1], 'apply_retention', {}, 'internal', 'retention-again')['identifiers_erased'] == 0


def test_retention_revokes_only_affected_child_exports_and_keeps_receipts(setup):
    retired_assignment(setup, 'SYNTHETIC-EXPORTED-RAW')
    prior = export(setup)
    assert 'SYNTHETIC-EXPORTED-RAW' in prior['document_json']
    guardian = export(setup, key='guardian', kind='guardian')
    other = {'subject_kind': 'child', 'subject_id': setup[4][1]}
    other_export = invoke(setup[1], 'export_personal_data', other, 'administrator', 'other')
    invoke(setup[1], 'apply_retention', {}, 'internal', 'retention-revoke')
    with pytest.raises(ValueError, match='expired or was revoked'):
        export(setup)
    assert export(setup, key='guardian', kind='guardian') == guardian
    assert invoke(setup[1], 'export_personal_data', other, 'administrator', 'other') == other_export
    assert 'SYNTHETIC-EXPORTED-RAW' not in export(setup, key='fresh')['document_json']
    with setup[0].transaction() as c:
        assert c.execute("SELECT COUNT(*) FROM command_results WHERE operation_id='export_personal_data'").fetchone()[0] == 4


def test_retention_export_revocation_and_scrub_roll_back_together(setup, monkeypatch):
    retired_assignment(setup, 'SYNTHETIC-ROLLBACK-RAW')
    before = export(setup)
    def fail(*args, **kwargs):
        raise RuntimeError('synthetic audit failure')
    monkeypatch.setattr(setup[1], '_audit', fail)
    with pytest.raises(RuntimeError, match='synthetic audit failure'):
        invoke(setup[1], 'apply_retention', {}, 'internal', 'retention-rollback')
    assert export(setup) == before
    with setup[0].transaction() as c:
        assert c.execute('SELECT identifier_erased FROM identifier_assignments').fetchone()[0] == 0


def test_manual_erasure_marks_identifier_for_retention(setup):
    retired_assignment(setup, 'SYNTHETIC-MANUAL-ERASURE')
    erase(setup)
    assert invoke(setup[1], 'apply_retention', {}, 'internal', 'after-erasure')['identifiers_erased'] == 0


def test_draft_migration_backfills_exact_legacy_markers_and_is_atomic(tmp_path):
    storage, service, clock, _, children = commercial_setup(tmp_path)
    with storage.transaction() as c:
        for i, raw in enumerate(['erased-SYNTHETIC-RAW', 'erased_' + hashlib.sha256(b'legacy1').hexdigest()]):
            c.execute('''INSERT INTO identifier_assignments
                (assignment_id,child_id,opaque_identifier,assigned_at,retired_at,created_at)
                VALUES (?,?,?,?,?,?)''', (f'legacy{i}', children[0], raw,
                clock.now().isoformat(), clock.now().isoformat(), clock.now().isoformat()))
    migrations = get_migrations()
    from child_center_application.migrations import _revision_0016
    def failing(c):
        _revision_0016(c)
        raise RuntimeError('synthetic migration failure')
    with pytest.raises(RuntimeError):
        storage.migrate(migrations[:-1] + [ApplicationMigration('0016', failing)], '0016')
    with storage.transaction() as c:
        assert 'identifier_erased' not in [r[1] for r in c.execute('PRAGMA table_info(identifier_assignments)')]
    storage.migrate(migrations, '0016')
    storage.migrate(migrations, '0016')
    with storage.transaction() as c:
        assert [r[0] for r in c.execute('SELECT identifier_erased FROM identifier_assignments ORDER BY assignment_id')] == [0, 1]
        with pytest.raises(sqlite3.IntegrityError):
            c.execute('UPDATE identifier_assignments SET identifier_erased=2')
