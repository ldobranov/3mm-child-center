import json
from pathlib import Path

from three_mm_protocol.application_extension import ApplicationExtensionV1
from three_mm_protocol.compiled_extension import CompiledUiExtensionV1
from three_mm_protocol.module_manifest import ModuleManifestV2


MODULE_ROOT = Path(__file__).parents[1]


def _read_json(name: str) -> dict:
    return json.loads((MODULE_ROOT / name).read_text(encoding="utf-8"))


def _assert_object_schemas_are_bounded(schema: object) -> None:
    if isinstance(schema, list):
        for item in schema:
            _assert_object_schemas_are_bounded(item)
        return
    if not isinstance(schema, dict):
        return
    schema_type = schema.get("type")
    if schema_type == "object" or (
        isinstance(schema_type, list) and "object" in schema_type
    ):
        assert "additionalProperties" in schema
        assert schema["additionalProperties"] is not True
    for value in schema.values():
        _assert_object_schemas_are_bounded(value)


def test_contracts_are_strict_and_identity_aligned():
    manifest_value = _read_json("manifest.json")
    application_value = _read_json("application-extension.json")
    compiled_ui_value = _read_json("compiled-ui.json")

    manifest = ModuleManifestV2.model_validate(manifest_value)
    application = ApplicationExtensionV1.model_validate(application_value)
    compiled_ui = CompiledUiExtensionV1.model_validate(compiled_ui_value)

    assert manifest.module_id == application.module_id == compiled_ui.module_id
    assert manifest.module_id == "org.3mm.child-center"
    assert manifest.version == application.version == compiled_ui.version == "0.6.7"
    assert "READER_DEVICE_ID" not in manifest.configuration_defaults
    assert manifest.entrypoints == {
        "core": "application-extension.json",
        "ui": "compiled-ui.json",
    }
    assert manifest.capabilities.consumes == ("identifier.scan.v1",)
    assert set(manifest.permissions) == {
        "data.read",
        "data.write",
        "events.consume",
        "network.outbound",
        "process.spawn",
        "secrets.use",
    }

    for operation in application_value["operations"]:
        _assert_object_schemas_are_bounded(operation["input_schema"])
        _assert_object_schemas_are_bounded(operation["output_schema"])
        expected = "forbidden" if operation["kind"] == "query" else "required"
        assert operation["idempotency"] == expected


def test_access_surfaces_and_personal_data_lifecycle_are_explicit():
    application = ApplicationExtensionV1.model_validate(
        _read_json("application-extension.json")
    )
    operations = {item.operation_id: item for item in application.operations}
    routes = {item.route_id: item for item in application.routes}

    assert set(routes) == {
        "cashier_desk",
        "tablet_registration",
        "kiosk_registration",
        "operator_desk",
        "active_visits",
        "visit_history",
        "administration",
    }
    assert routes["tablet_registration"].audience == "public"
    assert routes["tablet_registration"].layout == "application"
    assert routes["tablet_registration"].navigation is False
    assert routes["kiosk_registration"].audience == "kiosk"
    assert routes["kiosk_registration"].layout == "kiosk"
    assert routes["kiosk_registration"].navigation is False
    assert routes["operator_desk"].audience == "operator"
    assert routes["cashier_desk"].audience == "operator"
    assert routes["cashier_desk"].required_permissions == ("payments_manage",)
    for name in ("list_checkout_accounts", "get_checkout_account"):
        assert operations[name].required_permission == "payments_manage"
        assert operations[name].kind == "query"
        assert operations[name].idempotency == "forbidden"
    assert operations["list_operator_accounts"].required_permission == "visits_manage"
    assert operations["get_operator_account"].required_permission == "visits_manage"
    assert routes["active_visits"].audience == "operator"
    assert routes["active_visits"].required_permissions == ("visits_manage",)
    assert routes["visit_history"].audience == "operator"
    assert routes["visit_history"].required_permissions == ("visits_manage",)
    assert routes["administration"].audience == "administrator"
    assert set(routes["administration"].required_permissions) == {
        "configuration_manage",
        "privacy_manage",
    }
    assert all(route.navigation is False for route in routes.values())

    kiosk_operations = {
        item.operation_id for item in application.operations if "kiosk" in item.audiences
    }
    assert kiosk_operations == {
        "list_consumption_choices",
        "submit_registration",
        "get_kiosk_registration_result",
    }
    internal_operations = {
        item.operation_id
        for item in application.operations
        if item.audiences == ("internal",)
    }
    assert internal_operations == {
        "deliver_barsy_commands",
        "health",
        "process_identifier_scan",
        "apply_retention",
    }
    assert "get_tariff_configuration" not in operations
    assert "update_tariff_configuration" not in operations
    assert "add_consumption" not in operations
    assert operations["register_client"].audiences == ("operator", "administrator")
    assert operations["register_client"].required_permission == "registrations_manage"
    assert operations["register_client"].idempotency == "required"
    assert operations["export_personal_data"].audiences == ("administrator",)
    assert operations["erase_personal_data"].audiences == ("administrator",)
    assert operations["get_operator_reader_state"].audiences == (
        "operator",
        "administrator",
    )
    assert operations["get_operator_reader_state"].required_permission == "visits_manage"
    assert operations["set_operator_reader_purpose"].idempotency == "required"
    assert operations["process_identifier_scan"].audiences == ("internal",)
    assert operations["list_identifier_scan_activity"].audiences == (
        "administrator",
    )
    assert operations["list_identifier_scan_activity"].kind == "query"
    assert operations["list_identifier_scan_activity"].required_permission == "configuration_manage"
    assert operations["list_barsy_table_pool"].audiences == ("administrator",)
    assert operations["save_barsy_table_mapping"].required_permission == "configuration_manage"
    assert operations["save_barsy_table_mapping"].idempotency == "required"
    assert operations["set_barsy_table_mapping_enabled"].audiences == (
        "administrator",
    )
    assert operations["discover_barsy_places"].kind == "query"
    assert operations["discover_barsy_places"].required_permission == "configuration_manage"
    assert operations["get_barsy_integration_status"].audiences == (
        "administrator",
    )
    assert operations["list_clients"].audiences == ("administrator",)
    assert operations["update_client"].audiences == ("administrator",)
    assert operations["update_client"].idempotency == "required"
    assert operations["delete_client"].audiences == ("administrator",)
    assert operations["delete_client"].required_permission == "privacy_manage"
    assert operations["delete_client"].idempotency == "required"

    assert application.storage.contains_personal_data is True
    assert application.storage.engine == "sqlite"
    assert application.storage.schema_revision == "0015"
    assert application.storage.retention_operation_id == "apply_retention"
    assert application.storage.export_operation_id == "export_personal_data"
    assert application.storage.erasure_operation_id == "erase_personal_data"
    assert application.storage.backup_required is True
    assert application.lifecycle.disable_preserves_data is True
    assert application.lifecycle.rollback == "transactional"


def test_identifier_jobs_connector_and_secret_defaults_are_bounded():
    manifest_value = _read_json("manifest.json")
    application = ApplicationExtensionV1.model_validate(
        _read_json("application-extension.json")
    )

    assert "BARSY_API_CREDENTIAL" not in manifest_value["configuration_defaults"]
    assert manifest_value["configuration_schema"]["properties"][
        "BARSY_API_CREDENTIAL"
    ]["x-3mm-secret-reference"] is True
    serialized_defaults = json.dumps(
        manifest_value["configuration_defaults"], sort_keys=True
    ).lower()
    assert "password" not in serialized_defaults
    assert "username" not in serialized_defaults

    assert len(application.event_subscriptions) == 1
    subscription = application.event_subscriptions[0]
    assert subscription.event_type == "identifier.scan.v1"
    assert subscription.handler_operation_id == "process_identifier_scan"
    assert subscription.acknowledgement == "after_commit"

    assert {job.job_id for job in application.jobs} == {
        "apply_retention",
        "deliver_barsy_commands",
    }
    assert len(application.connectors) == 1
    connector = application.connectors[0]
    assert connector.connector_id == "barsy_api"
    assert connector.path_prefix == "/"
    assert connector.credential_ref_config_key == "BARSY_API_CREDENTIAL"
    assert connector.supports_mutations is True


def test_mutation_input_contract_forbids_unknown_root_fields():
    application_value = _read_json("application-extension.json")
    submit = next(
        item
        for item in application_value["operations"]
        if item["operation_id"] == "submit_registration"
    )
    assert submit["kind"] == "command"
    assert submit["input_schema"]["additionalProperties"] is False
    assert "unexpected" not in submit["input_schema"]["properties"]

    correction = next(
        item
        for item in application_value["operations"]
        if item["operation_id"] == "correct_registration"
    )
    assert correction["audiences"] == ["operator", "administrator"]
    assert correction["required_permission"] == "registrations_manage"
    assert correction["idempotency"] == "required"
    assert correction["audit"] == "redacted"
    assert correction["input_schema"]["additionalProperties"] is False

    kiosk_result = next(
        item
        for item in application_value["operations"]
        if item["operation_id"] == "get_kiosk_registration_result"
    )
    assert set(kiosk_result["input_schema"]["required"]) == {
        "registration_id",
        "receipt_token",
    }


def test_cc3_contract_records_time_without_owning_barsy_pricing():
    application_value = _read_json("application-extension.json")
    serialized = json.dumps(application_value, sort_keys=True).lower()

    for forbidden in (
        "tariff",
        "price_minor",
        "total_minor",
        "checkout_state",
        "catalog_item",
        "deliver_final_checkout",
    ):
        assert forbidden not in serialized

    operations = {
        item["operation_id"]: item for item in application_value["operations"]
    }
    assert set(operations["start_visit"]["output_schema"]["required"]) == {
        "visit_id",
        "state",
        "entered_at",
        "barsy_table",
    }
    assert set(operations["close_visit"]["output_schema"]["required"]) == {
        "state",
        "duration_seconds",
        "exited_at",
        "barsy_table",
    }
    assert "automatic_toggle" in operations["get_reader_configuration"]["output_schema"][
        "properties"
    ]["mode"]["enum"]
    assert "device_id" in operations["get_reader_configuration"]["output_schema"][
        "required"
    ]

    history = operations["list_visit_history"]
    assert history["kind"] == "query"
    assert history["audiences"] == ["operator", "administrator"]
    assert history["required_permission"] == "visits_manage"
    assert set(history["input_schema"]["required"]) == {
        "query",
        "date_from",
        "date_to",
        "cursor",
        "limit",
    }
    assert set(history["output_schema"]["properties"]["items"]["items"]["required"]) == {
        "visit_id",
        "child_id",
        "child_display_name",
        "guardian_display_name",
        "entered_at",
        "exited_at",
        "duration_seconds",
        "entry_source",
        "exit_source",
        "barsy_table",
    }

    history_source = (MODULE_ROOT / "source/frontend/VisitHistory.vue").read_text(
        encoding="utf-8"
    )
    assert "'list_visit_history'" in history_source
    assert "/child-center/history" in json.dumps(_read_json("compiled-ui.json"))
    for forbidden in ("price", "tariff", "currency", "payment", "receipt", "fiscal"):
        assert forbidden not in history_source.lower()


def test_cc4a_contract_exposes_only_mapping_and_mock_timing_state():
    application_value = _read_json("application-extension.json")
    operations = {
        item["operation_id"]: item for item in application_value["operations"]
    }
    pool = operations["list_barsy_table_pool"]
    assert pool["kind"] == "query"
    assert pool["output_schema"]["properties"]["delivery_mode"]["enum"] == ["mock", "live_start"]
    save = operations["save_barsy_table_mapping"]
    assert set(save["input_schema"]["properties"]) == {
        "table_slot_id",
        "barsy_place_id",
        "display_name",
        "priority",
        "enabled",
    }
    serialized = json.dumps(
        [pool, save, operations["set_barsy_table_mapping_enabled"]],
        sort_keys=True,
    ).lower()
    for forbidden in ("price", "tariff", "currency", "payment", "receipt", "fiscal"):
        assert forbidden not in serialized


def test_cc4b_discovery_is_read_only_and_production_mutations_are_disabled():
    application_value = _read_json("application-extension.json")
    operations = {
        item["operation_id"]: item for item in application_value["operations"]
    }
    discovery = operations["discover_barsy_places"]
    assert discovery["kind"] == "query"
    assert discovery["idempotency"] == "forbidden"
    assert discovery["input_schema"]["properties"]["limit"]["maximum"] == 256
    status = operations["get_barsy_integration_status"]
    assert status["output_schema"]["properties"]["production_mutations_enabled"]["type"] == "boolean"
    assert status["output_schema"]["properties"]["stop_contract_status"]["enum"] == [
        "unverified"
    ]


def test_administrator_frontend_uses_generic_admin_and_connector_routes():
    api_source = (MODULE_ROOT / "source/frontend/application-api.ts").read_text(
        encoding="utf-8"
    )
    administration_source = (
        MODULE_ROOT / "source/frontend/Administration.vue"
    ).read_text(encoding="utf-8")

    assert "audience === 'administrator' ? ''" in api_source
    assert "${MODULE_ID}/${audience}/operations" not in api_source
    assert "'/operational-status'" in api_source
    assert "`/connectors/${CONNECTOR_ID}`" in api_source
    assert "'/secrets'" in api_source
    assert "childcenter.barsy.in" in administration_source
    assert "endsWith('.in')" not in administration_source
    assert "localStorage.setItem" not in administration_source
    assert "autocomplete=\"new-password\"" in administration_source
    assert "listKioskTerminals" in administration_source
    assert "revokeKioskTerminal" in administration_source
    assert "'list_clients'" in administration_source
    assert "'update_client'" in administration_source
    assert "'delete_client'" in administration_source

    kiosk_source = (MODULE_ROOT / "source/frontend/kiosk-session.ts").read_text(
        encoding="utf-8"
    )
    assert "/kiosk/terminals`" in kiosk_source
    assert "method = 'GET'" in kiosk_source
    assert "'DELETE'" in kiosk_source
    assert "clearStoredKioskIdentity" in kiosk_source
    assert "KioskIdentityUnavailableError" in kiosk_source
    assert "REFRESH_MARGIN_MS" not in kiosk_source
    assert "const existingToken" not in kiosk_source

    kiosk_registration_source = (
        MODULE_ROOT / "source/frontend/KioskRegistration.vue"
    ).read_text(encoding="utf-8")
    assert "storedIdentity && !token" in kiosk_registration_source
    assert "kioskReady.value = false" in kiosk_registration_source
    assert "resetForm()" in kiosk_registration_source

    assert "child-center-admin-nav" in administration_source
    assert "const activeSection = ref<AdminSection>('clients')" in administration_source
    assert administration_source.index("{ id: 'clients'") < administration_source.index("{ id: 'tablets'")
    assert administration_source.index("{ id: 'tablets'") < administration_source.index("{ id: 'barsy'")
    assert administration_source.index("{ id: 'barsy'") < administration_source.index("{ id: 'system'")
    assert "selectAdminSection('clients')" in administration_source
    assert "readerConfiguration.device_id" in administration_source
    assert "activeSection === 'tablets'" in administration_source
    assert "activeSection === 'clients'" in administration_source
    assert "activeSection === 'barsy'" in administration_source
    assert "activeSection === 'system'" in administration_source
    assert "'get_reader_configuration'" in administration_source
    assert "'update_reader_configuration'" in administration_source
    assert "'list_identifier_scan_activity'" in administration_source
    assert "opaque_identifier" not in administration_source


def test_all_child_center_surfaces_follow_application_theme_variables():
    themed_sources = {
        name: (MODULE_ROOT / f"source/frontend/{name}").read_text(encoding="utf-8")
        for name in (
            "ActiveVisits.vue",
            "Administration.vue",
            "KioskRegistration.vue",
            "OperatorDesk.vue",
            "VisitHistory.vue",
        )
    }

    for source in themed_sources.values():
        assert "--text-color: var(--text-primary" in source
        assert "--muted-text-color: var(--text-secondary" in source
        assert "--surface-color: var(--card-bg" in source
        assert "--surface-muted: var(--color-background-soft" in source
        assert "--border-color: var(--card-border" in source
        assert "--danger-color: var(--error-color" in source

    for name in (
        "Administration.vue",
        "KioskRegistration.vue",
        "OperatorDesk.vue",
        "VisitHistory.vue",
    ):
        assert "var(--input-bg" in themed_sources[name]
        assert "var(--input-border" in themed_sources[name]

    combined = "\n".join(themed_sources.values())
    assert "var(--button-primary-text" in combined
    assert "var(--error-surface" in combined
    assert "var(--success-surface" in combined

    kiosk_runtime = (MODULE_ROOT / "source/frontend/KioskRuntime.vue").read_text(
        encoding="utf-8"
    )
    assert "import KioskRegistration from './KioskRegistration.vue'" in kiosk_runtime
