"""Core-delivered identifier events, durable outcomes and application-owned mode."""
from datetime import datetime, timedelta, timezone
import hashlib
import json
from three_mm_protocol.identifier_scan import IdentifierScanEventV1
from .errors import LocalRefusal


def canonical(value):
    return json.dumps(value, ensure_ascii=False, sort_keys=True, separators=(',', ':'))


def timestamp(value):
    parsed = datetime.fromisoformat(value)
    if parsed.tzinfo is None:
        raise ValueError('Timezone required')
    return parsed.astimezone(timezone.utc)


class Readers:
    def __init__(self, service):
        self.service = service

    def get_reader_settings(self, db, payload, context):
        row = db.execute('SELECT * FROM local_reader_settings WHERE singleton=1').fetchone()
        configuration = self.service.application.configuration
        return {'revision':row['revision'],'mode':row['mode'],'effective_from':row['effective_from'],
            **{key:json.loads(row[key]) for key in ('toggle_ids','entry_ids','exit_ids')},
            'device_ids':[configuration[key] for key in ('READER_DEVICE_ID','READER_SECONDARY_DEVICE_ID') if configuration.get(key)]}

    def set_reader_settings(self, db, payload, context):
        current = self.get_reader_settings(db, {}, context)
        if current['revision'] != payload['expected_revision']:
            raise LocalRefusal('Reader settings changed; refresh before saving')
        toggle, entry, exit_ids = (payload[key] for key in ('toggle_ids','entry_ids','exit_ids'))
        mode = payload['mode']
        if (mode == 'automatic_toggle' and (not toggle or entry or exit_ids)
                or mode == 'directional' and (toggle or not entry or not exit_ids)
                or mode == 'disabled' and (toggle or entry or exit_ids)
                or set(entry) & set(exit_ids)):
            raise LocalRefusal('Reader IDs do not match the selected mode')
        if mode != 'disabled' and not current['device_ids']:
            raise LocalRefusal('Select reader devices in Core before enabling scan processing')
        db.execute('''UPDATE local_reader_settings SET revision=revision+1,mode=?,effective_from=?,
            toggle_ids=?,entry_ids=?,exit_ids=? WHERE singleton=1''',
            (mode,self.service.now(),canonical(toggle),canonical(entry),canonical(exit_ids)))
        return {'status':'updated','revision':current['revision']+1}

    def list_reader_activity(self, db, payload, context):
        total = db.execute('SELECT COUNT(*) FROM local_reader_events').fetchone()[0]
        rows = db.execute('''SELECT e.event_id,e.device_id,e.reader_id,e.occurred_at,e.processed_at,
            e.outcome,e.visit_id,c.display_name child_name FROM local_reader_events e
            LEFT JOIN local_children c ON c.child_id=e.child_id
            ORDER BY e.sequence DESC LIMIT ? OFFSET ?''', (payload['limit'],payload['offset'])).fetchall()
        return {'total':total,'items':[dict(row) for row in rows]}

    def process(self, payload, context):
        # This is a Core event callback, never an operator/kiosk mutation. Core
        # rechecks the declared device/provider/grant before each signed dispatch.
        if (context.audience != 'internal' or context.user_id is not None
                or context.idempotency_key != payload.get('event_id')
                or context.correlation_id != payload.get('event_id')):
            raise LocalRefusal('Reader events require their original Core delivery identity')
        try:
            event = IdentifierScanEventV1.model_validate(payload)
        except ValueError:
            raise LocalRefusal('Invalid reader event') from None
        fingerprint = hashlib.sha256(canonical(payload).encode()).hexdigest()
        with self.service.application.storage.transaction() as db:
            old = db.execute('SELECT fingerprint,result_json FROM local_reader_events WHERE event_id=?', (event.event_id,)).fetchone()
            if old:
                if old['fingerprint'] != fingerprint:
                    raise LocalRefusal('Reader event identity conflict')
                return json.loads(old['result_json'])
            db.execute('SAVEPOINT reader_transition')
            try:
                status, visit_id, child_id = self.apply(db, event)
            except LocalRefusal as error:
                if str(error) not in ('commerce_legacy_bills','commerce_checkout_started','commerce_review_limit'):
                    raise
                db.execute('ROLLBACK TO reader_transition')
                status,visit_id,child_id='account_review',None,None
            finally:
                db.execute('RELEASE reader_transition')
            result = {'outcome':status,'visit_id':visit_id}
            # No opaque identifier, scan metadata, name/contact or raw error text
            # is stored in this technical journal. Current names are joined on read.
            db.execute('''INSERT INTO local_reader_events(event_id,fingerprint,device_id,reader_id,occurred_at,
                processed_at,outcome,visit_id,child_id,result_json) VALUES (?,?,?,?,?,?,?,?,?,?)''',
                (event.event_id,fingerprint,event.device_id,event.payload.reader_id,event.occurred_at.astimezone(timezone.utc).isoformat(),
                 self.service.now(),status,visit_id,child_id,canonical(result)))
            return result

    def apply(self, db, event):
        settings = self.get_reader_settings(db, {}, None)
        if event.device_id not in settings['device_ids']:
            return 'wrong_source', None, None
        if settings['mode'] == 'disabled':
            return 'disabled', None, None
        occurred = event.occurred_at.astimezone(timezone.utc)
        if occurred <= timestamp(settings['effective_from']):
            return 'old_configuration', None, None
        if occurred > timestamp(self.service.now()) + timedelta(seconds=30):
            return 'future_event', None, None
        if event.payload.device_health != 'ok':
            return 'degraded', None, None
        reader = event.payload.reader_id
        if settings['mode'] == 'automatic_toggle':
            if reader not in settings['toggle_ids']:
                return 'unmapped_reader', None, None
            purpose = 'toggle'
        else:
            purpose = 'entry' if reader in settings['entry_ids'] else 'exit' if reader in settings['exit_ids'] else None
            if purpose is None:
                return 'unmapped_reader', None, None
        assigned = db.execute('''SELECT b.*,r.status FROM local_bracelets b
            JOIN local_children c ON c.child_id=b.child_id JOIN local_registrations r ON r.registration_id=c.registration_id
            WHERE b.code=? AND b.retired_at IS NULL''', (event.payload.opaque_identifier,)).fetchone()
        if assigned is None or assigned['status'] != 'approved':
            return 'unknown_bracelet', None, None
        child_id = assigned['child_id']
        if occurred < timestamp(assigned['assigned_at']):
            return 'late_event', None, child_id
        latest = db.execute('SELECT * FROM local_visits WHERE child_id=? ORDER BY last_transition_at DESC LIMIT 1', (child_id,)).fetchone()
        if latest and occurred <= timestamp(latest['last_transition_at']):
            return 'late_event', latest['visit_id'], child_id
        visit = db.execute("SELECT * FROM local_visits WHERE child_id=? AND state='active'", (child_id,)).fetchone()
        inside = bool(visit and visit['inside_since'])
        if purpose == 'entry' and inside:
            return 'already_inside', visit['visit_id'], child_id
        if purpose == 'exit' and (not visit or not inside):
            return 'already_outside', visit['visit_id'] if visit else None, child_id
        action = 'pause' if inside else 'resume' if visit else 'start'
        result = self.service.scan_bracelet(db, {'code':event.payload.opaque_identifier,'action':action,
            'expected_visit_id':visit['visit_id'] if visit else None}, None, occurred_at=occurred.isoformat())
        return {'start':'started','pause':'paused','resume':'resumed'}[action], result['visit_id'], child_id
