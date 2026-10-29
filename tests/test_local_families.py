"""One family bill, per-child timing/consent and one-shot fiscal checkout."""
from datetime import timedelta
from dataclasses import replace
import json
import time
import pytest
from three_mm_application_sdk import ApplicationStorage,ApplicationMigration
from test_local_profile import app,child,request,finish_payload
from test_local_commerce import commerce,Barsy
from child_center_local.service import LocalRefusal,create_service
from child_center_local.migrations import get_migrations
from child_center_local.migrations import family_commerce
from test_local_profile import historical_client


def sibling(invoke,storage,registration,code):
    cid='child_'+('b' if code=='SECOND' else 'c')*32
    with storage.transaction() as db:
        db.execute("INSERT INTO local_children VALUES(?,?,?,'[]')",(cid,registration['registration_id'],code))
    invoke('assign_identifier',{'child_id':cid,'code':code,'expected_assignment_id':None},request(800 if code=='SECOND' else 801))
    return cid


def test_one_family_bill_two_clocks_child_consent_and_fiscal_checkout(commerce):
    app,broker,call,prepare,send,open_account,first,c,registration=commerce
    invoke,service,storage,clock=app
    open_account()
    second_child=sibling(invoke,storage,registration,'SECOND')
    clock.value+=timedelta(minutes=10,seconds=1)
    second=call('scan_bracelet',{'code':'SECOND','action':'start','expected_visit_id':None})['visit_id']
    detail=invoke('cashier_detail',{'visit_id':second,'offset':0},permissions=['payments_manage'])
    assert detail['visit_id']==first and detail['account']['account_id']==201
    assert len(detail['members'])==2
    assert len(invoke('cashier_list',{'filter':'open','offset':0,'limit':20})['items'])==1
    call('commerce_allow_child',{'child_id':c['child_id'],'expected_articles':[],'article_ids':[20],'reviewed':True})
    with pytest.raises(LocalRefusal,match='parent_permission'):
        prepare('consumption',consumer='child',consumer_child_id=second_child)
    send(prepare('consumption',consumer='child',consumer_child_id=c['child_id']))
    send(prepare('consumption',consumer='guardian',article_id=21))
    blocked=prepare('consumption',consumer='guardian',article_id=99)
    before=len(broker.sends)
    with pytest.raises(LocalRefusal,match='article_unavailable'):send(blocked)
    assert len(broker.sends)==before
    call('commerce_cancel',{'command_id':blocked})
    clock.value+=timedelta(minutes=5)
    d=invoke('cashier_detail',{'visit_id':first,'offset':0})
    member=next(m for m in d['members'] if m['visit_id']==first)
    call('family_transition',{'visit_id':first,'expected_transition_at':member['last_transition_at'],'action':'pause'},permissions=['visits_manage'])
    clock.value+=timedelta(minutes=20)
    d=invoke('cashier_detail',{'visit_id':first,'offset':0})
    assert next(m for m in d['members'] if m['visit_id']==first)['duration_seconds']==901
    assert next(m for m in d['members'] if m['visit_id']==second)['duration_seconds']==1500
    expected=[{'visit_id':m['visit_id'],'expected_transition_at':m['last_transition_at'],'expected_phase':m['phase']} for m in d['members']]
    call('family_finish',{'visit_id':first,'members':expected},permissions=['visits_manage'])
    send(prepare('time'))
    assert broker.accounts[201]['orders'][-1]=={'article_id':10,'amount':0.683} # 16 + 25 = 41 minutes
    with pytest.raises(LocalRefusal,match='checkout_started'):
        call('scan_bracelet',{'code':'TEST','action':'start','expected_visit_id':None})
    with storage.transaction() as db:
        assert db.execute("SELECT COUNT(*) FROM local_visits WHERE state='active'").fetchone()[0]==0
    q=call('cashier_preview',{'visit_id':second},permissions=['payments_manage'])
    p=call('cashier_prepare',{'visit_id':second,'quote_id':q['quote_id'],'paymethod_id':3,'confirmed':True},permissions=['payments_manage'])
    send(p['command_id'],'cashier')
    assert broker.sends[-1][1]=='Accounts_close'
    assert invoke('cashier_detail',{'visit_id':second,'offset':0})['account']['state']=='closed'
    assert len([r for r in broker.sends if r[1]=='Accounts_create'])==1
    clock.value+=timedelta(seconds=1)
    third=call('scan_bracelet',{'code':'TEST','action':'start','expected_visit_id':None})['visit_id']
    assert invoke('cashier_detail',{'visit_id':third,'offset':0})['account'] is None


def test_separate_families_share_one_place_and_open_automatically(commerce,monkeypatch):
    app,broker,call,prepare,send,open_account,first,c,registration=commerce
    invoke,service,storage,clock=app
    # Entry creates only durable local membership; opening work runs after commit.
    with storage.transaction() as db:db.execute('UPDATE local_commerce_settings SET default_place_id=7')
    service.families.wake()
    deadline=time.monotonic()+5
    while service.families.running and time.monotonic()<deadline:time.sleep(.01)
    assert invoke('cashier_detail',{'visit_id':first,'offset':0})['account']['state']=='open'
    other,c2=child(invoke,key=799)
    call('assign_identifier',{'child_id':c2['child_id'],'code':'OTHER','expected_assignment_id':None})
    second=call('scan_bracelet',{'code':'OTHER','action':'start','expected_visit_id':None})['visit_id']
    deadline=time.monotonic()+5
    while service.families.running and time.monotonic()<deadline:time.sleep(.01)
    d=invoke('cashier_detail',{'visit_id':second,'offset':0})
    assert d['account']['state']=='open' and d['account']['account_id']!=201
    assert len(broker.accounts)==2 and {a['place_id'] for a in broker.accounts.values()}=={7}


def test_lost_opening_reply_is_found_and_survives_restart_without_another_post(commerce):
    app,broker,call,prepare,send,open_account,visit,*_=commerce
    invoke,service,storage,_=app
    send(prepare('parent'))
    broker.lose=True
    with storage.transaction() as db:db.execute('UPDATE local_commerce_settings SET default_place_id=7')
    service.families.open(visit)
    before=len(broker.sends)
    d=invoke('cashier_detail',{'visit_id':visit,'offset':0})
    assert d['opening_error'] is None and d['account']['state']=='open' and d['opening_state']=='open'
    assert not d['attention']
    restarted=create_service(service.application)
    restarted.families.open(visit)
    assert len(broker.sends)==before


def test_unconfirmed_open_without_a_remote_match_never_replays_on_continuation(commerce):
    from three_mm_application_sdk import ApplicationPlatformError
    app,broker,call,prepare,send,_,visit,*_=commerce
    invoke,service,storage,_=app
    send(prepare('parent'))
    with storage.transaction() as db:db.execute('UPDATE local_commerce_settings SET default_place_id=7')
    def disconnected(endpoint):
        if endpoint=='Accounts_create':raise ApplicationPlatformError('PRIVATE connection lost',reason='timeout')
    broker.hook=disconnected
    service.families.open(visit)
    detail=invoke('cashier_detail',{'visit_id':visit,'offset':0})
    assert detail['opening_state']=='review' and detail['attention'][0]['state']=='uncertain'
    assert detail['attention'][0]['error_code']=='commerce_account_id_required'
    assert not broker.accounts
    before=len(broker.sends);broker.hook=None
    call('family_retry_open',{'visit_id':visit},permissions=['commerce_manage'])
    deadline=time.monotonic()+5
    while service.families.running and time.monotonic()<deadline:time.sleep(.01)
    assert len(broker.sends)==before and not broker.accounts
    assert invoke('cashier_detail',{'visit_id':visit,'offset':0})['opening_state']=='review'


def test_default_place_without_a_timer_field_opens_and_parent_uses_the_category(commerce):
    app,broker,call,prepare,send,_,visit,c,_=commerce
    invoke,service,storage,_=app
    broker.place_type=1  # A type ID is not a special timer-mode enum.
    with storage.transaction() as db:db.execute('UPDATE local_commerce_settings SET default_place_id=7')
    assert invoke('commerce_places',{},permissions=['commerce_manage'])['items']==[{'place_id':7,'label':'Play room'}]
    assert invoke('cashier_detail',{'visit_id':visit,'offset':0})['opening_state']=='synchronizing'
    service.families.open(visit)
    detail=invoke('cashier_detail',{'visit_id':visit,'offset':0})
    assert detail['opening_state']=='open' and detail['account']['account_id']==201
    assert detail['allowed_articles']==[] and not broker.accounts[201]['orders']
    catalog=invoke('commerce_catalog',{'visit_id':visit,'query':'','offset':0},permissions=['commerce_manage'])
    assert [r['article_id'] for r in catalog['items']]==[20,21]
    sent=next(body for _,endpoint,body,_ in reversed(broker.calls) if endpoint=='Articles_getlist')
    assert sent['filters']['parent_cat_id']==5 and sent['extra_properties']['article_type'] is True
    with pytest.raises(LocalRefusal,match='parent_permission'):prepare('consumption',consumer='child',article_id=20)
    send(prepare('consumption',consumer='guardian',article_id=21,quantity='2'))
    assert broker.accounts[201]['orders']==[{'article_id':21,'amount':2.0}]
    assert len([r for r in broker.sends if r[1]=='Accounts_create'])==1


def test_timer_on_created_account_never_allows_time_or_consumption(commerce):
    app,broker,call,prepare,_,_,visit,*_=commerce
    invoke,service,storage,_=app;broker.timer=1
    with storage.transaction() as db:db.execute('UPDATE local_commerce_settings SET default_place_id=7')
    service.families.open(visit)
    detail=invoke('cashier_detail',{'visit_id':visit,'offset':0})
    assert detail['opening_state']=='review' and detail['account']['state']=='prepared'
    assert detail['attention'][0]['error_code']=='commerce_remote_closed_or_timer'
    before=len(broker.sends)
    with pytest.raises(LocalRefusal,match='not_ready'):prepare('consumption',consumer='guardian')
    service.families.open(visit)
    assert len(broker.sends)==before and not broker.accounts[201]['orders']


@pytest.mark.parametrize('fault',['duplicate','foreign_client','too_many'])
def test_lost_reply_discovery_refuses_ambiguous_or_foreign_accounts(commerce,fault):
    _,broker,call,prepare,send,_,visit,*_=commerce
    send(prepare('parent'));command=prepare('open');broker.lose=True
    call('commerce_execute',{'command_id':command})
    original=dict(broker.accounts[201])
    if fault=='duplicate':broker.accounts[202]={**original,'account_id':202}
    elif fault=='foreign_client':broker.accounts[201]['client_id']=999
    else:
        for i in range(100):broker.accounts[202+i]={**original,'account_id':202+i,'account_alias':'Other'}
    before=len(broker.sends)
    with pytest.raises(LocalRefusal,match='identity_conflict|account_id_required|review_limit'):
        call('commerce_check',{'command_id':command,'account_id':None,'reviewed':False})
    assert len(broker.sends)==before


def test_family_finish_rejects_changed_member_set_atomically(commerce):
    app,broker,call,prepare,send,open_account,visit,c,registration=commerce
    invoke,service,storage,clock=app
    d=invoke('cashier_detail',{'visit_id':visit,'offset':0})
    old=[{'visit_id':m['visit_id'],'expected_transition_at':m['last_transition_at'],'expected_phase':m['phase']} for m in d['members']]
    sibling(invoke,storage,registration,'SECOND')
    call('scan_bracelet',{'code':'SECOND','action':'start','expected_visit_id':None})
    with pytest.raises(LocalRefusal,match='stale'):call('family_finish',{'visit_id':visit,'members':old})
    assert len(invoke('list_visits',{'state':'active','offset':0,'limit':20})['items'])==2
    with pytest.raises(LocalRefusal,match='denied'):call('family_finish',{'visit_id':visit,'members':old},permissions=['payments_manage'])


def test_network_entry_opens_once_and_pause_resume_keep_the_same_bill(app):
    from test_local_readers import bound,enable,event,deliver
    invoke,service,storage,clock=bound(app)
    broker=Barsy(storage)
    service.application=replace(service.application,platform=broker)
    invoke('commerce_save_settings',{'expected_revision':1,'time_article_id':10,'unit':'hours','places':[7],
        'default_place_id':7,'guardian_category_id':5,'articles':[{'article_id':20,'label':'Juice'}]},request(30),audience='administrator')
    enable(invoke)
    clock.value+=timedelta(seconds=1)
    started=deliver(service,event(clock,1))
    deadline=time.monotonic()+5
    while service.families.running and time.monotonic()<deadline:time.sleep(.01)
    account=invoke('cashier_detail',{'visit_id':started['visit_id'],'offset':0})['account']
    assert account['state']=='open'
    before=len(broker.sends)
    clock.value+=timedelta(minutes=2)
    assert deliver(service,event(clock,2))['outcome']=='paused'
    clock.value+=timedelta(minutes=20)
    assert deliver(service,event(clock,3))['outcome']=='resumed'
    assert invoke('cashier_detail',{'visit_id':started['visit_id'],'offset':0})['account']['account_id']==account['account_id']
    assert len(broker.sends)==before
    assert deliver(service,event(clock,3))['outcome']=='resumed'


def test_family_upgrade_preserves_accounts_and_rolls_back_as_one_migration(tmp_path):
    storage=ApplicationStorage(tmp_path/'family-upgrade');storage.migrate(get_migrations(),'local_0005')
    first='visit_'+'d'*32;second='visit_'+'e'*32
    with storage.transaction() as db:
        # Populate pre-family data, including an open remote identity.
        db.execute("INSERT INTO local_registrations VALUES(?, 'approved','Parent','000','','v1','2026-10-28T10:00:00Z','parent','2026-10-28T10:00:00Z',NULL,1)",('reg_'+'a'*32,))
        db.execute("INSERT INTO local_children VALUES(?,?,?,'[]')",('child_'+'b'*32,'reg_'+'a'*32,'One'))
        db.execute("INSERT INTO local_children VALUES(?,?,?,'[]')",('child_'+'c'*32,'reg_'+'a'*32,'Two'))
        for vid,cid in [(first,'child_'+'b'*32),(second,'child_'+'c'*32)]:
            db.execute("INSERT INTO local_visits VALUES(?,?,'active','2026-10-28T10:00:00Z','2026-10-28T10:00:00Z',0,'2026-10-28T10:00:00Z',NULL)",(vid,cid))
        db.execute("INSERT INTO local_commerce_accounts(visit_id,place_id,client_id,identity,account_id,state,time_article_id,unit) VALUES(?,7,101,'old-identity',201,'open',10,'hours')",(first,))
        before=dict(db.execute('SELECT * FROM local_commerce_accounts').fetchone())
    def fail(db):family_commerce(db);raise RuntimeError('test rollback')
    with pytest.raises(RuntimeError,match='rollback'):
        storage.migrate([*get_migrations()[:5],ApplicationMigration('local_0006',fail)],'local_0006')
    assert storage.status()['revision']=='local_0005'
    with storage.transaction() as db:
        assert 'default_place_id' not in [r[1] for r in db.execute('PRAGMA table_info(local_commerce_settings)')]
        assert dict(db.execute('SELECT * FROM local_commerce_accounts').fetchone())==before
    storage.migrate(get_migrations(),'local_0006')
    with storage.transaction() as db:
        assert dict(db.execute('SELECT * FROM local_commerce_accounts').fetchone())==before
        assert [r[0] for r in db.execute('SELECT family_visit_id FROM local_commerce_members')]==[first,first]
        assert db.execute('SELECT default_place_id FROM local_commerce_settings').fetchone()[0] is None


def test_fiscal_reply_loss_never_closes_or_charges_a_second_time(commerce):
    app,broker,call,prepare,send,open_account,visit,*_=commerce
    invoke,service,storage,clock=app
    open_account();clock.value+=timedelta(minutes=1)
    call('finish_visit',finish_payload(invoke,visit));send(prepare('time'))
    q=call('cashier_preview',{'visit_id':visit},permissions=['payments_manage'])
    cmd=call('cashier_prepare',{'visit_id':visit,'quote_id':q['quote_id'],'paymethod_id':3,'confirmed':True},permissions=['payments_manage'])['command_id']
    broker.lose=True
    assert call('cashier_execute',{'command_id':cmd},permissions=['payments_manage'])['state']=='uncertain'
    before=len(broker.sends)
    assert call('cashier_execute',{'command_id':cmd},permissions=['payments_manage'])['state']=='uncertain'
    assert len(broker.sends)==before
    with pytest.raises(LocalRefusal,match='manual_review'):
        call('cashier_check',{'command_id':cmd,'account_id':None,'reviewed':False},permissions=['payments_manage'])
    call('cashier_check',{'command_id':cmd,'account_id':None,'reviewed':True},permissions=['payments_manage'])
    assert invoke('cashier_detail',{'visit_id':visit,'offset':0})['account']['state']=='closed'
    assert len([r for r in broker.sends if r[1]=='Accounts_close'])==1


def test_opening_continuation_receipt_is_actor_scoped_and_does_not_replay(commerce,monkeypatch):
    app,broker,call,prepare,send,open_account,visit,*_=commerce
    invoke,service,storage,clock=app
    # A revoked connector stops before any external POST and remains reviewable.
    broker.fail=True
    with storage.transaction() as db:db.execute('UPDATE local_commerce_settings SET default_place_id=7')
    service.families.open(visit)
    assert not broker.sends
    monkeypatch.setattr(service.families,'wake',lambda:None)
    invoke('family_retry_open',{'visit_id':visit},request(899),permissions=['commerce_manage'])
    identity={'operation_id':'family_retry_open','request_id':request(899)}
    assert invoke('family_open_outcome',identity,permissions=['commerce_manage'])['status']=='confirmed'
    assert invoke('family_open_outcome',identity,user=43,permissions=['commerce_manage'])['status']=='unknown'
    with pytest.raises(LocalRefusal,match='denied'):
        invoke('family_open_outcome',identity,permissions=['payments_manage'])
