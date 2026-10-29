"""Interactive business acceptance against a synthetic Barsy, never a live POS."""
import base64
from dataclasses import replace
from datetime import timedelta
from decimal import Decimal
import json
import sqlite3
import pytest
from three_mm_application_sdk import ApplicationContext, ApplicationStorage, ApplicationPlatformError, OperationContext
from child_center_local.migrations import get_migrations,interactive_commerce
from child_center_local.service import create_service, LocalRefusal
from test_local_profile import app, child, request, finish_payload, historical_client


class Barsy:
    def __init__(self,storage):
        self.storage=storage;self.calls=[];self.clients={};self.accounts={};self.lose=False;self.fail=False
        self.precision=3;self.timer=0;self.payment_type=1;self.hook=None
        self.place_type=101;self.place_timer_hint=None
        self.can_read_card_on_get=True;self.can_read_card_on_list=True

    @property
    def sends(self):return [c for c in self.calls if c[0]=='POST']

    def connector_request(self,connector_id,**options):
        assert connector_id=='barsy_api'
        # Proves callers never hold a SQLite write transaction over the network.
        with self.storage.transaction() as db:db.execute('UPDATE local_commerce_settings SET revision=revision')
        method=options['method'];endpoint=options['path'].split('/')[-1];body=json.loads(options['body'])
        self.calls.append((method,endpoint,body,options))
        if self.hook:self.hook(endpoint)
        if self.fail:raise ApplicationPlatformError('PRIVATE password',reason='access_denied')
        result=None
        if endpoint=='Clients_getlist':
            result=[dict(c) for c in self.clients.values() if c['client_code']==body['filters']['client_code_match']]
            if not self.can_read_card_on_list:
                for row in result:row.pop('client_code',None)
        elif endpoint=='Clients_createsmart':
            result=101+len(self.clients);self.clients[result]={'client_id':result,**body['client']}
        elif endpoint=='Clients_get':
            result=dict(self.clients[body['client_id']])
            if not body.get('extra_properties',{}).get('client_code') or not self.can_read_card_on_get:result.pop('client_code',None)
        elif endpoint=='Places_getlist':
            result=[{'place_id':7,'place_type':self.place_type,'place_num':1,'name':'Play room'}]
            if self.place_timer_hint is not None:result[0]['time_calculation']=self.place_timer_hint
        elif endpoint=='Accounts_getlist':result=[a for a in self.accounts.values() if a['place_id']==body['filters']['place_id']
            and a['client_id']==body['filters']['client_id'] and a['status']==0][:body['length']]
        elif endpoint=='Accounts_create':
            result=201+len(self.accounts);self.accounts[result]={'account_id':result,**body['account'],'status':0,'time_calculation':self.timer,
                'orders':[],'total_real':'0.00','total_paid':'0.00','total_remain':'0.00','currency_id':1,'currency_rate':1,'fx':1,'last_order_num':0}
        elif endpoint=='Accounts_get':result=self.accounts[body['account_id']]
        elif endpoint=='Categories_getlist':result=[{'cat_id':5,'cat_name':'Cafe'},{'cat_id':6,'cat_name':'Other'}]
        elif endpoint=='Articles_getlist':
            filters=body['filters'];ids=[filters['article_id']] if 'article_id' in filters else [20,21]
            if 'parent_cat_id' in filters:ids=[i for i in ids if filters['parent_cat_id']==5 and i in (20,21)]
            result=[{'article_id':i,'article_name':'Synthetic article '+str(i),'article_type':1,'amount_type_id':1} for i in ids]
        elif endpoint=='Amounttypes_getlist':result=[{'amount_type_id':1,'value_precision':self.precision,'time_interval':0}]
        elif endpoint in ('Accounts_place','Accounts_close'):
            result=body['account_id'];a=self.accounts[result]
            if body.get('orders'):
                a['orders']+=body['orders'];a['last_order_num']+=1
                a['total_real']='12.50';a['total_remain']='12.50'
            if body.get('payments'):
                assert endpoint=='Accounts_close' and 'orders' not in body
                assert body['payments'][0]['original_paid_sum']==12.5
                a.update(status=1,total_paid='12.50',total_remain='0.00')
                result=None
        elif endpoint=='Paymentmethods_getlist':result=[{'paymethod_id':3,'name':'Cash','type_id':self.payment_type,'fx':1,'provider_id':None,'require_info':False,'currencies':[]}]
        elif endpoint=='Currencies_getlist':result=[{'currency_id':1,'currency_code':'EUR'}]
        else:raise AssertionError(endpoint)
        if method=='POST':
            assert options['request_id'].startswith('connector_') and options['idempotency_key']
            if self.lose:raise ApplicationPlatformError('PRIVATE lost reply',reason='timeout')
        return {'outcome':'succeeded','http_status':200,'body_base64':base64.b64encode(json.dumps(result).encode()).decode()}


@pytest.fixture
def commerce(app):
    invoke,service,storage,clock=app
    broker=Barsy(storage);service.application=replace(service.application,platform=broker)
    seq=iter(range(100,1000))
    def call(name,payload,**kwargs):return invoke(name,payload,request(next(seq)),**kwargs)
    call('commerce_save_settings',{'expected_revision':1,'time_article_id':10,'unit':'hours','places':[7],
        'articles':[{'article_id':20,'label':'Juice'}],'guardian_category_id':5},audience='administrator')
    registration,c=child(invoke)
    call('assign_identifier',{'child_id':c['child_id'],'code':'TEST','expected_assignment_id':None})
    visit=call('scan_bracelet',{'code':'TEST','action':'start','expected_visit_id':None})['visit_id']
    def prepare(kind,**kwargs):return call('commerce_prepare',{'visit_id':visit,'kind':kind,'place_id':7,'article_id':20,'quantity':'1','consumer':'guardian',**kwargs})['command_id']
    def send(command,prefix='commerce'):
        with storage.transaction() as db:kind=service.commerce.command(db,command)['kind']
        if kind in ('time','consumption'):call('commerce_validate',{'command_id':command})
        result=call(prefix+'_execute',{'command_id':command})
        if result['state']=='uncertain':call(prefix+'_check',{'command_id':command,'account_id':None,'reviewed':False})
        return result
    def open_account():send(prepare('parent'));send(prepare('open'))
    return app,broker,call,prepare,send,open_account,visit,c,registration


def test_full_operator_and_separate_cashier_flow_rounds_time_once_and_uses_barsy_amount(commerce):
    app,broker,call,prepare,send,open_account,visit,c,_=commerce
    invoke,service,storage,clock=app
    open_account()
    with pytest.raises(LocalRefusal,match='parent_permission'):prepare('consumption',consumer='child')
    call('commerce_allow_child',{'child_id':c['child_id'],'expected_articles':[],'article_ids':[20],'reviewed':True})
    send(prepare('consumption',consumer='child',quantity='2'))
    clock.value+=timedelta(minutes=30,seconds=1)
    call('finish_visit',finish_payload(invoke,visit))
    send(prepare('time'))
    time_order=broker.accounts[201]['orders'][-1]
    assert time_order=={'article_id':10,'amount':0.517}  # 31 rounded minutes, once.
    with pytest.raises(LocalRefusal,match='finish_first'):prepare('time')
    quote=call('cashier_preview',{'visit_id':visit},permissions=['payments_manage'])
    assert quote['amount']=='12.50' and quote['currency_code']=='EUR'
    payment=call('cashier_prepare',{'visit_id':visit,'quote_id':quote['quote_id'],'paymethod_id':3,'confirmed':True},permissions=['payments_manage'])['command_id']
    with pytest.raises(LocalRefusal,match='denied'):call('cashier_execute',{'command_id':payment},permissions=['commerce_manage'])
    send(payment,'cashier')
    detail=invoke('cashier_detail',{'visit_id':visit,'offset':0},permissions=['payments_manage'])
    assert detail['account']['state']=='closed' and broker.accounts[201]['status']==1
    assert len(broker.sends)==5  # parent, account, consumption, time, payment
    assert [r['kind'] for r in detail['commands']]==['payment','time','consumption','open','parent']
    with storage.transaction() as db:
        assert db.execute('SELECT COUNT(*) FROM local_consumption_consents').fetchone()[0]==1
        assert 'PRIVATE' not in str([tuple(r) for r in db.execute('SELECT * FROM local_commerce_requests')])


def test_uncertain_send_survives_restart_and_never_replays(commerce):
    app,broker,call,prepare,send,open_account,visit,*_=commerce
    invoke,service,storage,_=app;open_account();command=prepare('consumption');call('commerce_validate',{'command_id':command});broker.lose=True
    identity=request(990)
    result=invoke('commerce_execute',{'command_id':command},identity)
    assert result['state']=='uncertain'
    count=len(broker.sends)
    assert invoke('commerce_execute',{'command_id':command},identity)==result
    assert call('commerce_execute',{'command_id':command})==result
    restarted=create_service(service.application)
    result2=restarted.handle('commerce_execute',{'command_id':command},OperationContext(audience='operator',user_id=42,
        subject_id='usr_'+f'{42:032x}',permission_ids=('commerce_manage',),correlation_id='restart',idempotency_key=request(991)))
    assert result2['data']['state']=='uncertain' and len(broker.sends)==count
    with pytest.raises(LocalRefusal,match='pending'):prepare('consumption')
    with pytest.raises(LocalRefusal,match='no_cancel'):call('commerce_cancel',{'command_id':command})
    with pytest.raises(LocalRefusal,match='manual_review'):call('commerce_check',{'command_id':command,'account_id':None,'reviewed':False})
    call('commerce_check',{'command_id':command,'account_id':None,'reviewed':True})
    assert len(broker.sends)==count
    assert invoke('commerce_request_outcome',{'operation_id':'commerce_execute','request_id':identity})['status']=='confirmed'
    assert invoke('commerce_request_outcome',{'operation_id':'commerce_execute','request_id':identity},user=99)['status']=='unknown'


def test_lost_opening_reply_requires_exact_account_identity_not_arbitrary_id(commerce):
    app,broker,call,prepare,send,_,visit,*_=commerce
    send(prepare('parent'));broker.lose=True;command=prepare('open')
    call('commerce_execute',{'command_id':command})
    broker.accounts[201]['account_alias']='Other account'
    with pytest.raises(LocalRefusal,match='account_id_required'):call('commerce_check',{'command_id':command,'account_id':None,'reviewed':False})
    with pytest.raises(LocalRefusal,match='invalid_remote'):call('commerce_check',{'command_id':command,'account_id':201,'reviewed':True})
    broker.accounts[201]['account_alias']='3mm '+broker.accounts[201]['uuid']
    with app[2].transaction() as db:db.execute("UPDATE local_commerce_families SET opening_error='commerce_opening_review' WHERE visit_id=?",(visit,))
    call('commerce_check',{'command_id':command,'account_id':None,'reviewed':False})
    assert app[0]('cashier_detail',{'visit_id':visit,'offset':0})['opening_error'] is None
    assert len(broker.sends)==2


@pytest.mark.parametrize('failure',['stale_parent','timer','precision','consent','budget','denied'])
def test_preflight_refusal_is_definite_and_has_no_external_mutation(commerce,failure,monkeypatch):
    app,broker,call,prepare,send,open_account,visit,c,_=commerce
    invoke,service,storage,clock=app
    if failure in ('stale_parent','timer'):
        send(prepare('parent'));command=prepare('open')
        if failure=='timer':broker.timer=1;broker.place_timer_hint=1
        else:broker.clients[101]['tel']='changed'
    else:
        open_account()
        if failure=='precision':
            clock.value+=timedelta(minutes=1);call('finish_visit',finish_payload(invoke,visit));command=prepare('time');broker.precision=0
        elif failure=='consent':
            call('commerce_allow_child',{'child_id':c['child_id'],'expected_articles':[],'article_ids':[20],'reviewed':True})
            command=prepare('consumption',consumer='child')
            call('commerce_allow_child',{'child_id':c['child_id'],'expected_articles':[20],'article_ids':[],'reviewed':True})
        else:command=prepare('consumption')
    before=len(broker.sends)
    if failure=='denied':broker.fail=True
    if failure=='budget':
        times=iter([0,0,12]);monkeypatch.setattr('child_center_local.commerce.time.monotonic',lambda:next(times,12))
    operation='commerce_execute' if failure in ('stale_parent','timer') else 'commerce_validate'
    with pytest.raises(LocalRefusal):call(operation,{'command_id':command})
    assert len(broker.sends)==before
    row=invoke('commerce_detail',{'visit_id':visit,'offset':0})['commands'][0]
    assert row['state']=='prepared'


@pytest.mark.parametrize('change',['amount','expiry','method','actor'])
def test_cashier_rechecks_quote_and_can_cancel_unsent_payment(commerce,change):
    app,broker,call,prepare,send,open_account,visit,*_=commerce
    invoke,_,_,clock=app;open_account();clock.value+=timedelta(minutes=1);call('finish_visit',finish_payload(invoke,visit));send(prepare('time'))
    quote=call('cashier_preview',{'visit_id':visit})
    command=call('cashier_prepare',{'visit_id':visit,'quote_id':quote['quote_id'],'paymethod_id':3,'confirmed':True})['command_id']
    if change=='amount':broker.accounts[201]['total_remain']='13.00'
    elif change=='expiry':clock.value+=timedelta(minutes=3)
    elif change=='method':broker.payment_type=2
    before=len(broker.sends)
    with pytest.raises(LocalRefusal,match='quote_expired'):
        call('cashier_execute',{'command_id':command},**({'user':99} if change=='actor' else {}))
    assert len(broker.sends)==before
    call('cashier_cancel',{'command_id':command},permissions=['payments_manage'])


def test_unknown_rpc_receipt_and_permission_isolation(commerce):
    app,broker,call,prepare,send,open_account,visit,*_=commerce
    invoke,service,storage,_=app;open_account()
    identity=request(992);context=OperationContext(audience='operator',user_id=42,subject_id='usr_'+f'{42:032x}',correlation_id='crash',idempotency_key=identity)
    key=service.commerce.key(context,identity)
    with storage.transaction() as db:db.execute('INSERT INTO local_commerce_requests VALUES(?,?,?,NULL)',(key,'commerce_observe',__import__('child_center_local.commerce',fromlist=['digest']).digest({'visit_id':visit})))
    assert invoke('commerce_request_outcome',{'request_id':identity,'operation_id':'commerce_observe'})['status']=='unknown'
    before=len(broker.calls)
    invoke('commerce_observe',{'visit_id':visit},identity)
    assert len(broker.calls)==before
    for operation,payload in [('commerce_detail',{'visit_id':visit,'offset':0}),('cashier_detail',{'visit_id':visit,'offset':0})]:
        with pytest.raises(LocalRefusal,match='denied'):invoke(operation,payload,permissions=[])
    with pytest.raises(LocalRefusal,match='denied'):call('commerce_prepare',{'visit_id':visit,'kind':'time','place_id':None,'article_id':None,'quantity':'1','consumer':'guardian'},permissions=['payments_manage'])


def test_settings_lock_privacy_pending_and_outside_cashier_closure(commerce):
    app,broker,call,prepare,send,open_account,visit,_,registration=commerce
    invoke,service,storage,clock=app;open_account()
    with pytest.raises(LocalRefusal,match='accounts_pending'):
        call('commerce_save_settings',{'expected_revision':2,'time_article_id':10,'unit':'hours','places':[7],'articles':[]},audience='administrator')
    clock.value+=timedelta(minutes=1);call('finish_visit',finish_payload(invoke,visit));send(prepare('time'))
    with pytest.raises(LocalRefusal,match='commercial|Commercial|account|Account'):
        call('erase_personal_data',{'registration_id':registration['registration_id'],'confirmed':True},audience='administrator')
    broker.accounts[201].update(status=1,total_paid='12.50',total_remain='0.00')
    call('cashier_external_close',{'visit_id':visit,'reviewed':True},permissions=['payments_manage'])
    assert invoke('cashier_detail',{'visit_id':visit,'offset':0})['account']['state']=='closed'
    export=json.loads(call('export_personal_data',{'registration_id':registration['registration_id']},audience='administrator')['document_json'])
    assert export['children'][0]['commerce'][0]['account']['state']=='closed'


def test_commerce_upgrade_preserves_existing_rows_and_migration_is_atomic(tmp_path):
    storage=ApplicationStorage(tmp_path/'upgrade');storage.migrate(get_migrations(),'local_0004')
    with storage.transaction() as db:
        historical_client(db,'2026-10-27T10:00:00Z')
        before=[tuple(r) for r in db.execute('SELECT * FROM local_registrations')]
    from three_mm_application_sdk import ApplicationMigration
    def fail(db):interactive_commerce(db);raise RuntimeError('synthetic failed migration')
    with pytest.raises(RuntimeError,match='synthetic'):
        storage.migrate([*get_migrations()[:4],ApplicationMigration('local_0005',fail)],'local_0005')
    assert storage.status()['revision']=='local_0004'
    with storage.transaction() as db:assert 'allowed_articles' not in [r[1] for r in db.execute('PRAGMA table_info(local_children)')]
    storage.migrate(get_migrations(),'local_0005')
    with storage.transaction() as db:
        assert [tuple(r) for r in db.execute('SELECT * FROM local_registrations')]==before
        assert db.execute('SELECT allowed_articles FROM local_children').fetchone()[0]=='[]'
        assert db.execute('SELECT time_article_id FROM local_commerce_settings').fetchone()[0] is None
    storage.migrate(get_migrations(),'local_0005')


def test_zero_time_confirmation_has_no_barsy_sale(commerce):
    app,broker,call,prepare,send,open_account,visit,*_=commerce
    invoke,*_=app;open_account();call('finish_visit',finish_payload(invoke,visit));before=len(broker.calls)
    assert send(prepare('time'))['state']=='confirmed'
    assert len(broker.calls)==before and not broker.accounts[201]['orders']


def test_child_consumption_consent_saves_before_any_barsy_account_and_is_cas_guarded(commerce):
    app,broker,call,_,_,_,visit,c,_=commerce
    invoke,*_=app
    payload={'child_id':c['child_id'],'expected_articles':[],'article_ids':[20],'reviewed':True}
    call('commerce_allow_child',payload,permissions=['children_manage'])
    detail=invoke('commerce_detail',{'visit_id':visit,'offset':0})
    assert detail['account'] is None and detail['allowed_articles']==[20]
    assert not broker.calls  # Consent is local, independent of Barsy availability.
    with pytest.raises(LocalRefusal,match='stale'):
        call('commerce_allow_child',{**payload,'article_ids':[]})
    with pytest.raises(LocalRefusal,match='denied'):
        call('commerce_allow_child',{**payload,'expected_articles':[20],'article_ids':[]},permissions=['commerce_manage'])


def test_unresolved_command_remains_in_attention_even_when_older_than_journal_pages(commerce):
    app,broker,_,prepare,_,_,visit,*_=commerce
    invoke,_,storage,_=app;pending=prepare('parent')
    with storage.transaction() as db:
        for i in range(55):
            db.execute('''INSERT INTO local_commerce_commands(command_id,owner_key,visit_id,kind,state,parameters,created_at)
                VALUES(?,?,?,'consumption','confirmed','{}','2026-10-27T10:00:00Z')''',
                ('commercial_'+f'{i:032x}','past:'+str(i),visit))
    first=invoke('commerce_detail',{'visit_id':visit,'offset':0})
    later=invoke('commerce_detail',{'visit_id':visit,'offset':50})
    assert all(item['command_id']!=pending for item in first['commands'])
    assert [item['command_id'] for item in first['attention']]==[pending]
    assert [item['command_id'] for item in later['attention']]==[pending]
    assert not broker.sends


def test_hard_crash_after_external_effect_leaves_durable_uncertainty_and_no_completed_rpc(commerce,monkeypatch):
    app,broker,call,prepare,send,open_account,visit,*_=commerce
    invoke,service,storage,_=app;open_account();command=prepare('consumption');call('commerce_validate',{'command_id':command})
    class Crash(BaseException):pass
    original=broker.connector_request
    def crash(*args,**kwargs):
        result=original(*args,**kwargs)
        if kwargs['method']=='POST':raise Crash()
        return result
    monkeypatch.setattr(broker,'connector_request',crash)
    identity=request(995)
    with pytest.raises(Crash):invoke('commerce_execute',{'command_id':command},identity)
    assert invoke('commerce_request_outcome',{'operation_id':'commerce_execute','request_id':identity})['status']=='unknown'
    assert invoke('commerce_detail',{'visit_id':visit,'offset':0})['commands'][0]['state']=='uncertain'
    assert broker.accounts[201]['orders']==[{'article_id':20,'amount':1.0}]
    count=len(broker.sends)
    invoke('commerce_execute',{'command_id':command},identity)
    assert len(broker.sends)==count
    call('commerce_check',{'command_id':command,'account_id':None,'reviewed':True})


def test_failed_observation_clears_stale_success_and_outside_close_rechecks_local_race(commerce):
    app,broker,call,prepare,send,open_account,visit,*_=commerce
    invoke,service,storage,clock=app;open_account()
    call('commerce_observe',{'visit_id':visit});broker.fail=True
    with pytest.raises(LocalRefusal,match='unavailable'):call('commerce_observe',{'visit_id':visit})
    assert invoke('commerce_detail',{'visit_id':visit,'offset':0})['account']['remote_state']=='unknown'
    broker.fail=False;clock.value+=timedelta(minutes=1);call('finish_visit',finish_payload(invoke,visit));send(prepare('time'))
    broker.accounts[201].update(status=1,total_paid='12.50',total_remain='0.00')
    def concurrent(endpoint):
        if endpoint=='Accounts_get':broker.hook=None;prepare('consumption')
    broker.hook=concurrent
    with pytest.raises(LocalRefusal,match='stale'):call('cashier_external_close',{'visit_id':visit,'reviewed':True})
    assert invoke('commerce_detail',{'visit_id':visit,'offset':0})['account']['state']=='open'


def test_missing_sale_and_foreign_quantities_cannot_be_confirmed(commerce):
    app,broker,call,prepare,send,open_account,visit,*_=commerce
    invoke,*_=app;open_account();command=prepare('consumption');call('commerce_validate',{'command_id':command})
    call('commerce_execute',{'command_id':command});broker.accounts[201]['orders']=[]
    with pytest.raises(LocalRefusal,match='check_required'):call('commerce_check',{'command_id':command,'account_id':None,'reviewed':True})
    broker.accounts[201]['orders']=[{'article_id':20,'amount':2}]
    with pytest.raises(LocalRefusal,match='check_required'):call('commerce_check',{'command_id':command,'account_id':None,'reviewed':True})
    assert invoke('commerce_detail',{'visit_id':visit,'offset':0})['commands'][0]['state']=='uncertain'


@pytest.mark.parametrize('interval',['missing',False,60])
def test_unknown_boolean_or_temporal_consumption_unit_never_posts_sale(commerce,interval,monkeypatch):
    _,broker,call,prepare,send,open_account,*_=commerce;open_account();command=prepare('consumption')
    original=broker.connector_request
    def unit(*args,**kwargs):
        result=original(*args,**kwargs)
        if kwargs['path'].endswith('Amounttypes_getlist'):
            value={'amount_type_id':1,'value_precision':3}
            if interval!='missing':value['time_interval']=interval
            result['body_base64']=base64.b64encode(json.dumps([value]).encode()).decode()
        return result
    monkeypatch.setattr(broker,'connector_request',unit);before=len(broker.sends)
    with pytest.raises(LocalRefusal,match='article_unavailable'):call('commerce_validate',{'command_id':command})
    assert len(broker.sends)==before



def test_family_opening_uses_the_same_exact_parent_lookup_when_get_hides_the_card(commerce):
    app,broker,call,prepare,send,_,visit,*_=commerce
    invoke,service,storage,_=app
    send(prepare('parent'))
    broker.can_read_card_on_get=False
    with storage.transaction() as db:db.execute('UPDATE local_commerce_settings SET default_place_id=7')
    service.families.open(visit)
    detail=invoke('cashier_detail',{'visit_id':visit,'offset':0})
    assert detail['account']['state']=='open' and detail['opening_error'] is None
    assert len([row for row in broker.sends if row[1]=='Accounts_create'])==1
    assert all(row[1]!='Clients_get' for row in broker.calls)



@pytest.mark.parametrize('field,value,reason',[
    ('client_id',999,'commerce_parent_id_mismatch'),
    ('client_name','PRIVATE mismatch','commerce_parent_name_mismatch'),
    ('tel','PRIVATE mismatch','commerce_parent_phone_mismatch'),
    ('email','PRIVATE mismatch','commerce_parent_email_mismatch'),
    ('client_code','foreign-registration','commerce_parent_not_found'),
    ('hidden_card',False,'commerce_parent_code_unavailable'),
])
def test_opening_reports_the_exact_parent_difference_and_keeps_the_prepared_command(commerce,field,value,reason):
    app,broker,call,prepare,send,_,visit,*_=commerce
    invoke,service,storage,_=app
    send(prepare('parent'));command=prepare('open')
    with storage.transaction() as db:db.execute('UPDATE local_commerce_settings SET default_place_id=7')
    original=broker.can_read_card_on_list if field=='hidden_card' else broker.clients[101][field]
    if field=='hidden_card':broker.can_read_card_on_list=value
    else:broker.clients[101][field]=value
    before=len(broker.sends);service.families.open(visit)
    detail=invoke('cashier_detail',{'visit_id':visit,'offset':0})
    pending=next(c for c in detail['attention'] if c['command_id']==command)
    assert pending['state']=='prepared' and pending['error_code']==reason
    assert detail['opening_state']=='review' and len(broker.sends)==before
    assert 'PRIVATE mismatch' not in json.dumps(detail)
    if field=='hidden_card':broker.can_read_card_on_list=original
    else:broker.clients[101][field]=original
    service.families.open(visit)
    confirmed=invoke('cashier_detail',{'visit_id':visit,'offset':0})
    assert confirmed['account']['state']=='open' and confirmed['opening_error'] is None
    assert next(c for c in confirmed['commands'] if c['kind']=='open')['command_id']==command
    assert len([row for row in broker.sends if row[1]=='Accounts_create'])==1



def test_local_send_budget_failure_keeps_the_time_step_prepared_without_a_post(commerce,monkeypatch):
    app,broker,call,prepare,send,open_account,visit,*_=commerce
    invoke,service,storage,clock=app
    open_account();clock.value+=timedelta(seconds=61)
    call('finish_visit',finish_payload(invoke,visit));command=prepare('time')
    ticks=[0.0]
    monkeypatch.setattr('child_center_local.commerce.time.monotonic',lambda:ticks[0])
    call('commerce_validate',{'command_id':command})
    from child_center_local.commerce import Session
    original_request=Session.request
    def expire_before_send(session,method,*args,**kwargs):
        if method=='POST':ticks[0]=7.0
        return original_request(session,method,*args,**kwargs)
    monkeypatch.setattr(Session,'request',expire_before_send);before=len(broker.sends)
    with pytest.raises(LocalRefusal,match='commerce_delivery_not_sent'):call('commerce_execute',{'command_id':command})
    detail=invoke('commerce_detail',{'visit_id':visit,'offset':0})
    step=next(c for c in detail['commands'] if c['command_id']==command)
    assert step['state']=='prepared' and step['error_code']=='commerce_delivery_not_sent'
    assert not detail['account']['time_confirmed'] and len(broker.sends)==before and not broker.accounts[201]['orders']
    monkeypatch.setattr(Session,'request',original_request);ticks[0]=0.0
    send(command)
    assert len(broker.sends)==before+1 and invoke('commerce_detail',{'visit_id':visit,'offset':0})['account']['time_confirmed']==1


@pytest.mark.parametrize('phase',['not_dispatched','execution_unconfirmed'])
def test_sdk_dispatch_phase_controls_recovery_without_replaying_unknown_time(commerce,phase):
    app,broker,call,prepare,send,open_account,visit,*_=commerce
    invoke,service,storage,clock=app
    open_account();clock.value+=timedelta(minutes=1)
    call('finish_visit',finish_payload(invoke,visit));command=prepare('time')
    call('commerce_validate',{'command_id':command})
    def unavailable(endpoint):
        if endpoint=='Accounts_place':raise ApplicationPlatformError('PRIVATE transport detail',reason='transport_unavailable',phase=phase)
    broker.hook=unavailable
    if phase=='not_dispatched':
        with pytest.raises(LocalRefusal,match='commerce_delivery_not_sent'):call('commerce_execute',{'command_id':command})
    else:assert call('commerce_execute',{'command_id':command})['state']=='uncertain'
    detail=invoke('commerce_detail',{'visit_id':visit,'offset':0})
    assert next(c for c in detail['commands'] if c['command_id']==command)['state']==('prepared' if phase=='not_dispatched' else 'uncertain')
    assert 'PRIVATE transport detail' not in json.dumps(detail)
    before=len(broker.sends);broker.hook=None
    if phase=='not_dispatched':
        send(command);assert len(broker.sends)==before+1
    else:
        call('commerce_execute',{'command_id':command});assert len(broker.sends)==before and not broker.accounts[201]['orders']



def test_slow_validation_has_its_own_budget_and_dispatch_only_sends_one_post(commerce,monkeypatch):
    app,broker,call,prepare,send,open_account,visit,*_=commerce
    invoke,_,_,clock=app;open_account();clock.value+=timedelta(seconds=61)
    call('finish_visit',finish_payload(invoke,visit));command=prepare('time')
    ticks=[0.0];monkeypatch.setattr('child_center_local.commerce.time.monotonic',lambda:ticks[0])
    def slow(endpoint):
        if endpoint in ('Accounts_get','Articles_getlist','Amounttypes_getlist'):ticks[0]+=3
    broker.hook=slow;before=len(broker.sends)
    assert call('commerce_validate',{'command_id':command})['state']=='prepared'
    assert ticks[0]==9 and len(broker.sends)==before and not broker.accounts[201]['orders']
    reads=len(broker.calls)
    assert call('commerce_execute',{'command_id':command})['state']=='uncertain'
    assert [method for method,*_ in broker.calls[reads:]]==['POST']
    call('commerce_check',{'command_id':command,'account_id':None,'reviewed':False})
    assert broker.accounts[201]['orders']==[{'article_id':10,'amount':0.033}]
    assert len(broker.sends)==before+1


@pytest.mark.parametrize('change',['missing','expiry','clock_rollback','actor','consent','account','configuration'])
def test_dispatch_requires_fresh_actor_bound_validation_and_local_snapshot(commerce,change):
    app,broker,call,prepare,send,open_account,visit,c,_=commerce
    invoke,service,storage,clock=app;open_account()
    call('commerce_allow_child',{'child_id':c['child_id'],'expected_articles':[],'article_ids':[20],'reviewed':True})
    command=prepare('consumption',consumer='child')
    if change!='missing':call('commerce_validate',{'command_id':command})
    if change=='expiry':clock.value+=timedelta(seconds=16)
    elif change=='clock_rollback':clock.value-=timedelta(seconds=1)
    elif change=='consent':call('commerce_allow_child',{'child_id':c['child_id'],'expected_articles':[20],'article_ids':[],'reviewed':True})
    elif change=='account':
        with storage.transaction() as db:db.execute('UPDATE local_commerce_accounts SET account_id=999 WHERE visit_id=?',(visit,))
    elif change=='configuration':
        with storage.transaction() as db:db.execute('UPDATE local_commerce_settings SET revision=revision+1')
    before=len(broker.calls)
    with pytest.raises(LocalRefusal,match='commerce_validation_required'):
        call('commerce_execute',{'command_id':command},**({'user':99} if change=='actor' else {}))
    assert len(broker.calls)==before
    assert invoke('commerce_detail',{'visit_id':visit,'offset':0})['attention'][0]['state']=='prepared'


def test_validation_rechecks_local_races_and_permission_without_sending(commerce):
    app,broker,call,prepare,send,open_account,visit,c,_=commerce
    invoke,service,storage,_=app;open_account();command=prepare('consumption')
    before=len(broker.calls)
    with pytest.raises(LocalRefusal,match='denied'):
        call('commerce_validate',{'command_id':command},permissions=['payments_manage'])
    assert len(broker.calls)==before
    def changed(endpoint):
        if endpoint=='Amounttypes_getlist':
            with storage.transaction() as db:db.execute('UPDATE local_commerce_settings SET revision=revision+1')
    broker.hook=changed;before=len(broker.sends)
    with pytest.raises(LocalRefusal,match='commerce_stale'):call('commerce_validate',{'command_id':command})
    assert len(broker.sends)==before
    with storage.transaction() as db:assert service.commerce.command(db,command)['baseline'] is None


def test_expired_validation_receipt_is_not_a_fresh_proof_and_uncertain_never_revalidates(commerce):
    app,broker,call,prepare,send,open_account,visit,*_=commerce
    invoke,_,_,clock=app;open_account();command=prepare('consumption');identity=request(988)
    proof=invoke('commerce_validate',{'command_id':command},identity);before=len(broker.calls)
    clock.value+=timedelta(seconds=16)
    assert invoke('commerce_validate',{'command_id':command},identity)==proof and len(broker.calls)==before
    with pytest.raises(LocalRefusal,match='commerce_validation_required'):call('commerce_execute',{'command_id':command})
    call('commerce_validate',{'command_id':command});broker.lose=True
    assert call('commerce_execute',{'command_id':command})['state']=='uncertain'
    before=len(broker.calls)
    assert call('commerce_validate',{'command_id':command})['state']=='uncertain'
    assert call('commerce_execute',{'command_id':command})['state']=='uncertain' and len(broker.calls)==before



def test_failed_revalidation_invalidates_earlier_proof_without_any_send(commerce):
    app,broker,call,prepare,send,open_account,visit,*_=commerce
    invoke,_,_,_=app;open_account();command=prepare('consumption')
    call('commerce_validate',{'command_id':command});broker.accounts[201]['status']=1
    before=len(broker.sends)
    with pytest.raises(LocalRefusal,match='remote_closed_or_timer'):call('commerce_validate',{'command_id':command})
    with pytest.raises(LocalRefusal,match='validation_required'):call('commerce_execute',{'command_id':command})
    assert len(broker.sends)==before
    assert invoke('commerce_detail',{'visit_id':visit,'offset':0})['attention'][0]['state']=='prepared'


def test_dispatch_rechecks_consent_at_the_durable_fence_and_current_permission(commerce,monkeypatch):
    app,broker,call,prepare,send,open_account,visit,c,_=commerce
    invoke,service,_,_=app;open_account()
    call('commerce_allow_child',{'child_id':c['child_id'],'expected_articles':[],'article_ids':[20],'reviewed':True})
    command=prepare('consumption',consumer='child');call('commerce_validate',{'command_id':command})
    before=len(broker.calls)
    with pytest.raises(LocalRefusal,match='denied'):call('commerce_execute',{'command_id':command},permissions=['payments_manage'])
    assert len(broker.calls)==before
    original=service.commerce.require_sale_validation
    def revoke_after_read(cmd,v,a,context,db=None):
        original(cmd,v,a,context,db)
        if db is None:call('commerce_allow_child',{'child_id':c['child_id'],'expected_articles':[20],'article_ids':[],'reviewed':True})
    monkeypatch.setattr(service.commerce,'require_sale_validation',revoke_after_read)
    with pytest.raises(LocalRefusal,match='stale|validation_required'):call('commerce_execute',{'command_id':command})
    assert len(broker.calls)==before
    assert invoke('commerce_detail',{'visit_id':visit,'offset':0})['attention'][0]['state']=='prepared'



@pytest.mark.parametrize('phase',['budget','not_dispatched','execution_unconfirmed'])
def test_proven_unsent_payment_restores_quote_but_unknown_payment_never_replays(commerce,monkeypatch,phase):
    app,broker,call,prepare,send,open_account,visit,*_=commerce
    invoke,service,storage,clock=app;open_account();clock.value+=timedelta(minutes=1)
    call('finish_visit',finish_payload(invoke,visit));send(prepare('time'))
    quote=call('cashier_preview',{'visit_id':visit})
    command=call('cashier_prepare',{'visit_id':visit,'quote_id':quote['quote_id'],'paymethod_id':3,'confirmed':True})['command_id']
    ticks=[0.0];monkeypatch.setattr('child_center_local.commerce.time.monotonic',lambda:ticks[0])
    def interrupt(endpoint):
        if phase=='budget' and endpoint=='Paymentmethods_getlist':ticks[0]=7.0
        elif endpoint=='Accounts_close':raise ApplicationPlatformError('PRIVATE payment failure',reason='transport_unavailable',phase=phase)
    broker.hook=interrupt
    if phase=='execution_unconfirmed':assert call('cashier_execute',{'command_id':command})['state']=='uncertain'
    else:
        with pytest.raises(LocalRefusal,match='commerce_delivery_not_sent'):call('cashier_execute',{'command_id':command})
    with storage.transaction() as db:
        saved=db.execute('SELECT used,expires_at FROM local_commerce_quotes WHERE quote_id=?',(quote['quote_id'],)).fetchone()
        assert saved['used']==(1 if phase=='execution_unconfirmed' else 0)
        assert saved['expires_at']==quote['expires_at']
    broker.hook=None;ticks[0]=0.0;before=len(broker.sends)
    result=call('cashier_execute',{'command_id':command})
    assert result['state']=='uncertain'
    if phase=='execution_unconfirmed':
        assert len(broker.sends)==before and broker.accounts[201]['status']==0
    else:
        assert len(broker.sends)==before+1
        call('cashier_check',{'command_id':command,'account_id':None,'reviewed':False})
        assert invoke('cashier_detail',{'visit_id':visit,'offset':0})['account']['state']=='closed'


@pytest.mark.parametrize('quantity',['abc','NaN','1,5','0','-1'])
def test_bad_local_quantity_is_a_form_refusal_not_a_barsy_failure(commerce,quantity):
    _,broker,call,prepare,send,open_account,*_=commerce;open_account();before=len(broker.calls)
    with pytest.raises(LocalRefusal,match='commerce_invalid_quantity'):prepare('consumption',quantity=quantity)
    assert len(broker.calls)==before



def legacy_empty_bill(commerce,phase='inside'):
    app,broker,call,prepare,send,open_account,visit,*_=commerce
    invoke,service,storage,clock=app;open_account();clock.value+=timedelta(seconds=61)
    if phase=='paused':
        call('scan_bracelet',{'code':'TEST','action':'pause','expected_visit_id':visit});clock.value+=timedelta(minutes=4)
    call('finish_visit',finish_payload(invoke,visit));command=prepare('time')
    with storage.transaction() as db:
        step=service.commerce.command(db,command);params={**step['parameters'],'quantity':'0.033'}
        db.execute("UPDATE local_commerce_commands SET state='uncertain',parameters=?,baseline='{}',error_code='commerce_check_required' WHERE command_id=?",(json.dumps(params),command))
    broker.accounts[201].update(status=1,payments=[],payments_history=[])
    payload={'visit_id':visit,'expected_account_id':201,'reviewed':True,'accepted_missing_time':True,'reason':'Empty prototype test bill'}
    return payload,command


@pytest.mark.parametrize('phase',['inside','paused'])
def test_admin_releases_legacy_empty_bill_without_claiming_a_charge_or_replaying_it(commerce,phase):
    payload,command=legacy_empty_bill(commerce,phase)
    app,broker,call,prepare,send,_,visit,c,registration=commerce
    invoke,service,storage,clock=app;before=len(broker.sends);identity=request(980)
    result=invoke('commerce_release_empty',payload,identity,permissions=['administration_manage'])
    assert result['state']=='closed' and len(broker.sends)==before
    detail=invoke('commerce_detail',{'visit_id':visit,'offset':0})
    assert detail['account']['state']=='closed' and detail['account']['time_confirmed']==0 and detail['account']['quantity'] is None
    assert detail['attention']==[]
    waived=next(c for c in detail['commands'] if c['command_id']==command)
    assert waived['state']=='waived' and waived['acknowledged']==0 and waived['parameters']['quantity']=='0.033'
    assert waived['parameters']['_recovery']['reason']==payload['reason']
    assert waived['parameters']['_recovery']['release_id']==result['command_id']
    release=next(c for c in detail['commands'] if c['command_id']==result['command_id'])
    assert release['kind']=='release' and release['parameters']['waived_count']==1
    assert invoke('commerce_list',{'offset':0,'limit':20,'filter':'open'})['items']==[]
    assert len(invoke('commerce_list',{'offset':0,'limit':20,'filter':'all'})['items'])==1
    assert call('commerce_execute',{'command_id':command})['state']=='waived'
    assert call('commerce_check',{'command_id':command,'account_id':None,'reviewed':True})['state']=='waived'
    assert len(broker.sends)==before
    assert invoke('commerce_release_empty',payload,identity,permissions=['administration_manage'])==result
    assert call('commerce_release_empty',payload,permissions=['administration_manage'])==result
    receipt={'request_id':identity,'operation_id':'commerce_release_empty'}
    assert invoke('commerce_recovery_outcome',receipt,permissions=['administration_manage'])['status']=='confirmed'
    assert invoke('commerce_recovery_outcome',receipt,user=99,permissions=['administration_manage'])['status']=='unknown'
    with pytest.raises(LocalRefusal,match='denied'):invoke('commerce_recovery_outcome',receipt,permissions=['commerce_manage'])
    exported=json.loads(call('export_personal_data',{'registration_id':registration['registration_id']},audience='administrator')['document_json'])
    assert exported['children'][0]['commerce'][0]['account']['state']=='closed'
    clock.value+=timedelta(seconds=1)
    new_visit=call('scan_bracelet',{'code':'TEST','action':'start','expected_visit_id':None})['visit_id']
    assert new_visit!=visit and invoke('commerce_detail',{'visit_id':new_visit,'offset':0})['account'] is None


@pytest.mark.parametrize('failure',['permission','open','orders','payment','payment_history','total','identity','wrong_id','acknowledged','confirmed','active','clock_race','command_race','missing_payments','timer','blank_reason'])
def test_empty_bill_release_refuses_missing_proof_or_concurrent_changes(commerce,failure):
    payload,command=legacy_empty_bill(commerce)
    app,broker,call,prepare,send,_,visit,*_=commerce
    invoke,service,storage,_=app;a=broker.accounts[201]
    if failure=='open':a['status']=0
    elif failure=='orders':a['orders']=[{'article_id':20,'amount':1}]
    elif failure=='payment':a['payments']=[{'original_paid_sum':1}]
    elif failure=='payment_history':a['payments_history']=[{'original_paid_sum':0}]
    elif failure=='total':a['total_real']='1.00'
    elif failure=='identity':a['client_id']=999
    elif failure=='wrong_id':payload['expected_account_id']=999
    elif failure=='acknowledged':
        with storage.transaction() as db:db.execute('UPDATE local_commerce_commands SET acknowledged=1,candidate_id=201 WHERE command_id=?',(command,))
    elif failure=='confirmed':
        with storage.transaction() as db:db.execute("UPDATE local_commerce_commands SET state='confirmed' WHERE command_id=?",(command,))
    elif failure=='active':
        with storage.transaction() as db:db.execute("UPDATE local_visits SET state='active' WHERE visit_id=?",(visit,))
    elif failure=='missing_payments':a.pop('payments')
    elif failure=='timer':a['time_calculation']=1
    elif failure=='blank_reason':payload['reason']='  '
    elif failure in ('clock_race','command_race'):
        def race(endpoint):
            if endpoint=='Accounts_get':
                with storage.transaction() as db:
                    if failure=='clock_race':db.execute('UPDATE local_visits SET accumulated_us=accumulated_us+1 WHERE visit_id=?',(visit,))
                    else:db.execute("UPDATE local_commerce_commands SET error_code='concurrent' WHERE command_id=?",(command,))
        broker.hook=race
    before=len(broker.sends)
    with pytest.raises(LocalRefusal):call('commerce_release_empty',payload,permissions=['commerce_manage'] if failure=='permission' else ['administration_manage'])
    assert len(broker.sends)==before
    with storage.transaction() as db:
        assert db.execute('SELECT state FROM local_commerce_accounts WHERE visit_id=?',(visit,)).fetchone()[0]=='open'
        assert not db.execute("SELECT 1 FROM local_commerce_commands WHERE kind='release'").fetchone()
        assert service.commerce.command(db,command)['state']!='waived'



@pytest.mark.parametrize('phase',['inside','paused'])
def test_manual_finish_inside_or_after_exit_charges_once_without_needing_another_scan(commerce,phase):
    app,broker,call,prepare,send,open_account,visit,*_=commerce
    invoke,_,_,clock=app;open_account();clock.value+=timedelta(seconds=61)
    if phase=='paused':
        call('scan_bracelet',{'code':'TEST','action':'pause','expected_visit_id':visit});clock.value+=timedelta(minutes=4)
    call('finish_visit',finish_payload(invoke,visit));command=prepare('time');before=len(broker.sends)
    send(command)
    detail=invoke('commerce_detail',{'visit_id':visit,'offset':0})
    assert detail['visit_state']=='closed' and detail['account']['time_confirmed']==1
    assert broker.accounts[201]['orders']==[{'article_id':10,'amount':0.033}]
    assert call('commerce_execute',{'command_id':command})['state']=='confirmed' and len(broker.sends)==before+1



def failed_parent_request(commerce,legacy=False,created=False):
    app,broker,call,prepare,send,open_account,visit,c,registration=commerce
    invoke,service,storage,clock=app;command=prepare('parent')
    if created:
        broker.lose=True;call('commerce_execute',{'command_id':command});broker.lose=False
    else:
        # Unknown/rejected-shaped remote JSON has no integer acknowledgement.
        # This is not a claim about the exact historical Barsy error envelope.
        original=broker.connector_request
        def bad_reply(connector_id,**options):
            if options['method']=='POST':
                broker.calls.append(('POST','Clients_createsmart',json.loads(options['body']),options))
                return {'outcome':'succeeded','http_status':200,'body_base64':base64.b64encode(b'{"error":"unconfirmed creation"}').decode()}
            return original(connector_id,**options)
        broker.connector_request=bad_reply
        assert call('commerce_execute',{'command_id':command})['state']=='uncertain'
        broker.connector_request=original
    call('finish_visit',finish_payload(invoke,visit))
    if legacy:
        with storage.transaction() as db:
            db.execute('DELETE FROM local_commerce_members WHERE family_visit_id=?',(visit,))
            db.execute('DELETE FROM local_commerce_families WHERE visit_id=?',(visit,))
    return {'visit_id':visit,'reviewed':True,'accepted_orphaned_parent':True,'reason':'Retire an old unlinked test request'},command


@pytest.mark.parametrize('legacy',[False,True])
def test_archive_unlinked_parent_attempt_retires_it_and_allows_corrected_new_intent(commerce,legacy):
    payload,command=failed_parent_request(commerce,legacy=legacy)
    app,broker,call,prepare,send,_,visit,c,registration=commerce
    invoke,service,storage,clock=app
    # A similarly named foreign-code client must never be rebound or deleted.
    broker.clients[801]={'client_id':801,'client_code':'foreign','client_name':'Guardian','tel':'000','email':''}
    existing=json.dumps(broker.clients,sort_keys=True);before=len(broker.sends);identity=request(976)
    result=invoke('commerce_release_unlinked',payload,identity,permissions=['administration_manage'])
    assert result['state']=='archived' and len(broker.sends)==before and json.dumps(broker.clients,sort_keys=True)==existing
    detail=invoke('commerce_detail',{'visit_id':visit,'offset':0})
    assert detail['account'] is None and detail['opening_state']=='archived' and detail['attention']==[] and not detail['opening_available']
    assert next(c for c in detail['commands'] if c['command_id']==command)['state']=='abandoned'
    assert invoke('commerce_list',{'filter':'open','offset':0,'limit':20})['items']==[]
    assert invoke('commerce_list',{'filter':'all','offset':0,'limit':20})['items'][0]['account_state']=='archived'
    service.families.open(visit);assert len(broker.sends)==before
    with pytest.raises(LocalRefusal,match='unlinked_archived'):prepare('parent')
    with pytest.raises(LocalRefusal,match='unlinked_archived'):call('family_retry_open',{'visit_id':visit})
    assert call('commerce_execute',{'command_id':command})['state']=='abandoned'
    assert invoke('commerce_release_unlinked',payload,identity,permissions=['administration_manage'])==result
    assert call('commerce_release_unlinked',payload,permissions=['administration_manage'])==result
    receipt={'request_id':identity,'operation_id':'commerce_release_unlinked'}
    assert invoke('commerce_recovery_outcome',receipt,permissions=['administration_manage'])['status']=='confirmed'
    assert invoke('commerce_recovery_outcome',receipt,user=99,permissions=['administration_manage'])['status']=='unknown'
    clock.value+=timedelta(seconds=1)
    new_visit=call('scan_bracelet',{'code':'TEST','action':'start','expected_visit_id':None})['visit_id']
    assert new_visit!=visit
    def new_parent():return call('commerce_prepare',{'visit_id':new_visit,'kind':'parent','place_id':7,'article_id':None,'quantity':'1','consumer':'guardian'})['command_id']
    retry=new_parent()
    with pytest.raises(LocalRefusal,match='parent_attempt_retired'):call('commerce_execute',{'command_id':retry})
    assert len(broker.sends)==before
    call('commerce_cancel',{'command_id':retry})
    client=invoke('admin_get_client',{'registration_id':registration['registration_id']},audience='administrator')
    call('admin_update_client',{'registration_id':registration['registration_id'],'expected_revision':client['revision'],
        'guardian':{**client['guardian'],'display_name':'Corrected Parent'},'children':[{'child_id':row['child_id'],'display_name':row['display_name']} for row in client['children']]},audience='administrator')
    # Current admin schema accepts the same guardian contact fields without consent.
    fresh=new_parent();send(fresh)
    assert len(broker.sends)==before+1 and broker.clients[801]['client_code']=='foreign'
    assert invoke('commerce_detail',{'visit_id':new_visit,'offset':0})['parent_linked']
    assert invoke('commerce_detail',{'visit_id':visit,'offset':0})['attention']==[]


def test_unlinked_archive_keeps_an_existing_exact_code_client_and_reuses_it_readonly(commerce):
    payload,command=failed_parent_request(commerce,created=True)
    app,broker,call,prepare,send,_,visit,c,registration=commerce
    invoke,_,_,clock=app;before=len(broker.sends);saved=json.dumps(broker.clients,sort_keys=True)
    result=call('commerce_release_unlinked',payload,permissions=['administration_manage'])
    detail=invoke('commerce_detail',{'visit_id':visit,'offset':0})
    released=next(c for c in detail['commands'] if c['command_id']==result['command_id'])
    assert released['parameters']['remote_client_id']==101 and json.dumps(broker.clients,sort_keys=True)==saved
    clock.value+=timedelta(seconds=1)
    new_visit=call('scan_bracelet',{'code':'TEST','action':'start','expected_visit_id':None})['visit_id']
    cmd=call('commerce_prepare',{'visit_id':new_visit,'kind':'parent','place_id':7,'article_id':None,'quantity':'1','consumer':'guardian'})['command_id']
    assert call('commerce_execute',{'command_id':cmd})['state']=='confirmed'
    assert len(broker.sends)==before and len(broker.clients)==1


@pytest.mark.parametrize('failure',['permission','active','account','opening_attempt','charge','foreign_pending','family_race','parent_race','remote_failure','blank_reason'])
def test_unlinked_archive_denies_bill_risk_missing_authority_or_concurrent_changes(commerce,failure):
    payload,command=failed_parent_request(commerce)
    app,broker,call,prepare,send,_,visit,c,registration=commerce
    invoke,service,storage,clock=app
    if failure=='active':
        with storage.transaction() as db:db.execute("UPDATE local_visits SET state='active' WHERE visit_id=?",(visit,))
    elif failure=='account':
        with storage.transaction() as db:db.execute("INSERT INTO local_commerce_accounts(visit_id,place_id,client_id,identity,state,time_article_id,unit) VALUES(?,7,101,'test','prepared',10,'hours')",(visit,))
    elif failure in ('opening_attempt','charge'):
        with storage.transaction() as db:db.execute('UPDATE local_commerce_commands SET kind=? WHERE command_id=?',('open' if failure=='opening_attempt' else 'consumption',command))
    elif failure=='foreign_pending':
        clock.value+=timedelta(seconds=1)
        new_visit=call('scan_bracelet',{'code':'TEST','action':'start','expected_visit_id':None})['visit_id']
        call('finish_visit',finish_payload(invoke,new_visit))
        with storage.transaction() as db:db.execute('UPDATE local_commerce_commands SET visit_id=? WHERE command_id=?',(new_visit,command))
    elif failure in ('family_race','parent_race'):
        def race(endpoint):
            if endpoint=='Clients_getlist':
                with storage.transaction() as db:
                    if failure=='family_race':db.execute("UPDATE local_commerce_families SET opening_error='concurrent' WHERE visit_id=?",(visit,))
                    else:db.execute('UPDATE local_registrations SET revision=revision+1 WHERE registration_id=?',(registration['registration_id'],))
        broker.hook=race
    elif failure=='remote_failure':broker.fail=True
    elif failure=='blank_reason':payload['reason']='  '
    before=len(broker.sends)
    with pytest.raises(LocalRefusal):call('commerce_release_unlinked',payload,permissions=['commerce_manage'] if failure=='permission' else ['administration_manage'])
    assert len(broker.sends)==before
    with storage.transaction() as db:
        assert service.commerce.command(db,command)['state']=='uncertain'
        assert not db.execute("SELECT 1 FROM local_commerce_commands WHERE kind='release'").fetchone()



def test_late_background_parent_failure_cannot_reopen_an_archived_request(commerce):
    payload,command=failed_parent_request(commerce)
    app,broker,call,prepare,send,_,visit,*_=commerce
    invoke,service,storage,_=app
    with storage.transaction() as db:db.execute('UPDATE local_commerce_settings SET default_place_id=7')
    archived=[]
    def archive_during_lookup(endpoint):
        if endpoint=='Clients_getlist':
            broker.hook=None
            archived.append(call('commerce_release_unlinked',payload,permissions=['administration_manage']))
    before=len(broker.sends);broker.hook=archive_during_lookup
    service.families.open(visit)
    assert archived and archived[0]['state']=='archived'
    detail=invoke('commerce_detail',{'visit_id':visit,'offset':0})
    assert detail['opening_state']=='archived' and detail['opening_error'] is None and detail['attention']==[]
    assert invoke('commerce_list',{'filter':'open','offset':0,'limit':20})['items']==[]
    service.families.open(visit)
    assert len(broker.sends)==before



def test_late_parent_acknowledgement_preserves_archive_and_never_opens_a_bill(commerce):
    app,broker,call,prepare,send,_,visit,c,registration=commerce
    invoke,service,storage,_=app;call('finish_visit',finish_payload(invoke,visit));command=prepare('parent')
    with storage.transaction() as db:db.execute('UPDATE local_commerce_settings SET default_place_id=7')
    payload={'visit_id':visit,'reviewed':True,'accepted_orphaned_parent':True,'reason':'Retire in-flight client-only request'}
    def archive_before_reply(endpoint):
        if endpoint=='Clients_createsmart':
            broker.hook=None
            assert call('commerce_release_unlinked',payload,permissions=['administration_manage'])['state']=='archived'
    broker.hook=archive_before_reply;service.families.open(visit)
    detail=invoke('commerce_detail',{'visit_id':visit,'offset':0})
    old=next(c for c in detail['commands'] if c['command_id']==command)
    assert old['state']=='abandoned' and old['acknowledged']==1
    assert detail['opening_state']=='archived' and detail['account'] is None
    assert len(broker.clients)==1 and broker.clients[101]['client_code']=='3mm_'+registration['registration_id']
    assert [s[1] for s in broker.sends]==['Clients_createsmart']
    service.families.open(visit)
    assert len(broker.sends)==1


@pytest.mark.parametrize('kind',['empty','unlinked'])
@pytest.mark.parametrize('alias,permission',[
    ('commerce_request_outcome','commerce_manage'),
    ('cashier_request_outcome','payments_manage'),
    ('commerce_settings_outcome','barsy_manage'),
    ('commerce_child_outcome','children_manage'),
])
def test_admin_recovery_receipt_is_not_available_through_lower_permission_aliases(commerce,kind,alias,permission):
    payload,_=(legacy_empty_bill(commerce) if kind=='empty' else failed_parent_request(commerce))
    invoke=commerce[0][0];operation='commerce_release_'+kind;identity=request(975)
    invoke(operation,payload,identity,audience='administrator',permissions=['administration_manage'])
    receipt={'request_id':identity,'operation_id':operation}
    assert invoke('commerce_recovery_outcome',receipt,audience='administrator',permissions=['administration_manage'])['status']=='confirmed'
    # The same actor losing admin permission must not use a less privileged
    # receipt alias to recover a formerly privileged operation result.
    for permissions in ([permission],[permission,'administration_manage']):
        assert invoke(alias,receipt,audience='administrator',permissions=permissions)=={'status':'unknown','result_json':None}
