"""Own registrations, time and explicit journalled commercial steps."""
import hashlib
import json
import re
import uuid
from datetime import datetime, timezone
from .errors import LocalRefusal
from .administration import Administration
from .barsy import Barsy
from . import history
from .readers import Readers
from .commerce import Commerce
from .family import Families


def canonical(value):
    return json.dumps(value, ensure_ascii=False, sort_keys=True, separators=(',', ':'))


def digest(value):
    return hashlib.sha256(value.encode()).hexdigest()


def identity(prefix):
    return prefix + '_' + uuid.uuid4().hex


class LocalService:
    # Audiences are checked again here; Core separately enforces each permission.
    READS = {
        'list_registrations': ('operator', 'administrator'),
        'get_registration': ('operator', 'administrator'),
        'list_visits': ('operator', 'administrator'),
        'request_outcome': ('operator', 'administrator'),
        'visit_request_outcome': ('operator', 'administrator'),
        'privacy_request_outcome': ('administrator',),
        'kiosk_request_outcome': ('kiosk',),
        'admin_list_clients': ('administrator',),
        'admin_get_client': ('administrator',),
        'admin_get_settings': ('administrator',),
        'admin_request_outcome': ('administrator',),
        'get_visit': ('operator', 'administrator'),
        'preview_scan': ('operator', 'administrator'),
        'get_reader_settings': ('administrator',),
        'list_reader_activity': ('administrator',),
        'reader_request_outcome': ('administrator',),
        'commerce_settings': ('administrator',),
        'registration_choices': ('operator','administrator'),'kiosk_registration_choices': ('kiosk',),
        'commerce_list': ('operator','administrator'), 'commerce_detail': ('operator','administrator'),
        'cashier_list': ('operator','administrator'), 'cashier_detail': ('operator','administrator'),
        'commerce_request_outcome': ('operator','administrator'), 'cashier_request_outcome': ('operator','administrator'),
        'commerce_settings_outcome': ('administrator',),'commerce_child_outcome': ('operator','administrator'),
        'family_open_outcome': ('operator','administrator'),'commerce_recovery_outcome': ('operator','administrator'),
    }
    WRITES = {
        'register_client': ('operator', 'administrator'),
        'submit_registration': ('kiosk',),
        'approve_registration': ('operator', 'administrator'),
        'assign_identifier': ('operator', 'administrator'),
        'retire_identifier': ('operator', 'administrator'),
        'scan_bracelet': ('operator', 'administrator'),
        'finish_visit': ('operator', 'administrator'),
        'export_personal_data': ('administrator',),
        'erase_personal_data': ('administrator',),
        'admin_update_client': ('administrator',),
        'admin_save_settings': ('administrator',),
        'confirm_scan': ('operator', 'administrator'),
        'set_reader_settings': ('administrator',),
        'commerce_save_settings': ('administrator',), 'commerce_prepare': ('operator','administrator'),
        'cashier_prepare': ('operator','administrator'), 'commerce_cancel': ('operator','administrator'),
        'commerce_allow_child': ('operator','administrator'),
        'cashier_cancel': ('operator','administrator'),
        'family_finish': ('operator','administrator'),
        'family_transition': ('operator','administrator'),
        'family_retry_open': ('operator','administrator'),
    }

    def __init__(self, application):
        self.application = application
        self.administration = Administration(self)
        self.barsy = Barsy(application)
        self.readers = Readers(self)
        self.commerce = Commerce(self)
        self.families = Families(self)
        self.families.wake()

    def handler(self, operation):
        if operation in ('family_finish','family_transition','family_retry_open'):
            return getattr(self.families,{'family_finish':'finish','family_transition':'transition','family_retry_open':'retry'}[operation])
        if operation in Commerce.LOCAL:
            return lambda db,payload,context:self.commerce.local(db,operation,payload,context)
        if operation in ('get_reader_settings','list_reader_activity','set_reader_settings'):
            return getattr(self.readers, operation)
        return getattr(self.administration, operation) if operation.startswith('admin_') else getattr(self, operation)

    def now(self):
        return self.application.clock.now().astimezone(timezone.utc).isoformat()

    @staticmethod
    def actor(context):
        if context.audience in ('operator', 'administrator'):
            if type(context.user_id) is not int or context.user_id < 1:
                raise LocalRefusal('A current human actor is required')
            return context.audience + ':' + str(context.user_id)
        if context.audience == 'kiosk':
            terminal = context.terminal_id
            if not isinstance(terminal, str) or re.fullmatch(r'[0-9a-f]{32}',terminal) is None:
                raise LocalRefusal('A current Core kiosk identity is required')
            return 'kiosk:' + terminal
        return context.audience

    def key(self, context, request_id):
        # A kiosk key is a high-entropy receipt capability, never an enumeration ID.
        if not isinstance(request_id, str) or len(request_id) != 32:
            raise LocalRefusal('A 32-character request ID is required')
        try:
            int(request_id, 16)
        except ValueError:
            raise LocalRefusal('Invalid request ID') from None
        return digest(self.actor(context) + '\0' + request_id)

    def handle(self, operation, payload, context):
        if operation in ('admin_get_settings','admin_save_settings'):
            self.administration.settings_authority(context)
        if operation.startswith('ui_preferences_'):
            if context.audience not in ('operator','administrator') or payload:
                raise LocalRefusal('Operation is unavailable for this audience')
            self.actor(context)
            if not context.has_application_permission(operation.removeprefix('ui_preferences_')):
                raise LocalRefusal('commerce_denied')
            with self.application.storage.transaction() as db:
                return {'debug_mode':bool(db.execute('SELECT debug_mode FROM local_ui_settings WHERE singleton=1').fetchone()[0])}
        if operation=='commerce_catalog':
            self.actor(context)
            return self.commerce.catalog(payload,context)
        if operation=='family_open_outcome' and not context.has_application_permission('commerce_manage'):
            raise LocalRefusal('commerce_denied')
        if operation=='commerce_places':
            self.actor(context)
            return self.commerce.places(context)
        if operation in Commerce.EXTERNAL:
            self.actor(context)
            return self.commerce.external(operation,payload,context)
        if operation == 'process_network_scan':
            result=self.readers.process(payload, context)
            if result['outcome']=='started':self.families.wake()
            return result
        if operation == 'health':
            if context.audience != 'internal' or payload:
                raise LocalRefusal('Health is internal')
            # This approved native app owns its SDK-managed SQLite database;
            # it does not request per-transaction scoped SQL authority.
            if self.application.storage.status().get('revision') != 'local_0007':
                raise LocalRefusal('Storage is not ready')
            return {'status': 'ready'}
        allowed = ('administrator',) if operation in Barsy.OPERATIONS else self.READS.get(operation, self.WRITES.get(operation, ()))
        if context.audience not in allowed:
            raise LocalRefusal('Operation is unavailable for this audience')
        self.actor(context)
        if operation in Commerce.LOCAL:self.commerce.authorize(operation,context)
        if operation in Barsy.OPERATIONS:
            # Never hold a local SQLite write transaction during external reads.
            return self.barsy.invoke(operation, payload)
        if operation in self.READS:
            with self.application.storage.transaction() as db:
                return self.handler(operation)(db, payload, context)
        key = self.commerce.key(context,context.idempotency_key) if operation in Commerce.LOCAL else self.key(context, context.idempotency_key)
        fingerprint = digest(canonical(payload))
        with self.application.storage.transaction() as db:
            old = db.execute('SELECT * FROM local_requests WHERE request_key=?', (key,)).fetchone()
            if old:
                if old['operation_id'] != operation or old['fingerprint'] != fingerprint:
                    return {'status': 'rejected', 'data': None, 'message': 'Request ID was reused with different data'}
                # Privacy exports are fresh reads; never keep personal data in receipts.
                if operation == 'export_personal_data' and json.loads(old['result_json'])['status'] == 'applied':
                    try:
                        return {'status': 'applied', 'data': self.export_personal_data(db, payload, context), 'message': None}
                    except LocalRefusal as error:
                        return {'status': 'rejected', 'data': None, 'message': str(error)}
                return json.loads(old['result_json'])
            # All domain validation precedes writes. Engine/transport exceptions
            # still escape and roll back; they never become a rejected receipt.
            db.execute('SAVEPOINT domain_command')
            try:
                data = self.handler(operation)(db, payload, context)
                result = {'status': 'applied', 'data': data, 'message': None}
            except LocalRefusal as error:
                db.execute('ROLLBACK TO domain_command')
                result = {'status': 'rejected', 'data': None, 'message': str(error)}
            finally:
                db.execute('RELEASE domain_command')
            stored = {**result, 'data': None} if operation == 'export_personal_data' else result
            db.execute('INSERT INTO local_requests VALUES (?,?,?,?)',
                       (key, operation, fingerprint, canonical(stored)))
            db.execute('INSERT INTO local_audit VALUES (?,?,?,?)',
                       (uuid.uuid4().hex, operation, self.actor(context), self.now()))
        if result['status']=='applied' and operation in ('scan_bracelet','confirm_scan','family_retry_open','commerce_save_settings'):
            self.families.wake()
        return result

    def request_outcome(self, db, payload, context):
        key = self.key(context, payload['request_id'])
        row = db.execute('SELECT operation_id,result_json FROM local_requests WHERE request_key=?', (key,)).fetchone()
        if row is None or row['operation_id'] != payload['operation_id']:
            return {'status': 'unknown', 'result_json': None}
        return {'status': 'confirmed', 'result_json': row['result_json']}

    kiosk_request_outcome = request_outcome
    visit_request_outcome = request_outcome
    privacy_request_outcome = request_outcome
    reader_request_outcome = request_outcome
    family_open_outcome = request_outcome

    def create(self, db, payload, approved):
        guardian = payload['guardian']
        name = guardian['display_name'].strip()
        phone, email = guardian['phone'].strip(), guardian['email'].strip()
        children = [child['display_name'].strip() for child in payload['children']]
        if not name or not (phone or email) or not all(children):
            raise LocalRefusal('Names and at least one contact are required')
        try:
            consent = datetime.fromisoformat(guardian['consented_at'])
        except ValueError:
            raise LocalRefusal('Explicit dated consent is required') from None
        if consent.tzinfo is None or not guardian['consent_version'].strip():
            raise LocalRefusal('Explicit dated consent is required')
        choices={row['article_id'] for row in self.commerce.registration_choices(db,{},None)['items']}
        allowed_children=[source.get('allowed_article_ids',[]) for source in payload['children']]
        if any(article not in choices for allowed in allowed_children for article in allowed):
            raise LocalRefusal('commerce_parent_permission')
        registration = identity('reg')
        db.execute('''INSERT INTO local_registrations(registration_id,status,guardian_name,phone,email,
            consent_version,consented_at,search_text,created_at,receipt_hash) VALUES (?,?,?,?,?,?,?,?,?,NULL)''',
                   (registration, 'approved' if approved else 'submitted', name, phone, email,
                    guardian['consent_version'], consent.isoformat(),
                    ' '.join([name, phone, email, *children]).casefold(), self.now()))
        for child,allowed in zip(children,allowed_children):
            db.execute('INSERT INTO local_children(child_id,registration_id,display_name,allowed_articles) VALUES (?,?,?,?)',
                (identity('child'), registration, child,canonical(allowed)))
        return {'registration_id': registration, 'status': 'approved' if approved else 'submitted'}

    def register_client(self, db, payload, context):
        return self.create(db, payload, True)

    def submit_registration(self, db, payload, context):
        return self.create(db, payload, False)

    def list_registrations(self, db, payload, context):
        query = payload['query'].strip().casefold().replace('\\', '\\\\').replace('%', '\\%').replace('_', '\\_')
        params = (payload['status'], payload['status'], '%' + query + '%')
        where = "status!='erased' AND (?='all' OR status=?) AND search_text LIKE ? ESCAPE '\\'"
        total = db.execute('SELECT COUNT(*) AS n FROM local_registrations WHERE ' + where, params).fetchone()['n']
        rows = db.execute('SELECT registration_id,status,guardian_name,created_at FROM local_registrations WHERE ' +
                          where + ' ORDER BY created_at DESC,registration_id DESC LIMIT ? OFFSET ?',
                          (*params, payload['limit'], payload['offset'])).fetchall()
        return {'items': [dict(row) for row in rows], 'total': total}

    @staticmethod
    def registration(db, registration_id):
        row = db.execute("SELECT * FROM local_registrations WHERE registration_id=? AND status!='erased'", (registration_id,)).fetchone()
        if row is None:
            raise LocalRefusal('Registration was not found')
        return row

    def get_registration(self, db, payload, context):
        row = self.registration(db, payload['registration_id'])
        children = db.execute('''SELECT c.child_id,c.display_name,b.assignment_id
            FROM local_children c LEFT JOIN local_bracelets b ON b.child_id=c.child_id AND b.retired_at IS NULL
            WHERE c.registration_id=? ORDER BY c.child_id LIMIT 8''', (row['registration_id'],)).fetchall()
        return {'registration_id': row['registration_id'], 'status': row['status'],
                'guardian': {'display_name': row['guardian_name'], 'phone': row['phone'], 'email': row['email']},
                'children': [dict(child) for child in children]}

    def approve_registration(self, db, payload, context):
        row = self.registration(db, payload['registration_id'])
        if row['status'] != 'submitted':
            raise LocalRefusal('Only a pending registration can be approved')
        db.execute("UPDATE local_registrations SET status='approved',revision=revision+1 WHERE registration_id=?", (row['registration_id'],))
        return {'status': 'approved'}

    def child(self, db, child_id):
        row = db.execute('''SELECT c.child_id,r.status FROM local_children c
            JOIN local_registrations r ON r.registration_id=c.registration_id WHERE c.child_id=?''', (child_id,)).fetchone()
        if row is None or row['status'] != 'approved':
            raise LocalRefusal('An approved child is required')
        return row

    def check_assignment(self, db, payload):
        self.child(db, payload['child_id'])
        active = db.execute('SELECT assignment_id FROM local_bracelets WHERE child_id=? AND retired_at IS NULL', (payload['child_id'],)).fetchone()
        if (active['assignment_id'] if active else None) != payload['expected_assignment_id']:
            raise LocalRefusal('Bracelet changed; refresh before continuing')
        return active

    def assign_identifier(self, db, payload, context):
        self.check_assignment(db, payload)
        code = payload['code'].strip()
        if not code or db.execute('SELECT 1 FROM local_bracelets WHERE code=? AND retired_at IS NULL', (code,)).fetchone():
            raise LocalRefusal('Bracelet is empty or already assigned')
        db.execute('UPDATE local_bracelets SET retired_at=? WHERE child_id=? AND retired_at IS NULL', (self.now(), payload['child_id']))
        assignment = identity('assign')
        db.execute('INSERT INTO local_bracelets VALUES (?,?,?,?,NULL)', (assignment, payload['child_id'], code, self.now()))
        return {'status': 'assigned', 'assignment_id': assignment}

    def retire_identifier(self, db, payload, context):
        if not self.check_assignment(db, payload):
            raise LocalRefusal('No active bracelet')
        db.execute('UPDATE local_bracelets SET retired_at=? WHERE assignment_id=?', (self.now(), payload['expected_assignment_id']))
        return {'status': 'retired'}

    @staticmethod
    def elapsed(visit, now):
        total = visit['accumulated_us']
        if visit['inside_since']:
            delta = datetime.fromisoformat(now) - datetime.fromisoformat(visit['inside_since'])
            total += max(0, (delta.days * 86400 + delta.seconds) * 1000000 + delta.microseconds)
        return total

    def scan_bracelet(self, db, payload, context, *, occurred_at=None):
        assigned = db.execute('SELECT child_id FROM local_bracelets WHERE code=? AND retired_at IS NULL', (payload['code'].strip(),)).fetchone()
        if assigned is None:
            raise LocalRefusal('Unknown bracelet')
        self.child(db, assigned['child_id'])
        visit = db.execute("SELECT * FROM local_visits WHERE child_id=? AND state='active'", (assigned['child_id'],)).fetchone()
        now = occurred_at or self.now()
        expected = payload['expected_visit_id']
        if (visit['visit_id'] if visit else None) != expected:
            raise LocalRefusal('Visit changed; refresh before continuing')
        action = payload['action']
        if action == 'start':
            if visit:
                raise LocalRefusal('Child already has an active stay')
            latest = db.execute('SELECT last_transition_at FROM local_visits WHERE child_id=? ORDER BY last_transition_at DESC LIMIT 1', (assigned['child_id'],)).fetchone()
            if latest and datetime.fromisoformat(now) < datetime.fromisoformat(latest['last_transition_at']):
                raise LocalRefusal('Clock moved backwards; refresh before continuing')
            visit_id = identity('visit')
            db.execute("INSERT INTO local_visits VALUES (?,?, 'active',?,?,0,?,NULL)", (visit_id, assigned['child_id'], now, now, now))
            self.families.join(db,visit_id)
            self.record_transition(db, visit_id, 'start', now, 'inside', 0)
            return {'status': 'inside', 'visit_id': visit_id}
        if visit is None or datetime.fromisoformat(now) < datetime.fromisoformat(visit['last_transition_at']):
            raise LocalRefusal('No active stay or clock moved backwards')
        inside = bool(visit['inside_since'])
        if action not in ('pause', 'resume') or inside != (action == 'pause'):
            raise LocalRefusal('Stay is already in the requested state')
        db.execute('UPDATE local_visits SET inside_since=?,accumulated_us=?,last_transition_at=? WHERE visit_id=?',
                   (None if inside else now, self.elapsed(visit, now), now, visit['visit_id']))
        self.record_transition(db, visit['visit_id'], action, now, 'paused' if inside else 'inside', self.elapsed(visit, now))
        return {'status': 'paused' if inside else 'inside', 'visit_id': visit['visit_id']}

    def finish_visit(self, db, payload, context):
        visit = db.execute("SELECT * FROM local_visits WHERE visit_id=? AND state='active'", (payload['visit_id'],)).fetchone()
        now = self.now()
        if visit is None or datetime.fromisoformat(now) < datetime.fromisoformat(visit['last_transition_at']):
            raise LocalRefusal('No active stay or clock moved backwards')
        if (visit['last_transition_at'] != payload['expected_transition_at']
                or ('inside' if visit['inside_since'] else 'paused') != payload['expected_phase']):
            raise LocalRefusal('Visit changed; refresh before continuing')
        total = self.elapsed(visit, now)
        db.execute("UPDATE local_visits SET state='closed',inside_since=NULL,accumulated_us=?,last_transition_at=?,exited_at=? WHERE visit_id=?", (total, now, now, visit['visit_id']))
        self.record_transition(db, visit['visit_id'], 'finish', now, 'closed', total)
        return {'status': 'closed', 'duration_seconds': total // 1000000, 'rounded_minutes': (total + 59999999) // 60000000}

    def list_visits(self, db, payload, context):
        return history.listed(self, db, payload)

    def visit_result(self, v):
        now = self.now()
        return {'visit_id': v['visit_id'], 'child_name': v['display_name'],
                          'phase': 'closed' if v['state'] == 'closed' else 'inside' if v['inside_since'] else 'paused',
                          'last_transition_at': v['last_transition_at'],
                          'entered_at': v['entered_at'], 'exited_at': v['exited_at'],
                          'duration_seconds': self.elapsed(v, now) // 1000000,
                          'rounded_minutes': (self.elapsed(v, now) + 59999999) // 60000000}

    def get_visit(self, db, payload, context):
        return history.detail(self, db, payload)

    @staticmethod
    def record_transition(db, visit_id, kind, occurred_at, phase, total):
        db.execute('''INSERT INTO local_visit_events(event_id,visit_id,kind,occurred_at,phase,accumulated_us)
            VALUES (?,?,?,?,?,?)''', (identity('event'),visit_id,kind,occurred_at,phase,total))

    def preview_scan(self, db, payload, context):
        assigned = db.execute('''SELECT b.assignment_id,c.child_id,c.display_name FROM local_bracelets b
            JOIN local_children c ON c.child_id=b.child_id WHERE b.code=? AND b.retired_at IS NULL''', (payload['code'].strip(),)).fetchone()
        if assigned is None:
            raise LocalRefusal('Unknown bracelet')
        self.child(db, assigned['child_id'])
        visit = db.execute("SELECT * FROM local_visits WHERE child_id=? AND state='active'", (assigned['child_id'],)).fetchone()
        phase = 'inside' if visit and visit['inside_since'] else 'paused' if visit else 'absent'
        action = {'inside':'pause','paused':'resume','absent':'start'}[phase]
        sequence = db.execute('SELECT MAX(sequence) FROM local_visit_events WHERE visit_id=?', (visit['visit_id'],)).fetchone()[0] if visit else None
        token = digest(canonical([assigned['assignment_id'], assigned['child_id'], assigned['display_name'],
            visit['visit_id'] if visit else None, visit['last_transition_at'] if visit else None, phase, sequence]))
        return {'child_name':assigned['display_name'],'phase':phase,'action':action,'preview_token':token,
                'visit_id':visit['visit_id'] if visit else None}

    def confirm_scan(self, db, payload, context):
        preview = self.preview_scan(db, payload, context)
        if preview['preview_token'] != payload['preview_token']:
            raise LocalRefusal('Scan changed; scan the bracelet again')
        return self.scan_bracelet(db, {'code':payload['code'],'action':preview['action'],
            'expected_visit_id':preview['visit_id']}, context)

    def export_personal_data(self, db, payload, context):
        registration = self.get_registration(db, payload, context)
        row = self.registration(db, payload['registration_id'])
        registration['consent'] = {'version': row['consent_version'], 'at': row['consented_at']}
        for child in registration['children']:
            visits = db.execute('SELECT * FROM local_visits WHERE child_id=? ORDER BY entered_at LIMIT 201', (child['child_id'],)).fetchall()
            assignments = db.execute('SELECT * FROM local_bracelets WHERE child_id=? ORDER BY assigned_at LIMIT 201', (child['child_id'],)).fetchall()
            if len(visits) > 200 or len(assignments) > 200:
                raise LocalRefusal('Subject exceeds the bounded inline export; a paginated export is required')
            child['visits'] = [dict(v) for v in visits]
            child['stay_events'] = []
            for visit in visits:
                events = db.execute('SELECT event_id,kind,occurred_at,phase,accumulated_us FROM local_visit_events WHERE visit_id=? ORDER BY sequence LIMIT 201', (visit['visit_id'],)).fetchall()
                if len(events) > 200:
                    raise LocalRefusal('Subject exceeds the bounded inline export; a paginated export is required')
                child['stay_events'].append({'visit_id':visit['visit_id'],'events':[dict(e) for e in events]})
            child['bracelets'] = [dict(a) for a in assignments]
            child['allowed_article_ids']=json.loads(db.execute('SELECT allowed_articles FROM local_children WHERE child_id=?',(child['child_id'],)).fetchone()[0])
            consents=db.execute('SELECT actor,consented_at,articles FROM local_consumption_consents WHERE child_id=? LIMIT 201',(child['child_id'],)).fetchall()
            if len(consents)>200:raise LocalRefusal('Subject exceeds the bounded inline export; a paginated export is required')
            child['consumption_consents']=[dict(r) for r in consents]
            child['commerce']=[]
            for visit in visits:
                anchor=self.families.anchor(db,visit['visit_id'])
                account=db.execute('SELECT * FROM local_commerce_accounts WHERE visit_id=?',(anchor,)).fetchone()
                commands=db.execute('SELECT command_id,kind,state,parameters,created_at,error_code FROM local_commerce_commands WHERE visit_id=? LIMIT 201',(anchor,)).fetchall()
                if len(commands)>200:raise LocalRefusal('Subject exceeds the bounded inline export; a paginated export is required')
                child['commerce'].append({'visit_id':visit['visit_id'],'family_visit_id':anchor,'account':dict(account) if account else None,'commands':[dict(r) for r in commands]})
        if len(canonical(registration).encode()) > 262144:
            raise LocalRefusal('Subject exceeds the bounded inline export')
        return {'document_json': canonical(registration)}

    def erase_personal_data(self, db, payload, context):
        if payload['confirmed'] is not True:
            raise LocalRefusal('Explicit confirmation is required')
        self.registration(db, payload['registration_id'])
        if db.execute('''SELECT 1 FROM local_commerce_accounts a JOIN local_visits v ON v.visit_id=a.visit_id
            JOIN local_children c ON c.child_id=v.child_id WHERE c.registration_id=? AND a.state!='closed' ''',
            (payload['registration_id'],)).fetchone() or db.execute("SELECT 1 FROM local_commerce_commands WHERE registration_id=? AND state IN ('prepared','uncertain')",(payload['registration_id'],)).fetchone():
            raise LocalRefusal('commerce_accounts_pending')
        if db.execute('''SELECT 1 FROM local_visits v JOIN local_children c ON c.child_id=v.child_id
            WHERE c.registration_id=? AND v.state='active' LIMIT 1''', (payload['registration_id'],)).fetchone():
            raise LocalRefusal('Finish active stays before erasure')
        db.execute('''UPDATE local_bracelets SET code=assignment_id,retired_at=COALESCE(retired_at,?)
            WHERE child_id IN (SELECT child_id FROM local_children WHERE registration_id=?)''', (self.now(), payload['registration_id']))
        db.execute("UPDATE local_children SET display_name='[erased]',allowed_articles='[]' WHERE registration_id=?", (payload['registration_id'],))
        db.execute("""UPDATE local_registrations SET status='erased',guardian_name='[erased]',phone='',email='',
            search_text='',consent_version='',consented_at='',receipt_hash=NULL,revision=revision+1 WHERE registration_id=?""", (payload['registration_id'],))
        return {'status': 'erased'}


def create_service(application):
    return LocalService(application)
