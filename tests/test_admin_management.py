from datetime import UTC, datetime
import importlib.util
from pathlib import Path
import sqlite3

import pytest

from three_mm_application_sdk import ApplicationContext, ApplicationStorage, OperationContext


MODULE_ROOT = Path(__file__).parents[1]


class FixedClock:
    def now(self):
        return datetime(2026, 1, 15, 10, 30, tzinfo=UTC)


def _load(name: str, relative: str):
    spec = importlib.util.spec_from_file_location(name, MODULE_ROOT / relative)
    assert spec is not None and spec.loader is not None
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def _service(tmp_path):
    migrations = _load(
        "child_center_admin_migrations",
        "service/child_center_application/migrations.py",
    )
    service_module = _load(
        "child_center_admin_service",
        "service/child_center_application/service.py",
    )
    storage = ApplicationStorage(tmp_path / "child-center-data")
    storage.migrate(migrations.get_migrations(), "0011")
    service = service_module.create_service(
        ApplicationContext(
            module_id="org.3mm.child-center",
            version="0.5.0",
            data_dir=tmp_path / "child-center-data",
            configuration={},
            storage=storage,
            clock=FixedClock(),
        )
    )
    return service, storage


def _context(audience: str, key: str | None = None):
    return OperationContext(
        audience=audience,
        correlation_id=f"synthetic-admin-{audience}",
        user_id=42 if audience in {"operator", "administrator"} else None,
        idempotency_key=key,
    )


def _register(service):
    return service.handle(
        "register_client",
        {
            "guardian": {
                "display_name": "Synthetic Admin Guardian",
                "phone": "+359000000099",
                "email": "admin-guardian@example.invalid",
                "consent_version": "operator-registration-v1",
                "consented_at": "2026-01-15T10:30:00+00:00",
            },
            "child": {
                "display_name": "Synthetic Admin Child",
                "allowed_consumption_codes": [],
                "opaque_identifier": "synthetic-admin-bracelet",
            },
        },
        _context("operator", "synthetic-admin-register"),
    )


def test_administrator_can_search_and_update_approved_client(tmp_path):
    service, _storage = _service(tmp_path)
    created = _register(service)

    listed = service.handle(
        "list_clients",
        {"query": "Admin Child", "cursor": None, "limit": 100},
        _context("administrator"),
    )
    assert listed["next_cursor"] is None
    assert listed["items"] == [
        {
            "registration_id": created["registration_id"],
            "status": "approved",
            "guardian_display_name": "Synthetic Admin Guardian",
            "child_display_names": ["Synthetic Admin Child"],
            "updated_at": "2026-01-15T10:30:00+00:00",
        }
    ]

    detail = service.handle(
        "get_registration",
        {"registration_id": created["registration_id"]},
        _context("administrator"),
    )
    update = {
        "registration_id": created["registration_id"],
        "guardian": {
            "display_name": "Updated Guardian",
            "phone": "",
            "email": "updated@example.invalid",
        },
        "children": [
            {
                "child_id": detail["children"][0]["child_id"],
                "display_name": "Updated Child",
                "allowed_consumption_codes": [],
            }
        ],
    }
    result = service.handle(
        "update_client",
        update,
        _context("administrator", "synthetic-admin-update"),
    )
    assert result == {"status": "updated"}
    assert service.handle(
        "update_client",
        update,
        _context("administrator", "synthetic-admin-update"),
    ) == result

    changed = service.handle(
        "get_registration",
        {"registration_id": created["registration_id"]},
        _context("administrator"),
    )
    assert changed["guardian"]["display_name"] == "Updated Guardian"
    assert changed["guardian"]["email"] == "updated@example.invalid"
    assert changed["children"][0]["display_name"] == "Updated Child"
    assert changed["children"][0]["allowed_consumption_codes"] == []

    with pytest.raises(ValueError, match="audience"):
        service.handle(
            "update_client",
            update,
            _context("operator", "synthetic-operator-update"),
        )


def test_safe_client_deletion_blocks_active_visit_and_erases_personal_data(tmp_path):
    service, storage = _service(tmp_path)
    created = _register(service)
    visit = service.handle(
        "start_visit",
        {
            "child_id": created["child_id"],
            "assignment_id": created["assignment_id"],
            "occurred_at": "2026-01-15T10:31:00+00:00",
        },
        _context("administrator", "synthetic-admin-start"),
    )
    deletion_payload = {
        "registration_id": created["registration_id"],
        "reason": "administrator_request",
    }
    with pytest.raises(ValueError, match="active visit"):
        service.handle(
            "delete_client",
            deletion_payload,
            _context("administrator", "synthetic-admin-delete-active"),
        )

    service.handle(
        "close_visit",
        {"visit_id": visit["visit_id"], "occurred_at": "2026-01-15T10:32:00+00:00"},
        _context("administrator", "synthetic-admin-close"),
    )
    deleted = service.handle(
        "delete_client",
        deletion_payload,
        _context("administrator", "synthetic-admin-delete"),
    )
    assert deleted == {"status": "deleted", "retained_visit_count": 1}
    assert service.handle(
        "delete_client",
        deletion_payload,
        _context("administrator", "synthetic-admin-delete"),
    ) == deleted

    assert service.handle(
        "list_clients",
        {"query": "", "cursor": None, "limit": 100},
        _context("administrator"),
    )["items"] == []
    with pytest.raises(ValueError, match="not found"):
        service.handle(
            "get_registration",
            {"registration_id": created["registration_id"]},
            _context("administrator"),
        )

    with sqlite3.connect(storage.database_path) as connection:
        serialized = " ".join(
            str(value)
            for table in ("guardians", "children", "identifier_assignments")
            for row in connection.execute(f'SELECT * FROM "{table}"')
            for value in row
            if value is not None
        )
        assert "Synthetic Admin" not in serialized
        assert "+359000000099" not in serialized
        assert "admin-guardian@example.invalid" not in serialized
        assert "synthetic-admin-bracelet" not in serialized
        assert connection.execute("SELECT status FROM guardians").fetchone()[0] == "erased"
        assert connection.execute("SELECT status FROM children").fetchone()[0] == "erased"
        assert connection.execute("SELECT deleted_at FROM registrations").fetchone()[0]
        assert connection.execute("SELECT COUNT(*) FROM visits").fetchone()[0] == 1
        audit_payloads = " ".join(
            row[0] for row in connection.execute("SELECT metadata_json FROM domain_audit_events")
        )
        assert "Synthetic Admin" not in audit_payloads
        assert "synthetic-admin-bracelet" not in audit_payloads
