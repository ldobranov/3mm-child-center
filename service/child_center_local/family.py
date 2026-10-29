"""Family membership and entry-triggered opening in the supervised native service.

Only opening is automatic. No consumption, time sale or payment is delivered by
this worker. Prepared/uncertain command fences are the existing commerce journal.
"""
import json
import threading
from datetime import datetime
from .errors import LocalRefusal


class Families:
    def __init__(self, service):
        self.service = service
        self.lock = threading.Lock()
        self.wake_requested = False
        self.running = False

    @staticmethod
    def anchor(db, visit_id):
        row = db.execute('SELECT family_visit_id FROM local_commerce_members WHERE visit_id=?', (visit_id,)).fetchone()
        return row[0] if row else visit_id

    def join(self, db, visit_id):
        registration = db.execute('''SELECT c.registration_id FROM local_visits v
            JOIN local_children c ON c.child_id=v.child_id WHERE v.visit_id=?''', (visit_id,)).fetchone()[0]
        families = db.execute('''SELECT f.visit_id FROM local_commerce_families f
            LEFT JOIN local_commerce_accounts a ON a.visit_id=f.visit_id
            WHERE f.registration_id=? AND COALESCE(f.opening_error,'')!='commerce_unlinked_archived' AND (a.state IS NULL OR a.state!='closed') LIMIT 2''', (registration,)).fetchall()
        if len(families) > 1:
            raise LocalRefusal('commerce_legacy_bills')
        anchor = families[0][0] if families else visit_id
        if families:
            # Once checkout starts the family cannot accumulate another unbilled
            # stay. The paid account must close before a new family visit.
            if db.execute("SELECT 1 FROM local_commerce_commands WHERE visit_id=? AND kind IN ('time','payment') AND state!='cancelled'", (anchor,)).fetchone():
                raise LocalRefusal('commerce_checkout_started')
            if db.execute('SELECT COUNT(*) FROM local_commerce_members WHERE family_visit_id=?', (anchor,)).fetchone()[0] >= 64:
                raise LocalRefusal('commerce_review_limit')
        else:
            db.execute('INSERT INTO local_commerce_families(visit_id,registration_id) VALUES(?,?)', (anchor,registration))
        db.execute('INSERT INTO local_commerce_members VALUES(?,?)', (visit_id,anchor))

    def members(self, db, visit_id):
        rows = db.execute('''SELECT v.*,c.display_name,c.allowed_articles FROM local_visits v
            JOIN local_children c ON c.child_id=v.child_id WHERE v.visit_id IN
            (SELECT visit_id FROM local_commerce_members WHERE family_visit_id=?)
            ORDER BY v.entered_at,v.visit_id LIMIT 65''', (visit_id,)).fetchall()
        if len(rows)>64:
            raise LocalRefusal('commerce_review_limit')
        return [dict(row) for row in rows]

    def finish(self, db, payload, context):
        if not context.has_application_permission('visits_manage'):
            raise LocalRefusal('commerce_denied')
        anchor = self.anchor(db,payload['visit_id'])
        members = self.members(db,anchor)
        active = [v for v in members if v['state']=='active']
        expected = {v['visit_id']:(v['expected_transition_at'],v['expected_phase']) for v in payload['members']}
        actual = {v['visit_id']:(v['last_transition_at'],'inside' if v['inside_since'] else 'paused') for v in active}
        if not active or expected!=actual or len(expected)!=len(payload['members']):
            raise LocalRefusal('commerce_stale')
        now = self.service.now()
        if any(datetime.fromisoformat(v['last_transition_at'])>datetime.fromisoformat(now) for v in active):
            raise LocalRefusal('commerce_stale')
        for v in active:
            self.service.finish_visit(db,{'visit_id':v['visit_id'],'expected_transition_at':v['last_transition_at'],
                'expected_phase':'inside' if v['inside_since'] else 'paused'},context)
        return {'state':'closed'}

    def transition(self, db, payload, context):
        if not context.has_application_permission('visits_manage'):
            raise LocalRefusal('commerce_denied')
        visit=db.execute('SELECT * FROM local_visits WHERE visit_id=?',(payload['visit_id'],)).fetchone()
        if not visit or visit['state']!='active' or visit['last_transition_at']!=payload['expected_transition_at']:
            raise LocalRefusal('commerce_stale')
        bracelet=db.execute('SELECT code FROM local_bracelets WHERE child_id=? AND retired_at IS NULL',(visit['child_id'],)).fetchone()
        if not bracelet:
            raise LocalRefusal('Unknown bracelet')
        action=payload['action']
        if (action=='pause')!=bool(visit['inside_since']):
            raise LocalRefusal('commerce_stale')
        self.service.scan_bracelet(db,{'code':bracelet[0],'action':action,'expected_visit_id':visit['visit_id']},context)
        return {'state':'saved'}

    def wake(self):
        if self.service.application.platform is None:
            return
        with self.service.application.storage.transaction() as db:
            if not self.service.commerce.settings(db)['default_place_id']:
                return
        with self.lock:
            self.wake_requested = True
            if self.running:
                return
            self.running = True
        threading.Thread(target=self.run, name='child-center-opening',daemon=True).start()

    def run(self):
        # No timer or periodic retry. Wake once at startup/entry/explicit retry;
        # after any error the cashier must review or explicitly continue.
        try:
            while True:
                with self.lock:
                    self.wake_requested = False
                with self.service.application.storage.transaction() as db:
                    settings = self.service.commerce.settings(db)
                    rows = db.execute('''SELECT f.visit_id FROM local_commerce_families f
                        LEFT JOIN local_commerce_accounts a ON a.visit_id=f.visit_id
                        WHERE f.opening_error IS NULL AND (a.state IS NULL OR a.state='prepared')
                        ORDER BY f.rowid LIMIT 100''').fetchall() if settings['default_place_id'] else []
                for row in rows:
                    self.open(row[0])
                with self.lock:
                    if not self.wake_requested and len(rows)<100:
                        self.running = False
                        return
        except Exception:
            # A crashed worker never retries a mutation. Durable uncertainty is
            # retained; a later entry or explicit action can request review.
            with self.lock:
                self.running = False

    def open(self, visit_id):
        from .commerce import Session
        commerce = self.service.commerce
        try:
            # Each phase has a fresh bounded connector budget. The worker is
            # outside the scan transaction and never delays event acknowledgement.
            for _ in range(6):
                with self.service.application.storage.transaction() as db:
                    detail = commerce.commerce_detail(db,{'visit_id':visit_id,'offset':0},None)
                    settings = commerce.settings(db)
                    if detail['opening_state']=='archived':return
                    if detail['account'] and detail['account']['state']=='open':
                        db.execute('UPDATE local_commerce_families SET opening_error=NULL WHERE visit_id=?',(visit_id,))
                        return
                    if not settings['default_place_id']:
                        return
                    if detail['attention']:
                        cmd = detail['attention'][0]
                        if cmd['kind'] not in ('parent','open'):
                            return
                        command_id,state = cmd['command_id'],cmd['state']
                    else:
                        kind = 'parent' if not detail['parent_linked'] else 'open'
                        result = commerce.commerce_prepare(db,{'visit_id':visit_id,'kind':kind,
                            'place_id':settings['default_place_id']},None)
                        command_id,state = result['command_id'],'prepared'
                if state=='prepared':
                    commerce.commerce_execute(Session(commerce),{'command_id':command_id},None)
                # Read-only confirmation is permitted, including after restart.
                # An uncertain command is never dispatched again.
                result = commerce.commerce_check(Session(commerce),{'command_id':command_id,'account_id':None,'reviewed':False},None)
                if result['state']!='confirmed':
                    raise LocalRefusal('commerce_check_required')
        except (LocalRefusal,ValueError,TypeError,KeyError,ArithmeticError) as error:
            with self.service.application.storage.transaction() as db:
                db.execute("UPDATE local_commerce_families SET opening_error='commerce_opening_review' WHERE visit_id=? AND COALESCE(opening_error,'')!='commerce_unlinked_archived'", (visit_id,))
                # Keep the bounded public domain reason on the pending step;
                # do not persist exception text, connector bodies or credentials.
                reason=str(error) if isinstance(error,LocalRefusal) else 'commerce_invalid_remote'
                if reason in {'commerce_unavailable','commerce_identity_conflict','commerce_stale','commerce_invalid_remote',
                        'commerce_remote_closed_or_timer','commerce_account_id_required','commerce_check_required',
                        'commerce_not_ready','commerce_parent_required','commerce_invalid_settings','commerce_review_limit',
                        'commerce_parent_code_unavailable','commerce_parent_code_mismatch','commerce_parent_not_found',
                        'commerce_parent_id_mismatch','commerce_parent_name_mismatch','commerce_parent_phone_mismatch',
                        'commerce_parent_email_mismatch','commerce_delivery_not_sent','commerce_parent_attempt_retired'}:
                    db.execute("UPDATE local_commerce_commands SET error_code=? WHERE visit_id=? AND kind IN ('parent','open') AND state IN ('prepared','uncertain')",(reason,visit_id))

    def retry(self, db, payload, context):
        if not context.has_application_permission('commerce_manage'):
            raise LocalRefusal('commerce_denied')
        anchor = self.anchor(db,payload['visit_id'])
        archived=db.execute('SELECT opening_error FROM local_commerce_families WHERE visit_id=?',(anchor,)).fetchone()
        if archived and archived['opening_error']=='commerce_unlinked_archived':raise LocalRefusal('commerce_unlinked_archived')
        self.service.commerce.visit(db,anchor)
        settings=self.service.commerce.settings(db)
        if not settings['default_place_id'] or not settings['time_article_id']:
            raise LocalRefusal('commerce_not_ready')
        if not db.execute('SELECT 1 FROM local_commerce_families WHERE visit_id=?',(anchor,)).fetchone():
            raise LocalRefusal('commerce_not_ready')
        db.execute('UPDATE local_commerce_families SET opening_error=NULL WHERE visit_id=?',(anchor,))
        return {'state':'prepared'}
