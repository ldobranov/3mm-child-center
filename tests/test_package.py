import asyncio
import hashlib
import importlib
import importlib.util
import io
import json
from pathlib import Path
import sys
import zipfile

import pytest

from backend.services.module_packages import validate_module_package
from three_mm_application_sdk import (
    ApplicationContext,
    ApplicationStorage,
    OperationContext,
)


MODULE_ROOT = Path(__file__).parents[1]


def _builder_module():
    spec = importlib.util.spec_from_file_location(
        "child_center_test_builder",
        MODULE_ROOT / "build_child_center_package.py",
    )
    assert spec is not None and spec.loader is not None
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def test_reviewed_package_is_deterministic_valid_and_credential_free():
    builder = _builder_module()
    package = builder.build_package()
    assert package == builder.build_package()

    validated = validate_module_package(package, architecture="aarch64")
    assert validated.manifest.module_id == "org.3mm.child-center"
    assert validated.manifest.version == "0.7.6"
    assert "READER_DEVICE_ID" not in validated.manifest.configuration_defaults
    assert validated.manifest.registrations == ()
    assert validated.application_extension is not None
    assert validated.compiled_ui is not None

    with zipfile.ZipFile(io.BytesIO(package)) as archive:
        names = archive.namelist()
        assert names == [
            "manifest.json",
            "application-extension.json",
            "compiled-ui.json",
            "service/child_center_application-0.7.6-py3-none-any.whl",
            "source/frontend/AccessPanel.vue",
            "source/frontend/AccountDesk.vue",
            "source/frontend/ActiveVisits.vue",
            "source/frontend/Administration.vue",
            "source/frontend/BarsyDirectory.vue",
            "source/frontend/ConsumptionChoices.vue",
            "source/frontend/KioskRegistration.vue",
            "source/frontend/KioskRuntime.vue",
            "source/frontend/OperatorDesk.vue",
            "source/frontend/ScanOutcomes.vue",
            "source/frontend/StaffAccessGate.vue",
            "source/frontend/StaffAccessSettings.vue",
            "source/frontend/StaffCashier.vue",
            "source/frontend/StaffHistory.vue",
            "source/frontend/StaffOperator.vue",
            "source/frontend/StaffVisits.vue",
            "source/frontend/StayBills.vue",
            "source/frontend/VisitHistory.vue",
            "source/frontend/application-api.ts",
            "source/frontend/kiosk-session.ts",
            "source/frontend/language.ts",
        ]
        assert all(item.date_time == builder.FIXED_ARCHIVE_TIME for item in archive.infolist())
        wheel_name = validated.application_extension.service.artifact
        wheel = archive.read(wheel_name)
        assert hashlib.sha256(wheel).hexdigest() == (
            validated.application_extension.service.artifact_sha256
        )
        manifest_payload = archive.read("manifest.json").lower()
        assert b"password" not in manifest_payload
        assert b"username" not in manifest_payload
        frontend_payload = b"".join(
            archive.read(name) for name in names if name.startswith("source/frontend/")
        )
        assert b"crypto.randomUUID()" not in frontend_payload
        assert b"preferredLanguage" in frontend_payload
        assert b"requestFullscreen" in frontend_payload
        assert b"webkitRequestFullscreen" in frontend_payload
        assert b"cc-page:fullscreen" in frontend_payload
        assert b"childCenterKioskCredential" in frontend_payload
        assert b"applicationKioskToken" not in frontend_payload
        contract = json.loads(archive.read("application-extension.json"))
        operations = {item["operation_id"]: item for item in contract["operations"]}
        assert operations["reconcile_account_command"]["audiences"] == ["operator", "administrator"]
        assert operations["reconcile_account_command"]["required_permission"] == "visits_manage"
        assert operations["release_incomplete_closed_account"]["audiences"] == ["administrator"]
        assert operations["release_incomplete_closed_account"]["required_permission"] == "configuration_manage"

    with pytest.raises(ValueError, match="reviewed version"):
        builder.build_package(version="0.4.0")
    with pytest.raises(ValueError, match=r"HTTP\(S\) origin"):
        builder.build_package("http://account:secret@127.0.0.1:9921")


def test_extension_installer_compiles_and_stages_package(
    monkeypatch,
    tmp_path,
):
    import backend.database  # noqa: F401 - register installer ORM relationships
    from backend.routes import modules
    from backend.services.compiled_ui import load_compiled_ui_artifact

    builder = _builder_module()
    package = builder.build_package()
    validated = validate_module_package(package, architecture="aarch64")

    class Upload:
        async def read(self, limit):
            assert limit == 10 * 1024 * 1024 + 1
            return package

    class Database:
        def __init__(self):
            self.record = None

        def add(self, record):
            self.record = record

        def commit(self):
            return None

    settings = type(
        "Settings",
        (),
        {"backend": type("Backend", (), {"uploads_dir": tmp_path / "uploads"})()},
    )()
    monkeypatch.setattr(modules, "get_settings", lambda: settings)
    monkeypatch.setenv(
        "COMPILED_UI_ARTIFACTS_DIR",
        str(tmp_path / "compiled-ui"),
    )
    database = Database()

    result = asyncio.run(modules.upload_package(Upload(), object(), database))

    assert database.record is result
    assert result.module_id == "org.3mm.child-center"
    assert result.version == "0.7.6"
    assert result.sha256 == validated.sha256
    assert Path(result.file_path).read_bytes() == package
    assert result.registrations == []
    assert not hasattr(result, "enabled")
    artifact = load_compiled_ui_artifact(validated)
    assert set(artifact.entrypoints) == {
        "access_settings",
        "cashier_desk",
        "tablet_registration",
        "kiosk_registration",
        "operator_desk",
        "active_visits",
        "visit_history",
        "administration",
    }


def test_packaged_migration_and_health_operation(tmp_path):
    builder = _builder_module()
    package = builder.build_package()
    validated = validate_module_package(package, architecture="aarch64")
    assert validated.application_extension is not None

    with zipfile.ZipFile(io.BytesIO(package)) as archive:
        wheel_name = validated.application_extension.service.artifact
        wheel_path = tmp_path / Path(wheel_name).name
        wheel_path.write_bytes(archive.read(wheel_name))

    sys.path.insert(0, str(wheel_path))
    try:
        migrations = importlib.import_module("child_center_application.reliable_runtime")
        service_module = importlib.import_module("child_center_application.reliable_runtime")
        storage = ApplicationStorage(tmp_path / "application-data")
        storage.migrate(migrations.get_migrations(), "0020")
        service = service_module.create_service(
            ApplicationContext(
                module_id="org.3mm.child-center",
                version="0.7.6",
                data_dir=tmp_path / "application-data",
                configuration=validated.manifest.configuration_defaults,
                storage=storage,
            )
        )
        internal = OperationContext(
            audience="internal",
            correlation_id="correlation-health",
        )
        assert service.handle("health", {}, internal) == {
            "status": "ready",
            "schema_revision": "0020",
            "service_version": "0.7.6",
        }
        with pytest.raises(ValueError, match="not implemented"):
            service.handle(
                "correct_visit",
                {},
                OperationContext(
                    audience="kiosk",
                    correlation_id="correlation-unimplemented",
                    idempotency_key="command-unimplemented",
                ),
            )
        with pytest.raises(ValueError, match="empty request"):
            service.handle("health", {"unexpected": True}, internal)
    finally:
        sys.path.remove(str(wheel_path))
        for name in list(sys.modules):
            if name == "child_center_application" or name.startswith(
                "child_center_application."
            ):
                sys.modules.pop(name)
