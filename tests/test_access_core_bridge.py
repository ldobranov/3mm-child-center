"""Extension + actual SDK serialization/Core queue using isolated test databases.

No sockets, deployed installation or hardware. Only the signed transport itself
is replaced; platform permissions, binding validation and queue/lookup are real.
"""
from datetime import UTC, datetime

import pytest
from sqlalchemy import select
from three_mm_application_sdk import ApplicationPlatformClient
from backend.tests.test_application_commands import setup as core_setup
from backend.services import application_commands as broker
from backend.db.device import DeviceCommand
from test_access_journal import setup as journal_setup, REQUEST


def bridge(core, journal, request, point, monkeypatch, tmp_path, lose_reply=False):
    journal.clock.value = datetime.now(UTC)
    point = {**point, 'point_id': 'broker_gate', 'binding_id': 'gate',
        'sensor_device': core.devices[1].device_id, 'sensor_id': 'sensor.1',
        'arguments': {'channel': 'gpio.output.1', 'duration_ms': 100}}
    journal.register_point(point)
    request = {**request, 'point_id': 'broker_gate'}
    client = ApplicationPlatformClient(tmp_path / 'unused.sock', 'test', b's' * 32)
    actions = []
    def call(action, body):
        actions.append(action)
        if action == 'command.submit':
            result = broker.submit_command(core.db, core.app, body['command'])
            if lose_reply:
                raise TimeoutError('synthetic lost committed response')
            return result
        if action == 'command.lookup':
            return broker.command_lookup(core.db, core.app, body['lookup'])
        raise AssertionError(action)
    monkeypatch.setattr(client, '_call', call)
    journal.platform = client
    journal.prepare(request, admission_ready=True)
    return actions


def test_real_queue_lost_reply_lookup_does_not_duplicate(core_setup, journal_setup, monkeypatch, tmp_path):
    journal, request, point = journal_setup
    actions = bridge(core_setup, journal, request, point, monkeypatch, tmp_path, lose_reply=True)
    assert journal.dispatch(REQUEST)['state'] == 'review'
    result = journal.recover(REQUEST)
    assert result['state'] == 'submitted'
    assert actions == ['command.submit', 'command.lookup']
    commands = core_setup.db.scalars(select(DeviceCommand)).all()
    assert len(commands) == 1
    assert commands[0].command_id == result['command_id']
    assert commands[0].payload['arguments'] == {'channel': 'gpio.output.1', 'duration_ms': 100}
    with journal.transaction() as c:
        assert c.execute('SELECT inside_since FROM stay_sessions').fetchone()[0] is None


def test_real_queue_rejects_delayed_admission(core_setup, journal_setup, monkeypatch, tmp_path):
    journal, request, point = journal_setup
    actions = bridge(core_setup, journal, request, point, monkeypatch, tmp_path)
    deadline = datetime.fromisoformat(journal.get(REQUEST)['expires_at'])
    original = broker.queue_command
    monkeypatch.setattr(broker, 'queue_command', lambda *args, **kwargs:
        original(*args, **kwargs, now=deadline))
    assert journal.dispatch(REQUEST)['state'] == 'review'
    core_setup.db.rollback()
    assert not core_setup.db.scalars(select(DeviceCommand)).all()
    assert journal.recover(REQUEST)['state'] == 'review'
    assert actions == ['command.submit', 'command.lookup']
