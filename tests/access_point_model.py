"""Offline design model ONLY; not a driver, service or production protocol.

No network, GPIO, database or Barsy access. Snapshot models a durable journal
boundary but does not prove real atomic persistence or crash-safe hardware.
Integer seconds and opaque synthetic subject handles keep scenarios deterministic.
"""
from copy import deepcopy
from dataclasses import dataclass


@dataclass(frozen=True)
class Point:
    point_id: str
    reader_device: str
    actuator_device: str | None
    sensor_device: str | None
    mode: str = "sensor"

    def __post_init__(self):
        if self.mode not in {"scan", "sensor"}:
            raise ValueError("Blind actuator policy is not accepted")
        if self.mode == "sensor" and not (self.actuator_device and self.sensor_device):
            raise ValueError("Sensor mode needs both actuator and sensor")
        if self.mode == "scan" and (self.actuator_device or self.sensor_device):
            raise ValueError("Scan mode cannot operate hardware")


class Model:
    def __init__(self, point, snapshot=None):
        self.point = point
        self.data = deepcopy(snapshot) if snapshot is not None else {
            "epoch": 1, "enabled": True, "requests": {}, "events": {},
            "inside": {}, "elapsed": {}, "actuations": 0,
        }

    def snapshot(self):
        return deepcopy(self.data)

    def scan(self, request_id, subject, direction, device, now, *, known=True, ready=True):
        if direction not in {"entry", "exit"} or type(now) is not int or now < 0:
            raise ValueError("Invalid scan")
        signature = (subject, direction, device, now)
        previous = self.data["requests"].get(request_id)
        if previous:
            if previous["signature"] != signature:
                raise ValueError("Request identity conflict")
            return previous["state"]  # replay is never a new authorization
        allowed = self.data["enabled"] and known and device == self.point.reader_device
        allowed &= ready if direction == "entry" else True
        allowed &= (subject in self.data["inside"]) == (direction == "exit")
        allowed &= not any(r["subject"] == subject
                           and (r["state"] in {"attempted", "executed"}
                                or (r["state"] == "authorized" and now < r["expires"]))
                           and r["epoch"] == self.data["epoch"]
                           for r in self.data["requests"].values())
        row = {"signature": signature, "subject": subject, "direction": direction,
               "point": self.point.point_id, "epoch": self.data["epoch"],
               "issued": now, "expires": now + 10, "state": "authorized" if allowed else "denied"}
        self.data["requests"][request_id] = row
        if allowed and self.point.mode == "scan":
            self._cross(row, now)
        return row["state"]

    def _valid(self, row, now):
        return (self.data["enabled"] and row["epoch"] == self.data["epoch"]
                and row["point"] == self.point.point_id and row["issued"] <= now < row["expires"])

    def execute(self, request_id, device, now, *, lose_reply=False):
        row = self.data["requests"][request_id]
        if self.point.mode != "sensor" or device != self.point.actuator_device or not self._valid(row, now):
            return False
        if row["state"] != "authorized":
            return False
        row["state"] = "attempted"  # must be durable BEFORE hardware in real implementation
        self.data["actuations"] += 1
        if not lose_reply:
            row["state"] = "executed"
        return True

    def passage(self, event_id, request_id, point_id, direction, device, occurred, received):
        signature = (request_id, point_id, direction, device, occurred)
        prior = self.data["events"].get(event_id)
        if prior:
            if prior["signature"] != signature:
                raise ValueError("Event identity conflict")
            return prior["accepted"]
        row = self.data["requests"][request_id]
        accepted = (self.point.mode == "sensor" and device == self.point.sensor_device
                    and point_id == row["point"] and direction == row["direction"]
                    and occurred <= received and self._valid(row, occurred) and self._valid(row, received)
                    and row["state"] in {"attempted", "executed"})
        if accepted:
            self._cross(row, occurred)
        self.data["events"][event_id] = {"signature": signature, "accepted": accepted}
        return accepted

    def _cross(self, row, now):
        subject = row["subject"]
        if row["direction"] == "entry":
            self.data["inside"][subject] = now
        else:
            entered = self.data["inside"].pop(subject)
            self.data["elapsed"][subject] = self.data["elapsed"].get(subject, 0) + now - entered
        row["state"] = "crossed"

    def disable(self):
        self.data["enabled"] = False
        self.data["epoch"] += 1

    def enable(self):
        self.data["enabled"] = True

    def recover_snapshot(self):
        # Restore is not normal process restart: old physical grants are invalid.
        self.data["epoch"] += 1
