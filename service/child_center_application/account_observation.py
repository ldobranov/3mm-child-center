"""Cached, read-only observation; closure is not proof of delivery or payment."""
from datetime import timedelta

from three_mm_application_sdk import ApplicationPlatformError


def migrate(connection):
    connection.execute('''CREATE TABLE account_observations (
        visit_id TEXT PRIMARY KEY REFERENCES stay_accounts(visit_id) ON DELETE CASCADE,
        status TEXT NOT NULL CHECK(status IN ('unknown','open','closed')),
        checked_at TEXT NOT NULL,
        error_code TEXT CHECK(error_code IN ('closed_external_review','barsy_unavailable'))
    )''')


class AccountObservation:
    INTERVAL_SECONDS = 15

    def __init__(self, service):
        self.s = service

    def candidate(self, c):
        cutoff = (self.s.application.clock.now() - timedelta(seconds=self.INTERVAL_SECONDS)).isoformat()
        return c.execute('''SELECT a.visit_id FROM stay_accounts a
            JOIN visit_barsy_bindings b ON b.visit_id=a.visit_id
            JOIN barsy_timing_commands cmd ON cmd.command_id=b.start_command_id
            LEFT JOIN account_observations o ON o.visit_id=a.visit_id
            WHERE a.live=1 AND b.state='allocated' AND cmd.state='confirmed'
                AND cmd.remote_account_id IS NOT NULL
                AND (o.checked_at IS NULL OR o.checked_at<=?)
            ORDER BY COALESCE(o.checked_at,''),a.rowid LIMIT 1''', (cutoff,)).fetchone()

    def ready(self, c):
        return self.candidate(c) is not None

    @staticmethod
    def cached(c, visit_id):
        row = c.execute('SELECT status,checked_at,error_code FROM account_observations WHERE visit_id=?', (visit_id,)).fetchone()
        return dict(row) if row else {'status': 'unknown', 'checked_at': None, 'error_code': None}

    def observe(self):
        with self.s.application.storage.transaction() as c:
            candidate = self.candidate(c)
            if candidate is None:
                return 0
            row = self.s._commerce.row(c, candidate['visit_id'])
        status, error = 'unknown', 'barsy_unavailable'
        try:
            # Identity is checked, but current timer settings cannot prevent us
            # observing closure. Commercial preflight still uses strict remote().
            account = self.s._commerce.read_account(row)
            remote_status = self.s._barsy_integer(account.get('status'))
            if remote_status in (0, 1):
                status = 'closed' if remote_status == 1 else 'open'
                error = 'closed_external_review' if remote_status == 1 else None
        except (ApplicationPlatformError, ValueError, ArithmeticError, KeyError, TypeError):
            # Unknown/malformed identity and read failures clear stale evidence.
            # Never store connector messages or advance financial state.
            pass
        with self.s.application.storage.transaction() as c:
            current = self.s._commerce.row(c, row['visit_id'])
            if (current['binding_state'] != 'allocated' or not current['live']
                    or current['start_state'] != 'confirmed'
                    or current['remote_account_id'] != row['remote_account_id']
                    or current['start_id'] != row['start_id']
                    or current['barsy_place_id'] != row['barsy_place_id']):
                return 1
            c.execute('''INSERT INTO account_observations(visit_id,status,checked_at,error_code)
                VALUES (?,?,?,?) ON CONFLICT(visit_id) DO UPDATE SET
                status=excluded.status,checked_at=excluded.checked_at,error_code=excluded.error_code''',
                (row['visit_id'], status, self.s._now(), error))
        return 1
