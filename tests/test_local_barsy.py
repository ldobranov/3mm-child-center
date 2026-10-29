"""Bounded Barsy reads, real package setup/authority/broker and local fake HTTP."""
import base64
from dataclasses import replace
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
import json
import os
from pathlib import Path
import tempfile
from types import SimpleNamespace
import threading
import urllib.request

import pytest
from three_mm_application_sdk import ApplicationPlatformClient, ApplicationPlatformError
from child_center_local.barsy import MAX_RESPONSE
from test_local_profile import app, registration, request


@pytest.fixture
def tmp_path():
    # Core policy keys require real POSIX ownership/modes, not WSL /mnt/c modes.
    with tempfile.TemporaryDirectory(prefix='child-center-broker-') as directory:
        yield Path(directory)


class Responses:
    def __init__(self, data):
        self.data, self.calls = data, []
    def connector_request(self, connector_id, **options):
        self.calls.append((connector_id, options))
        return {'outcome': 'succeeded', 'http_status': 200,
                'body_base64': base64.b64encode(json.dumps(self.data).encode()).decode()}


def platform(app, broker):
    invoke, service, *_ = app
    service.barsy.application = replace(service.application, platform=broker)
    return invoke


def test_unconfigured_barsy_does_not_block_local_operations_or_health(app):
    invoke, *_ = app
    assert invoke('health', {}, audience='internal') == {'status': 'ready'}
    assert invoke('barsy_check', {}, audience='administrator') == {'status': 'unavailable', 'pos_id': None}
    assert invoke('register_client', registration(), request(21))['status'] == 'approved'


def test_categories_paginate_and_use_documented_parameters(app):
    data=[{'cat_id':i,'cat_name':f'Category {i}'} for i in range(1,26)]
    broker=Responses([{'cat_id':-1,'cat_name':'Uncategorized','parent_id':-1},*data])
    invoke=platform(app,broker)
    first=invoke('barsy_categories',{'offset':0},audience='administrator')
    last=invoke('barsy_categories',{'offset':20},audience='administrator')
    assert first['status']=='ready' and first['has_more'] and len(first['items'])==20
    assert last['status']=='ready' and not last['has_more'] and len(last['items'])==5
    assert first['items'][0]=={'category_id':1,'label':'Category 1'}
    selected=invoke('barsy_categories',{'offset':0,'category_id':25},audience='administrator')
    assert selected['items']==[{'category_id':25,'label':'Category 25'}]
    assert all(call['path']=='/endpoints/json/Categories_getlist' and call['method']=='GET'
        and json.loads(call['body'])=={'filters':{},'extra_properties':[]} for _,call in broker.calls)


@pytest.mark.parametrize('data',[[],{}, {'error':'PRIVATE'}, {'1':{'cat_id':True,'cat_name':'invalid'}},
    {'1':{'cat_id':1,'cat_name':'One'},'2':{'cat_id':1,'cat_name':'Duplicate'}},
    {'1':{'cat_id':1,'cat_name':''}},[{'cat_id':-2,'cat_name':'Invalid category'}],
    [{'cat_id':-1,'error':'PRIVATE'}]])
def test_empty_and_malformed_category_catalogues_are_distinct(app,data):
    broker=Responses(data);invoke=platform(app,broker)
    result=invoke('barsy_categories',{'offset':0},audience='administrator')
    assert result=={'status':'ready' if data==[] else 'invalid_response','items':[],'has_more':False}
    assert len(broker.calls)==1 and 'PRIVATE' not in str(result)


def test_owner_category_response_omits_uncategorized_without_losing_real_categories(app):
    # Exact response structure supplied from the owner's Barsy, including its
    # negative service ID and null metadata. No credentials or customer data.
    data=[{'cat_id':-1,'cat_path':None,'cat_name':'Некатегоризирани','parent_id':-1,'cat_path_ids':None},
        {'cat_id':1,'cat_path':'Бар','cat_name':'Бар','parent_id':None,'cat_path_ids':'1;'},
        {'cat_id':2,'cat_path':'КУХНЯ','cat_name':'КУХНЯ','parent_id':None,'cat_path_ids':'2;'},
        {'cat_id':3,'cat_path':'Игрална зала','cat_name':'Игрална зала','parent_id':None,'cat_path_ids':'3;'}]
    broker=Responses(data);invoke=platform(app,broker)
    assert invoke('barsy_categories',{'offset':0},audience='administrator')=={'status':'ready','items':[
        {'category_id':1,'label':'Бар'},{'category_id':2,'label':'КУХНЯ'},{'category_id':3,'label':'Игрална зала'}],
        'has_more':False}
    assert invoke('barsy_categories',{'offset':0,'category_id':1},audience='administrator')['items']==[{'category_id':1,'label':'Бар'}]
    broker.data=data[:1]
    assert invoke('barsy_categories',{'offset':0},audience='administrator')=={'status':'ready','items':[],'has_more':False}


def test_selected_place_names_are_filtered_before_pagination_without_changing_barsy_request(app):
    broker=Responses([{'place_id':i,'place_type':0,'name':f'Room {i}'} for i in range(1,71)])
    invoke=platform(app,broker);selected=list(range(31,63))
    first=invoke('barsy_places',{'offset':0,'place_ids':selected},audience='administrator')
    second=invoke('barsy_places',{'offset':20,'place_ids':selected},audience='administrator')
    assert first['has_more'] and not second['has_more']
    assert [r['place_id'] for r in first['items']+second['items']]==selected
    assert first['items'][0]['label']=='Room 31'
    assert all(json.loads(call['body'])=={} for _,call in broker.calls)


def test_selected_time_article_lookup_is_bounded_and_rejects_wrong_identity(app):
    broker=Responses([{'article_id':28,'article_name':'Play room minutes'}])
    invoke=platform(app,broker)
    result=invoke('barsy_articles',{'query':'','offset':0,'article_id':28},audience='administrator')
    assert result['items']==[{'article_id':28,'label':'Play room minutes'}]
    request_body=json.loads(broker.calls[0][1]['body'])
    assert request_body['filters']['article_id']==28 and request_body['length']==2
    broker.data=[{'article_id':29,'article_name':'Wrong article'}]
    assert invoke('barsy_articles',{'query':'','offset':0,'article_id':28},audience='administrator')['status']=='invalid_response'


def test_barsy_filters_pagination_safe_projection_and_audience_denial(app):
    rows = [{'article_id':str(i), 'article_name':f'Article {i}', 'sale_price':99} for i in range(1, 51)]
    broker = Responses(rows)
    invoke = platform(app, broker)
    for audience in ('operator', 'kiosk'):
        with pytest.raises(RuntimeError, match='audience'):
            invoke('barsy_articles', {'query':'needle','offset':50}, audience=audience)
    assert not broker.calls
    result = invoke('barsy_articles', {'query':'needle','offset':50}, audience='administrator')
    assert result['has_more'] and result['items'][0] == {'article_id':1,'label':'Article 1'}
    connector, call = broker.calls[0]
    assert connector == 'barsy_api' and call['method'] == 'GET' and call['path'] == '/endpoints/json/Articles_getlist'
    assert json.loads(call['body']) == {'filters':{'delete_flag':0,'is_for_sale':1,'article_name':'needle'},
        'offset':50,'length':50,'order_by':{'article_id':'asc'},'extra_properties':{'common':'min'}}
    assert call['headers'] == {'Content-Type':'application/json'}
    assert len(broker.calls) == 1
    broker.data = [{'place_id':1,'place_type':1}, {'place_id':2,'place_type':0,'name':'Table','accounts_count':'0'}]
    assert invoke('barsy_places', {'offset':0}, audience='administrator')['items'] == [{'place_id':2,'label':'Table','accounts_count':0}]
    broker.data = [{'amount_type_id':1,'value_precision':'3','time_interval':'0'}]
    assert invoke('barsy_units', {'offset':0}, audience='administrator')['items'] == [{'unit_id':1,'precision':3,'time_interval':0}]


@pytest.mark.parametrize('data', [None, {'error':'private external text'}, [True],
    [{'article_id':True,'article_name':'bad'}], [{'article_id':1,'article_name':''}],
    [{'article_id':1,'article_name':'ok'}, {'article_id':'1','article_name':'duplicate'}],
    [{'article_id':9007199254740992,'article_name':'overflow'}]])
def test_invalid_barsy_data_never_returns_partial_or_external_error(app, data):
    broker = Responses(data)
    invoke = platform(app, broker)
    assert invoke('barsy_articles', {'query':'','offset':0}, audience='administrator') == {
        'status':'invalid_response','items':[],'has_more':False}
    assert len(broker.calls) == 1


@pytest.mark.parametrize('mode', ['denied','timeout','redirect','invalid_base64','oversize','invalid_json'])
def test_broker_failure_is_redacted_and_never_retried(app, mode):
    class Failed(Responses):
        def connector_request(self, *args, **kwargs):
            self.calls.append((args, kwargs))
            if mode in ('denied','timeout'):
                raise ApplicationPlatformError('PRIVATE_DIAGNOSTIC', reason='access_denied')
            if mode == 'redirect': return {'outcome':'succeeded','http_status':302,'body_base64':'e30='}
            body = '!!!' if mode == 'invalid_base64' else 'A' * (MAX_RESPONSE*2) if mode == 'oversize' else base64.b64encode(b'{invalid').decode()
            return {'outcome':'succeeded','http_status':200,'body_base64':body}
    broker = Failed(None)
    invoke = platform(app, broker)
    result = invoke('barsy_check', {}, audience='administrator')
    assert result['status'] == ('unavailable' if mode in ('denied','timeout','redirect') else 'invalid_response')
    assert result['pos_id'] is None and 'PRIVATE' not in str(result) and len(broker.calls) == 1


# Use Core's established disposable policy-key/session fixtures. No installed
# database, network worker, credentials or user device is involved.
from backend.tests.test_application_connector_settings import fresh as core_setup
from backend.tests.test_application_authority_management import installed as managed, source_subject, source_installed, identity


def test_exact_package_core_settings_grant_fake_http_and_revocation(core_setup, app, monkeypatch):
    from sqlalchemy import update
    from sqlalchemy.orm import Session
    from backend.db.module import ModulePackage, ApplicationExtensionInstallation as Installation
    from backend.services.module_packages import validate_module_package
    from backend.services.compiled_ui import compile_ui_package
    from backend.services import application_connector_settings as settings
    from backend.services.application_connectors import ApplicationConnectorError
    from backend.tests.connector_helpers import execute_connector_request
    from build_local_package import build_package
    from local_contract import VERSION

    s = core_setup
    blob = build_package()
    s.validated = validate_module_package(blob)
    s.archive = s.root / 'modules' / (s.validated.sha256 + '.zip')
    s.archive.write_bytes(blob)
    # Compile the exact ZIP using an unchanged copy of Core's real compiler and
    # its existing dependency installation. Native/UI approval requires real
    # protected build provenance, not a mocked build hash.
    import backend
    compiler = Path(backend.__file__).parents[1] / 'frontend/compiler/compile-ui-extension.mjs'
    toolchain = s.root / 'ui-toolchain'; toolchain.mkdir()
    (toolchain/'compiler.mjs').write_bytes(compiler.read_bytes())
    (toolchain/'node_modules').symlink_to(Path(os.environ['THREE_MM_FRONTEND_ROOT'])/'node_modules', target_is_directory=True)
    monkeypatch.setenv('COMPILED_UI_COMPILER_SCRIPT', str(toolchain/'compiler.mjs'))
    monkeypatch.setenv('COMPILED_UI_ARTIFACTS_DIR', str(s.root/'compiled'))
    artifact = compile_ui_package(blob, s.validated)
    assert artifact.built_ui_sha256
    with s.engine.begin() as db:
        db.execute(update(ModulePackage).where(ModulePackage.id == 1).values(module_id=s.validated.manifest.module_id,
            version=VERSION, sha256=s.validated.sha256, manifest=s.validated.manifest.model_dump(mode='json'),
            file_path=str(s.archive), size_bytes=len(blob)))

    seen = []
    parents=[]
    class FakeBarsy(BaseHTTPRequestHandler):
        def do_GET(self):
            seen.append((self.path, self.headers.get('Authorization'), self.rfile.read(int(self.headers.get('Content-Length',0)))))
            body = json.dumps(parents).encode() if self.path.endswith('Clients_getlist') else b'{"pos_id":17}'
            self.send_response(200); self.send_header('Content-Type','application/json'); self.send_header('Content-Length',str(len(body))); self.end_headers(); self.wfile.write(body)
        def do_POST(self):
            raw=self.rfile.read(int(self.headers.get('Content-Length',0)))
            seen.append((self.path,self.headers.get('Authorization'),raw))
            assert self.path.endswith('Clients_createsmart')
            parents.append({'client_id':101,**json.loads(raw)['client']})
            self.send_response(200);self.send_header('Content-Length','3');self.end_headers();self.wfile.write(b'101')
        def log_message(self, *_): pass
    http = ThreadingHTTPServer(('127.0.0.1',0), FakeBarsy)
    thread = threading.Thread(target=http.serve_forever, daemon=True); thread.start()
    origin = f'http://127.0.0.1:{http.server_port}'
    try:
        before = settings.inspect(s.manager, s.validated.sha256, s.token)
        assert before['installation_id'] is None and before['connectors'][0]['state'] == 'unconfigured'
        configured = settings.configure(s.manager, s.validated.sha256, 'barsy_api', settings.ConnectorSettingsRequest(
            request_id=identity(), expected_snapshot=before['snapshot'], action='save', destination_origin=origin,
            create_credential=True, credential_label='Synthetic Barsy', credential={'username':'fake','password':'SYNTHETIC_ONLY'}), s.token)
        assert configured['status'] == 'applied' and not seen
        with Session(s.engine) as db:
            installation = db.get(Installation, 1)
            assert not installation.enabled and installation.active_version is None
        native = s.manager.record_native_review(1, actor_token=s.token, request_id=identity(),
            artifact_sha256=s.validated.sha256, review_document_sha256='b'*64,
            native_code_review_completed=True, accepts_native_host_risk=True,
            accepts_same_origin_ui_risk=True, built_ui_sha256=artifact.built_ui_sha256)
        def grant():
            plan = s.manager.create_review(1, actor_token=s.token, request_id=identity(),
                native_review_id=native['native_review_id'], scopes=['connector:barsy_api'])
            for decision in ('approve','apply'):
                plan = s.manager.decide(1, actor_token=s.token, request_id=identity(), plan_id=plan['plan_id'],
                    expected_revision=plan['revision'], fingerprint=plan['fingerprint'], decision=decision)
        grant()
        with s.engine.begin() as db:
            db.execute(update(Installation).where(Installation.id == 1).values(enabled=True,status='active',active_version=VERSION,authority_epoch=identity()))
        grant()

        def transport(method, url, *, headers, data, timeout, allow_redirects):
            assert url.startswith(origin + '/') and method in ('GET','POST') and allow_redirects is False
            with urllib.request.urlopen(urllib.request.Request(url, data=data, method=method, headers=headers), timeout=timeout) as response:
                return SimpleNamespace(status_code=response.status, content=response.read(), headers=dict(response.headers))
        class Broker(ApplicationPlatformClient):
            def _call(self, operation, payload):
                assert operation == 'connector.request'
                try:
                    with Session(s.engine) as db:
                        result = execute_connector_request(db, db.get(Installation,1), transport=transport,
                            connector_id=payload['connector_id'], request_id=payload['connector_request_id'], method=payload['method'],
                            path=payload['path'], body=base64.b64decode(payload['body_base64']), headers=payload['headers'], idempotency_key=payload['idempotency_key'])
                        db.commit(); return result
                except ApplicationConnectorError:
                    raise ApplicationPlatformError('Unavailable', reason='access_denied') from None
        broker=Broker(s.root/'unused.sock', 'synthetic', b'x'*32)
        invoke = platform(app, broker)
        assert invoke('barsy_check', {}, audience='administrator') == {'status':'ready','pos_id':17}
        assert len(seen) == 1 and seen[0][0] == '/endpoints/json/Poses_getcurrent'
        assert seen[0][1] == 'Basic ' + base64.b64encode(b'fake:SYNTHETIC_ONLY').decode()
        # The exact mutating declaration, native approval and public SDK reach a
        # local HTTP fake. A repeated command cannot send Clients_createsmart twice.
        invoke,service,*_=app
        service.application=replace(service.application,platform=broker)
        from test_local_profile import child
        _,c=child(invoke)
        invoke('assign_identifier',{'child_id':c['child_id'],'code':'broker-commerce','expected_assignment_id':None},request(2))
        visit=invoke('scan_bracelet',{'code':'broker-commerce','action':'start','expected_visit_id':None},request(3))['visit_id']
        command=invoke('commerce_prepare',{'visit_id':visit,'kind':'parent','place_id':None,'article_id':None,'quantity':'1','consumer':'guardian'},request(4))['command_id']
        result=invoke('commerce_execute',{'command_id':command},request(5))
        assert result['state']=='uncertain'
        assert invoke('commerce_execute',{'command_id':command},request(6))==result
        invoke('commerce_check',{'command_id':command,'account_id':None,'reviewed':False},request(7))
        assert sum(row[0].endswith('Clients_createsmart') for row in seen)==1
        count=len(seen)
        state = settings.inspect(s.manager, s.validated.sha256, s.token)
        settings.configure(s.manager, s.validated.sha256, 'barsy_api', settings.ConnectorSettingsRequest(
            request_id=identity(), expected_snapshot=state['snapshot'], action='revoke', confirm_credential_change=True,
            secret_ref=state['connectors'][0]['credential']['secret_ref']), s.token)
        assert invoke('barsy_check', {}, audience='administrator')['status'] == 'unavailable'
        assert len(seen) == count
        result=invoke('commerce_prepare',{'visit_id':visit,'kind':'parent','place_id':None,'article_id':None,'quantity':'1','consumer':'guardian'},request(8))
        with pytest.raises(RuntimeError,match='commerce_unavailable'):
            invoke('commerce_execute',{'command_id':result['command_id']},request(9))
        assert len(seen)==count
    finally:
        http.shutdown(); http.server_close(); thread.join(timeout=2)
