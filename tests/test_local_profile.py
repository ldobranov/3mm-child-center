"""SDK-managed own SQLite; package activation is tested in test_local_activation.py."""
from dataclasses import replace
from datetime import datetime, timedelta, timezone
import importlib.util
import io
import json
from pathlib import Path
import sqlite3
import sys
import zipfile

import pytest
from three_mm_application_sdk import ApplicationContext, ApplicationStorage, OperationContext
from three_mm_protocol.application_extension import ApplicationExtensionV1
from backend.services.application_extensions import validate_operation_payload
from backend.services.module_packages import validate_module_package
from child_center_local.service import create_service, LocalRefusal
from child_center_local.migrations import get_migrations

ROOT = Path(__file__).parents[1]
sys.path.insert(0, str(ROOT))
from build_local_package import build_package, package_files
from local_contract import VERSION


class Clock:
    def __init__(self):
        self.value = datetime(2026, 10, 27, 10, tzinfo=timezone.utc)
    def now(self):
        return self.value


@pytest.fixture
def app(tmp_path):
    definition = ApplicationExtensionV1.model_validate_json(package_files()['application-extension.json'])
    initial = ApplicationStorage(tmp_path / 'local')
    initial.migrate(get_migrations(), 'local_0007')
    clock = Clock()
    service = create_service(ApplicationContext(module_id='org.3mm.child-center', version=VERSION,
        data_dir=initial.data_dir, configuration={}, storage=initial, clock=clock))
    def invoke(name, payload, key=None, audience='operator', user=42, terminal='1'*32, permissions=None):
        context = OperationContext(audience=audience, correlation_id='local-test', user_id=user if audience in ('operator','administrator') else None,
            idempotency_key=key,terminal_id=terminal if audience=='kiosk' else None,
            subject_id='usr_'+f'{user:032x}' if audience in ('operator','administrator') else None,
            permission_ids=tuple(permissions if permissions is not None else [p.permission_id for p in definition.permissions]))
        operation = next(o for o in definition.operations if o.operation_id == name)
        validate_operation_payload(payload, operation.input_schema)
        result = service.handle(name, payload, context)
        validate_operation_payload(result, operation.output_schema)
        if operation.kind == 'command':
            if result['status'] == 'rejected':
                raise LocalRefusal(result['message'])
            return result['data']
        return result
    return invoke, service, initial, clock


def request(n):
    return f'{n:032x}'


def historical_client(db,now):
    """Seed an old schema without invoking a newer application implementation."""
    db.execute('''INSERT INTO local_registrations(registration_id,status,guardian_name,phone,email,
        consent_version,consented_at,search_text,created_at) VALUES(?,?,?,?,?,?,?,?,?)''',
        ('reg_'+'a'*32,'approved','Synthetic','000','','v1',now,'synthetic',now))
    db.execute('INSERT INTO local_children VALUES(?,?,?)',('child_'+'b'*32,'reg_'+'a'*32,'Synthetic Child'))


def test_kiosk_request_outcomes_belong_to_verified_terminal_not_only_audience(app):
    invoke,service,*_=app
    first=invoke('submit_registration',registration(),request(90),'kiosk',terminal='1'*32)
    identity={'request_id':request(90),'operation_id':'submit_registration'}
    assert invoke('kiosk_request_outcome',identity,audience='kiosk',terminal='1'*32)['status']=='confirmed'
    assert invoke('kiosk_request_outcome',identity,audience='kiosk',terminal='2'*32)['status']=='unknown'
    second=invoke('submit_registration',registration(),request(90),'kiosk',terminal='2'*32)
    assert second['registration_id']!=first['registration_id']
    with pytest.raises(LocalRefusal,match='Core kiosk identity'):
        service.handle('submit_registration',registration(),OperationContext(audience='kiosk',correlation_id='test',idempotency_key=request(91)))


def test_named_scan_confirmation_journal_and_original_request_replay(app):
    invoke, _, _, clock = app
    _, c = child(invoke)
    invoke('assign_identifier', {'child_id':c['child_id'],'code':'named','expected_assignment_id':None}, request(2))
    first = invoke('preview_scan', {'code':'named'})
    assert first['action'] == 'start' and first['child_name'] == 'Тест Дете'
    payload = {'code':'named','preview_token':first['preview_token']}
    started = invoke('confirm_scan', payload, request(3))
    assert invoke('confirm_scan', payload, request(3)) == started
    clock.value += timedelta(seconds=30)
    preview = invoke('preview_scan', {'code':'named'})
    invoke('confirm_scan', {'code':'named','preview_token':preview['preview_token']}, request(4))
    clock.value += timedelta(minutes=10)
    preview = invoke('preview_scan', {'code':'named'})
    invoke('confirm_scan', {'code':'named','preview_token':preview['preview_token']}, request(5))
    clock.value += timedelta(seconds=30)
    invoke('finish_visit', finish_payload(invoke, started['visit_id']), request(6))
    detail = invoke('get_visit', {'visit_id':started['visit_id'],'offset':0,'limit':20})
    assert detail['timeline_complete'] and detail['duration_seconds'] == 60
    assert [e['kind'] for e in detail['events']] == ['start','pause','resume','finish']
    assert [e['duration_seconds'] for e in detail['events']] == [0,30,30,60]
    exported = json.loads(invoke('export_personal_data', {'registration_id': invoke('list_registrations', {'status':'all','query':'','offset':0,'limit':20})['items'][0]['registration_id']}, request(7), 'administrator')['document_json'])
    assert len(exported['children'][0]['stay_events'][0]['events']) == 4


def test_stale_scan_refuses_reassignment_and_same_clock_state_cycle(app):
    invoke, *_ = app
    _, c = child(invoke)
    assigned = invoke('assign_identifier', {'child_id':c['child_id'],'code':'swap','expected_assignment_id':None}, request(2))
    old = invoke('preview_scan', {'code':'swap'})
    invoke('retire_identifier', {'child_id':c['child_id'],'expected_assignment_id':assigned['assignment_id']}, request(3))
    invoke('assign_identifier', {'child_id':c['child_id'],'code':'swap','expected_assignment_id':None}, request(4))
    with pytest.raises(LocalRefusal, match='Scan changed'):
        invoke('confirm_scan', {'code':'swap','preview_token':old['preview_token']}, request(5))
    preview = invoke('preview_scan', {'code':'swap'})
    invoke('confirm_scan', {'code':'swap','preview_token':preview['preview_token']}, request(6))
    old_inside = invoke('preview_scan', {'code':'swap'})
    invoke('confirm_scan', {'code':'swap','preview_token':old_inside['preview_token']}, request(7))
    paused = invoke('preview_scan', {'code':'swap'})
    invoke('confirm_scan', {'code':'swap','preview_token':paused['preview_token']}, request(8))
    with pytest.raises(LocalRefusal, match='Scan changed'):
        invoke('confirm_scan', {'code':'swap','preview_token':old_inside['preview_token']}, request(9))


def test_history_filters_sofia_dst_calendar_days_and_rejects_invalid_range(app):
    invoke, _, storage, _ = app
    _, c = child(invoke)
    timestamps = ['2026-10-24T20:59:59+00:00','2026-10-24T21:00:00+00:00',
                  '2026-10-25T21:59:59+00:00','2026-10-25T22:00:00+00:00']
    with storage.transaction() as db:
        for i, stamp in enumerate(timestamps):
            db.execute("INSERT INTO local_visits VALUES (?,?, 'closed',?,NULL,0,?,?)", ('visit_'+f'{i:032x}',c['child_id'],stamp,stamp,stamp))
    filters = {'state':'closed','query':'тест родител','started_from':'2026-10-25','started_to':'2026-10-25','limit':20,'offset':0}
    assert invoke('list_visits', filters)['total'] == 2  # DST day is 25 hours.
    assert invoke('list_visits', {**filters,'query':'%'})['total'] == 0
    assert invoke('list_visits', {**filters,'query':'0000000000'})['total'] == 0
    with pytest.raises(LocalRefusal, match='date range'):
        invoke('list_visits', {**filters,'started_from':'2026-10-26'})


def test_history_migration_preserves_existing_data_and_marks_partial_timeline(tmp_path):
    storage = ApplicationStorage(tmp_path/'history-upgrade')
    storage.migrate(get_migrations(), 'local_0002')
    service = create_service(ApplicationContext(module_id='org.3mm.child-center',version=VERSION,data_dir=storage.data_dir,
        configuration={},storage=storage,clock=Clock()))
    with storage.transaction() as db:
        historical_client(db,service.now())
        child_id = db.execute('SELECT child_id FROM local_children').fetchone()[0]
        visit_id = 'visit_'+'f'*32
        db.execute("INSERT INTO local_visits VALUES (?,?, 'closed',?,NULL,123000000,?,?)", (visit_id,child_id,service.now(),service.now(),service.now()))
        before = [dict(r) for r in db.execute('SELECT * FROM local_visits')]
    storage.migrate(get_migrations(), 'local_0003')
    with storage.transaction() as db:
        assert [dict(r) for r in db.execute('SELECT * FROM local_visits')] == before
        detail = service.get_visit(db, {'visit_id':visit_id,'offset':0,'limit':20}, None)
        assert not detail['timeline_complete'] and detail['event_total'] == 1
        assert detail['events'][0]['kind'] == 'snapshot' and detail['duration_seconds'] == 123
    with pytest.raises(ValueError, match='not forward-compatible'):
        storage.migrate(get_migrations(), 'local_0002')


def test_scan_timeline_failure_rolls_back_the_complete_mutation(app, monkeypatch):
    invoke, service, storage, _ = app
    _, c = child(invoke)
    invoke('assign_identifier', {'child_id':c['child_id'],'code':'atomic','expected_assignment_id':None}, request(2))
    preview = invoke('preview_scan', {'code':'atomic'})
    def failure(*_): raise sqlite3.OperationalError('synthetic history failure')
    monkeypatch.setattr(service,'record_transition',failure)
    with pytest.raises(sqlite3.OperationalError):
        invoke('confirm_scan', {'code':'atomic','preview_token':preview['preview_token']}, request(3))
    with storage.transaction() as db:
        assert db.execute('SELECT COUNT(*) FROM local_visits').fetchone()[0] == 0
        assert db.execute('SELECT COUNT(*) FROM local_requests').fetchone()[0] == 2


def test_stay_detail_paginates_timeline_and_denies_kiosk(app):
    invoke, *_ = app
    _, c = child(invoke)
    invoke('assign_identifier', {'child_id':c['child_id'],'code':'pages','expected_assignment_id':None}, request(2))
    visit = None
    for i in range(21):
        preview = invoke('preview_scan', {'code':'pages'})
        visit = invoke('confirm_scan', {'code':'pages','preview_token':preview['preview_token']}, request(10+i))['visit_id']
    first = invoke('get_visit', {'visit_id':visit,'offset':0,'limit':20})
    last = invoke('get_visit', {'visit_id':visit,'offset':20,'limit':20})
    assert first['event_total'] == 21 and len(first['events']) == 20 and len(last['events']) == 1
    assert len({e['event_id'] for e in first['events']+last['events']}) == 21
    with pytest.raises(LocalRefusal, match='audience'):
        invoke('get_visit', {'visit_id':visit,'offset':0,'limit':20}, audience='kiosk')
    with pytest.raises(LocalRefusal, match='audience'):
        invoke('preview_scan', {'code':'pages'}, audience='kiosk')


def test_administration_correction_cas_receipts_and_unchanged_relationships(app):
    invoke, service, storage, _ = app
    created, c = child(invoke)
    invoke('assign_identifier', {'child_id': c['child_id'], 'code': 'admin-check', 'expected_assignment_id': None}, request(2))
    visit = invoke('scan_bracelet', {'code': 'admin-check', 'action': 'start', 'expected_visit_id': None}, request(3))
    detail = invoke('admin_get_client', {'registration_id': created['registration_id']}, audience='administrator')
    payload = {'registration_id': detail['registration_id'], 'expected_revision': detail['revision'],
               'guardian': {'display_name': 'Коригиран Родител', 'phone': '123', 'email': ''},
               'children': [{'child_id': c['child_id'], 'display_name': 'Коригирано Дете'}]}
    result = invoke('admin_update_client', payload, request(4), 'administrator')
    assert result == {'status': 'updated', 'revision': 2}
    assert invoke('admin_update_client', payload, request(4), 'administrator') == result
    with pytest.raises(LocalRefusal, match='Client changed'):
        invoke('admin_update_client', payload, request(5), 'administrator')
    current = invoke('admin_get_client', {'registration_id': detail['registration_id']}, audience='administrator')
    assert current['consent_version'] == detail['consent_version'] and current['consented_at'] == detail['consented_at']
    assert current['children'][0]['assignment_id'] == detail['children'][0]['assignment_id']
    assert invoke('list_visits', {'state': 'active', 'limit': 20, 'offset': 0})['items'][0]['visit_id'] == visit['visit_id']
    assert invoke('admin_list_clients', {'status': 'all', 'query': 'коригирано дете', 'offset': 0, 'limit': 20}, audience='administrator')['total'] == 1
    outcome = invoke('admin_request_outcome', {'request_id': request(4), 'operation_id': 'admin_update_client'}, audience='administrator')
    assert json.loads(outcome['result_json'])['data'] == result
    assert invoke('admin_request_outcome', {'request_id': request(4), 'operation_id': 'admin_update_client'}, audience='administrator', user=99)['status'] == 'unknown'
    with storage.transaction() as db:
        assert 'Коригира' not in db.execute('SELECT group_concat(result_json) FROM local_requests').fetchone()[0]


def test_administration_denies_other_audiences_and_preserves_child_identity(app):
    invoke, *_ = app
    created, c = child(invoke)
    subject = {'registration_id': created['registration_id']}
    payload = {**subject, 'expected_revision': 1, 'guardian': {'display_name': 'Changed', 'phone': '123', 'email': ''},
               'children': [{'child_id': 'child_' + 'a'*32, 'display_name': 'Wrong child'}]}
    for audience in ('operator', 'kiosk'):
        for operation, data, key in [('admin_get_client', subject, None), ('admin_update_client', payload, request(2))]:
            with pytest.raises(LocalRefusal, match='audience'):
                invoke(operation, data, key, audience)
    with pytest.raises(LocalRefusal, match='existing children'):
        invoke('admin_update_client', payload, request(2), 'administrator')
    assert invoke('admin_get_client', subject, audience='administrator')['guardian']['display_name'] == registration()['guardian']['display_name']
    invoke('erase_personal_data', {**subject, 'confirmed': True}, request(3), 'administrator')
    payload['children'][0]['child_id'] = c['child_id']
    with pytest.raises(LocalRefusal, match='not found'):
        invoke('admin_update_client', payload, request(4), 'administrator')


def test_administration_migration_preserves_0001_data_and_refuses_silent_downgrade(tmp_path):
    storage = ApplicationStorage(tmp_path / 'upgrade')
    storage.migrate(get_migrations(), 'local_0001')
    service = create_service(ApplicationContext(module_id='org.3mm.child-center', version=VERSION,
        data_dir=storage.data_dir, configuration={}, storage=storage, clock=Clock()))
    context = OperationContext(audience='operator', user_id=42, correlation_id='old-schema', idempotency_key=request(1))
    with storage.transaction() as db:historical_client(db,service.now())
    created = {'registration_id':'reg_'+'a'*32}
    detail = service.handle('get_registration', {'registration_id': created['registration_id']}, replace(context, idempotency_key=None))
    c = detail['children'][0]
    service.handle('assign_identifier', {'child_id': c['child_id'], 'code': 'upgrade-check', 'expected_assignment_id': None}, replace(context, idempotency_key=request(2)))
    # Historical schema has no transition journal; seed its original visit shape.
    with storage.transaction() as db:
        db.execute("INSERT INTO local_visits VALUES (?,?, 'active',?,?,0,?,NULL)",
            ('visit_'+'a'*32,c['child_id'],service.now(),service.now(),service.now()))
    tables = ['local_registrations', 'local_children', 'local_bracelets', 'local_visits', 'local_requests', 'local_audit']
    with storage.transaction() as db:
        before = {table: [dict(row) for row in db.execute('SELECT * FROM ' + table)] for table in tables}
    storage.migrate(get_migrations(), 'local_0002')
    storage.migrate(get_migrations(), 'local_0002')
    with storage.transaction() as db:
        after = {table: [dict(row) for row in db.execute('SELECT * FROM ' + table)] for table in tables}
    assert after['local_registrations'][0].pop('revision') == 1
    assert after == before
    with pytest.raises(ValueError, match='not forward-compatible'):
        storage.migrate(get_migrations(), 'local_0001')
    assert storage.status()['revision'] == 'local_0002'


def registration(name='Тест Родител'):
    return {'guardian': {'display_name': name, 'phone': '0000000000', 'email': '',
            'consent_version': 'local-registration-v1', 'consented_at': '2026-10-27T10:00:00+00:00'},
            'children': [{'display_name': 'Тест Дете'}]}


def child(invoke, key=1):
    result = invoke('register_client', registration(), request(key))
    detail = invoke('get_registration', {'registration_id': result['registration_id']})
    return result, detail['children'][0]


def finish_payload(invoke, visit_id):
    visit = next(v for v in invoke('list_visits', {'state':'active','limit':20,'offset':0})['items'] if v['visit_id'] == visit_id)
    return {'visit_id':visit_id, 'expected_transition_at':visit['last_transition_at'], 'expected_phase':visit['phase']}


def test_candidate_package_validates_against_current_core_and_is_deterministic():
    payload = build_package()
    assert payload == build_package()
    package = validate_module_package(payload, architecture='aarch64')
    definition = package.application_extension
    assert definition.service.sdk_version == '1.3'
    assert definition.storage.relational is None
    assert not definition.jobs and not definition.command_bindings and len(definition.event_subscriptions) == 2
    assert len(definition.connectors) == 1 and definition.connectors[0].supports_mutations
    assert set(definition.optional_resources) == {'connector:barsy_api','event:reader_primary','event:reader_secondary'}
    with zipfile.ZipFile(io.BytesIO(payload)) as archive:
        wheel = archive.read(definition.service.artifact)
        with zipfile.ZipFile(io.BytesIO(wheel)) as inner:
            assert all(name.startswith(('child_center_local/', 'child_center_local-')) for name in inner.namelist())
        for name in archive.namelist():
            if name.endswith(('.vue', '.ts')):
                source = archive.read(name)
                assert b'fetch(' not in source and b'authToken' not in source and b'/api/v1/' not in source


def test_pending_kiosk_registration_approval_search_and_denial(app):
    invoke, service, initial, clock = app
    created = invoke('submit_registration', registration(), request(1), 'kiosk')
    assert created['status'] == 'submitted'
    assert invoke('submit_registration', registration(), request(1), 'kiosk') == created
    outcome = invoke('kiosk_request_outcome', {'request_id': request(1), 'operation_id': 'submit_registration'}, audience='kiosk')
    assert outcome['status'] == 'confirmed'
    with pytest.raises(LocalRefusal, match='audience'):
        invoke('list_registrations', {'query':'', 'status':'all', 'offset':0, 'limit':20}, audience='kiosk')
    detail = invoke('get_registration', {'registration_id':created['registration_id']})
    with pytest.raises(LocalRefusal, match='approved'):
        invoke('assign_identifier', {'child_id':detail['children'][0]['child_id'], 'code':'test', 'expected_assignment_id':None}, request(2))
    invoke('approve_registration', {'registration_id': created['registration_id']}, request(3))
    listed = invoke('list_registrations', {'query':'тест родител', 'status':'approved', 'offset':0, 'limit':20})
    assert listed['total'] == 1


def test_receipt_actor_isolation_conflict_and_restart(app):
    invoke, service, initial, clock = app
    result, _ = child(invoke)
    with pytest.raises(LocalRefusal, match='reused'):
        invoke('register_client', registration('Other'), request(1))
    assert invoke('request_outcome', {'request_id':request(1), 'operation_id':'register_client'}, user=99)['status'] == 'unknown'
    assert invoke('request_outcome', {'request_id':request(1), 'operation_id':'register_client'})['status'] == 'confirmed'
    reopened = create_service(service.application)
    result2 = reopened.handle('register_client', registration(), OperationContext(audience='operator', user_id=42, correlation_id='restart', idempotency_key=request(1)))
    assert result2['data'] == result
    assert invoke('list_registrations', {'query':'', 'status':'all', 'offset':0, 'limit':20})['total'] == 1


def test_stay_pause_resume_round_once_and_no_duplicate_transition(app):
    invoke, service, initial, clock = app
    reg, c = child(invoke)
    assigned = invoke('assign_identifier', {'child_id':c['child_id'], 'code':'scan-1', 'expected_assignment_id':None}, request(2))
    started = invoke('scan_bracelet', {'code':'scan-1','action':'start','expected_visit_id':None}, request(3))
    visit = started['visit_id']
    clock.value += timedelta(minutes=12, seconds=20)
    paused = invoke('scan_bracelet', {'code':'scan-1','action':'pause','expected_visit_id':visit}, request(4))
    clock.value += timedelta(hours=1)
    assert invoke('scan_bracelet', {'code':'scan-1','action':'pause','expected_visit_id':visit}, request(4)) == paused
    invoke('scan_bracelet', {'code':'scan-1','action':'resume','expected_visit_id':visit}, request(5))
    clock.value += timedelta(minutes=17, seconds=50)
    ending = finish_payload(invoke, visit)
    finished = invoke('finish_visit', ending, request(6))
    assert finished == {'status':'closed', 'duration_seconds':1810, 'rounded_minutes':31}
    assert invoke('finish_visit', ending, request(6)) == finished
    listed = invoke('list_visits', {'state':'closed','limit':20,'offset':0})
    assert listed['items'][0]['duration_seconds'] == 1810
    with pytest.raises(LocalRefusal, match='changed'):
        invoke('scan_bracelet', {'code':'scan-1','action':'resume','expected_visit_id':visit}, request(7))


def test_assignment_cas_duplicate_and_retirement(app):
    invoke, *_ = app
    _, c = child(invoke)
    assigned = invoke('assign_identifier', {'child_id':c['child_id'],'code':'scan-1','expected_assignment_id':None}, request(2))
    with pytest.raises(LocalRefusal, match='changed'):
        invoke('assign_identifier', {'child_id':c['child_id'],'code':'scan-2','expected_assignment_id':None}, request(3))
    invoke('retire_identifier', {'child_id':c['child_id'],'expected_assignment_id':assigned['assignment_id']}, request(4))
    with pytest.raises(LocalRefusal, match='Unknown'):
        invoke('scan_bracelet', {'code':'scan-1','action':'start','expected_visit_id':None}, request(5))


def test_privacy_export_erasure_no_pii_in_receipts_and_active_stay_block(app):
    invoke, service, initial, clock = app
    reg, c = child(invoke)
    subject = {'registration_id':reg['registration_id']}
    invoke('assign_identifier', {'child_id':c['child_id'],'code':'secret-bracelet','expected_assignment_id':None}, request(2))
    started = invoke('scan_bracelet', {'code':'secret-bracelet','action':'start','expected_visit_id':None}, request(3))
    exported = invoke('export_personal_data', subject, request(4), 'administrator')
    assert 'Тест Родител' in exported['document_json'] and 'secret-bracelet' in exported['document_json']
    with pytest.raises(LocalRefusal, match='active'):
        invoke('erase_personal_data', {**subject,'confirmed':True}, request(5), 'administrator')
    invoke('finish_visit', finish_payload(invoke, started['visit_id']), request(6))
    invoke('erase_personal_data', {**subject,'confirmed':True}, request(7), 'administrator')
    with pytest.raises(LocalRefusal, match='not found'):
        invoke('export_personal_data', subject, request(4), 'administrator')
    with initial.transaction() as db:
        assert db.execute('SELECT phone FROM local_registrations').fetchone()[0] == ''
        assert db.execute('SELECT code FROM local_bracelets').fetchone()[0] != 'secret-bracelet'
        assert all('Тест' not in row[0] for row in db.execute('SELECT result_json FROM local_requests').fetchall())


def test_legacy_schema_refuses_without_reset(tmp_path):
    db = sqlite3.connect(tmp_path / 'legacy.sqlite3')
    db.execute('CREATE TABLE registrations (name TEXT)')
    db.execute("INSERT INTO registrations VALUES ('preserved')")
    with pytest.raises(ValueError, match='reviewed import'):
        get_migrations()[0].apply(db)
    assert db.execute('SELECT name FROM registrations').fetchone()[0] == 'preserved'


def test_backwards_clock_cannot_reduce_a_stay(app):
    invoke, service, initial, clock = app
    _, c = child(invoke)
    invoke('assign_identifier', {'child_id':c['child_id'],'code':'clock','expected_assignment_id':None}, request(2))
    visit = invoke('scan_bracelet', {'code':'clock','action':'start','expected_visit_id':None}, request(3))
    clock.value -= timedelta(seconds=1)
    with pytest.raises(LocalRefusal, match='clock'):
        invoke('finish_visit', finish_payload(invoke, visit['visit_id']), request(4))


def test_health_checks_own_migrated_storage_and_rejection_has_durable_receipt(app):
    invoke, service, initial, clock = app
    assert invoke('health', {}, audience='internal') == {'status':'ready'}
    with pytest.raises(LocalRefusal, match='Unknown'):
        invoke('scan_bracelet', {'code':'missing','action':'start','expected_visit_id':None}, request(8))
    outcome = invoke('request_outcome', {'request_id':request(8), 'operation_id':'scan_bracelet'})
    assert outcome['status'] == 'confirmed'
    assert json.loads(outcome['result_json'])['status'] == 'rejected'


def test_stale_finish_refuses_after_another_operator_pauses(app):
    invoke, service, initial, clock = app
    _, c = child(invoke)
    invoke('assign_identifier', {'child_id':c['child_id'],'code':'stale','expected_assignment_id':None}, request(2))
    visit = invoke('scan_bracelet', {'code':'stale','action':'start','expected_visit_id':None}, request(3))['visit_id']
    displayed = finish_payload(invoke, visit)
    clock.value += timedelta(seconds=30)
    invoke('scan_bracelet', {'code':'stale','action':'pause','expected_visit_id':visit}, request(4), user=99)
    with pytest.raises(LocalRefusal, match='changed'):
        invoke('finish_visit', displayed, request(5))
    assert invoke('list_visits', {'state':'active','limit':20,'offset':0})['items'][0]['phase'] == 'paused'
    result = invoke('finish_visit', finish_payload(invoke, visit), request(6))
    assert result['duration_seconds'] == 30
    assert invoke('visit_request_outcome', {'request_id':request(6), 'operation_id':'finish_visit'})['status'] == 'confirmed'


def test_new_visit_cannot_overlap_a_closed_stay_after_clock_rollback(app):
    invoke, service, initial, clock = app
    _, c = child(invoke)
    invoke('assign_identifier', {'child_id':c['child_id'],'code':'overlap','expected_assignment_id':None}, request(2))
    visit = invoke('scan_bracelet', {'code':'overlap','action':'start','expected_visit_id':None}, request(3))['visit_id']
    clock.value += timedelta(minutes=5)
    invoke('finish_visit', finish_payload(invoke, visit), request(4))
    clock.value -= timedelta(minutes=1)
    with pytest.raises(LocalRefusal, match='Clock moved backwards'):
        invoke('scan_bracelet', {'code':'overlap','action':'start','expected_visit_id':None}, request(5))
    assert invoke('list_visits', {'state':'active','limit':20,'offset':0})['total'] == 0



@pytest.mark.parametrize('enabled',[False,True])
def test_persisted_ui_preferences_are_shared_across_existing_permissions_without_configuration_leakage(app,enabled):
    invoke,service,storage,_=app
    service.application=replace(service.application,configuration={'DEBUG_MODE':True,
        'BARSY_CREDENTIAL_REF':'secret_'+'a'*32,'BARSY_API_URL':'https://private.example.invalid'})
    assert invoke('admin_get_settings',{},audience='administrator')=={'revision':1,'debug_mode':False}
    invoke('admin_save_settings',{'expected_revision':1,'debug_mode':enabled},request(991),audience='administrator')
    for audience in ('operator','administrator'):
        for permission in ('registrations_manage','children_manage','visits_manage','privacy_manage','administration_manage','barsy_manage','readers_manage','commerce_manage','payments_manage'):
            assert invoke('ui_preferences_'+permission,{},audience=audience,permissions=[permission])=={'debug_mode':enabled}
    with pytest.raises(LocalRefusal,match='denied'):
        invoke('ui_preferences_registrations_manage',{},permissions=[])
    for audience in ('kiosk','internal'):
        with pytest.raises(LocalRefusal,match='audience'):invoke('ui_preferences_registrations_manage',{},audience=audience)
    with pytest.raises(LocalRefusal,match='actor'):
        service.handle('ui_preferences_registrations_manage',{},OperationContext(audience='operator',correlation_id='ui-preferences'))


def test_admin_settings_compare_and_set_receipt_replay_and_actor_isolation(app):
    invoke,service,storage,_=app
    payload={'expected_revision':1,'debug_mode':True};key=request(990)
    first=invoke('admin_save_settings',payload,key,audience='administrator')
    assert first=={'revision':2,'debug_mode':True}
    assert invoke('admin_save_settings',payload,key,audience='administrator')==first
    with pytest.raises(LocalRefusal,match='settings changed'):
        invoke('admin_save_settings',{'expected_revision':1,'debug_mode':False},request(989),audience='administrator')
    receipt={'request_id':key,'operation_id':'admin_save_settings'}
    assert invoke('admin_request_outcome',receipt,audience='administrator')['status']=='confirmed'
    assert invoke('admin_request_outcome',receipt,audience='administrator',user=99)['status']=='unknown'
    for name,body,key_ in [('admin_get_settings',{},None),('admin_save_settings',payload,key)]:
        with pytest.raises(LocalRefusal,match='denied'):invoke(name,body,key_,audience='administrator',permissions=[])
        with pytest.raises(LocalRefusal,match='denied'):invoke(name,body,key_,audience='operator')
    assert invoke('admin_get_settings',{},audience='administrator')==first
    invoke('admin_save_settings',{'expected_revision':2,'debug_mode':False},request(988),audience='administrator')
    assert invoke('admin_get_settings',{},audience='administrator')=={'revision':3,'debug_mode':False}


def test_ui_settings_migrate_from_v6_atomically_without_rewriting_business_records(app):
    from three_mm_application_sdk import ApplicationMigration
    from child_center_local.migrations import presentation_settings
    invoke,service,storage,clock=app
    created,c=child(invoke)
    invoke('assign_identifier',{'child_id':c['child_id'],'code':'MIGRATION','expected_assignment_id':None},request(980))
    visit=invoke('scan_bracelet',{'code':'MIGRATION','action':'start','expected_visit_id':None},request(981))['visit_id']
    with storage.transaction() as db:
        db.execute("INSERT INTO local_commerce_accounts(visit_id,place_id,client_id,identity,account_id,state,time_article_id,unit) VALUES(?,7,101,'retained-id',44,'open',28,'minutes')",(visit,))
        db.execute('DROP TABLE local_ui_settings')
        db.execute("DELETE FROM three_mm_schema_migrations WHERE revision='local_0007'")
        tables=[r[0] for r in db.execute("SELECT name FROM sqlite_master WHERE type='table' AND name LIKE 'local_%'")]
        before={name:[tuple(r) for r in db.execute('SELECT * FROM '+name)] for name in tables}
    def fail(db):
        presentation_settings(db)
        raise RuntimeError('UI migration rollback')
    with pytest.raises(RuntimeError,match='migration rollback'):
        storage.migrate([*get_migrations()[:6],ApplicationMigration('local_0007',fail)],'local_0007')
    assert storage.status()['revision']=='local_0006'
    with storage.transaction() as db:assert not db.execute("SELECT 1 FROM sqlite_master WHERE name='local_ui_settings'").fetchone()
    storage.migrate(get_migrations(),'local_0007')
    with storage.transaction() as db:
        assert {name:[tuple(r) for r in db.execute('SELECT * FROM '+name)] for name in tables}==before
        assert tuple(db.execute('SELECT * FROM local_ui_settings').fetchone())==(1,1,0)
        snapshot='\n'.join(db.iterdump())
    storage.migrate(get_migrations(),'local_0007')
    with storage.transaction() as db:assert '\n'.join(db.iterdump())==snapshot


@pytest.mark.parametrize('old_marker',[False,True])
def test_current_installation_configuration_keeps_its_connection_during_debug_ui_upgrade(old_marker):
    from backend.services.application_configuration import resolve_application_configuration
    files=package_files();manifest=json.loads(files['manifest.json'])
    definition=ApplicationExtensionV1.model_validate_json(files['application-extension.json'])
    existing={'DEBUG_MODE':old_marker,'BARSY_API_URL':'https://private.example.invalid','BARSY_CREDENTIAL_REF':'secret_'+'a'*32}
    assert resolve_application_configuration(manifest['configuration_schema'],manifest['configuration_defaults'],definition,existing=existing)==existing
    assert 'DEBUG_MODE' not in manifest['configuration_defaults']
