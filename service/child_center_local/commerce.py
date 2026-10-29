"""Interactive commercial steps. One explicit send; uncertainty never resends.

Endpoint shapes/identity/fixed-quantity and cash/card rules follow the preserved
commercial service. No scheduler, credential store, local prices or live timers.
"""
import base64
import hashlib
import json
import time
import uuid
from datetime import timedelta, datetime
from decimal import Decimal, ROUND_HALF_UP
from three_mm_application_sdk import ApplicationPlatformError
from .barsy import integer, label, reject_constant
from .errors import LocalRefusal


def canonical(value):
    return json.dumps(value,ensure_ascii=False,sort_keys=True,separators=(',',':'))


def digest(value):
    return hashlib.sha256(canonical(value).encode()).hexdigest()


def remote_rows(value,maximum=1000):
    if not isinstance(value,list) or len(value)>maximum or any(not isinstance(row,dict) for row in value):
        raise LocalRefusal('commerce_invalid_remote')
    return value


def money(value):
    if isinstance(value,bool) or value is None:raise LocalRefusal('commerce_invalid_remote')
    try:result=Decimal(str(value))
    except Exception:raise LocalRefusal('commerce_invalid_remote') from None
    if not result.is_finite() or abs(result)>Decimal('1000000000'):raise LocalRefusal('commerce_invalid_remote')
    return result


class _NotDispatched(LocalRefusal):
    """Local pre-send refusal or an explicit SDK proof; never a remote guess."""


class Session:
    def __init__(self,commerce,budget=8.5):
        self.commerce=commerce;self.deadline=time.monotonic()+budget

    def request(self,method,endpoint,body=None,identity=None):
        # Declared connector deadline is 2 s; keep an internal margin before
        # the operation deadline. Validation has a separate read-only budget.
        # No worker or lock spans these calls.
        if time.monotonic()+2.2>=self.deadline:raise _NotDispatched('commerce_unavailable')
        platform=self.commerce.service.application.platform
        if platform is None:raise _NotDispatched('commerce_unavailable')
        try:
            response=platform.connector_request('barsy_api',method=method,path='/endpoints/json/'+endpoint,
                body=canonical(body or {}).encode(),headers={'Content-Type':'application/json'},
                **({'request_id':'connector_'+identity,'idempotency_key':str(uuid.UUID(identity))} if identity else {}))
            if (not isinstance(response,dict) or response.get('outcome')!='succeeded'
                    or type(response.get('http_status')) is not int or not 200<=response['http_status']<300):
                raise LocalRefusal('commerce_unavailable')
            encoded=response.get('body_base64')
            if not isinstance(encoded,str) or len(encoded)>699052:raise ValueError()
            raw=base64.b64decode(encoded,validate=True)
            if len(raw)>512*1024:raise ValueError()
            return json.loads(raw.decode(),parse_constant=reject_constant)
        except LocalRefusal:raise
        except ApplicationPlatformError as error:
            if error.phase=='not_dispatched':raise _NotDispatched('commerce_unavailable') from None
            raise LocalRefusal('commerce_unavailable') from None
        except (OSError,TimeoutError,ValueError,TypeError,KeyError,UnicodeError,RecursionError):
            raise LocalRefusal('commerce_unavailable') from None

    def read(self,endpoint,body=None):return self.request('GET',endpoint,body)


class Commerce:
    LOCAL={'commerce_settings','commerce_save_settings','registration_choices','kiosk_registration_choices','commerce_list','cashier_list',
        'commerce_detail','cashier_detail','commerce_prepare','cashier_prepare','commerce_cancel',
        'commerce_request_outcome','cashier_request_outcome','commerce_settings_outcome','commerce_child_outcome','commerce_recovery_outcome','commerce_allow_child','cashier_cancel'}
    EXTERNAL={'commerce_release_unlinked','commerce_release_empty','commerce_validate','commerce_execute','cashier_execute','commerce_check','cashier_check','cashier_preview','cashier_external_close','commerce_observe'}

    def __init__(self,service):self.service=service

    def authorize(self,operation,context):
        if operation in ('registration_choices','kiosk_registration_choices'):
            if operation=='kiosk_registration_choices' and context.audience!='kiosk':raise LocalRefusal('commerce_denied')
            if operation=='registration_choices' and (context.audience not in ('operator','administrator') or not context.has_application_permission('registrations_manage')):raise LocalRefusal('commerce_denied')
            return
        permission='administration_manage' if operation in ('commerce_release_empty','commerce_release_unlinked','commerce_recovery_outcome') else 'payments_manage' if operation.startswith('cashier_') else 'barsy_manage' if operation in ('commerce_settings','commerce_save_settings','commerce_settings_outcome') else 'children_manage' if operation in ('commerce_allow_child','commerce_child_outcome') else 'commerce_manage'
        if context.audience not in ('operator','administrator') or not context.has_application_permission(permission):
            raise LocalRefusal('commerce_denied')
        self.actor(context)

    def key(self,context,request_id):
        self.service.key(context,request_id)  # Validate the opaque request ID.
        return digest([self.actor(context),request_id])

    def local(self,db,operation,payload,context):
        self.authorize(operation,context)
        if operation.endswith('_request_outcome') or operation in ('commerce_settings_outcome','commerce_child_outcome','commerce_recovery_outcome'):
            recovery=payload['operation_id'] in ('commerce_release_empty','commerce_release_unlinked')
            # Privileged recovery receipts belong only to their admin-gated read.
            if (operation=='commerce_recovery_outcome')!=recovery:return {'status':'unknown','result_json':None}
            key=self.key(context,payload['request_id'])
            row=db.execute('SELECT * FROM local_commerce_requests WHERE request_key=?',(key,)).fetchone()
            if row and row['operation_id']==payload['operation_id']:
                return {'status':'confirmed' if row['result_json'] else 'unknown','result_json':row['result_json']}
            row=db.execute('SELECT operation_id,result_json FROM local_requests WHERE request_key=?',(key,)).fetchone()
            return {'status':'confirmed','result_json':row['result_json']} if row and row['operation_id']==payload['operation_id'] else {'status':'unknown','result_json':None}
        method=operation if operation in ('cashier_prepare','cashier_cancel') else operation.replace('cashier_','commerce_')
        return getattr(self,method)(db,payload,context)

    def external(self,operation,payload,context):
        self.authorize(operation,context)
        key=self.key(context,context.idempotency_key);fingerprint=digest(payload)
        with self.service.application.storage.transaction() as db:
            old=db.execute('SELECT * FROM local_commerce_requests WHERE request_key=?',(key,)).fetchone()
            if old:
                if old['operation_id']!=operation or old['fingerprint']!=fingerprint:raise LocalRefusal('commerce_identity_conflict')
                return json.loads(old['result_json']) if old['result_json'] else {'status':'applied','data':{'state':'uncertain'},'message':None}
            db.execute('INSERT INTO local_commerce_requests VALUES(?,?,?,NULL)',(key,operation,fingerprint))
        try:
            session=Session(self,budget=13.5 if operation=='commerce_validate' else 8.5)
            method={'cashier_preview':'commerce_preview','cashier_external_close':'commerce_external_close'}.get(operation,operation)
            data=getattr(self,method)(session,payload,context)
            result={'status':'applied','data':data,'message':None}
        except LocalRefusal as error:
            result={'status':'rejected','data':None,'message':str(error)}
        except (ValueError,TypeError,KeyError,ArithmeticError,UnicodeError):
            result={'status':'rejected','data':None,'message':'commerce_invalid_remote'}
        with self.service.application.storage.transaction() as db:
            db.execute('UPDATE local_commerce_requests SET result_json=? WHERE request_key=?',(canonical(result),key))
            db.execute('INSERT INTO local_audit VALUES(?,?,?,?)',(uuid.uuid4().hex,operation,self.actor(context),self.service.now()))
        return result

    @staticmethod
    def settings(db):return dict(db.execute('SELECT * FROM local_commerce_settings WHERE singleton=1').fetchone())

    def commerce_settings(self,db,payload,context):
        row=self.settings(db)
        return {**{k:row[k] for k in ('revision','time_article_id','unit','default_place_id','guardian_category_id')},'places':json.loads(row['places']),'articles':json.loads(row['articles'])}

    def commerce_save_settings(self,db,payload,context):
        if self.settings(db)['revision']!=payload['expected_revision']:raise LocalRefusal('commerce_stale')
        if db.execute("SELECT 1 FROM local_commerce_accounts WHERE state!='closed'").fetchone():raise LocalRefusal('commerce_accounts_pending')
        places=payload['places'];articles=payload['articles']
        if len(set(places))!=len(places) or len({a['article_id'] for a in articles})!=len(articles):raise LocalRefusal('commerce_invalid_settings')
        if payload['time_article_id'] in {a['article_id'] for a in articles}:raise LocalRefusal('commerce_invalid_settings')
        default=payload.get('default_place_id',self.settings(db)['default_place_id'])
        if default is not None and default not in places:raise LocalRefusal('commerce_invalid_settings')
        category=payload.get('guardian_category_id',self.settings(db)['guardian_category_id'])
        db.execute('UPDATE local_commerce_settings SET revision=revision+1,time_article_id=?,unit=?,places=?,articles=?,default_place_id=?,guardian_category_id=?',
            (payload['time_article_id'],payload['unit'],canonical(places),canonical(articles),default,category))
        return {'state':'saved'}

    def registration_choices(self,db,payload,context):return {'items':json.loads(self.settings(db)['articles'])}

    def kiosk_registration_choices(self,db,payload,context):return self.registration_choices(db,payload,context)

    def places(self,context):
        self.authorize('commerce_places',context)
        with self.service.application.storage.transaction() as db:ids=json.loads(self.settings(db)['places'])
        places=remote_rows(Session(self).read('Places_getlist'),10000)
        items=[]
        for row in places:
            if integer(row.get('place_id'),1) not in ids:continue
            if not self.place_available(row):continue
            items.append({'place_id':integer(row['place_id'],1),'label':label(row.get('name') or str(row.get('place_num',row['place_id'])))})
        return {'items':items}

    @staticmethod
    def place_available(row):
        # PlaceData uses arbitrary type IDs; Places_getlist does not guarantee
        # time_calculation. Accounts_get still confirms the actual timer mode.
        integer(row.get('place_type'))
        return 'time_calculation' not in row or integer(row['time_calculation'])==0

    def catalog(self,payload,context):
        self.authorize('commerce_catalog',context)
        with self.service.application.storage.transaction() as db:
            self.visit(db,payload['visit_id'])
            settings=self.settings(db)
        category=settings['guardian_category_id']
        if category is None:raise LocalRefusal('commerce_guardian_category_required')
        rows=remote_rows(Session(self).read('Articles_getlist',{'filters':{'delete_flag':0,'is_for_sale':1,
            'article_type':1,'parent_cat_id':category,'article_name':payload['query']},'extra_properties':{'common':'min','article_type':True},
            'offset':payload['offset'],'length':20,'order_by':{'article_id':'asc'}}),20)
        seen=set();items=[]
        for row in rows:
            article=integer(row.get('article_id'),1)
            if article in seen:raise LocalRefusal('commerce_invalid_remote')
            seen.add(article)
            if article!=settings['time_article_id'] and integer(row.get('article_type'))==1:
                items.append({'article_id':article,'label':label(row.get('article_name'))})
        return {'items':items,'has_more':len(rows)==20}

    def commerce_allow_child(self,db,payload,context):
        self.service.child(db,payload['child_id'])
        if not payload['reviewed'] or any(a not in {r['article_id'] for r in json.loads(self.settings(db)['articles'])} for a in payload['article_ids']):raise LocalRefusal('commerce_parent_permission')
        if payload['expected_articles']!=json.loads(db.execute('SELECT allowed_articles FROM local_children WHERE child_id=?',(payload['child_id'],)).fetchone()[0]):raise LocalRefusal('commerce_stale')
        db.execute('UPDATE local_children SET allowed_articles=? WHERE child_id=?',(canonical(payload['article_ids']),payload['child_id']))
        db.execute('INSERT INTO local_consumption_consents(child_id,actor,consented_at,articles) VALUES(?,?,?,?)',
            (payload['child_id'],self.actor(context),self.service.now(),canonical(payload['article_ids'])))
        return {'state':'saved'}

    def commerce_list(self,db,payload,context):
        rows=db.execute('''SELECT v.visit_id,c.display_name child_name,r.guardian_name,v.state visit_state,
            a.account_id,CASE WHEN f.opening_error='commerce_unlinked_archived' THEN 'archived' ELSE a.state END account_state,a.place_id FROM local_visits v JOIN local_children c ON c.child_id=v.child_id
            JOIN local_registrations r ON r.registration_id=c.registration_id LEFT JOIN local_commerce_accounts a ON a.visit_id=v.visit_id
            LEFT JOIN local_commerce_families f ON f.visit_id=v.visit_id
            WHERE r.status!='erased' AND (?='all' OR (COALESCE(a.state,'unlinked')!='closed' AND COALESCE(f.opening_error,'')!='commerce_unlinked_archived'))
            AND NOT EXISTS(SELECT 1 FROM local_commerce_members m WHERE m.visit_id=v.visit_id AND m.family_visit_id!=v.visit_id)
            ORDER BY v.entered_at DESC,v.visit_id LIMIT ? OFFSET ?''',(payload['filter'],payload['limit'],payload['offset'])).fetchall()
        items=[]
        for row in rows:
            v=self.visit(db,row['visit_id'])
            items.append({**dict(row),'child_name':', '.join(dict.fromkeys(m['display_name'] for m in v['family_members'])),'visit_state':v['state']})
        return {'items':items,'has_more':len(rows)==payload['limit']}

    def visit(self,db,visit_id):
        visit_id=self.service.families.anchor(db,visit_id)
        row=db.execute('''SELECT v.*,c.display_name,c.allowed_articles,r.registration_id,r.revision,
            r.guardian_name,r.phone,r.email,r.status registration_status FROM local_visits v
            JOIN local_children c ON c.child_id=v.child_id JOIN local_registrations r ON r.registration_id=c.registration_id
            WHERE v.visit_id=? AND r.status!='erased' ''',(visit_id,)).fetchone()
        if row is None or row['registration_status']!='approved':raise LocalRefusal('commerce_client_unavailable')
        result=dict(row)
        members=self.service.families.members(db,visit_id) or [dict(row)]
        result.update(family_members=members,state='active' if any(m['state']=='active' for m in members) else 'closed')
        return result

    def commerce_detail(self,db,payload,context):
        v=self.visit(db,payload['visit_id']);a=db.execute('SELECT * FROM local_commerce_accounts WHERE visit_id=?',(v['visit_id'],)).fetchone()
        parent=db.execute('SELECT * FROM local_commerce_parents WHERE registration_id=?',(v['registration_id'],)).fetchone()
        family=db.execute('SELECT opening_error FROM local_commerce_families WHERE visit_id=?',(v['visit_id'],)).fetchone()
        archived=bool(family and family['opening_error']=='commerce_unlinked_archived')
        commands=db.execute('''SELECT command_id,kind,state,error_code,created_at,parameters,acknowledged FROM local_commerce_commands
            WHERE visit_id=? OR (?=0 AND registration_id=?) ORDER BY sequence DESC LIMIT 50 OFFSET ?''',(v['visit_id'],archived,v['registration_id'],payload['offset'])).fetchall()
        attention=db.execute('''SELECT command_id,kind,state,error_code,created_at,parameters,acknowledged FROM local_commerce_commands
            WHERE (visit_id=? OR registration_id=?) AND state IN ('prepared','uncertain') ORDER BY sequence DESC LIMIT 2''',(v['visit_id'],v['registration_id'])).fetchall() if not archived else []
        settings=self.settings(db)
        parent_linked=bool(parent and parent['source_digest']==self.parent_digest(v))
        opening_available=bool(not archived and family and settings['default_place_id'] and settings['time_article_id'])
        opening_state=('archived' if archived else 'open' if a and a['account_id'] else 'setup_required' if not opening_available
            else 'review' if family['opening_error'] else 'opening' if parent_linked else 'synchronizing')
        return {'visit_id':v['visit_id'],'child_id':v['child_id'],'child_name':v['display_name'],'guardian_name':v['guardian_name'],
            'visit_state':v['state'],'parent_linked':parent_linked,
            'account':dict(a) if a else None,'choices':json.loads(self.settings(db)['articles']),
            'allowed_articles':json.loads(v['allowed_articles']),'commands':[{**dict(c),'parameters':json.loads(c['parameters'])} for c in commands],
            'attention':[{**dict(c),'parameters':json.loads(c['parameters'])} for c in attention],
            'members':[{'visit_id':m['visit_id'],'child_id':m['child_id'],'child_name':m['display_name'],
                'phase':'closed' if m['state']=='closed' else 'inside' if m['inside_since'] else 'paused',
                'last_transition_at':m['last_transition_at'],'duration_seconds':self.service.elapsed(m,self.service.now())//1000000,
                'allowed_articles':json.loads(m['allowed_articles'])} for m in v['family_members']],
            'opening_error':family['opening_error'] if family and not archived else None,
            'opening_available':opening_available,'opening_state':opening_state,
            'has_more':len(commands)==50}

    @staticmethod
    def parent_digest(v):return digest([v['guardian_name'],v['phone'],v['email']])

    def commerce_prepare(self,db,payload,context):
        v=self.visit(db,payload['visit_id']);kind=payload['kind'];payment=kind=='payment'
        family=db.execute('SELECT opening_error FROM local_commerce_families WHERE visit_id=?',(v['visit_id'],)).fetchone()
        if family and family['opening_error']=='commerce_unlinked_archived':raise LocalRefusal('commerce_unlinked_archived')
        if payment and not (context.has_application_permission('payments_manage') and payload.get('_cashier',False)):
            raise LocalRefusal('commerce_denied')
        settings=self.settings(db);a=db.execute('SELECT * FROM local_commerce_accounts WHERE visit_id=?',(v['visit_id'],)).fetchone()
        params={};owner='visit:'+v['visit_id'];registration=None
        if kind=='parent':
            owner='parent:'+v['registration_id'];registration=v['registration_id']
            params={'source_digest':self.parent_digest(v)}
        elif kind=='open':
            if a is not None or settings['time_article_id'] is None:raise LocalRefusal('commerce_not_ready')
            parent=db.execute('SELECT * FROM local_commerce_parents WHERE registration_id=?',(v['registration_id'],)).fetchone()
            if parent is None or parent['source_digest']!=self.parent_digest(v):raise LocalRefusal('commerce_parent_required')
            place=payload['place_id']
            if place not in json.loads(settings['places']):raise LocalRefusal('commerce_invalid_settings')
            params={'place_id':place,'client_id':parent['client_id'],'time_article_id':settings['time_article_id'],'unit':settings['unit'],'source_digest':self.parent_digest(v)}
        else:
            if a is None or a['state']!='open' or not a['account_id']:raise LocalRefusal('commerce_not_ready')
            if kind=='time':
                if v['state']!='closed' or a['time_confirmed']:raise LocalRefusal('commerce_finish_first')
                if db.execute("SELECT 1 FROM local_commerce_commands WHERE visit_id=? AND kind='time' AND state!='cancelled'",(v['visit_id'],)).fetchone():raise LocalRefusal('commerce_pending')
                minutes=sum((m['accumulated_us']+59999999)//60000000 for m in v['family_members'])
                params={'article_id':a['time_article_id'],'minutes':minutes,'unit':a['unit']}
            elif kind=='consumption':
                article=payload['article_id']
                try:quantity=money(payload['quantity'])
                except LocalRefusal:raise LocalRefusal('commerce_invalid_quantity') from None
                if (article==a['time_article_id'] or (payload['consumer']=='child' and article not in {x['article_id'] for x in json.loads(settings['articles'])})
                        or quantity<=0 or quantity>100 or quantity.as_tuple().exponent < -3):raise LocalRefusal('commerce_invalid_quantity')
                if payload['consumer']=='guardian' and settings['guardian_category_id'] is None:raise LocalRefusal('commerce_guardian_category_required')
                child_id=payload.get('consumer_child_id') or v['child_id']
                child=next((m for m in v['family_members'] if m['child_id']==child_id),None)
                if payload['consumer']=='child' and (child is None or article not in json.loads(child['allowed_articles'])):raise LocalRefusal('commerce_parent_permission')
                params={'article_id':article,'quantity':str(quantity),'consumer':payload['consumer'],'consumer_child_id':child_id,
                    'category_id':settings['guardian_category_id'] if payload['consumer']=='guardian' else None}
            elif kind=='payment':
                if v['state']!='closed' or not a['time_confirmed'] or not payload['confirmed']:raise LocalRefusal('commerce_finish_first')
                q=db.execute('SELECT * FROM local_commerce_quotes WHERE quote_id=?',(payload['quote_id'],)).fetchone()
                if (q is None or q['visit_id']!=v['visit_id'] or q['used'] or q['actor']!=self.actor(context)
                        or q['expires_at']<=self.service.now() or payload['paymethod_id'] not in [m['paymethod_id'] for m in json.loads(q['methods'])]):raise LocalRefusal('commerce_quote_expired')
                params={k:q[k] for k in ('quote_id','fingerprint','amount','currency_id','currency_code','expires_at')};params['paymethod_id']=payload['paymethod_id']
                params['method_label']=next(m['label'] for m in json.loads(q['methods']) if m['paymethod_id']==payload['paymethod_id'])
            else:raise LocalRefusal('commerce_invalid_settings')
        if db.execute("SELECT 1 FROM local_commerce_commands WHERE owner_key=? AND state IN ('prepared','uncertain')",(owner,)).fetchone():raise LocalRefusal('commerce_pending')
        identifier='commercial_'+uuid.uuid4().hex
        db.execute('''INSERT INTO local_commerce_commands(command_id,owner_key,visit_id,registration_id,kind,state,parameters,created_at)
            VALUES(?,?,?,?,?,'prepared',?,?)''',(identifier,owner,v['visit_id'],registration,kind,canonical(params),self.service.now()))
        if kind=='open':
            db.execute('''INSERT INTO local_commerce_accounts(visit_id,place_id,client_id,identity,state,time_article_id,unit)
                VALUES(?,?,?,?,'prepared',?,?)''',(v['visit_id'],params['place_id'],params['client_id'],self.identity(identifier),params['time_article_id'],params['unit']))
        return {'command_id':identifier,'state':'prepared'}

    def cashier_prepare(self,db,payload,context):return self.commerce_prepare(db,{**payload,'_cashier':True,'kind':'payment'},context)

    @staticmethod
    def actor(context):
        if not context.subject_id:raise LocalRefusal('commerce_denied')
        return context.audience+':'+context.subject_id

    @staticmethod
    def identity(command_id):return str(uuid.UUID(command_id.removeprefix('commercial_')))

    @staticmethod
    def command(db,command_id):
        row=db.execute('SELECT * FROM local_commerce_commands WHERE command_id=?',(command_id,)).fetchone()
        if row is None:raise LocalRefusal('commerce_not_found')
        return {**dict(row),'parameters':json.loads(row['parameters'])}

    def commerce_cancel(self,db,payload,context):
        cmd=self.command(db,payload['command_id'])
        if (cmd['kind']=='payment') != payload.get('_cashier',False) or cmd['state']!='prepared':raise LocalRefusal('commerce_no_cancel')
        db.execute("UPDATE local_commerce_commands SET state='cancelled' WHERE command_id=?",(cmd['command_id'],))
        if cmd['kind'] in ('parent','open'):
            db.execute("UPDATE local_commerce_families SET opening_error='commerce_opening_review' WHERE visit_id=?",(cmd['visit_id'],))
        if cmd['kind']=='open':db.execute('DELETE FROM local_commerce_accounts WHERE visit_id=?',(cmd['visit_id'],))
        return {'state':'cancelled'}

    def cashier_cancel(self,db,payload,context):return self.commerce_cancel(db,{**payload,'_cashier':True},context)

    def read_context(self,command_id,context):
        with self.service.application.storage.transaction() as db:
            cmd=self.command(db,command_id);v=self.visit(db,cmd['visit_id'])
            a=db.execute('SELECT * FROM local_commerce_accounts WHERE visit_id=?',(v['visit_id'],)).fetchone()
        return cmd,v,dict(a) if a else None

    def parent_rows(self,session,v):
        # Use one documented exact-code lookup for synchronization and opening.
        # Clients_get can hide the card code even when explicitly requested.
        rows=remote_rows(session.read('Clients_getlist',{'filters':{'client_code_match':'3mm_'+v['registration_id']},
            'extra_properties':{'client_id':True,'client_name':True,'client_code':True,'tel':True,'email':True},'length':2}),2)
        if len(rows)>1:raise LocalRefusal('commerce_identity_conflict')
        return rows

    @staticmethod
    def require_parent(row,v,expected_client_id=None):
        if not isinstance(row,dict):raise LocalRefusal('commerce_invalid_remote')
        if row.get('client_code') in (None,''):raise LocalRefusal('commerce_parent_code_unavailable')
        if row['client_code']!='3mm_'+v['registration_id']:raise LocalRefusal('commerce_parent_code_mismatch')
        client_id=integer(row.get('client_id'),1)
        if expected_client_id is not None and client_id!=expected_client_id:raise LocalRefusal('commerce_parent_id_mismatch')
        if str(row.get('client_name','')).strip().casefold()!=v['guardian_name'].strip().casefold():raise LocalRefusal('commerce_parent_name_mismatch')
        if str(row.get('tel') or '').strip()!=v['phone'].strip():raise LocalRefusal('commerce_parent_phone_mismatch')
        if str(row.get('email') or '').strip().casefold()!=v['email'].strip().casefold():raise LocalRefusal('commerce_parent_email_mismatch')
        return client_id

    @staticmethod
    def account_valid(row,a):
        marker='3mm '+a['identity'];alias=row.get('account_alias','') if isinstance(row,dict) else ''
        return (isinstance(row,dict) and integer(row.get('account_id'),1)==a['account_id']
            and integer(row.get('place_id'),1)==a['place_id'] and integer(row.get('client_id'),1)==a['client_id']
            and isinstance(alias,str) and (alias==marker or alias.startswith(marker+' | ')))

    def account(self,session,a,*,open_only=True):
        row=session.read('Accounts_get',{'account_id':a['account_id'],'extra_properties':{'orders':True,'payments':True,'payments_history':True}})
        try:
            if not self.account_valid(row,a):raise ValueError()
            if integer(row.get('status')) not in (0,1) or not isinstance(row.get('orders'),list) or len(row['orders'])>1000:raise ValueError()
            for order in row['orders']:
                if not isinstance(order,dict):raise ValueError()
                integer(order.get('article_id'),1);money(order.get('amount'))
            if integer(row.get('time_calculation'))!=0 or (open_only and integer(row['status'])!=0):raise LocalRefusal('commerce_remote_closed_or_timer')
        except (ValueError,TypeError,KeyError):raise LocalRefusal('commerce_invalid_remote') from None
        return row

    @staticmethod
    def quantities(account):
        totals={}
        for row in account['orders']:
            key=str(integer(row['article_id'],1));totals[key]=str(money(totals.get(key,'0'))+money(row['amount']))
        return {key:str(Decimal(value).normalize()) for key,value in totals.items() if Decimal(value)!=0}

    @staticmethod
    def fingerprint(account):return digest({k:account.get(k) for k in ('orders','total_real','total_paid','total_remain','currency_id','currency_rate','status','last_order_num')})

    def article(self,session,article_id,unit=None,category=None):
        filters={'article_id':article_id,'delete_flag':0,'is_for_sale':1}
        if category is not None:filters['parent_cat_id']=category
        articles=remote_rows(session.read('Articles_getlist',{'filters':filters,
            'extra_properties':{'common':'min','amount_type_id':True,'article_type':True},'length':2}),2)
        if len(articles)!=1 or integer(articles[0].get('article_id'),1)!=article_id or integer(articles[0].get('article_type'))!=1:raise LocalRefusal('commerce_article_unavailable')
        label(articles[0].get('article_name'))
        units=remote_rows(session.read('Amounttypes_getlist'))
        matches=[u for u in units if integer(u.get('amount_type_id'),1)==integer(articles[0].get('amount_type_id'),1)]
        if len(matches)!=1 or 'time_interval' not in matches[0]:raise LocalRefusal('commerce_article_unavailable')
        precision=integer(matches[0].get('value_precision'));interval=matches[0].get('time_interval')
        if isinstance(interval,bool):raise LocalRefusal('commerce_article_unavailable')
        if precision>9 or (unit=='hours' and precision<3):raise LocalRefusal('commerce_article_unavailable')
        if interval not in (None,0,'0') and (unit is None or str(interval)!=('60' if unit=='hours' else '1')):raise LocalRefusal('commerce_article_unavailable')
        return precision,label(articles[0].get('article_name'))

    def sale_binding(self,db,v,a,context):
        fields=('visit_id','account_id','place_id','client_id','identity','state','time_article_id','unit','time_confirmed')
        return digest([v,{k:a[k] for k in fields},self.settings(db)['revision'],self.actor(context)])

    def require_sale_validation(self,cmd,v,a,context,db=None):
        proof=cmd['parameters'].get('_validation')
        if not isinstance(proof,dict) or cmd['baseline'] is None:raise LocalRefusal('commerce_validation_required')
        age=(datetime.fromisoformat(self.service.now())-datetime.fromisoformat(proof['validated_at'])).total_seconds()
        if db is None:
            with self.service.application.storage.transaction() as current_db:binding=self.sale_binding(current_db,v,a,context)
        else:binding=self.sale_binding(db,v,a,context)
        if not 0<=age<=15 or proof['binding']!=binding:raise LocalRefusal('commerce_validation_required')

    def commerce_validate(self,session,payload,context):
        cmd,v,a=self.read_context(payload['command_id'],context);params=cmd['parameters'];kind=cmd['kind']
        if kind not in ('time','consumption'):raise LocalRefusal('commerce_denied')
        if cmd['state']!='prepared':return {'command_id':cmd['command_id'],'state':cmd['state']}
        if not a or a['state']!='open':raise LocalRefusal('commerce_not_ready')
        if kind=='time' and params['minutes']==0:return {'command_id':cmd['command_id'],'state':'prepared'}
        with self.service.application.storage.transaction() as db:
            current=self.command(db,cmd['command_id'])
            if current['state']!='prepared':return {'command_id':cmd['command_id'],'state':current['state']}
            if current['parameters']!=params:raise LocalRefusal('commerce_stale')
            # A failed new validation must not leave an older proof usable.
            db.execute('UPDATE local_commerce_commands SET baseline=NULL WHERE command_id=?',(cmd['command_id'],))
            settings=self.settings(db);binding=self.sale_binding(db,v,a,context)
        if kind=='consumption':
            if params['consumer']=='child' and params['article_id'] not in {r['article_id'] for r in json.loads(settings['articles'])}:raise LocalRefusal('commerce_article_unavailable')
            if params['consumer']=='guardian' and (settings['guardian_category_id'] is None or settings['guardian_category_id']!=params.get('category_id')):raise LocalRefusal('commerce_guardian_category_required')
            child=next((m for m in v['family_members'] if m['child_id']==params.get('consumer_child_id',v['child_id'])),None)
            if params['consumer']=='child' and (child is None or params['article_id'] not in json.loads(child['allowed_articles'])):raise LocalRefusal('commerce_parent_permission')
        baseline=self.quantities(self.account(session,a))
        precision,article_label=self.article(session,params['article_id'],params.get('unit'),params.get('category_id'))
        quantity=(Decimal(params['minutes'])/(60 if params['unit']=='hours' else 1)).quantize(Decimal(1).scaleb(-precision),rounding=ROUND_HALF_UP) if kind=='time' else money(params['quantity'])
        if quantity<=0 or quantity!=quantity.quantize(Decimal(1).scaleb(-precision)):raise LocalRefusal('commerce_invalid_quantity')
        with self.service.application.storage.transaction() as db:
            current=self.command(db,cmd['command_id']);fresh=self.visit(db,v['visit_id'])
            fresh_account=db.execute('SELECT * FROM local_commerce_accounts WHERE visit_id=?',(v['visit_id'],)).fetchone()
            if current['state']!='prepared':return {'command_id':cmd['command_id'],'state':current['state']}
            if current['parameters']!=params or self.sale_binding(db,fresh,dict(fresh_account),context)!=binding:raise LocalRefusal('commerce_stale')
            validated={**params,'quantity':str(quantity),'label':article_label,
                '_validation':{'validated_at':self.service.now(),'binding':binding}}
            db.execute('UPDATE local_commerce_commands SET parameters=?,baseline=?,error_code=NULL WHERE command_id=?',
                (canonical(validated),canonical(baseline),cmd['command_id']))
        return {'command_id':cmd['command_id'],'state':'prepared'}

    def commerce_execute(self,session,payload,context):
        cmd,v,a=self.read_context(payload['command_id'],context)
        payment=cmd['kind']=='payment'
        if payment != payload.get('_cashier',False):raise LocalRefusal('commerce_denied')
        if cmd['state']!='prepared':return {'command_id':cmd['command_id'],'state':cmd['state']}
        params=cmd['parameters'];kind=cmd['kind'];baseline=None;quantity=None
        if kind=='parent':
            if params['source_digest']!=self.parent_digest(v):raise LocalRefusal('commerce_stale')
            rows=self.parent_rows(session,v)
            if rows:return self.confirm_parent(cmd,v,self.require_parent(rows[0],v))
            with self.service.application.storage.transaction() as db:
                abandoned=db.execute("SELECT parameters FROM local_commerce_commands WHERE registration_id=? AND kind='parent' AND state='abandoned' LIMIT 1001",(v['registration_id'],)).fetchall()
            if len(abandoned)>1000:raise LocalRefusal('commerce_review_limit')
            if any(json.loads(row['parameters']).get('source_digest')==params['source_digest'] for row in abandoned):raise LocalRefusal('commerce_parent_attempt_retired')
            endpoint='Clients_createsmart';body={'client':{'client_name':v['guardian_name'],'tel':v['phone'],'email':v['email'],'client_code':'3mm_'+v['registration_id']}}
        elif kind=='open':
            if self.parent_digest(v)!=params['source_digest']:raise LocalRefusal('commerce_stale')
            rows=self.parent_rows(session,v)
            if not rows:raise LocalRefusal('commerce_parent_not_found')
            self.require_parent(rows[0],v,expected_client_id=a['client_id'])
            places=remote_rows(session.read('Places_getlist'),10000)
            matches=[p for p in places if integer(p.get('place_id'),1)==a['place_id']]
            if len(matches)!=1 or not self.place_available(matches[0]):raise LocalRefusal('commerce_remote_closed_or_timer')
            endpoint='Accounts_create';body={'account':{'uuid':a['identity'],'place_id':a['place_id'],'client_id':a['client_id'],'account_alias':'3mm '+a['identity']},'rows':[]}
        else:
            if not a or a['state']!='open':raise LocalRefusal('commerce_not_ready')
            if kind=='time' and params['minutes']==0:
                # Zero-duration stays create no sale and no external request.
                with self.service.application.storage.transaction() as db:
                    current=self.command(db,cmd['command_id']);fresh=self.visit(db,v['visit_id'])
                    if current['state']!='prepared':return {'state':current['state']}
                    if digest(fresh)!=digest(v):raise LocalRefusal('commerce_stale')
                    db.execute("UPDATE local_commerce_commands SET state='confirmed',parameters=? WHERE command_id=?",(canonical({**params,'quantity':'0'}),cmd['command_id']))
                    db.execute("UPDATE local_commerce_accounts SET time_confirmed=1,quantity='0' WHERE visit_id=?",(v['visit_id'],))
                return {'state':'confirmed'}
            body={'account_id':a['account_id'],'account':{},'orders':[],'payments':[],'flag_close_account':0};endpoint='Accounts_place'
            if payment:
                remote=self.account(session,a);baseline=self.quantities(remote)
                if v['state']!='closed' or not a['time_confirmed'] or params['expires_at']<=self.service.now() or self.fingerprint(remote)!=params['fingerprint']:raise LocalRefusal('commerce_quote_expired')
                if params['paymethod_id'] not in [m['paymethod_id'] for m in self.methods(session)]:raise LocalRefusal('commerce_quote_expired')
                endpoint='Accounts_close'
                body={'account_id':a['account_id'],'payments':[{'paymethod_id':params['paymethod_id'],
                    'original_paid_sum':float(money(params['amount'])),'currency_id':params['currency_id']}]}
            else:
                # Only the preceding read-only validation may supply quantities
                # and baseline. It is short-lived and bound to this actor and
                # the current local family, account and configuration.
                self.require_sale_validation(cmd,v,a,context)
                baseline=json.loads(cmd['baseline']);quantity=money(params['quantity'])
                body['orders']=[{'article_id':params['article_id'],'amount':float(quantity)}]
        with self.service.application.storage.transaction() as db:
            current=self.command(db,cmd['command_id']);fresh=self.visit(db,v['visit_id'])
            if current['state']!='prepared':return {'command_id':cmd['command_id'],'state':current['state']}
            if digest(fresh)!=digest(v):raise LocalRefusal('commerce_stale')
            if kind in ('time','consumption'):
                fresh_account=db.execute('SELECT * FROM local_commerce_accounts WHERE visit_id=?',(v['visit_id'],)).fetchone()
                if current['parameters']!=params:raise LocalRefusal('commerce_stale')
                self.require_sale_validation(current,fresh,dict(fresh_account),context,db)
            if payment:
                q=db.execute('SELECT * FROM local_commerce_quotes WHERE quote_id=?',(params['quote_id'],)).fetchone()
                if q is None or q['used'] or q['actor']!=self.actor(context) or q['expires_at']<=self.service.now():raise LocalRefusal('commerce_quote_expired')
                db.execute('UPDATE local_commerce_quotes SET used=1 WHERE quote_id=?',(params['quote_id'],))
            db.execute("UPDATE local_commerce_commands SET state='uncertain',baseline=?,error_code='commerce_check_required' WHERE command_id=?",(canonical(baseline) if baseline is not None else None,cmd['command_id']))
            if kind in ('time','consumption'):
                params={**params,'quantity':str(quantity)}
                db.execute('UPDATE local_commerce_commands SET parameters=? WHERE command_id=?',(canonical(params),cmd['command_id']))
        # The durable uncertainty fence commits BEFORE the only external POST.
        try:
            response=session.request('POST',endpoint,body,cmd['command_id'].removeprefix('commercial_'))
            if payment:
                if response is not None:raise ValueError()
                remote_id=a['account_id']
            else:remote_id=integer(response,1)
            if kind not in ('parent','open') and remote_id!=a['account_id']:raise ValueError()
            with self.service.application.storage.transaction() as db:
                db.execute('UPDATE local_commerce_commands SET acknowledged=1,candidate_id=? WHERE command_id=?',(remote_id,cmd['command_id']))
        except _NotDispatched:
            # Undo only our uncertainty fence when no SDK dispatch was possible,
            # or the SDK explicitly proves it. HTTP errors, absent remote orders
            # and ambiguous transport failures must never take this path.
            with self.service.application.storage.transaction() as db:
                restored=db.execute("UPDATE local_commerce_commands SET state='prepared',baseline=NULL,error_code='commerce_delivery_not_sent' WHERE command_id=? AND state='uncertain' AND acknowledged=0 AND candidate_id IS NULL",(cmd['command_id'],)).rowcount
                if restored and payment:
                    # Only a proven unsent payment can release its one-shot
                    # quote. The original actor/amount/expiry checks still apply.
                    db.execute('UPDATE local_commerce_quotes SET used=0 WHERE quote_id=? AND actor=?',(params['quote_id'],self.actor(context)))
                state=self.command(db,cmd['command_id'])['state']
            if restored:raise LocalRefusal('commerce_delivery_not_sent') from None
            return {'command_id':cmd['command_id'],'state':state}
        except (LocalRefusal,ValueError,TypeError):pass
        return {'command_id':cmd['command_id'],'state':'uncertain'}

    def cashier_execute(self,session,payload,context):return self.commerce_execute(session,{**payload,'_cashier':True},context)

    def confirm_parent(self,cmd,v,client_id):
        with self.service.application.storage.transaction() as db:
            current=self.command(db,cmd['command_id'])
            if current['state'] not in ('prepared','uncertain'):return {'command_id':cmd['command_id'],'state':current['state']}
            fresh=self.visit(db,v['visit_id'])
            if self.parent_digest(fresh)!=cmd['parameters']['source_digest']:raise LocalRefusal('commerce_stale')
            db.execute('INSERT INTO local_commerce_parents VALUES(?,?,?) ON CONFLICT(registration_id) DO UPDATE SET client_id=excluded.client_id,source_digest=excluded.source_digest',
                (v['registration_id'],client_id,self.parent_digest(v)))
            db.execute("UPDATE local_commerce_commands SET state='confirmed',error_code=NULL WHERE command_id=?",(cmd['command_id'],))
        return {'command_id':cmd['command_id'],'state':'confirmed'}

    def commerce_check(self,session,payload,context):
        cmd,v,a=self.read_context(payload['command_id'],context);params=cmd['parameters'];kind=cmd['kind']
        if (kind=='payment') != payload.get('_cashier',False):raise LocalRefusal('commerce_denied')
        if cmd['state']!='uncertain':return {'command_id':cmd['command_id'],'state':cmd['state']}
        if kind=='parent':
            rows=self.parent_rows(session,v)
            if not rows:raise LocalRefusal('commerce_parent_not_found')
            return self.confirm_parent(cmd,v,self.require_parent(rows[0],v))
        if kind=='open':
            candidate=payload.get('account_id') or cmd['candidate_id']
            if candidate is None:
                # A lost create reply never permits another POST. Locate one
                # exact marker among this client's open bills on this place,
                # then verify the full account independently below.
                rows=remote_rows(session.read('Accounts_getlist',{'filters':{
                    'client_id':a['client_id'],'place_id':a['place_id'],'status':0},
                    'extra_properties':[],'offset':0,'length':101,'order_by':{'account_id':'asc'}}),101)
                if len(rows)>100:raise LocalRefusal('commerce_review_limit')
                marker='3mm '+a['identity']
                matches=[r for r in rows if isinstance(r.get('account_alias'),str)
                    and (r['account_alias']==marker or r['account_alias'].startswith(marker+' | '))]
                if len(matches)>1:raise LocalRefusal('commerce_identity_conflict')
                if not matches:raise LocalRefusal('commerce_account_id_required')
                candidate=integer(matches[0].get('account_id'),1)
            a={**a,'account_id':candidate};remote=self.account(session,a,open_only=False)
            if integer(remote['status'])!=0 or integer(remote.get('time_calculation'))!=0:raise LocalRefusal('commerce_remote_closed_or_timer')
        else:
            remote=self.account(session,a,open_only=False)
            if kind=='payment':
                if not self.paid(remote) or integer(remote.get('currency_id'),1)!=params['currency_id'] or self.fingerprint_orders(remote)!=self.fingerprint_orders_from_baseline(cmd):raise LocalRefusal('commerce_check_required')
            else:
                expected=json.loads(cmd['baseline']);key=str(params['article_id']);expected[key]=str(money(expected.get(key,'0'))+money(params['quantity']))
                expected={key:str(Decimal(value).normalize()) for key,value in expected.items() if Decimal(value)!=0}
                if self.quantities(remote)!=expected:raise LocalRefusal('commerce_check_required')
            if not cmd['acknowledged'] and not payload['reviewed']:raise LocalRefusal('commerce_manual_review_required')
        with self.service.application.storage.transaction() as db:
            current=self.command(db,cmd['command_id'])
            if current['state']!='uncertain':return {'command_id':cmd['command_id'],'state':current['state']}
            db.execute("UPDATE local_commerce_commands SET state='confirmed',error_code=NULL WHERE command_id=?",(cmd['command_id'],))
            if kind=='open':
                db.execute("UPDATE local_commerce_accounts SET account_id=?,state='open',remote_state='open',observed_at=? WHERE visit_id=?",(a['account_id'],self.service.now(),v['visit_id']))
                db.execute('UPDATE local_commerce_families SET opening_error=NULL WHERE visit_id=?',(v['visit_id'],))
            if kind=='time':db.execute('UPDATE local_commerce_accounts SET time_confirmed=1,quantity=? WHERE visit_id=?',(params['quantity'],v['visit_id']))
            if kind=='payment':db.execute("UPDATE local_commerce_accounts SET state='closed',remote_state='closed',observed_at=? WHERE visit_id=?",(self.service.now(),v['visit_id']))
        return {'command_id':cmd['command_id'],'state':'confirmed'}

    def cashier_check(self,session,payload,context):return self.commerce_check(session,{**payload,'_cashier':True},context)

    def fingerprint_orders(self,account):return self.quantities(account)
    def fingerprint_orders_from_baseline(self,cmd):return json.loads(cmd['baseline'])

    @staticmethod
    def paid(account):
        return (integer(account.get('status'))==1 and money(account.get('total_remain'))==0
            and money(account.get('total_paid'))>=money(account.get('total_real'))>=0 and integer(account.get('fx'))==1
            and money(account.get('currency_rate'))==1)

    def methods(self,session):
        rows=remote_rows(session.read('Paymentmethods_getlist',{'filters':{'delete_flag':0},'extra_properties':{'currencies':True}}))
        return [{'paymethod_id':integer(r.get('paymethod_id'),1),'label':label(r.get('name'))} for r in rows
            if isinstance(r,dict) and str(r.get('type_id')) in ('1','5') and str(r.get('fx'))=='1'
            and r.get('provider_id') in (None,0,'0') and r.get('require_info') in (None,False,0,'0','') and not r.get('currencies')][:32]

    def commerce_preview(self,session,payload,context):
        with self.service.application.storage.transaction() as db:
            v=self.visit(db,payload['visit_id']);a=db.execute('SELECT * FROM local_commerce_accounts WHERE visit_id=?',(v['visit_id'],)).fetchone()
            if a is None or a['state']!='open' or v['state']!='closed' or not a['time_confirmed']:raise LocalRefusal('commerce_finish_first')
            if db.execute("SELECT 1 FROM local_commerce_commands WHERE visit_id=? AND state IN ('prepared','uncertain')",(v['visit_id'],)).fetchone():raise LocalRefusal('commerce_pending')
            a=dict(a)
        remote=self.account(session,a);amount=money(remote.get('total_remain'));currency=integer(remote.get('currency_id'),1)
        if amount<=0 or amount.as_tuple().exponent < -2 or money(remote.get('currency_rate'))!=1:raise LocalRefusal('commerce_invalid_payment')
        methods=self.methods(session);currencies=remote_rows(session.read('Currencies_getlist'))
        codes=[r.get('currency_code') for r in currencies if integer(r.get('currency_id'),1)==currency] if isinstance(currencies,list) else []
        if not methods or len(codes)!=1 or not isinstance(codes[0],str) or len(codes[0])!=3 or not codes[0].isascii() or not codes[0].isalpha():raise LocalRefusal('commerce_invalid_payment')
        quote='quote_'+uuid.uuid4().hex;expiry=(self.service.application.clock.now()+timedelta(minutes=2)).isoformat()
        with self.service.application.storage.transaction() as db:
            db.execute('INSERT INTO local_commerce_quotes VALUES(?,?,?,?,?,?,?,?,?,0)',(quote,v['visit_id'],self.actor(context),self.fingerprint(remote),str(amount),currency,codes[0].upper(),canonical(methods),expiry))
        return {'quote_id':quote,'amount':str(amount),'currency_code':codes[0].upper(),'methods':methods,'expires_at':expiry}

    def commerce_observe(self,session,payload,context):
        with self.service.application.storage.transaction() as db:
            anchor=self.service.families.anchor(db,payload['visit_id'])
            a=db.execute('SELECT * FROM local_commerce_accounts WHERE visit_id=?',(anchor,)).fetchone()
            if a is None or not a['account_id']:raise LocalRefusal('commerce_not_ready')
            a=dict(a)
            db.execute("UPDATE local_commerce_accounts SET remote_state='unknown',observed_at=NULL WHERE visit_id=?",(a['visit_id'],))
        remote=self.account(session,a,open_only=False);state='closed' if integer(remote['status'])==1 else 'open'
        with self.service.application.storage.transaction() as db:
            db.execute('UPDATE local_commerce_accounts SET remote_state=?,observed_at=? WHERE visit_id=?',(state,self.service.now(),a['visit_id']))
        return {'state':state}

    def commerce_release_unlinked(self,session,payload,context):
        if payload['reviewed'] is not True or payload['accepted_orphaned_parent'] is not True:raise LocalRefusal('commerce_unlinked_release_denied')
        reason=payload['reason'].strip()
        if not reason or len(reason)>240:raise LocalRefusal('commerce_unlinked_release_denied')
        with self.service.application.storage.transaction() as db:
            v=self.visit(db,payload['visit_id'])
            family=db.execute('SELECT * FROM local_commerce_families WHERE visit_id=?',(v['visit_id'],)).fetchone()
            family=dict(family) if family else None
            if v['state']!='closed' or db.execute('SELECT 1 FROM local_commerce_accounts WHERE visit_id=?',(v['visit_id'],)).fetchone():raise LocalRefusal('commerce_unlinked_release_denied')
            commands=[self.command(db,r[0]) for r in db.execute("SELECT command_id FROM local_commerce_commands WHERE visit_id=? OR (registration_id=? AND kind='parent') ORDER BY sequence LIMIT 1001",(v['visit_id'],v['registration_id']))]
        if len(commands)>1000:raise LocalRefusal('commerce_review_limit')
        for cmd in commands:
            if cmd['visit_id']==v['visit_id'] and cmd['kind'] in ('open','time','consumption','payment') and cmd['state']!='cancelled':raise LocalRefusal('commerce_unlinked_release_denied')
            if cmd['state'] in ('prepared','uncertain') and (cmd['kind']!='parent' or cmd['visit_id']!=v['visit_id']):raise LocalRefusal('commerce_unlinked_release_denied')
        # Read exact registration code only. An existing remote client is retained,
        # never rebound by name or deleted as part of retiring a local attempt.
        rows=self.parent_rows(session,v);remote_client=None
        if rows:
            if rows[0].get('client_code')!='3mm_'+v['registration_id']:raise LocalRefusal('commerce_identity_conflict')
            remote_client=integer(rows[0].get('client_id'),1)
        now=self.service.now();release_id='commercial_'+uuid.uuid4().hex;snapshot=digest(commands)
        with self.service.application.storage.transaction() as db:
            fresh=self.visit(db,v['visit_id'])
            fresh_family=db.execute('SELECT * FROM local_commerce_families WHERE visit_id=?',(v['visit_id'],)).fetchone()
            fresh_family=dict(fresh_family) if fresh_family else None
            fresh_commands=[self.command(db,r[0]) for r in db.execute("SELECT command_id FROM local_commerce_commands WHERE visit_id=? OR (registration_id=? AND kind='parent') ORDER BY sequence LIMIT 1001",(v['visit_id'],v['registration_id']))]
            if (digest(fresh)!=digest(v) or fresh_family!=family or digest(fresh_commands)!=snapshot
                    or db.execute('SELECT 1 FROM local_commerce_accounts WHERE visit_id=?',(v['visit_id'],)).fetchone()):raise LocalRefusal('commerce_stale')
            previous=next((c for c in commands if c['visit_id']==v['visit_id'] and c['kind']=='release' and c['parameters'].get('mode')=='unlinked'),None)
            if family and family['opening_error']=='commerce_unlinked_archived' and previous:return {'state':'archived','command_id':previous['command_id']}
            retired=0
            for cmd in commands:
                if cmd['visit_id']==v['visit_id'] and cmd['kind']=='parent' and cmd['state'] in ('prepared','uncertain'):
                    retired+=1
                    params={**cmd['parameters'],'_recovery':{'release_id':release_id,'reason':reason,'actor':self.actor(context),
                        'resolved_at':now,'remote_client_id':remote_client,'original_state':cmd['state']}}
                    db.execute("UPDATE local_commerce_commands SET state='abandoned',parameters=?,error_code='commerce_parent_attempt_retired' WHERE command_id=?",(canonical(params),cmd['command_id']))
            db.execute("INSERT INTO local_commerce_families(visit_id,registration_id,opening_error) VALUES(?,?,'commerce_unlinked_archived') ON CONFLICT(visit_id) DO UPDATE SET opening_error='commerce_unlinked_archived'",(v['visit_id'],v['registration_id']))
            for member in v['family_members']:
                db.execute('INSERT INTO local_commerce_members(visit_id,family_visit_id) VALUES(?,?) ON CONFLICT(visit_id) DO NOTHING',(member['visit_id'],v['visit_id']))
            params={'mode':'unlinked','reason':reason,'actor':self.actor(context),'released_at':now,'retired_count':retired,'remote_client_id':remote_client}
            db.execute("INSERT INTO local_commerce_commands(command_id,owner_key,visit_id,kind,state,parameters,created_at) VALUES(?,?,?,'release','confirmed',?,?)",(release_id,'recovery:'+v['visit_id'],v['visit_id'],canonical(params),now))
        return {'state':'archived','command_id':release_id}

    def commerce_release_empty(self,session,payload,context):
        # Administrative reconciliation only: this method can GET, never POST.
        # The owner closes the exact empty bill in Barsy before releasing it.
        if payload['reviewed'] is not True or payload['accepted_missing_time'] is not True:raise LocalRefusal('commerce_empty_release_denied')
        reason=payload['reason'].strip()
        if not reason or len(reason)>240:raise LocalRefusal('commerce_empty_release_denied')
        with self.service.application.storage.transaction() as db:
            v=self.visit(db,payload['visit_id'])
            row=db.execute('SELECT * FROM local_commerce_accounts WHERE visit_id=?',(v['visit_id'],)).fetchone()
            if row is None or row['account_id']!=payload['expected_account_id'] or v['state']!='closed':raise LocalRefusal('commerce_empty_release_denied')
            a=dict(row)
            commands=[self.command(db,r[0]) for r in db.execute('SELECT command_id FROM local_commerce_commands WHERE visit_id=? ORDER BY sequence LIMIT 1001',(v['visit_id'],))]
        if len(commands)>1000:raise LocalRefusal('commerce_review_limit')
        for cmd in commands:
            if cmd['kind'] not in ('time','consumption','payment'):
                if cmd['state'] in ('prepared','uncertain'):raise LocalRefusal('commerce_empty_release_denied')
                continue
            if cmd['state']=='confirmed' and money(cmd['parameters'].get('quantity',cmd['parameters'].get('amount','0')))!=0:raise LocalRefusal('commerce_empty_release_denied')
            if cmd['state'] in ('prepared','uncertain') and (cmd['acknowledged'] or cmd['candidate_id'] is not None):raise LocalRefusal('commerce_empty_release_denied')
        remote=self.account(session,a,open_only=False)
        if (integer(remote['status'])!=1 or remote['orders'] or remote.get('payments')!=[] or remote.get('payments_history')!=[]
                or any(money(remote.get(k))!=0 for k in ('total_real','total_paid','total_remain'))):raise LocalRefusal('commerce_empty_release_denied')
        snapshot=digest(commands);now=self.service.now();release_id='commercial_'+uuid.uuid4().hex
        with self.service.application.storage.transaction() as db:
            fresh=self.visit(db,v['visit_id'])
            fresh_account=db.execute('SELECT * FROM local_commerce_accounts WHERE visit_id=?',(v['visit_id'],)).fetchone()
            fresh_commands=[self.command(db,r[0]) for r in db.execute('SELECT command_id FROM local_commerce_commands WHERE visit_id=? ORDER BY sequence LIMIT 1001',(v['visit_id'],))]
            if digest(fresh)!=digest(v) or dict(fresh_account)!=a or digest(fresh_commands)!=snapshot:raise LocalRefusal('commerce_stale')
            previous=next((c for c in commands if c['kind']=='release' and c['state']=='confirmed'),None)
            if previous and a['state']=='closed':return {'state':'closed','command_id':previous['command_id']}
            waived=0
            for cmd in commands:
                if cmd['kind'] in ('time','consumption','payment') and cmd['state'] in ('prepared','uncertain'):
                    waived+=1
                    params={**cmd['parameters'],'_recovery':{'release_id':release_id,'reason':reason,'actor':self.actor(context),'resolved_at':now,
                        'account_id':a['account_id'],'remote_snapshot':self.fingerprint(remote)}}
                    db.execute("UPDATE local_commerce_commands SET state='waived',parameters=?,error_code='commerce_empty_released' WHERE command_id=?",(canonical(params),cmd['command_id']))
            db.execute("UPDATE local_commerce_accounts SET state='closed',remote_state='closed',observed_at=? WHERE visit_id=?",(now,v['visit_id']))
            db.execute('UPDATE local_commerce_quotes SET used=1 WHERE visit_id=?',(v['visit_id'],))
            db.execute('UPDATE local_commerce_families SET opening_error=NULL WHERE visit_id=?',(v['visit_id'],))
            params={'reason':reason,'actor':self.actor(context),'released_at':now,'remote_account_id':a['account_id'],
                'waived_count':waived,'remote_snapshot':self.fingerprint(remote)}
            db.execute("INSERT INTO local_commerce_commands(command_id,owner_key,visit_id,kind,state,parameters,created_at) VALUES(?,?,?,'release','confirmed',?,?)",
                (release_id,'recovery:'+v['visit_id'],v['visit_id'],canonical(params),now))
        return {'state':'closed','command_id':release_id}

    def commerce_external_close(self,session,payload,context):
        if payload['reviewed'] is not True:raise LocalRefusal('commerce_manual_review_required')
        with self.service.application.storage.transaction() as db:
            v=self.visit(db,payload['visit_id']);a=db.execute('SELECT * FROM local_commerce_accounts WHERE visit_id=?',(v['visit_id'],)).fetchone()
            commands=[self.command(db,r[0]) for r in db.execute('SELECT command_id FROM local_commerce_commands WHERE visit_id=? LIMIT 1001',(v['visit_id'],))]
            if len(commands)>1000:raise LocalRefusal('commerce_review_limit')
        if a is None or v['state']!='closed' or not a['time_confirmed']:raise LocalRefusal('commerce_finish_first')
        if any(c['state'] in ('prepared','uncertain') and c['kind']!='payment' for c in commands):raise LocalRefusal('commerce_pending')
        remote=self.account(session,dict(a),open_only=False);expected={}
        for cmd in commands:
            if cmd['kind'] in ('time','consumption') and cmd['state']=='confirmed':
                p=cmd['parameters'];key=str(p['article_id']);expected[key]=str(money(expected.get(key,'0'))+money(p['quantity']))
        expected={key:str(Decimal(value).normalize()) for key,value in expected.items() if Decimal(value)!=0}
        if not self.paid(remote) or self.quantities(remote)!=expected:raise LocalRefusal('commerce_check_required')
        with self.service.application.storage.transaction() as db:
            # A local operator could have prepared a new sale during the GET.
            fresh=self.visit(db,v['visit_id'])
            if digest(fresh)!=digest(v) or db.execute("SELECT 1 FROM local_commerce_commands WHERE visit_id=? AND kind!='payment' AND state IN ('prepared','uncertain')",(v['visit_id'],)).fetchone():raise LocalRefusal('commerce_stale')
            db.execute("UPDATE local_commerce_accounts SET state='closed',remote_state='closed',observed_at=? WHERE visit_id=?",(self.service.now(),v['visit_id']))
            db.execute("UPDATE local_commerce_commands SET state='confirmed',error_code=NULL WHERE visit_id=? AND kind='payment' AND state='uncertain'",(v['visit_id'],))
            db.execute("UPDATE local_commerce_commands SET state='cancelled',error_code=NULL WHERE visit_id=? AND kind='payment' AND state='prepared'",(v['visit_id'],))
        return {'state':'closed'}
