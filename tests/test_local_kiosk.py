"""Exact Child Center ZIP: real Core pairing/catalog/HTTP -> signed native host.

Disposable Linux database/keys/process; no Raspberry or browser credentials.
"""
import base64
import os
from pathlib import Path
import sys
import tempfile
from contextlib import contextmanager

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient
from sqlalchemy import select, update
from sqlalchemy.orm import Session, sessionmaker

from backend.tests.test_application_connector_settings import fresh as core_setup
from backend.tests.test_application_authority_management import installed as managed, source_subject, source_installed, identity
from test_local_profile import registration

sys.path.insert(0,str(Path(__file__).parents[1]/'tools'))


@pytest.fixture
def tmp_path():
    with tempfile.TemporaryDirectory(prefix='cc-kiosk-') as directory:
        yield Path(directory)


@contextmanager
def response_runtime(root):
    import threading
    from three_mm_platform_runtime.responses import ApplicationResponses
    server=ApplicationResponses(root/'response.sock',root/'unused.sock',core_uid=os.geteuid())
    server.start();worker=threading.Thread(target=server.serve_forever,daemon=True);worker.start()
    try:yield server
    finally:server.close();worker.join(timeout=2)


def test_exact_package_pair_recover_register_renew_isolate_and_revoke(core_setup,monkeypatch):
    import backend
    import backend.database
    from backend.config import ApplicationRuntimeSettings
    from backend.db.module import ModulePackage, ApplicationExtensionInstallation as Installation
    from backend.routes import application_extensions as routes, modules
    from backend.services.compiled_ui import compile_ui_package
    from backend.services.module_packages import validate_module_package
    from backend.utils.db_utils import get_db
    from build_local_package import build_package
    from local_contract import VERSION
    from application_process_check import disposable_runtime,activate,client

    s=core_setup
    # Match configured_manager's production contention budget; the shared Core
    # fixture otherwise intentionally uses fail-fast locks for policy tests.
    s.manager=type(s.manager)(s.engine,uploads_root=s.root,core_version='0.3.0',
        review_key_directory=s.key_directory,key_lock_wait_seconds=0.25)
    blob=build_package();s.validated=validate_module_package(blob)
    s.archive=s.root/'modules'/(s.validated.sha256+'.zip');s.archive.write_bytes(blob)
    toolchain=s.root/'kiosk-compiler';toolchain.mkdir()
    (toolchain/'compiler.mjs').write_bytes((Path(backend.__file__).parents[1]/'frontend/compiler/compile-ui-extension.mjs').read_bytes())
    (toolchain/'node_modules').symlink_to(Path(os.environ['THREE_MM_FRONTEND_ROOT'])/'node_modules',target_is_directory=True)
    monkeypatch.setenv('COMPILED_UI_COMPILER_SCRIPT',str(toolchain/'compiler.mjs'))
    monkeypatch.setenv('COMPILED_UI_ARTIFACTS_DIR',str(s.root/'compiled-kiosk'))
    build=compile_ui_package(blob,s.validated)
    with disposable_runtime(s.root/'kiosk-host-logs') as (base,supervisor),response_runtime(base) as responses:
        runtime=activate(base,supervisor,blob)
        with Session(s.engine) as db,db.begin():
            db.execute(update(ModulePackage).where(ModulePackage.id==1).values(module_id=s.validated.manifest.module_id,
                version=VERSION,sha256=s.validated.sha256,manifest=s.validated.manifest.model_dump(mode='json'),
                file_path=str(s.archive),size_bytes=len(blob)))
            db.add(Installation(id=1,module_id=s.validated.manifest.module_id,module_package_id=1,
                instance_id=runtime.instance_id,socket_path=str(runtime.socket_path),active_version=VERSION,
                status='disabled',enabled=False,configuration={}))
        review=s.manager.record_native_review(1,actor_token=s.token,request_id=identity(),artifact_sha256=s.validated.sha256,
            review_document_sha256='b'*64,native_code_review_completed=True,accepts_native_host_risk=True,
            accepts_same_origin_ui_risk=True,built_ui_sha256=build.built_ui_sha256)
        def grant():
            plan=s.manager.create_review(1,actor_token=s.token,request_id=identity(),native_review_id=review['native_review_id'],scopes=[])
            for decision in ('approve','apply'):
                plan=s.manager.decide(1,actor_token=s.token,request_id=identity(),plan_id=plan['plan_id'],
                    expected_revision=plan['revision'],fingerprint=plan['fingerprint'],decision=decision)
        grant()
        with s.engine.begin() as db:
            db.execute(update(Installation).where(Installation.id==1).values(status='active',enabled=True,authority_epoch=identity()))
        grant()
        import pwd
        settings=ApplicationRuntimeSettings(root=supervisor.root,key_root=supervisor.keys,helper_socket=base/'unused.sock',
            runtime_user=pwd.getpwuid(os.geteuid()).pw_name,application_response_socket=responses.path)
        monkeypatch.setattr(routes,'get_settings',lambda:type('Settings',(),{'applications':settings})())
        monkeypatch.setattr(backend.database,'SessionLocal',sessionmaker(s.engine))
        app=FastAPI();app.include_router(routes.router);app.include_router(modules.router)
        def database():
            with Session(s.engine) as db:yield db
        app.dependency_overrides[get_db]=database
        prefix='/api/v1/application-extensions/'+s.validated.manifest.module_id
        admin={'Authorization':'Bearer '+s.token}
        binding={'host_version':1,'entrypoint_id':'local_kiosk','artifact_sha256':s.validated.sha256,'built_ui_sha256':build.built_ui_sha256}
        with TestClient(app) as http:
            # Pages refresh independent public-host reads together. Exercise the
            # real HTTP admission/completion path, rather than a mocked UI host.
            from concurrent.futures import ThreadPoolExecutor
            def read(operation):
                payload={'status':'all','query':'','offset':0,'limit':20} if operation=='list_registrations' else {}
                return http.post(prefix+'/operations/'+operation,headers=admin,json={'payload':payload,
                    'ui_context':{**binding,'entrypoint_id':'local_admin'}})
            with ThreadPoolExecutor(max_workers=2) as reads:
                for response in reads.map(read,['list_registrations','get_reader_settings']*4):
                    assert response.status_code==200,response.text
            def pair(label):
                body={'request_id':identity(),'label':label,'expires_in_minutes':15}
                response=http.post(prefix+'/kiosk/enrollments',json=body,headers=admin)
                assert response.status_code==201,response.text
                assert http.post(prefix+'/kiosk/enrollments',json=body,headers=admin).json()==response.json()
                claim={'request_id':identity(),'recovery_proof':base64.urlsafe_b64encode(os.urandom(32)).decode().rstrip('='),'code':response.json()['code']}
                connected=http.post(prefix+'/kiosk/enrollments/claim',json=claim)
                assert connected.status_code==200,connected.text
                recovered=http.post(prefix+'/kiosk/enrollments/claim',json=claim)
                assert recovered.status_code==200 and recovered.json()['terminal_id']==connected.json()['terminal_id']
                assert recovered.json()['credential']==connected.json()['credential']
                assert http.post(prefix+'/kiosk/enrollments/claim',json={**claim,'request_id':identity()}).status_code==409
                return connected.json()
            first=pair('Synthetic kiosk A');second=pair('Synthetic kiosk B')
            def headers(terminal):return {'Authorization':'Bearer '+terminal['access_token']}
            catalog=http.get('/api/v1/modules/compiled-ui/catalog',headers=headers(first))
            assert catalog.status_code==200,catalog.text
            entries=[entry for item in catalog.json()['items'] for entry in item['entrypoints']]
            assert len(entries)==1 and entries[0]['application_audience']=='kiosk'
            request_id=identity()
            def invoke(terminal,operation,payload,key=None):
                return http.post(prefix+'/kiosk/operations/'+operation,headers=headers(terminal),json={
                    'payload':payload,'idempotency_key':key,'ui_context':binding})
            created=invoke(first,'submit_registration',registration(),request_id)
            assert created.status_code==200,created.text
            original=created.json()
            outcome={'request_id':request_id,'operation_id':'submit_registration'}
            saved=invoke(first,'kiosk_request_outcome',outcome)
            assert saved.status_code==200 and saved.json()['status']=='confirmed',saved.text
            foreign=invoke(second,'kiosk_request_outcome',outcome)
            assert foreign.status_code==200 and foreign.json()['status']=='unknown',foreign.text
            renewed=http.post(prefix+'/kiosk/sessions',json={key:first[key] for key in ('terminal_id','credential')})
            assert renewed.status_code==200,renewed.text
            first.update(renewed.json())
            assert invoke(first,'submit_registration',registration(),request_id).json()==original
            denied=invoke(first,'list_registrations',{'status':'all','query':'','offset':0,'limit':20})
            assert denied.status_code in (403,409),denied.text
            assert http.delete(prefix+'/kiosk/terminals/'+first['terminal_id'],headers=admin).status_code==200
            assert invoke(first,'kiosk_request_outcome',outcome).status_code==401
            assert http.post(prefix+'/kiosk/sessions',json={key:first[key] for key in ('terminal_id','credential')}).status_code==401
            assert invoke(second,'kiosk_request_outcome',outcome).json()['status']=='unknown'
        native=client(supervisor,runtime.instance_id)
        records=native.invoke('list_registrations',{'status':'all','query':'','offset':0,'limit':20},
            {'audience':'administrator','user_id':42,'subject_id':'usr_'+'4'*32,'correlation_id':'kiosk-acceptance'})
        assert records['total']==1 and records['items'][0]['status']=='submitted'
