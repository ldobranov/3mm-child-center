"""SQLite snapshot recovery; not a deployed Core restore or hardware test."""
import sqlite3
from datetime import timedelta

import pytest
from three_mm_application_sdk import ApplicationStorage
from child_center_application.access_points import AccessJournal
from test_access_journal import setup, REQUEST, VISIT, event, transition


def snapshot(storage, directory):
    restored = ApplicationStorage(directory)
    directory.mkdir()
    with sqlite3.connect(storage.database_path) as source:
        with sqlite3.connect(restored.database_path) as destination:
            source.backup(destination)
    return restored


def test_restart_never_sends_prepared_intent_even_before_expiry(setup):
    journal, request, _ = setup
    journal.prepare(request, admission_ready=True)
    restarted = AccessJournal(journal.storage, journal.platform, journal.clock)
    result = restarted.dispatch(REQUEST)
    assert result['state'] == 'review'
    assert result['error_code'] == 'startup_unsubmitted_review'
    assert not journal.platform.calls
    with pytest.raises(sqlite3.IntegrityError):
        restarted.prepare({**request, 'request_id': 'access_' + 'a' * 32}, admission_ready=True)


@pytest.mark.parametrize('stage', ['prepared', 'submitting', 'submitted', 'confirmed'])
def test_restored_snapshot_never_replays_or_reauthorizes(setup, tmp_path, stage):
    journal, request, _ = setup
    journal.prepare(request, admission_ready=True)
    evidence = event(journal)
    if stage == 'submitting':
        journal.platform.failure = KeyboardInterrupt()
        with pytest.raises(KeyboardInterrupt):
            journal.dispatch(REQUEST)
    elif stage in {'submitted', 'confirmed'}:
        journal.dispatch(REQUEST)
        if stage == 'confirmed':
            journal.confirm(evidence, transition)
    restored = snapshot(journal.storage, tmp_path / 'restored')
    # Platform independently invalidates its command generation on real restore.
    journal.platform.result['status'] = 'invalidated'
    count = len(journal.platform.calls)
    recovered = AccessJournal(restored, journal.platform, journal.clock)
    result = recovered.dispatch(REQUEST)
    assert result['state'] != 'prepared'
    assert len(journal.platform.calls) == count
    if stage == 'confirmed':
        assert not recovered.confirm(evidence, lambda *args: pytest.fail('Replayed transition'))
    else:
        with pytest.raises(ValueError):
            recovered.confirm(evidence, lambda *args: pytest.fail('Restored authority accepted'))
    with recovered.transaction() as c:
        assert c.execute('SELECT inside_since FROM stay_sessions WHERE visit_id=?', (VISIT,)).fetchone()[0] == (journal.clock.now().isoformat() if stage == 'confirmed' else None)


@pytest.mark.parametrize('submitted', [False, True])
def test_timeout_is_review_not_a_retry_or_proof_of_non_execution(setup, submitted):
    journal, request, _ = setup
    journal.prepare(request, admission_ready=True)
    if submitted:
        journal.dispatch(REQUEST)
    assert journal.review_pending() == 0
    journal.clock.value += timedelta(seconds=10)
    assert journal.review_pending() == 1
    assert journal.review_pending() == 0
    result = journal.dispatch(REQUEST)
    assert result['state'] == 'review'
    assert result['error_code'] == ('passage_timeout_review' if submitted else 'expired_before_submit')
    assert len(journal.platform.calls) == int(submitted)
    with pytest.raises(sqlite3.IntegrityError):
        journal.prepare({**request, 'request_id': 'access_' + 'a' * 32}, admission_ready=True)


def test_missing_migration_prevents_usable_journal(tmp_path):
    storage = ApplicationStorage(tmp_path)
    with pytest.raises(sqlite3.OperationalError):
        AccessJournal(storage, object(), object())
