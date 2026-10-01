"""Draft administrator review/read boundary; not a physical-action override.

Only demonstrably unsubmitted requests may be cleared. Unknown driver/submission
outcomes remain blocked. Export covers this journal, NOT the complete customer
record. Full privacy handlers and public contracts are still required for release.
"""
import json
from typing import Literal

from pydantic import BaseModel, ConfigDict, Field


class Page(BaseModel):
    model_config = ConfigDict(extra='forbid', strict=True)
    offset: int = Field(default=0, ge=0, le=1000000)
    limit: int = Field(default=50, ge=1, le=100)


class ExportPage(Page):
    registration_id: str = Field(min_length=1, max_length=96)


class ResolveUnsent(BaseModel):
    model_config = ConfigDict(extra='forbid', strict=True)
    request_id: str = Field(pattern=r'^access_[0-9a-f]{32}$')
    expected_error_code: Literal['expired_before_submit', 'visit_changed_before_submit']
    confirmed: Literal[True]


class AccessReview:
    def __init__(self, service, journal):
        self.s, self.journal = service, journal

    def _administrator(self, context):
        self.s._require_audience(context, 'administrator')
        if type(context.user_id) is not int or context.user_id < 1:
            raise ValueError('An authenticated administrator is required')

    def list_pending(self, payload, context):
        self._administrator(context)
        page = Page.model_validate(payload)
        with self.journal.transaction() as c:
            rows = c.execute("""SELECT request_id, visit_id, point_id, state, error_code,
                created_at, expires_at, command_id FROM access_intents
                WHERE state IN ('review','invalidated') ORDER BY created_at, request_id
                LIMIT ? OFFSET ?""", (page.limit + 1, page.offset)).fetchall()
        return {'items': [dict(row) for row in rows[:page.limit]], 'has_more': len(rows) > page.limit}

    def resolve_unsent(self, payload, context):
        self._administrator(context)
        if not isinstance(payload, dict) or payload.get('confirmed') is not True:
            raise ValueError('Explicit confirmation is required')
        request = ResolveUnsent.model_validate(payload)

        def mutation(c):
            row = self.journal._row(c, request.request_id)
            if (row['state'] != 'review' or row['error_code'] != request.expected_error_code
                    or row['command_id'] is not None or row['generation'] is not None
                    or row['passage_event_id'] is not None):
                raise ValueError('Only a definitely unsubmitted request can be resolved')
            # A restored 'prepared' snapshot is NOT proof of non-submission after
            # the backup was taken. startup_unsubmitted_review is never eligible.
            # Retain the request tombstone. Never re-arm its idempotency identity,
            # change measured time, close an account or free a Barsy table here.
            c.execute("UPDATE access_intents SET state='resolved' WHERE request_id=?", (request.request_id,))
            self.s._audit(c, event_type='access.unsent_resolved', entity_type='visit',
                entity_id=row['visit_id'], context=context,
                metadata={'request_id': request.request_id, 'reason': request.expected_error_code})
            return {'request_id': request.request_id, 'state': 'resolved'}

        return self.s._idempotent('resolve_unsent_access', request.model_dump(), context, mutation)

    def export_registration(self, payload, context):
        self._administrator(context)
        page = ExportPage.model_validate(payload)
        with self.journal.transaction() as c:
            if not c.execute('SELECT 1 FROM registrations WHERE registration_id=?', (page.registration_id,)).fetchone():
                raise ValueError('Registration was not found')
            rows = c.execute("""SELECT i.request_id,i.visit_id,i.state,i.created_at,i.expires_at,
                i.payload_json,p.payload_json passage_json
                FROM access_intents i JOIN visits v ON v.visit_id=i.visit_id
                JOIN children ch ON ch.child_id=v.child_id
                LEFT JOIN access_passages p ON p.request_id=i.request_id
                WHERE ch.registration_id=? ORDER BY i.created_at,i.request_id
                LIMIT ? OFFSET ?""", (page.registration_id, page.limit + 1, page.offset)).fetchall()
            items = []
            for row in rows[:page.limit]:
                # Exclude device topology, command generation and opaque bracelet.
                passage = json.loads(row['passage_json']) if row['passage_json'] else None
                items.append({'request_id': row['request_id'], 'visit_id': row['visit_id'],
                    'state': row['state'], 'requested_at': row['created_at'],
                    'expires_at': row['expires_at'], 'direction': json.loads(row['payload_json'])['direction'],
                    'passed_at': passage['occurred_at'] if passage else None})
            return {'items': items, 'has_more': len(rows) > page.limit}
