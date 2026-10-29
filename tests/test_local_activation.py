"""Real standard activation and signed Unix-socket host, in disposable Linux paths.

Only the systemd process controller is replaced; health/migrations/SDK/wheel
imports and the activation/rollback code are real. No installed service is used.
"""
from dataclasses import asdict
import hashlib
import io
import json
import os
import sqlite3
from pathlib import Path
import subprocess
import sys
import tempfile
import time
import zipfile

import pytest
import three_mm_runtime
from three_mm_runtime.application_activation import (
    activate_application_package, ApplicationActivationError, application_instance_id,
)
from three_mm_runtime.application_transport import ApplicationServiceClient, ApplicationTransportError

sys.path.insert(0, str(Path(__file__).parents[1]))
from build_local_package import build_package


sys.path.insert(0, str(Path(__file__).parents[1] / 'tools'))
from application_process_check import disposable_runtime, activate, client


@pytest.fixture
def runtime():
    with disposable_runtime(Path(__file__).parents[1] / '.runtime/activation-checks') as state:
        yield state


def context(key=None, audience='operator'):
    return dict(audience=audience, user_id=42 if audience in ('operator','administrator') else None,
                subject_id='usr_'+'4'*32 if audience in ('operator','administrator') else None,
                correlation_id='actual-activation-check', idempotency_key=key)


def test_standard_activation_migrates_real_wheel_serves_and_restarts(runtime):
    base, supervisor = runtime
    payload = build_package()
    result = activate(base, supervisor, payload)
    service = client(supervisor, result.instance_id)
    assert service.invoke('health', {}, context(audience='internal')) == {'status':'ready'}
    registration = {'guardian': {'display_name':'Synthetic activation parent', 'phone':'00000000',
        'email':'', 'consent_version':'local-registration-v1', 'consented_at':'2026-10-27T10:00:00+00:00'},
        'children':[{'display_name':'Synthetic activation child'}]}
    created = service.invoke('register_client', registration, context('1'*32))
    assert created['status'] == 'applied'
    assert service.invoke('list_registrations', {'status':'all','query':'','limit':20,'offset':0},context())['total'] == 1
    with pytest.raises(ApplicationTransportError):
        service.invoke('list_registrations', {'status':'all','query':'','limit':20,'offset':0},context(audience='kiosk'))
    # Recreate the installed local_0001 schema with real client/receipt data.
    # The next standard activation must snapshot it, migrate it and retain IDs.
    supervisor.stop(result.instance_id)
    database = supervisor.root / result.instance_id / 'data/state.sqlite3'
    with sqlite3.connect(database) as db:
        for table in ('local_ui_settings','local_commerce_members','local_commerce_families','local_commerce_quotes','local_commerce_requests','local_commerce_commands','local_commerce_accounts','local_commerce_parents','local_commerce_settings','local_consumption_consents'):
            db.execute('DROP TABLE '+table)
        db.execute('ALTER TABLE local_children DROP COLUMN allowed_articles')
        db.execute('DROP TABLE local_reader_events')
        db.execute('DROP TABLE local_reader_settings')
        db.execute('DROP TABLE local_visit_events')
        db.execute('ALTER TABLE local_registrations DROP COLUMN revision')
        db.execute("DELETE FROM three_mm_schema_migrations WHERE revision IN ('local_0002','local_0003','local_0004','local_0005','local_0006','local_0007')")
    # Standard reactivation stages a real SQLite snapshot and reruns host boot.
    restarted = activate(base, supervisor, payload)
    replay = client(supervisor, restarted.instance_id).invoke('register_client',registration,context('1'*32))
    assert replay == created
    assert client(supervisor, restarted.instance_id).invoke('list_registrations', {'status':'all','query':'','limit':20,'offset':0},context())['total'] == 1
    detail = client(supervisor, restarted.instance_id).invoke('admin_get_client',
        {'registration_id': created['data']['registration_id']}, context(audience='administrator'))
    assert detail['revision'] == 1 and detail['guardian']['display_name'] == registration['guardian']['display_name']
    # The actual public application operation persists the visible setting across
    # a real host restart, independently of the connector configuration dialog.
    admin={**context(audience='administrator'),'permission_ids':['administration_manage']}
    runtime_client=client(supervisor,restarted.instance_id)
    assert runtime_client.invoke('admin_get_settings',{},admin)=={'revision':1,'debug_mode':False}
    saved=runtime_client.invoke('admin_save_settings',{'expected_revision':1,'debug_mode':True},{**admin,'idempotency_key':'2'*32})
    assert saved['status']=='applied' and saved['data']['debug_mode'] is True
    again=activate(base,supervisor,payload)
    assert client(supervisor,again.instance_id).invoke('admin_get_settings',{},admin)=={'revision':2,'debug_mode':True}



def test_scoped_sql_declaration_reproduces_the_original_activation_refusal(runtime):
    base, supervisor = runtime
    output = io.BytesIO()
    with zipfile.ZipFile(io.BytesIO(build_package())) as source, zipfile.ZipFile(output,'w') as archive:
        for name in source.namelist():
            data = source.read(name)
            if name == 'application-extension.json':
                definition = json.loads(data)
                definition['storage']['relational'] = dict(contract_version=1, mode='read_write', limit_class='cooperative_v1',
                    max_database_bytes=32*1024*1024, auxiliary_pause_bytes=4*1024*1024, max_statement_bytes=8192,
                    max_value_bytes=262144, max_result_bytes=512*1024, max_result_rows=512, max_transaction_ms=5000, max_busy_ms=500)
                data = json.dumps(definition).encode()
            archive.writestr(name,data)
    with pytest.raises(ApplicationActivationError, match='relational storage runtime is not implemented'):
        activate(base, supervisor, output.getvalue())
    assert not supervisor.root.exists() and not supervisor.keys.exists()
    assert supervisor.calls == []


def test_own_storage_does_not_replace_prepared_relational_state(runtime):
    base, supervisor = runtime
    instance = application_instance_id('org.3mm.child-center')
    directory = supervisor.root/instance
    directory.mkdir(parents=True)
    marker = directory/'relational.json'
    marker.write_text('{"preserved":"prepared relational state"}')
    with pytest.raises(ApplicationActivationError, match='relational lifecycle requires explicit recovery review'):
        activate(base, supervisor, build_package())
    assert marker.read_text() == '{"preserved":"prepared relational state"}'
    assert supervisor.calls == []


@pytest.mark.parametrize('reader_keys',[(),('READER_DEVICE_ID',),('READER_DEVICE_ID','READER_SECONDARY_DEVICE_ID')])
def test_actual_http_activation_keeps_lifecycle_and_admin_checks(runtime, monkeypatch, reader_keys):
    from types import SimpleNamespace
    from fastapi import FastAPI
    from fastapi.testclient import TestClient
    from sqlalchemy import create_engine, select
    from sqlalchemy.orm import Session
    import backend.database
    from backend.db.base import Base
    from backend.db.authority import CoreAuthorityGuard
    from backend.db.user import User
    from backend.db.device import Device
    from datetime import datetime, timezone
    from backend.db.module import ModulePackage, ApplicationExtensionInstallation
    from backend.routes import application_extensions as routes
    from backend.utils.db_utils import get_db
    from backend.utils.jwt_utils import create_access_token
    from backend.services.module_packages import validate_module_package
    from three_mm_runtime.update_helper_client import UpdateHelperError

    base, supervisor = runtime
    blob = build_package()
    package = validate_module_package(blob)
    archive = base/'candidate.zip'; archive.write_bytes(blob)
    engine = create_engine('sqlite:///'+str(base/'core-test.db'), connect_args={'check_same_thread':False})
    Base.metadata.create_all(engine)
    with Session(engine) as db, db.begin():
        db.add_all([CoreAuthorityGuard(singleton_id=1),
            User(id=1, username='admin', email='admin@example.invalid', hashed_password='x',role='admin'),
            User(id=2, username='staff', email='staff@example.invalid', hashed_password='x',role='user'),
            ModulePackage(id=1, module_id=package.manifest.module_id, version=package.manifest.version,
                sha256=package.sha256, manifest=package.manifest.model_dump(mode='json'),
                size_bytes=len(blob), file_path=str(archive))])
        if reader_keys:
            db.add(Device(id=1,device_id='dev_'+'9'*32,role='standalone',protocol_version='1.0',approved_at=datetime.now(timezone.utc)))
    app = FastAPI(); app.include_router(routes.router)
    def database():
        with Session(engine) as db:
            yield db
    app.dependency_overrides[get_db] = database
    monkeypatch.setattr(routes,'get_settings',lambda:SimpleNamespace(applications=SimpleNamespace(helper_socket=base/'unused.sock')))
    calls=[]
    def helper(_self, sha, user_id, configuration, lifecycle):
        calls.append(sha)
        # Use the actual package activation, migrations, host and signed health.
        try:
            result=activate(base,supervisor,blob,configuration)
        except ApplicationActivationError as error:
            raise UpdateHelperError(str(error)) from error
        # The helper's JSON wire serializes its Path fields as strings.
        return {name: str(value) if isinstance(value, Path) else value for name,value in asdict(result).items()}
    monkeypatch.setattr(routes.UpdateHelperClient,'activate_application_extension',helper)
    url=f'/api/v1/application-extensions/packages/{package.sha256}/activate'
    try:
        with TestClient(app) as http:
            assert http.post(url,json={}).status_code in (401,403)
            staff={'Authorization':'Bearer '+create_access_token('2',{'role':'user'})}
            assert http.post(url,json={},headers=staff).status_code==403
            assert calls==[]
            admin={'Authorization':'Bearer '+create_access_token('1',{'role':'admin'})}
            invalid=http.post(url,json={'configuration':{'READER_DEVICE_ID':'dev_'+'8'*32}},headers=admin)
            assert invalid.status_code==422 and calls==[]
            # Zero devices, primary only, or both selected: omitted optional
            # keys must stay omitted; a supplied unknown source still denies.
            configuration={key:'dev_'+'9'*32 for key in reader_keys}
            missing=http.post(url,json={'configuration':configuration} if reader_keys else {},headers=admin)
            assert missing.status_code==200,missing.text
            with Session(engine) as db:
                installed=db.scalar(select(ApplicationExtensionInstallation))
                for key in ('READER_DEVICE_ID','READER_SECONDARY_DEVICE_ID'):
                    assert installed.configuration.get(key)==configuration.get(key)
            result=missing
            assert result.status_code==200,result.text
            assert result.json()['status']=='active' and result.json()['enabled'] is True
            with Session(engine) as db:
                installed=db.scalar(select(ApplicationExtensionInstallation))
                assert installed.status=='active' and installed.error is None
            assert len(calls)==1
    finally:
        engine.dispose()
