"""Internal commercial/passage adapter, pending runtime contract activation.

Only authenticated internal callers may use this adapter. It does not expose
HTTP operations or turn an untrusted scan into an authenticated identity.
The service entrypoint does not yet instantiate it: lifecycle, privacy and
configured driver contracts must be completed before enabling hardware.
"""
import json

from pydantic import BaseModel, ConfigDict, Field
from child_center_application.access_points import AdmissionRequest, SensorPoint


class Reservation(BaseModel):
    model_config = ConfigDict(extra="forbid", strict=True)
    child_id: str = Field(pattern=r"^child_[0-9a-f]{32}$")
    assignment_id: str = Field(pattern=r"^assign_[0-9a-f]{32}$")
    point_id: str = Field(pattern=r"^[a-z][a-z0-9_]{0,95}$")
    reader_device: str = Field(pattern=r"^dev_[0-9a-f]{32}$")
    reader_id: str = Field(pattern=r"^[A-Za-z0-9][A-Za-z0-9_.:-]{0,95}$")


class SensorAdmission:
    def __init__(self, service, journal):
        self.s, self.journal = service, journal
        if service.application.storage.database_path != journal.storage.database_path:
            raise ValueError("Admission and journal must share extension storage")

    def reserve(self, payload, context):
        self.s._require_audience(context, "internal")
        request = Reservation.model_validate(payload)

        def mutation(c):
            raw = c.execute("SELECT configuration_json FROM access_points WHERE point_id=?", (request.point_id,)).fetchone()
            if raw is None:
                raise ValueError("Unknown point")
            point = SensorPoint.model_validate_json(raw[0])
            if (request.reader_device, request.reader_id) != (point.reader_device, point.reader_id):
                raise ValueError("Wrong reader")
            # First admission only. Re-entry must use the existing sensor stay,
            # never the legacy start operation which resumes on scan alone.
            if c.execute("SELECT 1 FROM visits WHERE child_id=? AND state='active'", (request.child_id,)).fetchone():
                raise ValueError("Use the existing sensor stay")
            if not self.s._live_start(c):
                raise ValueError("Sensor admission requires confirmed commercial capacity")
            result = self.s._start_visit_mutation(c, child_id=request.child_id,
                assignment_id=request.assignment_id, occurred_at=self.s._now(),
                context=context, source_event_id=None, details={"source": "sensor_reservation"})
            c.execute("INSERT INTO access_sensor_stays VALUES (?,?)", (result["visit_id"], request.point_id))
            self.s._audit(c, event_type="access.admission_reserved", entity_type="visit",
                entity_id=result["visit_id"], context=context, metadata={"point_id": request.point_id})
            return result

        return self.s._idempotent("reserve_sensor_admission", request.model_dump(), context, mutation)

    def _local(self, c, request):
        owner = c.execute("SELECT point_id FROM access_sensor_stays WHERE visit_id=?", (request["visit_id"],)).fetchone()
        if owner is None or owner[0] != request["point_id"]:
            raise ValueError("Visit does not belong to this sensor point")
        row = self.s._commerce.row(c, request["visit_id"])
        assignment = c.execute("""SELECT 1 FROM visits v JOIN identifier_assignments a
            ON a.assignment_id=v.assignment_id AND a.child_id=v.child_id
            WHERE v.visit_id=? AND a.retired_at IS NULL""", (request["visit_id"],)).fetchone()
        child = c.execute("SELECT status FROM children WHERE child_id=?", (row["child_id"],)).fetchone()
        if row["visit_state"] != "active":
            raise ValueError("Visit has ended")
        # No commercial block on exit. Emergency egress remains hardware-owned.
        if request["direction"] == "entry" and (not assignment or child[0] != "active"
                or not row["live"] or not row["admitted"] or row["start_state"] != "confirmed"
                or row["binding_state"] != "allocated" or row["remote_account_id"] is None):
            raise ValueError("Admission is not ready")
        return row

    def _preflight(self, request):
        with self.journal.transaction() as c:
            row = self._local(c, request)
        if request["direction"] == "entry":
            remote = self.s._commerce.remote(row)
            if self.s._barsy_integer(remote.get("status")) != 0:
                raise ValueError("Barsy account is no longer open")

    def prepare(self, payload, context):
        self.s._require_audience(context, "internal")
        request = AdmissionRequest.model_validate(payload).model_dump()
        self._preflight(request)
        return self.journal.prepare(request, admission_ready=True)

    def dispatch(self, request_id, context):
        self.s._require_audience(context, "internal")
        row = self.journal.get(request_id)
        if row["state"] != "prepared":
            return row
        request = json.loads(row["payload_json"])
        # Remote read before the FULL-synchronous pre-submit transaction.
        self._preflight(request)
        return self.journal.dispatch(request_id, guard=lambda c, _: self._local(c, request))

    def confirm(self, payload, context):
        self.s._require_audience(context, "internal")

        def transition(c, visit_id, direction, occurred_at, event_id):
            # No remote request in this transaction. Receipt, intervals and audit
            # either all commit, or all roll back for safe event redelivery.
            row = self.s._commerce.row(c, visit_id)
            if direction == "entry" and (not row["admitted"] or row["binding_state"] != "allocated"):
                raise ValueError("Admission was withdrawn")
            self.s._transition_stay(c, visit_id, occurred_at.isoformat(), direction == "entry",
                context, event_id, {"source": "confirmed_passage"})

        return self.journal.confirm(payload, transition)
