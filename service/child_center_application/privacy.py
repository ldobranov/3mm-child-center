"""Extension-local privacy workflows. No remote erasure or financial mutation.

Retain technical identities and measured/financial history; redact selected
personal fields. This is not a claim of irreversible database anonymization.
Export artifacts are short-lived and revoked on erasure; command tombstones stay.
"""
from datetime import timedelta
import hashlib
import json
import uuid
from typing import Literal

from pydantic import BaseModel, ConfigDict, Field


class Subject(BaseModel):
    model_config = ConfigDict(extra='forbid', strict=True)
    subject_kind: Literal['guardian', 'child']
    subject_id: str = Field(min_length=1, max_length=64)


class Erasure(Subject):
    scope: Literal['anonymize', 'erase_where_permitted']
    reason: str = Field(min_length=1, max_length=240)


class Empty(BaseModel):
    model_config = ConfigDict(extra='forbid', strict=True)


class DeleteClient(BaseModel):
    model_config = ConfigDict(extra='forbid', strict=True)
    registration_id: str = Field(pattern=r'^reg_[0-9a-f]{32}$')
    reason: Literal['administrator_request']


class PrivacyBlocked(ValueError):
    pass


def contains_reference(value, identifiers):
    if isinstance(value, str):
        return value in identifiers
    if isinstance(value, list):
        return any(contains_reference(item, identifiers) for item in value)
    if isinstance(value, dict):
        return any(contains_reference(item, identifiers) for item in value.values())
    return False


class PrivacyWorkflow:
    # Provisional CC-0 defaults. Export lifetime is a new conservative test default.
    CONTACT_DAYS = 30
    IDENTIFIER_DAYS = 7
    EXPORT_MINUTES = 15
    BATCH = 50

    def __init__(self, service):
        self.s = service

    def admin(self, context):
        self.s._require_audience(context, 'administrator')
        if type(context.user_id) is not int or context.user_id < 1:
            raise ValueError('An authenticated administrator is required')

    @staticmethod
    def subject(c, request):
        table, key = ('guardians', 'guardian_id') if request.subject_kind == 'guardian' else ('children', 'child_id')
        row = c.execute(f'SELECT * FROM {table} WHERE {key}=?', (request.subject_id,)).fetchone()
        if row is None:
            raise ValueError('Privacy subject was not found')
        return row

    @staticmethod
    def rows(c, sql, parameters):
        rows = c.execute(sql, parameters).fetchmany(5001)
        if len(rows) > 5000:
            raise ValueError('Export exceeds the inline limit; a separate export workflow is required')
        return [dict(row) for row in rows]

    def export(self, payload, context):
        self.admin(context)
        request = Subject.model_validate(payload)

        def mutation(c):
            row = dict(self.subject(c, request))
            # Only the selected person, not other family members' profiles.
            row.pop('registration_id', None)
            document = {'subject_kind': request.subject_kind, 'subject': row,
                'scope': 'extension_local_only', 'retained_history': True}
            if request.subject_kind == 'guardian':
                document['relationships'] = self.rows(c, 'SELECT child_id,authority_type,consent_version,active_from,active_until FROM guardian_children WHERE guardian_id=?', (request.subject_id,))
                document['external_client_link'] = self.rows(c, 'SELECT state,remote_client_id,updated_at FROM barsy_parent_links WHERE guardian_id=?', (request.subject_id,))
            else:
                document['relationships'] = self.rows(c, 'SELECT guardian_id,authority_type,consent_version,active_from,active_until FROM guardian_children WHERE child_id=?', (request.subject_id,))
                document['identifiers'] = self.rows(c, 'SELECT assignment_id,opaque_identifier,assigned_at,retired_at,retire_reason FROM identifier_assignments WHERE child_id=?', (request.subject_id,))
                document['visits'] = self.rows(c, 'SELECT visit_id,state,entered_at,exited_at,duration_seconds,display_timezone FROM visits WHERE child_id=?', (request.subject_id,))
                document['intervals'] = self.rows(c, 'SELECT i.visit_id,i.entered_at,i.exited_at FROM stay_intervals i JOIN visits v ON v.visit_id=i.visit_id WHERE v.child_id=?', (request.subject_id,))
                document['events'] = self.rows(c, 'SELECT e.visit_id,e.event_type,e.occurred_at FROM visit_events e JOIN visits v ON v.visit_id=e.visit_id WHERE v.child_id=?', (request.subject_id,))
                document['billing'] = self.rows(c, 'SELECT b.visit_id,b.rounded_minutes,b.quantity,b.article_id,b.state,b.remote_account_id FROM stay_bills b JOIN visits v ON v.visit_id=b.visit_id WHERE v.child_id=?', (request.subject_id,))
                document['consumption'] = self.rows(c, "SELECT a.visit_id,a.article_id,a.quantity,a.consumer,a.state,a.created_at FROM account_commands a JOIN visits v ON v.visit_id=a.visit_id WHERE v.child_id=? AND a.kind='consumption'", (request.subject_id,))
                document['access'] = self.rows(c, 'SELECT i.request_id,i.visit_id,i.state,i.created_at,i.expires_at,i.payload_json FROM access_intents i JOIN visits v ON v.visit_id=i.visit_id WHERE v.child_id=?', (request.subject_id,))
                for item in document['access']:
                    item['direction'] = json.loads(item.pop('payload_json'))['direction']
                document['passages'] = self.rows(c, 'SELECT p.event_id,p.payload_json FROM access_passages p JOIN access_intents i ON i.request_id=p.request_id JOIN visits v ON v.visit_id=i.visit_id WHERE v.child_id=?', (request.subject_id,))
                for item in document['passages']:
                    item['occurred_at'] = json.loads(item.pop('payload_json'))['occurred_at']
            encoded = json.dumps(document, ensure_ascii=False, sort_keys=True)
            export_id = 'export_' + uuid.uuid4().hex
            result = {'export_id': export_id, 'status': 'ready', 'document_json': encoded}
            if len(json.dumps(result).encode()) > 1040000:
                raise ValueError('Export exceeds the inline limit; no partial document was created')
            expires = (self.s.application.clock.now() + timedelta(minutes=self.EXPORT_MINUTES)).isoformat()
            c.execute('INSERT INTO privacy_exports VALUES (?,?,?,?,?)', (export_id, request.subject_kind, request.subject_id, encoded, expires))
            self.s._audit(c, event_type='privacy.export_created', entity_type=request.subject_kind,
                entity_id=request.subject_id, context=context, metadata={})
            # Do not copy the personal document into the permanent command cache.
            return {'export_id': export_id, 'status': 'ready'}

        result = self.s._idempotent('export_personal_data', request.model_dump(), context, mutation)
        with self.s.application.storage.transaction() as c:
            artifact = c.execute('SELECT document_json,expires_at FROM privacy_exports WHERE export_id=?', (result['export_id'],)).fetchone()
            if artifact is None or self.s._parse_time(artifact['expires_at']) <= self.s.application.clock.now():
                raise ValueError('Export expired or was revoked; use a new request')
            return {**result, 'document_json': artifact['document_json']}

    def safe(self, c, request):
        row = self.subject(c, request)
        if request.subject_kind == 'child':
            children = [request.subject_id]
        else:
            children = [r[0] for r in c.execute('SELECT child_id FROM guardian_children WHERE guardian_id=?', (request.subject_id,))]
            link = c.execute('SELECT state FROM barsy_parent_links WHERE guardian_id=?', (request.subject_id,)).fetchone()
            if link and link[0] in {'ambiguous', 'manual_review'}:
                raise PrivacyBlocked('Resolve the external client synchronization first')
        for child in children:
            if c.execute("SELECT 1 FROM visits v LEFT JOIN visit_barsy_bindings b ON b.visit_id=v.visit_id WHERE v.child_id=? AND (v.state='active' OR b.state='allocated') LIMIT 1", (child,)).fetchone():
                raise PrivacyBlocked('Resolve active visits and allocated accounts first')
            for table, allowed in [('stay_bills', "'confirmed','mock_confirmed'"), ('account_commands', "'confirmed','mock_confirmed'"), ('barsy_timing_commands', "'confirmed','mock_confirmed'"), ('access_intents', "'confirmed','resolved'")]:
                if c.execute(f'SELECT 1 FROM {table} x JOIN visits v ON v.visit_id=x.visit_id WHERE v.child_id=? AND x.state NOT IN ({allowed}) LIMIT 1', (child,)).fetchone():
                    raise PrivacyBlocked('Resolve pending financial or physical commands first')
        return row

    def redact(self, c, request, context):
        row = self.safe(c, request)
        status = 'anonymized' if request.scope == 'anonymize' else 'erased'
        now = self.s._now()
        if row['status'] == 'erased' or row['status'] == status:
            return 0
        before = c.total_changes
        if request.subject_kind == 'guardian':
            c.execute("UPDATE guardians SET display_name='Removed guardian',contact_kind='phone',contact_value='',phone='',email='',status=?,updated_at=? WHERE guardian_id=?", (status, now, request.subject_id))
        else:
            c.execute("UPDATE children SET display_name='Removed child',notes=NULL,allowed_consumption_codes_json='[]',status=?,updated_at=? WHERE child_id=?", (status, now, request.subject_id))
            for assignment in c.execute('SELECT assignment_id FROM identifier_assignments WHERE child_id=?', (request.subject_id,)).fetchall():
                marker = 'erased_' + hashlib.sha256(assignment[0].encode()).hexdigest()
                c.execute("UPDATE identifier_assignments SET opaque_identifier=?,identifier_erased=1,retired_at=COALESCE(retired_at,?),retire_reason='privacy' WHERE assignment_id=?", (marker, now, assignment[0]))
        key = 'guardian_id' if request.subject_kind == 'guardian' else 'child_id'
        c.execute(f'UPDATE guardian_children SET active_until=COALESCE(active_until,?) WHERE {key}=?', (now, request.subject_id))
        c.execute('UPDATE registrations SET kiosk_receipt_hash=NULL WHERE registration_id=?', (row['registration_id'],))
        c.execute('DELETE FROM privacy_exports WHERE subject_kind=? AND subject_id=?', (request.subject_kind, request.subject_id))
        # Preserve idempotency identities; invalidate cached results referencing
        # the subject/family instead of deleting keys and enabling re-execution.
        identifiers = {request.subject_id, row['registration_id']}
        for command in c.execute('SELECT idempotency_key,result_json FROM command_results WHERE instr(result_json,?)>0 OR instr(result_json,?)>0', (request.subject_id, row['registration_id'])).fetchall():
            if contains_reference(json.loads(command['result_json']), identifiers):
                c.execute("UPDATE command_results SET result_json='{}' WHERE idempotency_key=?", (command['idempotency_key'],))
                c.execute('INSERT OR IGNORE INTO privacy_redacted_commands VALUES (?)', (command['idempotency_key'],))
        affected = c.total_changes - before
        self.s._audit(c, event_type='privacy.fields_redacted', entity_type=request.subject_kind,
            entity_id=request.subject_id, context=context, metadata={'scope': request.scope})
        return affected

    def erase(self, payload, context):
        self.admin(context)
        request = Erasure.model_validate(payload)
        def mutation(c):
            count = self.redact(c, request, context)
            return {'status': 'anonymized' if request.scope == 'anonymize' else 'erased', 'affected_records': count}
        return self.s._idempotent('erase_personal_data', request.model_dump(), context, mutation)

    def delete_client(self, payload, context):
        self.admin(context)
        request = DeleteClient.model_validate(payload)
        def mutation(c):
            self.s._registration(c, request.registration_id)
            subjects = [('child', r[0]) for r in c.execute('SELECT child_id FROM children WHERE registration_id=?', (request.registration_id,))]
            subjects += [('guardian', r[0]) for r in c.execute('SELECT guardian_id FROM guardians WHERE registration_id=?', (request.registration_id,))]
            for kind, identity in subjects:
                self.redact(c, Erasure(subject_kind=kind, subject_id=identity,
                    scope='erase_where_permitted', reason=request.reason), context)
                c.execute('DELETE FROM privacy_exports WHERE subject_kind=? AND subject_id=?', (kind, identity))
            count = c.execute('SELECT COUNT(*) FROM visits v JOIN children ch ON ch.child_id=v.child_id WHERE ch.registration_id=?', (request.registration_id,)).fetchone()[0]
            c.execute('UPDATE registrations SET deleted_at=?,deleted_by=?,updated_at=?,kiosk_receipt_hash=NULL WHERE registration_id=?',
                (self.s._now(), str(context.user_id), self.s._now(), request.registration_id))
            self.s._audit(c, event_type='client.deleted', entity_type='registration',
                entity_id=request.registration_id, context=context, metadata={'retained_visit_count': count})
            return {'status': 'deleted', 'retained_visit_count': count}
        return self.s._idempotent('delete_client', request.model_dump(), context, mutation)

    def retention(self, payload, context):
        self.s._require_audience(context, 'internal')
        Empty.model_validate(payload)
        def mutation(c):
            now = self.s.application.clock.now()
            result = {'anonymized': 0, 'identifiers_erased': 0, 'deleted': 0}
            cursor = c.execute('SELECT guardian_id FROM privacy_retention_cursor WHERE singleton=1').fetchone()[0]
            rows = c.execute("""SELECT g.guardian_id,MAX(v.exited_at) last_closed
                FROM guardians g JOIN guardian_children gc ON gc.guardian_id=g.guardian_id
                JOIN visits v ON v.child_id=gc.child_id WHERE g.status='active' AND g.guardian_id>?
                GROUP BY g.guardian_id HAVING MAX(v.exited_at) IS NOT NULL
                ORDER BY g.guardian_id LIMIT ?""", (cursor, self.BATCH)).fetchall()
            c.execute('UPDATE privacy_retention_cursor SET guardian_id=? WHERE singleton=1', (rows[-1]['guardian_id'] if rows else '',))
            for row in rows:
                if self.s._parse_time(row['last_closed']) > now - timedelta(days=self.CONTACT_DAYS):
                    continue
                request = Erasure(subject_kind='guardian', subject_id=row['guardian_id'], scope='anonymize', reason='retention')
                try:
                    if self.redact(c, request, context):
                        result['anonymized'] += 1
                except PrivacyBlocked:
                    continue
            assignments = c.execute("SELECT assignment_id,child_id,retired_at FROM identifier_assignments WHERE retired_at IS NOT NULL AND identifier_erased=0 ORDER BY retired_at,assignment_id LIMIT ?", (self.BATCH,)).fetchall()
            for row in assignments:
                if self.s._parse_time(row['retired_at']) <= now - timedelta(days=self.IDENTIFIER_DAYS):
                    marker = 'erased_' + hashlib.sha256(row['assignment_id'].encode()).hexdigest()
                    c.execute('UPDATE identifier_assignments SET opaque_identifier=?,identifier_erased=1 WHERE assignment_id=?', (marker, row['assignment_id']))
                    c.execute("DELETE FROM privacy_exports WHERE subject_kind='child' AND subject_id=?", (row['child_id'],))
                    result['identifiers_erased'] += 1
            # Bounded artifact expiry. Technical and financial history is retained;
            # the 24-month archive/purge policy is NOT implemented here.
            artifacts = c.execute('SELECT export_id,expires_at FROM privacy_exports ORDER BY expires_at,export_id LIMIT ?', (self.BATCH,)).fetchall()
            for artifact in artifacts:
                if self.s._parse_time(artifact['expires_at']) <= now:
                    c.execute('DELETE FROM privacy_exports WHERE export_id=?', (artifact['export_id'],))
                    result['deleted'] += 1
            self.s._audit(c, event_type='privacy.retention_applied', entity_type='retention',
                entity_id='local', context=context, metadata=result)
            return result
        return self.s._idempotent('apply_retention', {}, context, mutation)
