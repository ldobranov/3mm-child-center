from datetime import timedelta

import pytest
from child_center_application.access_runtime import create_service
from test_sensor_admission import setup, reserve, prepare, passage
from test_operator_accounts import tick, setup as commercial_setup, start
from test_stays import invoke
from test_cc4_barsy_pool import _context


def runtime_setup(tmp_path):
    w, payload, old, clock, remote, children = setup(tmp_path)
    # One peer supplies both real SDK surfaces in production; both are mocked here.
    remote.submit_command = w.journal.platform.submit_command
    remote.command_status = w.journal.platform.command_status
    remote.commands = w.journal.platform.commands
    service = create_service(old.application)
    return service, payload, clock, remote, children


def test_factory_keeps_schema_0015_scan_workflow(tmp_path):
    _, old, clock, _, children = commercial_setup(tmp_path)
    service = create_service(old.application)
    assert service.access_journal is None
    visit = start(service, clock, children[0])
    tick(service)
    with service.application.storage.transaction() as c:
        assert c.execute('SELECT inside_since FROM stay_sessions WHERE visit_id=?', (visit,)).fetchone()[0]


def test_runtime_blocks_legacy_resume_but_accepts_passage_and_operator_finish(tmp_path):
    service, payload, clock, remote, _ = runtime_setup(tmp_path)
    w = service.sensor_admission
    visit = reserve(w, payload)
    tick(service)
    clock.current += timedelta(seconds=1)
    with pytest.raises(ValueError, match='confirmed sensor passage'):
        invoke(service, 'start_visit', dict(child_id=payload['child_id'], assignment_id=payload['assignment_id'],
            occurred_at=clock.now().isoformat()), key='legacy-resume')
    passage(w, prepare(w, visit), clock)
    clock.current += timedelta(seconds=1)
    with service.application.storage.transaction() as c:
        with pytest.raises(ValueError, match='confirmed sensor passage'):
            service._transition_stay(c, visit, clock.now().isoformat(), False,
                _context('internal'), 'evt_' + 'a' * 32, {'purpose': 'exit'})
    invoke(service, 'close_visit', dict(visit_id=visit, occurred_at=clock.now().isoformat()), key='finish')
    with service.application.storage.transaction() as c:
        assert c.execute('SELECT state FROM visits WHERE visit_id=?', (visit,)).fetchone()[0] == 'closed'


def test_factory_runs_recovery_before_exposing_adapter(tmp_path):
    service, payload, clock, remote, _ = runtime_setup(tmp_path)
    visit = reserve(service.sensor_admission, payload)
    tick(service)
    intent = prepare(service.sensor_admission, visit)
    recovered = create_service(service.application)
    result = recovered.sensor_admission.dispatch(intent['request_id'], _context('internal'))
    assert result['state'] == 'review'
    assert not remote.commands
