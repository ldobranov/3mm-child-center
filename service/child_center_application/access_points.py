"""Internal durable sensor-admission journal; not enabled by the 0.6.7 contract.

No driver, HTTP endpoint or automatic work queue. The future service adapter must
authorize scans, confirm commercial admission, validate installed bindings, and
invalidate restored intents BEFORE enabling dispatch. No personal fields belong
in command arguments. Unresolved intents deliberately require manual review.
"""
from contextlib import contextmanager
from datetime import UTC, datetime, timedelta
import json
import sqlite3
from threading import Lock
from re import fullmatch
from typing import Literal

from pydantic import BaseModel, ConfigDict, Field
from three_mm_protocol.passage import PassageEventV1


def canonical(value):
    return json.dumps(value, sort_keys=True, separators=(",", ":"), allow_nan=False)


def timestamp(value):
    if not isinstance(value, datetime) or value.tzinfo is None:
        raise ValueError("An aware timestamp is required")
    return value.astimezone(UTC)


class PulseArguments(BaseModel):
    model_config = ConfigDict(extra='forbid', frozen=True, strict=True)
    channel: str = Field(pattern=r'^[A-Za-z0-9][A-Za-z0-9_.:-]{0,31}$')
    duration_ms: int = Field(ge=50, le=500)


class SensorPoint(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True, strict=True)
    point_id: str = Field(pattern=r"^[a-z][a-z0-9_]{0,95}$")
    reader_device: str = Field(pattern=r"^dev_[0-9a-f]{32}$")
    reader_id: str = Field(pattern=r"^[A-Za-z0-9][A-Za-z0-9_.:-]{0,95}$")
    binding_id: str = Field(pattern=r"^[a-z][a-z0-9_]{0,95}$")
    sensor_device: str = Field(pattern=r"^dev_[0-9a-f]{32}$")
    sensor_id: str = Field(pattern=r"^[A-Za-z0-9][A-Za-z0-9_.:-]{0,95}$")
    entry_direction: Literal["forward", "reverse"]
    ttl_seconds: int = Field(ge=1, le=10, default=10)
    arguments: PulseArguments | None = None


class AdmissionRequest(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True, strict=True)
    request_id: str = Field(pattern=r"^access_[0-9a-f]{32}$")
    point_id: str = Field(pattern=r"^[a-z][a-z0-9_]{0,95}$")
    visit_id: str = Field(pattern=r"^visit_[0-9a-f]{32}$")
    direction: Literal["entry", "exit"]
    reader_device: str = Field(pattern=r"^dev_[0-9a-f]{32}$")
    reader_id: str = Field(pattern=r"^[A-Za-z0-9][A-Za-z0-9_.:-]{0,95}$")


class AccessJournal:
    def __init__(self, storage, platform, clock):
        self.storage, self.platform, self.clock = storage, platform, clock
        self.submission_lock = Lock()
        # Construct once at service startup, after migration and before accepting
        # events. ApplicationContext cannot distinguish restore from restart.
        # Therefore neither may revive an old, not-yet-submitted authorization.
        # A failure here prevents creation of a usable journal (fail closed).
        with self.transaction() as c:
            c.execute("""UPDATE access_intents SET state='review',
                error_code='startup_unsubmitted_review' WHERE state='prepared'""")
            c.execute("""UPDATE access_intents SET state='review',
                error_code='startup_submit_unknown' WHERE state='submitting'""")

    @contextmanager
    def transaction(self):
        # Explicit FULL durability for the pre-submit record; no network inside.
        c = sqlite3.connect(self.storage.database_path, timeout=30)
        c.row_factory = sqlite3.Row
        try:
            c.execute("PRAGMA foreign_keys=ON")
            c.execute("PRAGMA synchronous=FULL")
            c.execute("BEGIN IMMEDIATE")
            yield c
            c.commit()
        except BaseException:
            c.rollback()
            raise
        finally:
            c.close()

    @staticmethod
    def _row(c, request_id):
        row = c.execute("SELECT * FROM access_intents WHERE request_id=?", (request_id,)).fetchone()
        if row is None:
            raise ValueError("Unknown admission request")
        return row

    def get(self, request_id):
        with self.transaction() as c:
            return dict(self._row(c, request_id))

    def register_point(self, payload):
        """Immutable configuration. Exact replay only; no hidden reconfiguration."""
        point = SensorPoint.model_validate(payload)
        encoded = canonical(point.model_dump())
        with self.transaction() as c:
            previous = c.execute("SELECT configuration_json FROM access_points WHERE point_id=?", (point.point_id,)).fetchone()
            if previous and previous[0] != encoded:
                raise ValueError("Point configuration conflict")
            c.execute("INSERT OR IGNORE INTO access_points VALUES (?, ?)", (point.point_id, encoded))

    def prepare(self, payload, *, admission_ready):
        """Readiness is supplied by the trusted commercial adapter, never a UI flag."""
        request = AdmissionRequest.model_validate(payload)
        encoded = canonical(request.model_dump())
        now = timestamp(self.clock.now())
        with self.transaction() as c:
            previous = c.execute("SELECT * FROM access_intents WHERE request_id=?", (request.request_id,)).fetchone()
            if previous:
                if previous["payload_json"] != encoded:
                    raise ValueError("Admission identity conflict")
                return dict(previous)
            row = c.execute("SELECT configuration_json FROM access_points WHERE point_id=?", (request.point_id,)).fetchone()
            if row is None:
                raise ValueError("Unknown point")
            point = SensorPoint.model_validate_json(row[0])
            if (request.reader_device, request.reader_id) != (point.reader_device, point.reader_id):
                raise ValueError("Wrong reader")
            if request.direction == "entry" and admission_ready is not True:
                raise ValueError("Admission is not ready")
            visit = c.execute("SELECT v.state, s.inside_since FROM visits v JOIN stay_sessions s ON s.visit_id=v.visit_id WHERE v.visit_id=?", (request.visit_id,)).fetchone()
            if visit is None or visit["state"] != "active" or (visit["inside_since"] is not None) != (request.direction == "exit"):
                raise ValueError("Visit direction is inconsistent")
            c.execute("""INSERT INTO access_intents(request_id,point_id,visit_id,payload_json,state,created_at,expires_at)
                VALUES (?,?,?,?,'prepared',?,?)""", (request.request_id, request.point_id, request.visit_id,
                encoded, now.isoformat(), (now + timedelta(seconds=point.ttl_seconds)).isoformat()))
            return dict(self._row(c, request.request_id))

    def dispatch(self, request_id, *, guard=None):
        with self.submission_lock:
            return self._dispatch(request_id, guard=guard)

    @staticmethod
    def _command(reply, row):
        if (not isinstance(reply, dict)
                or not fullmatch(r'cmd_[0-9a-f]{32}', str(reply.get('command_id')))
                or not fullmatch(r'[0-9a-f]{32}', str(reply.get('generation')))
                or type(reply.get('claimed')) is not bool
                or not isinstance(reply.get('expires_at'), str)
                or reply.get('status') not in {'queued','delivered','succeeded','failed','expired','unknown','invalidated'}):
            raise ValueError('Invalid command correlation')
        expiry = timestamp(datetime.fromisoformat(reply['expires_at']))
        if not timestamp(datetime.fromisoformat(row['created_at'])) < expiry <= timestamp(datetime.fromisoformat(row['expires_at'])):
            raise ValueError('Command deadline does not match admission')
        if row['command_id'] is not None and (row['command_id'] != reply['command_id'] or row['generation'] != reply['generation']):
            raise ValueError('Command identity changed')
        return expiry.isoformat()

    def _dispatch(self, request_id, *, guard=None):
        # Arguments come only from the immutable point, never from a scan.
        # The platform independently enforces the installed binding schema.
        with self.transaction() as c:
            row = self._row(c, request_id)
            if row["state"] != "prepared":
                return dict(row)
            if guard is not None:
                guard(c, row)
            request = json.loads(row["payload_json"])
            visit = c.execute("SELECT v.state, s.inside_since FROM visits v JOIN stay_sessions s ON s.visit_id=v.visit_id WHERE v.visit_id=?", (row["visit_id"],)).fetchone()
            if visit is None or visit["state"] != "active" or (visit["inside_since"] is not None) != (request["direction"] == "exit"):
                c.execute("UPDATE access_intents SET state='review', error_code='visit_changed_before_submit' WHERE request_id=?", (request_id,))
                return dict(self._row(c, request_id))
            now = timestamp(self.clock.now())
            remaining = int((datetime.fromisoformat(row["expires_at"]) - now).total_seconds())
            if now < datetime.fromisoformat(row["created_at"]) or remaining < 1:
                c.execute("UPDATE access_intents SET state='review', error_code='expired_before_submit' WHERE request_id=?", (request_id,))
                return dict(self._row(c, request_id))
            point = SensorPoint.model_validate_json(c.execute("SELECT configuration_json FROM access_points WHERE point_id=?", (row["point_id"],)).fetchone()[0])
            direction = request["direction"]
            wire_direction = point.entry_direction if direction == "entry" else ("reverse" if point.entry_direction == "forward" else "forward")
            c.execute("UPDATE access_intents SET state='submitting' WHERE request_id=?", (request_id,))
        try:
            reply = self.platform.submit_command(point.binding_id, request_id=request_id,
                arguments=point.arguments.model_dump() if point.arguments else {},
                ttl_seconds=min(remaining, point.ttl_seconds), direction=wire_direction,
                not_after=timestamp(datetime.fromisoformat(row['expires_at'])))
            # Validate correlation before storing anything returned by transport.
            expiry = self._command(reply, row)
        except Exception:
            with self.transaction() as c:
                c.execute("UPDATE access_intents SET state='review', error_code='submit_outcome_unknown' WHERE request_id=? AND state='submitting'", (request_id,))
        else:
            with self.transaction() as c:
                # Preserve correlation even if maintenance has classified a slow
                # submit as review while the external request was in flight.
                c.execute("""UPDATE access_intents SET
                    state=CASE WHEN state='submitting' AND ? THEN 'submitted' ELSE 'review' END,
                    command_id=?, generation=?, expires_at=?
                    WHERE request_id=? AND state IN ('submitting','review')""",
                    (reply['status'] != 'invalidated' and timestamp(self.clock.now()) < datetime.fromisoformat(expiry),
                     reply['command_id'], reply['generation'], expiry, request_id))
        return self.get(request_id)

    def recover(self, request_id):
        """Read-only remote lookup. Never submit, free capacity or infer passage.

        One journal owns each service instance. Refuse recovery during its live
        submitting worker, even when maintenance has changed its durable state.
        Not-found and invalidated/expired evidence remain explicitly reviewable.
        """
        if not self.submission_lock.acquire(blocking=False):
            raise ValueError('Submission is still in progress')
        try:
            row = self.get(request_id)
            if row['state'] in {'confirmed', 'resolved', 'prepared'}:
                return row
            if row['state'] == 'submitting':
                raise ValueError('Submission is still in progress')
            with self.transaction() as c:
                point = SensorPoint.model_validate_json(c.execute(
                    'SELECT configuration_json FROM access_points WHERE point_id=?', (row['point_id'],)).fetchone()[0])
            result = self.platform.command_lookup(request_id=request_id, binding_id=point.binding_id)
            if result == {'status': 'not_found'}:
                # Even after expiry, absence is not sufficient proof for a
                # restored snapshot or deleted platform history. Keep blocked.
                return row
            if not isinstance(result, dict) or result.get('status') != 'found':
                raise ValueError('Invalid command lookup response')
            reply = result['command']
            expiry = self._command(reply, row)
            with self.transaction() as c:
                current = self._row(c, request_id)
                if dict(current) != row:
                    raise ValueError('Admission changed during recovery')
                resumable = (row['state'] == 'submitted' or
                    (row['state'] == 'review' and row['error_code'] in
                     {'submit_outcome_unknown', 'startup_submit_unknown'}))
                state = 'submitted' if (resumable and reply['status'] != 'invalidated'
                    and timestamp(self.clock.now()) < datetime.fromisoformat(expiry)) else 'review'
                if row['state'] == 'invalidated' or reply['status'] == 'invalidated':
                    state = 'invalidated'
                c.execute('''UPDATE access_intents SET state=?,command_id=?,generation=?,expires_at=?
                    WHERE request_id=?''', (state, reply['command_id'], reply['generation'], expiry, request_id))
            return self.get(request_id)
        finally:
            self.submission_lock.release()

    def invalidate(self):
        """Lifecycle hook, including restored UNSUBMITTED intents. No auto release."""
        with self.transaction() as c:
            c.execute("UPDATE access_intents SET state='invalidated', error_code='lifecycle_review' WHERE state NOT IN ('confirmed','resolved')")

    def review_pending(self):
        """Internal maintenance only: classify expired work without sending it.

        A timeout is not evidence of non-execution. Keep both identities and
        capacity blocked for manual review. Do not automatically release a stay.
        """
        now = timestamp(self.clock.now())
        with self.transaction() as c:
            rows = c.execute("SELECT request_id,expires_at FROM access_intents WHERE state IN ('prepared','submitting','submitted')").fetchall()
            expired = [row["request_id"] for row in rows if datetime.fromisoformat(row["expires_at"]) <= now]
            c.executemany("""UPDATE access_intents SET
                error_code=CASE WHEN state='prepared' THEN 'expired_before_submit'
                    ELSE 'passage_timeout_review' END, state='review'
                WHERE request_id=?""", ((identity,) for identity in expired))
            return len(expired)

    def confirm(self, payload, transition):
        """Trusted broker delivery only. Transition must be SQL-only in this transaction.

        Fresh broker status proves ownership/current generation and accepted event;
        a successful pulse alone can never call the business transition.
        """
        event = PassageEventV1.model_validate(payload)
        encoded = canonical(event.model_dump(mode="json"))
        with self.transaction() as c:
            prior = c.execute("SELECT payload_json FROM access_passages WHERE event_id=?", (event.event_id,)).fetchone()
            if prior:
                if prior[0] != encoded:
                    raise ValueError("Passage identity conflict")
                return False
            row = c.execute("SELECT * FROM access_intents WHERE command_id=?", (event.payload.command_id,)).fetchone()
            if row is None or row["state"] != "submitted":
                raise ValueError("Passage requires a submitted intent")
            request_id = row["request_id"]
        status = self.platform.command_status(event.payload.command_id)
        if (status.get("command_id") != event.payload.command_id or status.get("generation") != event.payload.generation
                or status.get("claimed") is not True or status.get("status") == "invalidated"
                or status.get("passage_event_id") != event.event_id):
            raise ValueError("Passage is not confirmed by current platform authority")
        with self.transaction() as c:
            row = self._row(c, request_id)
            prior = c.execute("SELECT payload_json FROM access_passages WHERE event_id=?", (event.event_id,)).fetchone()
            if prior:
                if prior[0] != encoded:
                    raise ValueError("Passage identity conflict")
                return False
            point = SensorPoint.model_validate_json(c.execute("SELECT configuration_json FROM access_points WHERE point_id=?", (row["point_id"],)).fetchone()[0])
            request = json.loads(row["payload_json"])
            direction = point.entry_direction if request["direction"] == "entry" else ("reverse" if point.entry_direction == "forward" else "forward")
            now = timestamp(self.clock.now())
            visit = c.execute("SELECT v.state, s.inside_since FROM visits v JOIN stay_sessions s ON s.visit_id=v.visit_id WHERE v.visit_id=?", (row["visit_id"],)).fetchone()
            if visit is None or visit["state"] != "active" or (visit["inside_since"] is not None) != (request["direction"] == "exit"):
                raise ValueError("Visit changed before passage confirmation")
            if (row["state"] != "submitted" or event.payload.generation != row["generation"]
                    or event.device_id != point.sensor_device or event.payload.sensor_id != point.sensor_id
                    or event.payload.binding_id != point.binding_id or event.payload.direction != direction
                    or event.payload.device_health != "ok"
                    or not datetime.fromisoformat(row["created_at"]) <= event.occurred_at <= now
                    or now >= datetime.fromisoformat(row["expires_at"])):
                raise ValueError("Passage does not match a current admission")
            transition(c, row["visit_id"], request["direction"], event.occurred_at, event.event_id)
            c.execute("INSERT INTO access_passages VALUES (?,?,?)", (event.event_id, request_id, encoded))
            c.execute("UPDATE access_intents SET state='confirmed', passage_event_id=? WHERE request_id=?", (event.event_id, request_id))
        return True
