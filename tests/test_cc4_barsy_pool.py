from datetime import UTC, datetime
import base64
import importlib.util
import json
from pathlib import Path
import sqlite3

import pytest

from three_mm_application_sdk import ApplicationContext, ApplicationStorage, OperationContext


MODULE_ROOT = Path(__file__).parents[1]


class MutableClock:
    def __init__(self, value: str):
        self.current = datetime.fromisoformat(value).astimezone(UTC)

    def now(self):
        return self.current


class FakePlatform:
    def __init__(self, result):
        self.result = result
        self.calls = []

    def connector_request(self, connector_id, **request):
        self.calls.append((connector_id, request))
        return self.result


def _load(name: str, relative: str):
    spec = importlib.util.spec_from_file_location(name, MODULE_ROOT / relative)
    assert spec is not None and spec.loader is not None
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def _context(audience: str, key: str | None = None):
    return OperationContext(
        audience=audience,
        correlation_id=f"synthetic-cc4a-{audience}",
        user_id=91 if audience in {"operator", "administrator"} else None,
        idempotency_key=key,
    )


def _service(tmp_path, platform=None, schema_revision="0011"):
    migrations = _load(
        "child_center_cc4a_migrations",
        "service/child_center_application/migrations.py",
    )
    service_module = _load(
        "child_center_cc4a_service",
        "service/child_center_application/service.py",
    )
    storage = ApplicationStorage(tmp_path / "child-center-data")
    storage.migrate(migrations.get_migrations(), schema_revision)
    clock = MutableClock("2026-08-30T20:50:00+00:00")
    service = service_module.create_service(
        ApplicationContext(
            module_id="org.3mm.child-center",
            version="0.5.0",
            data_dir=storage.data_dir,
            configuration={"DISPLAY_TIMEZONE": "Europe/Sofia"},
            storage=storage,
            platform=platform,
            clock=clock,
        )
    )
    return storage, service, clock


def _approved_children(service, count: int = 3):
    submitted = service.handle(
        "submit_registration",
        {
            "guardian": {
                "display_name": "Synthetic Pool Guardian",
                "phone": "+359000000009",
                "email": "",
                "consent_version": "synthetic-cc4a-v1",
                "consented_at": "2026-08-30T20:45:00+00:00",
            },
            "children": [
                {
                    "display_name": f"Synthetic Pool Child {index}",
                    "allowed_consumption_codes": [],
                }
                for index in range(1, count + 1)
            ],
        },
        _context("kiosk", "synthetic-cc4a-registration"),
    )
    approved = service.handle(
        "approve_registration",
        {"registration_id": submitted["registration_id"]},
        _context("operator", "synthetic-cc4a-approval"),
    )
    return approved["child_ids"]


def _save_table(service, place_id: int, priority: int, key: str):
    payload = {
        "table_slot_id": None,
        "barsy_place_id": place_id,
        "display_name": f"Synthetic table {place_id}",
        "priority": priority,
        "enabled": True,
    }
    result = service.handle(
        "save_barsy_table_mapping",
        payload,
        _context("administrator", key),
    )
    assert service.handle(
        "save_barsy_table_mapping",
        payload,
        _context("administrator", key),
    ) == result
    return result["table_slot_id"]


def test_cc4a_pool_claims_once_releases_same_table_and_never_sends_network(tmp_path):
    storage, service, _clock = _service(tmp_path)
    child_ids = _approved_children(service)
    first_slot = _save_table(service, 101, 10, "synthetic-table-101")
    _save_table(service, 102, 20, "synthetic-table-102")

    first_payload = {
        "child_id": child_ids[0],
        "assignment_id": None,
        "occurred_at": "2026-08-30T20:50:00+00:00",
    }
    first = service.handle(
        "start_visit",
        first_payload,
        _context("operator", "synthetic-first-start"),
    )
    assert service.handle(
        "start_visit",
        first_payload,
        _context("operator", "synthetic-first-start"),
    ) == first
    assert first["barsy_table"]["barsy_place_id"] == 101
    assert first["barsy_table"]["timing_state"] == "mock_confirmed"

    second = service.handle(
        "start_visit",
        {
            "child_id": child_ids[1],
            "assignment_id": None,
            "occurred_at": "2026-08-30T20:51:00+00:00",
        },
        _context("operator", "synthetic-second-start"),
    )
    assert second["barsy_table"]["barsy_place_id"] == 102

    with pytest.raises(ValueError, match="No Barsy table"):
        service.handle(
            "start_visit",
            {
                "child_id": child_ids[2],
                "assignment_id": None,
                "occurred_at": "2026-08-30T20:52:00+00:00",
            },
            _context("operator", "synthetic-third-start-blocked"),
        )

    with pytest.raises(ValueError, match="cannot be disabled"):
        service.handle(
            "set_barsy_table_mapping_enabled",
            {"table_slot_id": first_slot, "enabled": False},
            _context("administrator", "synthetic-disable-allocated"),
        )

    close_payload = {
        "visit_id": first["visit_id"],
        "occurred_at": "2026-08-30T21:20:00+00:00",
    }
    closed = service.handle(
        "close_visit",
        close_payload,
        _context("operator", "synthetic-first-stop"),
    )
    assert closed["duration_seconds"] == 1800
    assert closed["barsy_table"]["barsy_place_id"] == 101
    assert service.handle(
        "close_visit",
        close_payload,
        _context("operator", "synthetic-first-stop"),
    ) == closed

    third = service.handle(
        "start_visit",
        {
            "child_id": child_ids[2],
            "assignment_id": None,
            "occurred_at": "2026-08-30T21:21:00+00:00",
        },
        _context("operator", "synthetic-third-start"),
    )
    assert third["barsy_table"]["barsy_place_id"] == 101

    pool = service.handle("list_barsy_table_pool", {}, _context("administrator"))
    assert pool["delivery_mode"] == "mock"
    assert (pool["configured"], pool["enabled"], pool["free"], pool["allocated"]) == (
        2,
        2,
        0,
        2,
    )
    with pytest.raises(ValueError, match="audience"):
        service.handle("list_barsy_table_pool", {}, _context("operator"))

    integration = service.handle(
        "get_barsy_integration_status", {}, _context("administrator")
    )
    assert integration == {
        "commands": [],
        "delivery_mode": "mock",
        "production_mutations_enabled": False,
        "stop_contract_status": "unverified",
        "start_commands": 3,
        "stop_commands": 1,
        "mock_confirmed": 4,
        "retryable": 0,
        "ambiguous": 0,
        "manual_review": 0,
    }

    with sqlite3.connect(storage.database_path) as connection:
        assert connection.execute("SELECT COUNT(*) FROM visits").fetchone()[0] == 3
        assert connection.execute(
            "SELECT COUNT(*) FROM visit_barsy_bindings"
        ).fetchone()[0] == 3
        assert connection.execute(
            "SELECT COUNT(*) FROM barsy_timing_commands WHERE command_kind = 'start'"
        ).fetchone()[0] == 3
        assert connection.execute(
            "SELECT COUNT(*) FROM barsy_timing_commands WHERE command_kind = 'stop'"
        ).fetchone()[0] == 1
        assert connection.execute(
            "SELECT COUNT(*) FROM barsy_timing_commands WHERE state <> 'mock_confirmed'"
        ).fetchone()[0] == 0


def test_cc4a_empty_or_disabled_pool_preserves_local_visit_workflow(tmp_path):
    _storage, service, _clock = _service(tmp_path)
    child_id = _approved_children(service, 1)[0]
    started = service.handle(
        "start_visit",
        {
            "child_id": child_id,
            "assignment_id": None,
            "occurred_at": "2026-08-30T20:50:00+00:00",
        },
        _context("operator", "synthetic-local-only-start"),
    )
    assert started["barsy_table"] is None
    closed = service.handle(
        "close_visit",
        {
            "visit_id": started["visit_id"],
            "occurred_at": "2026-08-30T21:20:00+00:00",
        },
        _context("operator", "synthetic-local-only-stop"),
    )
    assert closed["barsy_table"] is None
    assert closed["duration_seconds"] == 1800


def test_cc4b_discovers_bounded_read_only_places_and_marks_existing_mapping(tmp_path):
    response = [
        {
            "place_id": "102",
            "name": "Synthetic place B",
            "salon_name": "Synthetic salon",
            "type_name": "Play table",
            "accounts_count": "0",
            "ignored_remote_field": "not exposed",
        },
        {
            "place_id": 101,
            "name": "Synthetic place A",
            "salon_name": "Synthetic salon",
            "type_name": "Play table",
            "accounts_count": 1,
        },
    ]
    platform = FakePlatform(
        {
            "outcome": "succeeded",
            "http_status": 200,
            "error_category": None,
            "body_base64": base64.b64encode(json.dumps(response).encode()).decode(),
        }
    )
    _storage, service, _clock = _service(tmp_path, platform)
    mapped_slot = _save_table(service, 101, 10, "synthetic-discovery-mapping")

    discovered = service.handle(
        "discover_barsy_places", {"limit": 256}, _context("administrator")
    )
    assert discovered == {
        "status": "available",
        "items": [
            {
                "barsy_place_id": 101,
                "display_name": "Synthetic place A",
                "salon_name": "Synthetic salon",
                "type_name": "Play table",
                "accounts_count": 1,
                "mapped_table_slot_id": mapped_slot,
            },
            {
                "barsy_place_id": 102,
                "display_name": "Synthetic place B",
                "salon_name": "Synthetic salon",
                "type_name": "Play table",
                "accounts_count": 0,
                "mapped_table_slot_id": None,
            },
        ],
        "truncated": False,
        "http_status": 200,
        "error_category": None,
    }
    assert platform.calls == [
        (
            "barsy_api",
            {"method": "GET", "path": "/endpoints/json/Places_getlist"},
        )
    ]
    assert "ignored_remote_field" not in json.dumps(discovered)


def test_cc4b_discovery_failures_are_bounded_and_do_not_change_pool(tmp_path):
    platform = FakePlatform(
        {
            "outcome": "retryable",
            "http_status": 503,
            "error_category": "remote_unavailable",
            "body_base64": "",
        }
    )
    _storage, service, _clock = _service(tmp_path, platform)
    retryable = service.handle(
        "discover_barsy_places", {"limit": 10}, _context("administrator")
    )
    assert retryable == {
        "status": "retryable",
        "items": [],
        "truncated": False,
        "http_status": 503,
        "error_category": "remote_unavailable",
    }

    platform.result = {
        "outcome": "succeeded",
        "http_status": 200,
        "error_category": None,
        "body_base64": base64.b64encode(b'{"unexpected":true}').decode(),
    }
    invalid = service.handle(
        "discover_barsy_places", {"limit": 10}, _context("administrator")
    )
    assert invalid["status"] == "invalid_response"
    assert invalid["items"] == []
    assert service.handle(
        "list_barsy_table_pool", {}, _context("administrator")
    )["configured"] == 0

    _storage, unavailable_service, _clock = _service(tmp_path / "other")
    unavailable = unavailable_service.handle(
        "discover_barsy_places", {"limit": 10}, _context("administrator")
    )
    assert unavailable["status"] == "unavailable"
    assert unavailable["error_category"] == "platform_unavailable"


def test_discovery_excludes_service_places_and_uses_table_numbers(tmp_path):
    response = [
        {"place_id": 901, "place_type": 1, "place_num": "0", "is_public": 0},
        {"place_id": 902, "place_type": "1", "place_num": "0", "is_public": 1},
        {"place_id": 903, "place_type": 101, "place_num": "1",
         "type_name": "Synthetic play area", "is_public": 1},
        {"place_id": 904, "place_type": 2, "place_num": 0,
         "type_name": "Synthetic table", "is_public": 0},
    ]
    platform = FakePlatform({
        "outcome": "succeeded", "http_status": 200, "error_category": None,
        "body_base64": base64.b64encode(json.dumps(response).encode()).decode(),
    })
    storage, service, _clock = _service(tmp_path, platform)
    result = service.handle(
        "discover_barsy_places", {"limit": 2}, _context("administrator")
    )
    assert result["status"] == "available"
    assert result["truncated"] is False
    assert [(p["barsy_place_id"], p["display_name"]) for p in result["items"]] == [
        (903, "Synthetic play area 1"), (904, "Synthetic table 0"),
    ]
    with storage.transaction() as connection:
        assert connection.execute("SELECT COUNT(*) FROM barsy_table_slots").fetchone()[0] == 0
        assert connection.execute("SELECT COUNT(*) FROM barsy_timing_commands").fetchone()[0] == 0
