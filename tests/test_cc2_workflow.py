from datetime import UTC, datetime
import importlib.util
import json
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
        "child_center_cc2_migrations",
        "service/child_center_application/migrations.py",
    )
    service_module = _load(
        "child_center_cc2_service",
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
        correlation_id=f"synthetic-correlation-{audience}",
        user_id=42 if audience in {"operator", "administrator"} else None,
        idempotency_key=key,
    )


def _registration_payload():
    return {
        "guardian": {
            "display_name": "Synthetic Guardian",
            "phone": "",
            "email": "guardian@example.invalid",
            "consent_version": "synthetic-consent-v1",
            "consented_at": "2026-01-15T10:30:00+00:00",
        },
        "children": [
            {
                "display_name": "Synthetic Child One",
                "allowed_consumption_codes": [],
            },
            {
                "display_name": "Synthetic Child Two",
                "allowed_consumption_codes": [],
            },
        ],
    }


def test_cc2_registration_correction_approval_and_identifier_lifecycle(tmp_path):
    service, storage = _service(tmp_path)
    kiosk = _context("kiosk", "synthetic-submit-key")
    payload = _registration_payload()

    submitted = service.handle("submit_registration", payload, kiosk)
    assert submitted["status"] == "submitted"
    assert submitted["receipt_token"].startswith("receipt_")
    assert service.handle("submit_registration", payload, kiosk) == submitted

    changed = _registration_payload()
    changed["guardian"]["email"] = "changed@example.invalid"
    with pytest.raises(ValueError, match="reused"):
        service.handle("submit_registration", changed, kiosk)

    with pytest.raises(ValueError, match="audience"):
        service.handle(
            "list_registrations",
            {"status": "submitted", "cursor": None, "limit": 20},
            _context("kiosk"),
        )
    with pytest.raises(ValueError, match="unavailable"):
        service.handle(
            "get_kiosk_registration_result",
            {
                "registration_id": submitted["registration_id"],
                "receipt_token": "receipt_" + "0" * 64,
            },
            _context("kiosk"),
        )

    assert service.handle(
        "get_kiosk_registration_result",
        {
            "registration_id": submitted["registration_id"],
            "receipt_token": submitted["receipt_token"],
        },
        _context("kiosk"),
    )["status"] == "submitted"

    operator = _context("operator")
    listed = service.handle(
        "list_registrations",
        {"status": "submitted", "cursor": None, "limit": 20},
        operator,
    )
    assert listed["items"] == [
        {
            "registration_id": submitted["registration_id"],
            "status": "submitted",
            "submitted_at": "2026-01-15T10:30:00+00:00",
            "child_count": 2,
        }
    ]
    assert "display_name" not in listed["items"][0]

    detail = service.handle(
        "get_registration",
        {"registration_id": submitted["registration_id"]},
        operator,
    )
    assert detail["guardian"]["phone"] == ""
    assert detail["guardian"]["email"] == "guardian@example.invalid"
    correction = {
        "registration_id": detail["registration_id"],
        "guardian": {
            "display_name": "Synthetic Guardian Corrected",
            "phone": "+359000000000",
            "email": "corrected@example.invalid",
        },
        "children": [
            {
                "child_id": child["child_id"],
                "display_name": f"Synthetic Corrected {index}",
                "allowed_consumption_codes": [],
            }
            for index, child in enumerate(detail["children"], start=1)
        ],
    }
    assert service.handle(
        "correct_registration",
        correction,
        _context("operator", "synthetic-correction-key"),
    ) == {"status": "corrected"}

    approved = service.handle(
        "approve_registration",
        {"registration_id": submitted["registration_id"]},
        _context("operator", "synthetic-approval-key"),
    )
    assert approved["status"] == "approved"
    assert len(approved["child_ids"]) == 2

    first = approved["child_ids"][0]
    second = approved["child_ids"][1]
    assigned = service.handle(
        "assign_identifier",
        {"child_id": first, "opaque_identifier": "synthetic-opaque-one"},
        _context("operator", "synthetic-assign-one"),
    )
    assert assigned["status"] == "assigned"
    replacement = service.handle(
        "assign_identifier",
        {"child_id": first, "opaque_identifier": "synthetic-opaque-two"},
        _context("operator", "synthetic-assign-two"),
    )
    assert replacement["assignment_id"] != assigned["assignment_id"]

    with pytest.raises(ValueError, match="already assigned"):
        service.handle(
            "assign_identifier",
            {"child_id": second, "opaque_identifier": "synthetic-opaque-two"},
            _context("operator", "synthetic-conflicting-assign"),
        )

    approved_detail = service.handle(
        "get_registration",
        {"registration_id": submitted["registration_id"]},
        operator,
    )
    first_detail = next(item for item in approved_detail["children"] if item["child_id"] == first)
    assert "opaque_identifier" not in json.dumps(first_detail)
    assert len(first_detail["identifier_assignments"]) == 2
    assert sum(item["retired_at"] is None for item in first_detail["identifier_assignments"]) == 1

    assert service.handle(
        "retire_identifier",
        {"assignment_id": replacement["assignment_id"], "reason": "manual"},
        _context("operator", "synthetic-retire-key"),
    ) == {"status": "retired"}

    assert service.handle(
        "get_kiosk_registration_result",
        {
            "registration_id": submitted["registration_id"],
            "receipt_token": submitted["receipt_token"],
        },
        _context("kiosk"),
    )["status"] == "approved"

    with sqlite3.connect(storage.database_path) as connection:
        stored_registration = connection.execute(
            "SELECT kiosk_receipt_hash, submission_idempotency_key FROM registrations"
        ).fetchone()
        assert submitted["receipt_token"] not in stored_registration
        assert "synthetic-submit-key" not in stored_registration
        command_results = " ".join(
            row[0] for row in connection.execute("SELECT result_json FROM command_results")
        )
        assert "receipt_" not in command_results
        audits = " ".join(
            row[0] for row in connection.execute("SELECT metadata_json FROM domain_audit_events")
        )
        assert "Synthetic" not in audits
        assert "example.invalid" not in audits
        assert "synthetic-opaque" not in audits


def test_cc2_rejects_correction_after_approval_and_cross_audience_health(tmp_path):
    service, _storage = _service(tmp_path)
    payload = _registration_payload()
    submitted = service.handle(
        "submit_registration",
        payload,
        _context("kiosk", "synthetic-second-submit"),
    )
    detail = service.handle(
        "get_registration",
        {"registration_id": submitted["registration_id"]},
        _context("administrator"),
    )
    correction = {
        "registration_id": detail["registration_id"],
        "guardian": {
            "display_name": detail["guardian"]["display_name"],
            "phone": detail["guardian"]["phone"],
            "email": detail["guardian"]["email"],
        },
        "children": [
            {
                "child_id": item["child_id"],
                "display_name": item["display_name"],
                "allowed_consumption_codes": item["allowed_consumption_codes"],
            }
            for item in detail["children"]
        ],
    }
    service.handle(
        "approve_registration",
        {"registration_id": submitted["registration_id"]},
        _context("administrator", "synthetic-second-approval"),
    )
    with pytest.raises(ValueError, match="submitted"):
        service.handle(
            "correct_registration",
            correction,
            _context("administrator", "synthetic-late-correction"),
        )
    with pytest.raises(ValueError, match="audience"):
        service.handle("health", {}, _context("administrator"))


def test_operator_registers_approved_client_and_bracelet_atomically(tmp_path):
    service, storage = _service(tmp_path)
    payload = {
        "guardian": {
            "display_name": "Synthetic Desk Guardian",
            "phone": "+359000000001",
            "email": "desk@example.invalid",
            "consent_version": "operator-registration-v1",
            "consented_at": "2026-01-15T10:30:00+00:00",
        },
        "child": {
            "display_name": "Synthetic Desk Child",
            "allowed_consumption_codes": [],
            "opaque_identifier": "synthetic-desk-bracelet",
        },
    }
    context = _context("operator", "synthetic-desk-registration")

    created = service.handle("register_client", payload, context)
    assert created["status"] == "approved"
    assert service.handle("register_client", payload, context) == created

    detail = service.handle(
        "get_registration",
        {"registration_id": created["registration_id"]},
        _context("operator"),
    )
    assert detail["status"] == "approved"
    assert detail["guardian"]["phone"] == "+359000000001"
    assert detail["guardian"]["email"] == "desk@example.invalid"
    assert detail["children"][0]["status"] == "active"
    assert detail["children"][0]["identifier_assignments"] == [
        {
            "assignment_id": created["assignment_id"],
            "assigned_at": "2026-01-15T10:30:00+00:00",
            "retired_at": None,
            "retire_reason": None,
        }
    ]
    assert "synthetic-desk-bracelet" not in json.dumps(detail)

    with pytest.raises(ValueError, match="audience"):
        service.handle(
            "register_client",
            payload,
            _context("kiosk", "synthetic-kiosk-desk-registration"),
        )
    with sqlite3.connect(storage.database_path) as connection:
        assert connection.execute("SELECT COUNT(*) FROM registrations").fetchone()[0] == 1
        assert connection.execute("SELECT COUNT(*) FROM identifier_assignments").fetchone()[0] == 1


def test_registration_requires_phone_or_email(tmp_path):
    service, _storage = _service(tmp_path)
    payload = _registration_payload()
    payload["guardian"]["phone"] = ""
    payload["guardian"]["email"] = ""

    with pytest.raises(ValueError, match="phone or email"):
        service.handle(
            "submit_registration",
            payload,
            _context("kiosk", "synthetic-no-contact"),
        )
