from dataclasses import replace
from datetime import timedelta
import json
import os
from pathlib import Path
import sqlite3
import tempfile
import sys
import pytest
from three_mm_application_sdk import OperationContext, ApplicationContext, ApplicationStorage
from child_center_local.service import create_service, LocalRefusal
from child_center_local.migrations import get_migrations
from test_local_profile import app, child, request, Clock
from local_contract import VERSION
sys.path.insert(0,str(Path(__file__).parents[1]/'tools'))


@pytest.fixture
def tmp_path():
    with tempfile.TemporaryDirectory(prefix='child-center-readers-') as directory:
        yield Path(directory)

DEVICE = 'dev_'+'9'*32


def bound(app):
    invoke, service, storage, clock = app
    service.application = replace(service.application, configuration={'READER_DEVICE_ID':DEVICE})
    _, c = child(invoke)
    invoke('assign_identifier',{'child_id':c['child_id'],'code':'synthetic-private-tag','expected_assignment_id':None},request(2))
    return invoke, service, storage, clock


def enable(invoke, mode='automatic_toggle', revision=1):
    return invoke('set_reader_settings',{'expected_revision':revision,'mode':mode,
        'toggle_ids':['reader.1'] if mode=='automatic_toggle' else [],'entry_ids':['in'] if mode=='directional' else [],
        'exit_ids':['out'] if mode=='directional' else []},request(20+revision),'administrator')


def event(clock, number, reader='reader.1', **changes):
    return {'event_id':'evt_'+f'{number:032x}','device_id':DEVICE,'event_type':'identifier.scan.v1',
        'occurred_at':clock.value.isoformat(),'payload':{'schema_version':1,'capability_id':'identifier.scan.v1',
        'opaque_identifier':'synthetic-private-tag','reader_id':reader,'adapter_kind':'mock','sequence':number,
        'device_health':'ok','scan_metadata':{}},**changes}


def deliver(invoke, value, **context):
    # Exercise the same declared input/output schemas as ordinary invocations.
    from local_contract import descriptors
    from backend.services.application_extensions import validate_operation_payload
    definition = next(o for o in descriptors()[1]['operations'] if o['operation_id']=='process_network_scan')
    service = invoke  # Callback receives a service, not the actor-wrapping human helper.
    validate_operation_payload(value, definition['input_schema'])
    result = service.handle('process_network_scan',value,OperationContext(audience='internal',correlation_id=value['event_id'],
        idempotency_key=value['event_id'],**context))
    validate_operation_payload(result, definition['output_schema'])
    return result


def test_event_toggle_idempotency_restart_and_no_private_scan_in_receipts(app):
    invoke, service, storage, clock = bound(app)
    enable(invoke)
    clock.value += timedelta(seconds=1)
    first = event(clock,1)
    started = deliver(service,first)
    assert started['outcome']=='started'
    assert deliver(create_service(service.application),first)==started
    clock.value += timedelta(seconds=30)
    assert deliver(service,event(clock,2))['outcome']=='paused'
    clock.value += timedelta(minutes=10)
    assert deliver(service,event(clock,3))['outcome']=='resumed'
    details=invoke('get_visit',{'visit_id':started['visit_id'],'offset':0,'limit':20})
    assert [e['kind'] for e in details['events']]==['start','pause','resume']
    assert details['duration_seconds']==30
    with storage.transaction() as db:
        technical=[dict(r) for r in db.execute('SELECT * FROM local_reader_events')]
    assert len(technical)==3 and 'synthetic-private-tag' not in str(technical) and 'Тест' not in str(technical)
    activity=invoke('list_reader_activity',{'offset':0,'limit':20},audience='administrator')
    assert activity['total']==3 and activity['items'][0]['child_name']=='Тест Дете'


def test_directional_mode_does_not_toggle_duplicate_direction_or_replay_old_policy(app):
    invoke, service, _, clock=bound(app)
    enable(invoke,'directional')
    clock.value += timedelta(seconds=1)
    assert deliver(service,event(clock,1,'in'))['outcome']=='started'
    clock.value += timedelta(seconds=1)
    assert deliver(service,event(clock,2,'in'))['outcome']=='already_inside'
    clock.value += timedelta(seconds=1)
    assert deliver(service,event(clock,3,'out'))['outcome']=='paused'
    clock.value += timedelta(seconds=1)
    assert deliver(service,event(clock,4,'out'))['outcome']=='already_outside'
    pending=event(clock,5,'in')
    clock.value += timedelta(seconds=1)
    enable(invoke,'directional',2)
    assert deliver(service,pending)['outcome']=='old_configuration'


@pytest.mark.parametrize('case,expected',[('wrong_source','wrong_source'),('future','future_event'),
    ('degraded','degraded'),('unmapped','unmapped_reader'),('unknown','unknown_bracelet')])
def test_unsafe_or_unmatched_event_is_recorded_without_stay_mutation(app,case,expected):
    invoke,service,storage,clock=bound(app)
    enable(invoke);clock.value += timedelta(seconds=1)
    value=event(clock,1)
    if case=='wrong_source':value['device_id']='dev_'+'8'*32
    if case=='future':value['occurred_at']=(clock.value+timedelta(minutes=5)).isoformat()
    if case=='degraded':value['payload']['device_health']='degraded'
    if case=='unmapped':value['payload']['reader_id']='other'
    if case=='unknown':value['payload']['opaque_identifier']='unknown-private-tag'
    assert deliver(service,value)=={'outcome':expected,'visit_id':None}
    with storage.transaction() as db: assert db.execute('SELECT COUNT(*) FROM local_visits').fetchone()[0]==0


def test_original_event_identity_cannot_be_changed_or_promoted_from_human(app):
    invoke,service,_,clock=bound(app);enable(invoke);clock.value+=timedelta(seconds=1)
    value=event(clock,1);deliver(service,value)
    changed={**value,'occurred_at':(clock.value+timedelta(seconds=1)).isoformat()}
    with pytest.raises(LocalRefusal,match='conflict'):deliver(service,changed)
    with pytest.raises(LocalRefusal,match='Core delivery'):
        service.handle('process_network_scan',value,OperationContext(audience='operator',user_id=42,
            correlation_id=value['event_id'],idempotency_key=value['event_id']))
    with pytest.raises(LocalRefusal,match='Core delivery'):
        service.handle('process_network_scan',value,OperationContext(audience='internal',
            correlation_id='different',idempotency_key=value['event_id']))


def test_settings_denial_cas_and_no_binding_enable_refusal(app):
    invoke,service,*_=app
    with pytest.raises(LocalRefusal,match='Select reader devices'):enable(invoke)
    service.application=replace(service.application,configuration={'READER_DEVICE_ID':DEVICE})
    # The original definite refusal owns its request ID; a new command is explicit.
    payload={'expected_revision':1,'mode':'automatic_toggle','toggle_ids':['reader.1'],'entry_ids':[],'exit_ids':[]}
    invoke('set_reader_settings',payload,request(50),'administrator')
    with pytest.raises(LocalRefusal,match='changed'):invoke('set_reader_settings',payload,request(51),'administrator')
    with pytest.raises(LocalRefusal,match='audience'):invoke('get_reader_settings',{},audience='kiosk')
    with pytest.raises(LocalRefusal,match='audience'):invoke('set_reader_settings',payload,request(52),'operator')


def test_out_of_order_event_and_event_commit_is_atomic(app):
    invoke,service,storage,clock=bound(app);enable(invoke);clock.value+=timedelta(seconds=1)
    value=event(clock,1)
    with storage.transaction() as db:
        db.execute("CREATE TRIGGER synthetic_event_failure BEFORE INSERT ON local_reader_events BEGIN SELECT RAISE(ABORT,'synthetic'); END")
    with pytest.raises(sqlite3.IntegrityError):deliver(service,value)
    with storage.transaction() as db:
        assert db.execute('SELECT COUNT(*) FROM local_visits').fetchone()[0]==0
        assert db.execute('SELECT COUNT(*) FROM local_visit_events').fetchone()[0]==0
        db.execute('DROP TRIGGER synthetic_event_failure')
    assert deliver(service,value)['outcome']=='started'
    clock.value += timedelta(seconds=10)
    assert deliver(service,event(clock,3))['outcome']=='paused'
    older=event(clock,2,occurred_at=(clock.value-timedelta(seconds=5)).isoformat())
    assert deliver(service,older)['outcome']=='late_event'


def test_delayed_scan_cannot_start_a_stay_for_new_tag_owner(app):
    invoke,service,storage,clock=bound(app);enable(invoke)
    clock.value+=timedelta(seconds=1)
    queued=event(clock,1)
    with storage.transaction() as db:
        assignment=dict(db.execute('SELECT * FROM local_bracelets WHERE retired_at IS NULL').fetchone())
    clock.value+=timedelta(seconds=1)
    invoke('retire_identifier',{'child_id':assignment['child_id'],'expected_assignment_id':assignment['assignment_id']},request(60))
    _,new_child=child(invoke,61)
    invoke('assign_identifier',{'child_id':new_child['child_id'],'code':'synthetic-private-tag','expected_assignment_id':None},request(62))
    assert deliver(service,queued)['outcome']=='late_event'
    with storage.transaction() as db:
        assert db.execute('SELECT COUNT(*) FROM local_visits').fetchone()[0]==0


def test_reader_migration_preserves_existing_stay_tables_and_starts_disabled(tmp_path):
    storage=ApplicationStorage(tmp_path/'reader-upgrade');storage.migrate(get_migrations(),'local_0003')
    service=create_service(ApplicationContext(module_id='org.3mm.child-center',version=VERSION,configuration={},
        data_dir=storage.data_dir,storage=storage,clock=Clock()))
    with storage.transaction() as db:
        from test_local_profile import historical_client
        historical_client(db,service.now())
        before=[dict(r) for r in db.execute('SELECT * FROM local_registrations')]
    storage.migrate(get_migrations(),'local_0004')
    with storage.transaction() as db:
        assert before==[dict(r) for r in db.execute('SELECT * FROM local_registrations')]
        assert service.readers.get_reader_settings(db,{},None)['mode']=='disabled'
    storage.migrate(get_migrations(),'local_0004')


from backend.tests.test_application_connector_settings import fresh as core_setup
from backend.tests.test_application_authority_management import installed as managed, source_subject, source_installed, identity


def test_real_core_event_grant_signed_host_delivery_deduplication_and_revoke(core_setup, monkeypatch):
    from datetime import datetime, timezone
    from sqlalchemy import update, select
    from sqlalchemy.orm import Session
    import backend
    from backend.db.module import ModulePackage, ApplicationExtensionInstallation as Installation, ApplicationEventDelivery
    from backend.db.device import DeviceCapabilityProvider, DeviceEvent
    from backend.services.module_packages import validate_module_package
    from backend.services.compiled_ui import compile_ui_package
    from backend.services import application_events as broker
    from backend.tests.test_application_events import pump
    from backend.tests.test_application_authority_sources import DEVICE as CORE_DEVICE
    from backend.config import ApplicationRuntimeSettings
    from build_local_package import build_package
    from application_process_check import disposable_runtime, activate, client

    s=core_setup;blob=build_package();s.validated=validate_module_package(blob)
    s.archive=s.root/'modules'/(s.validated.sha256+'.zip');s.archive.write_bytes(blob)
    toolchain=s.root/'reader-compiler';toolchain.mkdir()
    compiler=Path(backend.__file__).parents[1]/'frontend/compiler/compile-ui-extension.mjs'
    (toolchain/'compiler.mjs').write_bytes(compiler.read_bytes())
    (toolchain/'node_modules').symlink_to(Path(os.environ['THREE_MM_FRONTEND_ROOT'])/'node_modules',target_is_directory=True)
    monkeypatch.setenv('COMPILED_UI_COMPILER_SCRIPT',str(toolchain/'compiler.mjs'))
    monkeypatch.setenv('COMPILED_UI_ARTIFACTS_DIR',str(s.root/'compiled-readers'))
    build=compile_ui_package(blob,s.validated)
    configuration={'READER_DEVICE_ID':CORE_DEVICE,'READER_SECONDARY_DEVICE_ID':CORE_DEVICE}
    with disposable_runtime(s.root/'reader-host-logs') as (base,supervisor):
        runtime=activate(base,supervisor,blob,configuration)
        native_client=client(supervisor,runtime.instance_id)
        human={'audience':'administrator','user_id':42,'subject_id':'usr_'+'4'*32,'correlation_id':'reader-fixture'}
        created=native_client.invoke('register_client',{'guardian':{'display_name':'Synthetic Parent','phone':'000',
            'email':'','consent_version':'v1','consented_at':datetime.now(timezone.utc).isoformat()},
            'children':[{'display_name':'Synthetic Child'}]}, {**human,'idempotency_key':identity()})['data']
        child_id=native_client.invoke('get_registration',{'registration_id':created['registration_id']},human)['children'][0]['child_id']
        native_client.invoke('assign_identifier',{'child_id':child_id,'code':'synthetic-event-tag','expected_assignment_id':None},
            {**human,'idempotency_key':identity()})
        native_client.invoke('set_reader_settings',{'expected_revision':1,'mode':'automatic_toggle','toggle_ids':['network.1'],
            'entry_ids':[],'exit_ids':[]},{**human,'idempotency_key':identity()})
        with Session(s.engine) as db,db.begin():
            db.execute(update(ModulePackage).where(ModulePackage.id==1).values(module_id=s.validated.manifest.module_id,
                version=VERSION,sha256=s.validated.sha256,manifest=s.validated.manifest.model_dump(mode='json'),
                file_path=str(s.archive),size_bytes=len(blob)))
            db.add(Installation(id=1,module_id=s.validated.manifest.module_id,module_package_id=1,
                instance_id=runtime.instance_id,socket_path=str(runtime.socket_path),active_version=VERSION,
                status='disabled',enabled=False,configuration=configuration))
            # Model an existing stopped installation, reviewed through real Core
            # adoption; no fabricated sealed grant or permission callback.
            provider=db.scalar(select(DeviceCapabilityProvider))
            provider.configured_capability_ids=['identifier.scan.v1']
            provider.capabilities=[{'capability_id':'identifier.scan.v1','metadata':{}}]
            # Current Core pins event admission to fresh health for the exact
            # selected declaration. The fixture's old GPIO digest is not valid
            # after replacing its capability with the synthetic reader.
            from backend.services.device_capability_registry import capability_catalog
            from backend.db.device import Device, DeviceCapabilityHealth
            db.flush()
            declaration=next(row for row in capability_catalog(db,db.get(Device,provider.device_id))
                if row.capability_id=='identifier.scan.v1')
            health=db.scalar(select(DeviceCapabilityHealth).where(DeviceCapabilityHealth.device_id==provider.device_id,
                DeviceCapabilityHealth.provider_type==provider.provider_type,DeviceCapabilityHealth.provider_id==provider.provider_id))
            if health is None:
                health=DeviceCapabilityHealth(device_id=provider.device_id,provider_type=provider.provider_type,provider_id=provider.provider_id)
                db.add(health)
            health.observed_at=datetime.now(timezone.utc)
            health.expires_at=datetime.now(timezone.utc)+timedelta(minutes=5)
            health.report={'declaration_digest':declaration.declaration_digest,
                'capabilities':[{'capability_id':'identifier.scan.v1','healthy':True}]}
        review=s.manager.record_native_review(1,actor_token=s.token,request_id=identity(),
            artifact_sha256=s.validated.sha256,review_document_sha256='b'*64,native_code_review_completed=True,
            accepts_native_host_risk=True,accepts_same_origin_ui_risk=True,built_ui_sha256=build.built_ui_sha256)
        def grant():
            plan=s.manager.create_review(1,actor_token=s.token,request_id=identity(),native_review_id=review['native_review_id'],
                scopes=['event:reader_primary','event:reader_secondary'])
            for decision in ('approve','apply'):
                plan=s.manager.decide(1,actor_token=s.token,request_id=identity(),plan_id=plan['plan_id'],
                    expected_revision=plan['revision'],fingerprint=plan['fingerprint'],decision=decision)
        grant()
        with s.engine.begin() as db:
            db.execute(update(Installation).where(Installation.id==1).values(status='active',enabled=True,authority_epoch=identity()))
        grant()
        settings=ApplicationRuntimeSettings(key_root=supervisor.keys)
        def send_event():
            with Session(s.engine) as db:
                row=DeviceEvent(event_id='evt_'+identity(),device_id=1,event_type='identifier.scan.v1',
                    occurred_at=datetime.now(timezone.utc)+timedelta(milliseconds=2),payload={'schema_version':1,
                    'capability_id':'identifier.scan.v1','opaque_identifier':'synthetic-event-tag','reader_id':'network.1',
                    'adapter_kind':'mock','sequence':1,'device_health':'ok','scan_metadata':{}})
                db.add(row);db.commit();db.refresh(row)
                broker.enqueue_application_event(db,row,settings);pump(db,settings)
                return row.id
        original=send_event()
        activity=native_client.invoke('list_reader_activity',{'offset':0,'limit':20},human)
        assert activity['total']==1 and activity['items'][0]['outcome']=='started'
        with Session(s.engine) as db:
            deliveries=list(db.scalars(select(ApplicationEventDelivery)))
            assert len(deliveries)==2 and all(row.status=='acknowledged' for row in deliveries)
            broker.enqueue_application_event(db,db.get(DeviceEvent,original),settings);pump(db,settings)
        assert native_client.invoke('list_reader_activity',{'offset':0,'limit':20},human)['total']==1
        status=s.manager.inspect(1)
        s.manager.revoke(1,actor_token=s.token,request_id=identity(),expected_revision=status['grant_record_revision'])
        send_event()
        assert native_client.invoke('list_reader_activity',{'offset':0,'limit':20},human)['total']==1
