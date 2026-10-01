from dataclasses import replace
from datetime import timedelta
import uuid

import pytest
from child_center_application.access_control import get_migrations
from child_center_application.access_runtime import create_service
from test_access_runtime import runtime_setup
from test_operator_accounts import tick
from test_cc4_barsy_pool import _context


@pytest.fixture
def setup(tmp_path):
    old, _, clock, remote, children = runtime_setup(tmp_path)
    old.application.storage.migrate(get_migrations(), '0017')
    cfg = {**old.application.configuration, 'READER_DEVICE_ID': 'dev_' + '1' * 32,
           'ACCESS_SENSOR_DEVICE_ID': 'dev_' + '2' * 32, 'ACCESS_OUTPUT_DEVICE_ID': 'dev_' + '1' * 32}
    s = create_service(replace(old.application, configuration=cfg, version='0.6.8'))
    def lookup(**request):
        found = [r for r, p in remote.commands.values() if p['request_id'] == request['request_id']]
        return {'status': 'found', 'command': found[0].copy()} if found else {'status': 'not_found'}
    remote.command_lookup = lookup
    return s, clock, remote, children


def configure(s):
    return s.handle('configure_access_point', dict(expected_point_id=None, enabled=True,
        reader_id='reader.synthetic', channel='gpio.output.1', duration_ms=100, safety_confirmed=True),
        _context('administrator', 'configure'))


def scan(s, clock, identity=None):
    payload = {'event_id': identity or 'evt_' + uuid.uuid4().hex,
        'device_id': 'dev_' + '1' * 32, 'event_type': 'identifier.scan.v1',
        'occurred_at': clock.now().isoformat(), 'payload': {'schema_version': 1,
        'capability_id': 'identifier.scan.v1', 'opaque_identifier': 'SYNTHETIC-SENSOR-ONLY',
        'reader_id': 'reader.synthetic', 'adapter_kind': 'mock', 'sequence': 1,
        'device_health': 'ok', 'scan_metadata': {}}}
    return payload, s.handle('process_identifier_scan', payload, _context('internal'))


def work(s, key='work'):
    return s.handle('process_access_work', {}, _context('internal', key))


def confirm(s, remote, clock):
    command, (status, payload) = list(remote.commands.items())[-1]
    identity = 'evt_' + uuid.uuid4().hex
    status['passage_event_id'] = identity
    clock.current += timedelta(seconds=1)
    event = {'event_id': identity, 'device_id': 'dev_' + '2' * 32,
        'occurred_at': clock.now().isoformat(), 'payload': {'direction': payload['direction'],
        'command_id': command, 'generation': status['generation'], 'binding_id': 'access_output',
        'sensor_id': 'access.sensor', 'device_health': 'ok'}}
    assert s.handle('process_access_passage', event, _context('internal')) == {'accepted': True}
    assert s.handle('process_access_passage', event, _context('internal')) == {'accepted': False}


def test_scan_account_dispatch_sensor_pause_and_operator_finish(setup):
    s, clock, remote, _ = setup
    configure(s)
    clock.current += timedelta(seconds=1)
    payload, result = scan(s, clock)
    visit = result['visit_id']
    assert s.handle('process_identifier_scan', payload, _context('internal')) == result
    work(s)
    assert not remote.commands  # account has not yet been confirmed
    tick(s)
    work(s, 'ready')
    work(s, 'repeat')
    assert len(remote.commands) == 1
    with s.application.storage.transaction() as c:
        assert c.execute('SELECT inside_since FROM stay_sessions').fetchone()[0] is None
    confirm(s, remote, clock)
    clock.current += timedelta(seconds=60)
    scan(s, clock)
    work(s, 'exit')
    confirm(s, remote, clock)
    clock.current += timedelta(minutes=3)
    s.handle('close_visit', {'visit_id': visit, 'occurred_at': clock.now().isoformat()}, _context('operator', 'finish'))
    with s.application.storage.transaction() as c:
        assert c.execute('SELECT duration_seconds FROM visits').fetchone()[0] == 61
        assert c.execute('SELECT rounded_minutes FROM stay_bills').fetchone()[0] == 2
        assert c.execute('SELECT retired_at FROM identifier_assignments').fetchone()[0] is not None
    assert len(remote.accounts) == 1
    assert len(remote.commands) == 2


def test_default_is_scan_only_and_config_requires_idle_and_confirmation(setup):
    s, clock, remote, _ = setup
    assert s.handle('get_access_settings', {}, _context('administrator'))['enabled'] is False
    for audience in ['operator', 'kiosk', 'internal']:
        with pytest.raises(ValueError):
            s.handle('configure_access_point', {}, _context(audience, 'denied'))
    configure(s)
    clock.current += timedelta(seconds=1)
    scan(s, clock)
    settings = s.handle('get_access_settings', {}, _context('administrator'))
    with pytest.raises(ValueError, match='Finish visits'):
        s.handle('configure_access_point', dict(expected_point_id=settings['point_id'], enabled=False,
            reader_id=settings['reader_id'], channel=settings['channel'], duration_ms=100,
            safety_confirmed=False), _context('administrator', 'disable'))


def test_changed_devices_and_expired_events_never_dispatch(setup):
    s, clock, remote, _ = setup
    configure(s)
    clock.current += timedelta(seconds=1)
    payload, result = scan(s, clock)
    clock.current += timedelta(seconds=10)
    tick(s)
    work(s)
    assert not remote.commands
    status = s.handle('get_access_status', {}, _context('operator'))
    assert status['items'][0]['error_code'] == 'expired_before_submit'
    s.application.configuration['ACCESS_OUTPUT_DEVICE_ID'] = 'dev_' + '3' * 32
    assert s.handle('get_access_status', {}, _context('operator'))['binding_valid'] is False


def test_manual_review_requires_isolation_and_preserves_money(setup):
    s, clock, remote, _ = setup
    configure(s)
    clock.current += timedelta(seconds=1)
    _, result = scan(s, clock)
    tick(s)
    work(s)
    clock.current += timedelta(seconds=10)
    work(s)
    row = s.handle('get_access_status', {}, _context('operator'))['items'][0]
    payload = dict(request_id=row['request_id'], expected_state='review', observed_inside=False,
                   hardware_isolated=False, confirmed=True)
    with pytest.raises(ValueError, match='isolation'):
        s.handle('reconcile_access', payload, _context('administrator', 'review'))
    payload['hardware_isolated'] = True
    context = _context('administrator', 'review')
    reply = s.handle('reconcile_access', payload, context)
    assert s.handle('reconcile_access', payload, context) == reply
    assert reply['state'] == 'resolved'
    with s.application.storage.transaction() as c:
        assert c.execute('SELECT inside_since FROM stay_sessions').fetchone()[0] is None
        assert c.execute('SELECT state FROM visit_barsy_bindings').fetchone()[0] == 'allocated'
    assert len(remote.commands) == 1
