import importlib.util
from pathlib import Path
import sqlite3

from three_mm_application_sdk import ApplicationStorage


MODULE_ROOT = Path(__file__).parents[1]


def _migrations_module():
    path = MODULE_ROOT / "service" / "child_center_application" / "migrations.py"
    spec = importlib.util.spec_from_file_location("child_center_test_migrations", path)
    assert spec is not None and spec.loader is not None
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def test_revision_0008_is_forward_only_repeatable_and_domain_owned(tmp_path):
    migrations = _migrations_module().get_migrations()
    assert [item.revision for item in migrations] == ["0001", "0002", "0003", "0004", "0005", "0006", "0007", "0008", "0009", "0010", "0011", "0012", "0013", "0014", "0015", "0016"]

    storage = ApplicationStorage(tmp_path / "child-center-data")
    storage.migrate(migrations, "0001")
    assert storage.status() == {"revision": "0001", "outbox": {}}
    storage.migrate(migrations, "0002")
    assert storage.status() == {"revision": "0002", "outbox": {}}
    storage.migrate(migrations, "0003")
    storage.migrate(migrations, "0004")
    storage.migrate(migrations, "0005")
    storage.migrate(migrations, "0006")
    storage.migrate(migrations, "0007")
    storage.migrate(migrations, "0008")
    storage.migrate(migrations, "0008")

    storage.migrate(migrations, "0009")
    storage.migrate(migrations, "0009")
    storage.migrate(migrations, "0010")
    storage.migrate(migrations, "0010")
    storage.migrate(migrations, "0011")
    storage.migrate(migrations, "0011")
    assert storage.status() == {"revision": "0011", "outbox": {}}
    with sqlite3.connect(storage.database_path) as connection:
        tables = {
            row[0]
            for row in connection.execute(
                "SELECT name FROM sqlite_master WHERE type = 'table'"
            )
        }
        assert {
            "registrations",
            "guardians",
            "children",
            "guardian_children",
            "identifier_assignments",
            "reader_configurations",
            "visits",
            "visit_events",
            "external_mappings",
            "command_results",
            "domain_audit_events",
            "identifier_event_results",
            "identifier_scan_activity",
            "barsy_table_slots",
            "visit_barsy_bindings",
            "barsy_timing_commands",
            "three_mm_outbox",
            "three_mm_schema_migrations",
        }.issubset(tables)
        assert {
            "tariffs",
            "tariff_versions",
            "catalog_items",
            "catalog_staging",
            "consumption_records",
        }.isdisjoint(tables)
        domain_tables = tables - {
            "three_mm_outbox",
            "three_mm_schema_migrations",
            "reader_configurations",
        }
        domain_tables -= {"barsy_delivery_settings"}
        assert connection.execute("SELECT live_start FROM barsy_delivery_settings").fetchone() == (0,)
        assert all(
            connection.execute(f'SELECT COUNT(*) FROM "{table}"').fetchone()[0] == 0
            for table in domain_tables
        )
        registration_columns = {
            row[1] for row in connection.execute("PRAGMA table_info(registrations)")
        }
        assert "submission_idempotency_key" in registration_columns
        assert "kiosk_receipt_hash" in registration_columns
        assert {"deleted_at", "deleted_by"}.issubset(registration_columns)
        guardian_columns = {
            row[1] for row in connection.execute("PRAGMA table_info(guardians)")
        }
        assert {"phone", "email"}.issubset(guardian_columns)
        registration_definition = connection.execute(
            "SELECT sql FROM sqlite_master WHERE type = 'table' AND name = ?",
            ("registrations",),
        ).fetchone()[0]
        assert "submission_idempotency_key TEXT NOT NULL UNIQUE" in registration_definition
        active_identifier_index = connection.execute(
            "SELECT sql FROM sqlite_master WHERE name = ?",
            ("uq_identifier_assignments_active_identifier",),
        ).fetchone()[0]
        active_visit_index = connection.execute(
            "SELECT sql FROM sqlite_master WHERE name = ?",
            ("uq_visits_active_child",),
        ).fetchone()[0]
        assert "WHERE retired_at IS NULL" in active_identifier_index
        assert "WHERE state = 'active'" in active_visit_index
        receipt_index = connection.execute(
            "SELECT sql FROM sqlite_master WHERE name = ?",
            ("uq_registrations_kiosk_receipt_hash",),
        ).fetchone()[0]
        assert "WHERE kiosk_receipt_hash IS NOT NULL" in receipt_index
        assert connection.execute("PRAGMA foreign_key_list(visits)").fetchall()
        visit_columns = {
            row[1] for row in connection.execute("PRAGMA table_info(visits)")
        }
        assert {
            "currency",
            "tariff_version_id",
            "time_charge_minor",
            "consumption_charge_minor",
            "total_minor",
            "checkout_state",
        }.isdisjoint(visit_columns)
        assert connection.execute(
            "SELECT mode, operator_selected_purpose FROM reader_configurations WHERE retired_at IS NULL"
        ).fetchone() == ("automatic_toggle", "entry")
        binding_index = connection.execute(
            "SELECT sql FROM sqlite_master WHERE name = ?",
            ("uq_visit_barsy_bindings_allocated_slot",),
        ).fetchone()[0]
        assert "WHERE state = 'allocated'" in binding_index


def test_revision_0005_preserves_existing_phone_and_email_contacts(tmp_path):
    migrations = _migrations_module().get_migrations()
    storage = ApplicationStorage(tmp_path / "child-center-upgrade-data")
    storage.migrate(migrations, "0004")

    with sqlite3.connect(storage.database_path) as connection:
        for suffix, contact_kind, contact_value in (
            ("phone", "phone", "+359000000001"),
            ("email", "email", "guardian@example.invalid"),
        ):
            connection.execute(
                """
                INSERT INTO registrations(
                    registration_id, kiosk_terminal_id, submission_idempotency_key,
                    status, consent_version, submitted_at, created_at, updated_at,
                    kiosk_receipt_hash
                ) VALUES (?, 'synthetic-terminal', ?, 'submitted', 'v1', ?, ?, ?, NULL)
                """,
                (
                    f"registration-{suffix}",
                    f"idempotency-{suffix}",
                    "2026-01-15T10:30:00+00:00",
                    "2026-01-15T10:30:00+00:00",
                    "2026-01-15T10:30:00+00:00",
                ),
            )
            connection.execute(
                """
                INSERT INTO guardians(
                    guardian_id, registration_id, display_name, contact_kind,
                    contact_value, consent_version, consented_at, status,
                    created_at, updated_at
                ) VALUES (?, ?, 'Synthetic Guardian', ?, ?, 'v1', ?, 'active', ?, ?)
                """,
                (
                    f"guardian-{suffix}",
                    f"registration-{suffix}",
                    contact_kind,
                    contact_value,
                    "2026-01-15T10:30:00+00:00",
                    "2026-01-15T10:30:00+00:00",
                    "2026-01-15T10:30:00+00:00",
                ),
            )
        connection.commit()

    storage.migrate(migrations, "0005")

    with sqlite3.connect(storage.database_path) as connection:
        assert connection.execute(
            "SELECT phone, email FROM guardians WHERE guardian_id = 'guardian-phone'"
        ).fetchone() == ("+359000000001", "")
        assert connection.execute(
            "SELECT phone, email FROM guardians WHERE guardian_id = 'guardian-email'"
        ).fetchone() == ("", "guardian@example.invalid")
