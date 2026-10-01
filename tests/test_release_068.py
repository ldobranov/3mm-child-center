import json

import pytest
from backend.services.application_extensions import validate_operation_payload
from backend.tests.test_application_access import environment, headers
from backend.routes import application_extensions
from test_package import _builder_module
from test_contract import _assert_object_schemas_are_bounded
from test_access_control import setup, configure, scan, work
from test_cc4_barsy_pool import _context
from test_operator_accounts import tick
from child_center_application.access_runtime import create_service
from child_center_application.access_control import get_migrations
from three_mm_application_sdk import ApplicationStorage, ApplicationMigration
from datetime import timedelta


def test_generated_release_contracts_match_runtime(setup):
    files = _builder_module().package_files()
    contract = json.loads(files['application-extension.json'])
    assert contract['version'] == '0.7.6'
    assert contract['storage']['schema_revision'] == '0020'
    assert contract['service']['entrypoint'].endswith('reliable_runtime:create_service')
    assert contract['command_bindings'][0]['sensor_id'] == 'access.sensor'
    for operation in contract['operations']:
        for kind in ['input_schema', 'output_schema']:
            _assert_object_schemas_are_bounded(operation[kind])
    from dataclasses import replace
    from child_center_application.reliable_runtime import get_migrations as latest_migrations, create_service as latest_service
    old = setup[0]
    old.application.storage.migrate(latest_migrations(), '0020')
    s = latest_service(replace(old.application, version='0.7.6'))
    for name, audience in [('get_access_settings', 'administrator'), ('get_access_status', 'operator'), ('health', 'internal')]:
        operation = next(o for o in contract['operations'] if o['operation_id'] == name)
        validate_operation_payload(s.handle(name, {}, _context(audience)), operation['output_schema'])


@pytest.mark.parametrize('operation', ['configure_access_point', 'reconcile_access', 'resolve_unsent_access'])
def test_physical_administration_cannot_be_called_by_staff(monkeypatch, tmp_path, operation):
    client, db, engine, _, user, _, _, admin, staff = environment(monkeypatch, tmp_path, blob=_builder_module().build_package())
    calls = []
    monkeypatch.setattr(application_extensions, '_invoke', lambda *a: calls.append(a) or {})
    base = '/api/v1/application-extensions/org.3mm.child-center'
    try:
        client.post(base + '/permissions/grants', json={'user_id': user.id, 'permission_id': 'configuration_manage'}, headers=headers(admin))
        assert client.post(base + '/operations/' + operation, json={'payload': {}, 'idempotency_key': 'synthetic'}, headers=headers(staff)).status_code == 403
        assert client.post(base + '/operator/operations/' + operation, json={'payload': {}, 'idempotency_key': 'synthetic'}, headers=headers(staff)).status_code == 403
        assert not calls
    finally:
        client.close(); db.close(); engine.dispose()


def test_manual_start_cannot_bypass_sensor_mode(setup):
    s, clock, _, children = setup
    configure(s)
    with pytest.raises(ValueError, match='fresh bracelet scan'):
        s.handle('start_visit', {'child_id': children[0], 'assignment_id': None, 'occurred_at': clock.now().isoformat()}, _context('operator', 'manual'))
    with s.application.storage.transaction() as c:
        assert c.execute('SELECT COUNT(*) FROM visits').fetchone()[0] == 0


def test_restart_discards_unsent_work_and_does_not_resume_on_job(setup):
    s, clock, remote, _ = setup
    configure(s)
    clock.current += timedelta(seconds=1)
    scan(s, clock)
    with s.application.storage.transaction() as c:
        assert c.execute('SELECT state FROM access_intents').fetchone()[0] == 'prepared'
    recovered = create_service(s.application)
    work(recovered)
    assert not remote.commands
    row = recovered.handle('get_access_status', {}, _context('operator'))['items'][0]
    assert row['state'] == 'review' and row['error_code'] == 'startup_unsubmitted_review'


def test_0017_migration_is_atomic_and_repeatable(tmp_path):
    storage = ApplicationStorage(tmp_path)
    migrations = get_migrations()
    storage.migrate(migrations, '0016')
    def fail(c):
        migrations[-1].apply(c)
        raise RuntimeError('synthetic failure')
    with pytest.raises(RuntimeError):
        storage.migrate([*migrations[:-1], ApplicationMigration('0017', fail)], '0017')
    with storage.transaction() as c:
        assert not c.execute("SELECT 1 FROM sqlite_master WHERE name='access_control_settings'").fetchone()
    storage.migrate(migrations, '0017')
    storage.migrate(migrations, '0017')
    with storage.transaction() as c:
        assert c.execute('SELECT point_id FROM access_control_settings').fetchone()[0] is None
        assert not c.execute('PRAGMA foreign_key_check').fetchall()
