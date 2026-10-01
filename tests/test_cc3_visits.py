from datetime import UTC, datetime
import importlib.util
import json
from pathlib import Path
import sqlite3

import pytest

from three_mm_application_sdk import ApplicationContext, ApplicationStorage, OperationContext


MODULE_ROOT = Path(__file__).parents[1]
DEVICE_ID = "dev_0123456789abcdef0123456789abcdef"


class MutableClock:
    def __init__(self, value: str):
        self.current = datetime.fromisoformat(value).astimezone(UTC)

    def now(self):
        return self.current


def _load(name: str, relative: str):
    spec = importlib.util.spec_from_file_location(name, MODULE_ROOT / relative)
    assert spec is not None and spec.loader is not None
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def _create_service(storage, clock):
    service_module = _load(
        f"child_center_cc3_service_{id(clock)}",
        "service/child_center_application/service.py",
    )
    return service_module.create_service(
        ApplicationContext(
            module_id="org.3mm.child-center",
            version="0.5.0",
            data_dir=storage.data_dir,
            configuration={
                "READER_DEVICE_ID": DEVICE_ID,
                "DISPLAY_TIMEZONE": "Europe/Sofia",
            },
            storage=storage,
            clock=clock,
        )
    )


def _context(audience: str, key: str | None = None):
    return OperationContext(
        audience=audience,
        correlation_id=f"synthetic-cc3-{audience}",
        user_id=73 if audience in {"operator", "administrator"} else None,
        idempotency_key=key,
    )


def _scan(event_id: str, occurred_at: str, opaque: str, reader_id: str = "reader-1"):
    return {
        "event_id": event_id,
        "device_id": DEVICE_ID,
        "event_type": "identifier.scan.v1",
        "occurred_at": occurred_at,
        "payload": {
            "schema_version": 1,
            "capability_id": "identifier.scan.v1",
            "opaque_identifier": opaque,
            "reader_id": reader_id,
            "adapter_kind": "mock",
            "sequence": 1,
            "device_health": "ok",
            "scan_metadata": {},
        },
    }


def _approved_child(service):
    submitted = service.handle(
        "submit_registration",
        {
            "guardian": {
                "display_name": "Synthetic CC3 Guardian",
                "phone": "",
                "email": "cc3@example.invalid",
                "consent_version": "synthetic-cc3-v1",
                "consented_at": "2026-08-30T08:00:00+00:00",
            },
            "children": [
                {
                    "display_name": "Synthetic CC3 Child",
                    "allowed_consumption_codes": [],
                }
            ],
        },
        _context("kiosk", "synthetic-cc3-registration"),
    )
    approved = service.handle(
        "approve_registration",
        {"registration_id": submitted["registration_id"]},
        _context("operator", "synthetic-cc3-approval"),
    )
    child_id = approved["child_ids"][0]
    service.handle(
        "assign_identifier",
        {"child_id": child_id, "opaque_identifier": "synthetic-cc3-opaque"},
        _context("operator", "synthetic-cc3-assignment"),
    )
    return child_id


def test_cc3_scan_transitions_duplicates_restart_and_late_events(tmp_path):
    migrations = _load(
        "child_center_cc3_migrations",
        "service/child_center_application/migrations.py",
    )
    storage = ApplicationStorage(tmp_path / "child-center-data")
    storage.migrate(migrations.get_migrations(), "0011")
    clock = MutableClock("2026-08-30T09:00:00+00:00")
    service = _create_service(storage, clock)
    assert service.handle(
        "get_reader_configuration",
        {},
        _context("administrator"),
    )["device_id"] == DEVICE_ID
    child_id = _approved_child(service)
    service.handle(
        "update_reader_configuration",
        {
            "mode": "operator_selected",
            "operator_selected_purpose": "entry",
            "entry_reader_ids": [],
            "exit_reader_ids": [],
        },
        _context("administrator", "synthetic-operator-selected-config"),
    )

    entry = _scan(
        "evt_00000000000000000000000000000001",
        "2026-08-30T09:00:00+00:00",
        "synthetic-cc3-opaque",
    )
    started = service.handle(
        "process_identifier_scan",
        entry,
        _context("internal", "synthetic-entry-command"),
    )
    assert started["status"] == "started"
    assert service.handle(
        "process_identifier_scan",
        entry,
        _context("internal", "synthetic-entry-command"),
    ) == started
    assert service.handle(
        "process_identifier_scan",
        entry,
        _context("internal", "synthetic-entry-redelivery"),
    ) == started

    already_active = service.handle(
        "process_identifier_scan",
        _scan(
            "evt_00000000000000000000000000000002",
            "2026-08-30T09:01:00+00:00",
            "synthetic-cc3-opaque",
        ),
        _context("internal", "synthetic-second-entry"),
    )
    assert already_active == {"status": "already_active", "visit_id": started["visit_id"]}

    clock.current = datetime.fromisoformat("2026-08-30T09:30:00+00:00")
    active = service.handle(
        "list_active_visits",
        {"cursor": None, "limit": 20},
        _context("operator"),
    )
    assert active["items"][0]["child_id"] == child_id
    assert active["items"][0]["elapsed_seconds"] == 1800
    assert active["items"][0]["child_display_name"] == "Synthetic CC3 Child"

    restarted_clock = MutableClock("2026-08-30T10:00:00+00:00")
    restarted = _create_service(storage, restarted_clock)
    after_restart = restarted.handle(
        "list_active_visits",
        {"cursor": None, "limit": 20},
        _context("operator"),
    )
    assert after_restart["items"][0]["visit_id"] == started["visit_id"]
    assert after_restart["items"][0]["elapsed_seconds"] == 3600

    restarted.handle(
        "update_reader_configuration",
        {
            "mode": "dedicated_readers",
            "operator_selected_purpose": "entry",
            "entry_reader_ids": ["entry-reader"],
            "exit_reader_ids": ["exit-reader"],
        },
        _context("administrator", "synthetic-dedicated-config"),
    )
    wrong_reader = restarted.handle(
        "process_identifier_scan",
        _scan(
            "evt_00000000000000000000000000000003",
            "2026-08-30T10:01:00+00:00",
            "synthetic-cc3-opaque",
            "other-reader",
        ),
        _context("internal", "synthetic-wrong-reader"),
    )
    assert wrong_reader == {"status": "wrong_reader_mode", "visit_id": None}

    exit_event = _scan(
        "evt_00000000000000000000000000000004",
        "2026-08-30T10:02:00+00:00",
        "synthetic-cc3-opaque",
        "exit-reader",
    )
    closed = restarted.handle(
        "process_identifier_scan",
        exit_event,
        _context("internal", "synthetic-exit-command"),
    )
    assert closed == {"status": "closed", "visit_id": started["visit_id"]}
    assert restarted.handle(
        "process_identifier_scan",
        exit_event,
        _context("internal", "synthetic-exit-redelivery"),
    ) == closed
    assert restarted.handle(
        "list_active_visits",
        {"cursor": None, "limit": 20},
        _context("operator"),
    )["items"] == []

    detail = restarted.handle(
        "get_visit",
        {"visit_id": started["visit_id"]},
        _context("operator"),
    )
    assert detail["state"] == "closed"
    assert detail["duration_seconds"] == 3720
    assert detail["exited_at"] == "2026-08-30T10:02:00+00:00"
    assert not ({"currency", "total_minor", "tariff_version_id", "checkout_state"} & detail.keys())

    late = restarted.handle(
        "process_identifier_scan",
        _scan(
            "evt_00000000000000000000000000000005",
            "2026-08-30T09:45:00+00:00",
            "synthetic-cc3-opaque",
            "entry-reader",
        ),
        _context("internal", "synthetic-late-event"),
    )
    assert late == {"status": "late_event", "visit_id": started["visit_id"]}

    unknown = restarted.handle(
        "process_identifier_scan",
        _scan(
            "evt_00000000000000000000000000000006",
            "2026-08-30T10:03:00+00:00",
            "synthetic-unknown-opaque",
            "entry-reader",
        ),
        _context("internal", "synthetic-unknown-event"),
    )
    assert unknown == {"status": "unknown_identifier", "visit_id": None}

    activity = restarted.handle(
        "list_identifier_scan_activity",
        {"limit": 50},
        _context("administrator"),
    )["items"]
    assert len(activity) == 6
    assert activity[0] == {
        "event_id": "evt_00000000000000000000000000000006",
        "reader_id": "entry-reader",
        "adapter_kind": "mock",
        "device_health": "ok",
        "status": "unknown_identifier",
        "child_id": None,
        "child_display_name": None,
        "visit_id": None,
        "occurred_at": "2026-08-30T10:03:00+00:00",
        "processed_at": "2026-08-30T10:00:00+00:00",
    }
    assert any(
        item["child_display_name"] == "Synthetic CC3 Child"
        and item["status"] == "closed"
        for item in activity
    )
    with pytest.raises(ValueError, match="audience"):
        restarted.handle(
            "list_identifier_scan_activity",
            {"limit": 50},
            _context("operator"),
        )

    with sqlite3.connect(storage.database_path) as connection:
        assert connection.execute("SELECT COUNT(*) FROM visits").fetchone()[0] == 1
        assert connection.execute("SELECT COUNT(*) FROM visit_events").fetchone()[0] == 2
        assert connection.execute(
            "SELECT COUNT(*) FROM identifier_event_results"
        ).fetchone()[0] == 6
        assert connection.execute(
            "SELECT COUNT(*) FROM identifier_scan_activity"
        ).fetchone()[0] == 6
        private_results = " ".join(
            row[0] for row in connection.execute(
                "SELECT payload_hash || result_json FROM identifier_event_results"
            )
        )
        audit_metadata = " ".join(
            row[0] for row in connection.execute("SELECT metadata_json FROM domain_audit_events")
        )
        visit_details = " ".join(
            row[0] for row in connection.execute("SELECT details_json FROM visit_events")
        )
        scan_diagnostics = " ".join(
            str(value)
            for row in connection.execute("SELECT * FROM identifier_scan_activity")
            for value in row
            if value is not None
        )
        assert "synthetic-cc3-opaque" not in private_results
        assert "synthetic-cc3-opaque" not in audit_metadata
        assert "synthetic-cc3-opaque" not in visit_details
        assert "synthetic-cc3-opaque" not in scan_diagnostics


def test_cc3_operator_purpose_manual_close_and_audience_isolation(tmp_path):
    migrations = _load(
        "child_center_cc3_migrations_second",
        "service/child_center_application/migrations.py",
    )
    storage = ApplicationStorage(tmp_path / "child-center-data")
    storage.migrate(migrations.get_migrations(), "0011")
    clock = MutableClock("2026-08-30T11:00:00+00:00")
    service = _create_service(storage, clock)
    child_id = _approved_child(service)

    service.handle(
        "update_reader_configuration",
        {
            "mode": "operator_selected",
            "operator_selected_purpose": "entry",
            "entry_reader_ids": [],
            "exit_reader_ids": [],
        },
        _context("administrator", "synthetic-manual-mode-config"),
    )

    assert service.handle("get_operator_reader_state", {}, _context("operator"))["operator_selected_purpose"] == "entry"
    assert service.handle(
        "set_operator_reader_purpose",
        {"purpose": "exit"},
        _context("operator", "synthetic-purpose-exit"),
    ) == {"status": "updated", "purpose": "exit"}

    started = service.handle(
        "start_visit",
        {
            "child_id": child_id,
            "assignment_id": None,
            "occurred_at": "2026-08-30T11:00:00+00:00",
        },
        _context("operator", "synthetic-manual-start"),
    )
    closed = service.handle(
        "close_visit",
        {
            "visit_id": started["visit_id"],
            "occurred_at": "2026-08-30T11:05:00+00:00",
        },
        _context("operator", "synthetic-manual-close"),
    )
    assert closed["duration_seconds"] == 300
    assert service.handle(
        "close_visit",
        {
            "visit_id": started["visit_id"],
            "occurred_at": "2026-08-30T11:05:00+00:00",
        },
        _context("operator", "synthetic-manual-close"),
    ) == closed

    with pytest.raises(ValueError, match="audience"):
        service.handle(
            "list_active_visits",
            {"cursor": None, "limit": 20},
            _context("kiosk"),
        )
    with pytest.raises(ValueError, match="audience"):
        service.handle(
            "process_identifier_scan",
            _scan(
                "evt_00000000000000000000000000000007",
                "2026-08-30T11:06:00+00:00",
                "synthetic-cc3-opaque",
            ),
            _context("operator", "synthetic-wrong-audience"),
        )


def test_default_reader_mode_automatically_toggles_entry_and_exit(tmp_path):
    migrations = _load(
        "child_center_cc3_migrations_automatic",
        "service/child_center_application/migrations.py",
    )
    storage = ApplicationStorage(tmp_path / "child-center-data")
    storage.migrate(migrations.get_migrations(), "0011")
    clock = MutableClock("2026-08-30T12:00:00+00:00")
    service = _create_service(storage, clock)
    _approved_child(service)

    reader = service.handle("get_operator_reader_state", {}, _context("operator"))
    assert reader["mode"] == "automatic_toggle"

    entry = _scan(
        "evt_00000000000000000000000000000008",
        "2026-08-30T12:00:00+00:00",
        "synthetic-cc3-opaque",
    )
    started = service.handle(
        "process_identifier_scan",
        entry,
        _context("internal", "synthetic-automatic-entry"),
    )
    assert started["status"] == "started"
    assert service.handle(
        "process_identifier_scan",
        entry,
        _context("internal", "synthetic-automatic-entry-redelivery"),
    ) == started

    closed = service.handle(
        "process_identifier_scan",
        _scan(
            "evt_00000000000000000000000000000009",
            "2026-08-30T12:10:00+00:00",
            "synthetic-cc3-opaque",
        ),
        _context("internal", "synthetic-automatic-exit"),
    )
    assert closed == {"status": "closed", "visit_id": started["visit_id"]}
    detail = service.handle(
        "get_visit",
        {"visit_id": started["visit_id"]},
        _context("operator"),
    )
    assert detail["duration_seconds"] == 600


def test_visit_history_filters_paginates_and_excludes_pricing(tmp_path):
    migrations = _load(
        "child_center_history_migrations",
        "service/child_center_application/migrations.py",
    )
    storage = ApplicationStorage(tmp_path / "child-center-data")
    storage.migrate(migrations.get_migrations(), "0011")
    clock = MutableClock("2026-08-30T08:00:00+00:00")
    service = _create_service(storage, clock)
    child_id = _approved_child(service)

    first = service.handle(
        "start_visit",
        {
            "child_id": child_id,
            "assignment_id": None,
            "occurred_at": "2026-08-30T08:00:00+00:00",
        },
        _context("operator", "synthetic-history-first-start"),
    )
    service.handle(
        "close_visit",
        {
            "visit_id": first["visit_id"],
            "occurred_at": "2026-08-30T08:10:00+00:00",
        },
        _context("operator", "synthetic-history-first-close"),
    )
    second = service.handle(
        "start_visit",
        {
            "child_id": child_id,
            "assignment_id": None,
            "occurred_at": "2026-08-30T09:00:00+00:00",
        },
        _context("operator", "synthetic-history-second-start"),
    )
    service.handle(
        "close_visit",
        {
            "visit_id": second["visit_id"],
            "occurred_at": "2026-08-30T09:05:00+00:00",
        },
        _context("operator", "synthetic-history-second-close"),
    )

    first_page = service.handle(
        "list_visit_history",
        {
            "query": "CC3 Child",
            "date_from": "2026-08-30T07:00:00+00:00",
            "date_to": "2026-08-30T10:00:00+00:00",
            "cursor": None,
            "limit": 1,
        },
        _context("operator"),
    )
    assert [item["visit_id"] for item in first_page["items"]] == [second["visit_id"]]
    assert first_page["next_cursor"] is not None
    assert first_page["items"][0]["duration_seconds"] == 300
    assert first_page["items"][0]["entry_source"] == "operator"
    assert first_page["items"][0]["exit_source"] == "operator"

    second_page = service.handle(
        "list_visit_history",
        {
            "query": "CC3 Child",
            "date_from": "2026-08-30T07:00:00+00:00",
            "date_to": "2026-08-30T10:00:00+00:00",
            "cursor": first_page["next_cursor"],
            "limit": 1,
        },
        _context("administrator"),
    )
    assert [item["visit_id"] for item in second_page["items"]] == [first["visit_id"]]
    assert second_page["items"][0]["guardian_display_name"] == "Synthetic CC3 Guardian"
    assert second_page["items"][0]["duration_seconds"] == 600
    assert second_page["next_cursor"] is None

    earlier = service.handle(
        "list_visit_history",
        {
            "query": "Synthetic CC3 Guardian",
            "date_from": None,
            "date_to": "2026-08-30T08:30:00+00:00",
            "cursor": None,
            "limit": 20,
        },
        _context("operator"),
    )
    assert [item["visit_id"] for item in earlier["items"]] == [first["visit_id"]]
    serialized = json.dumps(first_page["items"] + second_page["items"]).lower()
    for forbidden in ("price", "tariff", "currency", "payment", "receipt", "fiscal"):
        assert forbidden not in serialized

    with pytest.raises(ValueError, match="date range"):
        service.handle(
            "list_visit_history",
            {
                "query": "",
                "date_from": "2026-08-30T10:00:00+00:00",
                "date_to": "2026-08-30T09:00:00+00:00",
                "cursor": None,
                "limit": 20,
            },
            _context("operator"),
        )
    with pytest.raises(ValueError, match="audience"):
        service.handle(
            "list_visit_history",
            {
                "query": "",
                "date_from": None,
                "date_to": None,
                "cursor": None,
                "limit": 20,
            },
            _context("kiosk"),
        )
