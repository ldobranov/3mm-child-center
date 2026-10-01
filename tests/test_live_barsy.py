"""Network-free delivery tests; remote mutations are represented by a strict fake."""
import base64
import json
import uuid

import pytest
from backend.services.application_extensions import validate_operation_payload
from backend.services.application_connectors import REQUEST_ID_PATTERN

from test_cc4_barsy_pool import _service, _context, _approved_children, _save_table, MODULE_ROOT


def response(body):
    return {"outcome": "succeeded", "http_status": 200,
            "body_base64": base64.b64encode(json.dumps(body).encode()).decode()}


class Remote:
    def __init__(self):
        self.calls = []
        self.posts = []
        self.outcome = "succeeded"
        self.closed = False
        self.occupied = False
        self.alias = None

    def connector_request(self, connector_id, **request):
        assert connector_id == "barsy_api"
        self.calls.append(request)
        path = request["path"]
        assert "?" not in path
        if request["method"] == "POST":
            assert REQUEST_ID_PATTERN.fullmatch(request["request_id"])
            assert path == "/endpoints/json/Accounts_create"
            body = json.loads(request["body"])
            assert set(body) == {"account", "rows"}
            assert body["rows"] == []
            assert set(body["account"]) == {"uuid", "place_id", "account_alias", "client_id"}
            assert body["account"]["client_id"] == 601
            assert request["idempotency_key"] == body["account"]["uuid"]
            uuid.UUID(request["idempotency_key"])
            assert request["request_id"] == "connector_" + uuid.UUID(request["idempotency_key"]).hex
            self.posts.append(body)
            self.alias = body["account"]["account_alias"]
            if self.outcome == "crash":
                raise RuntimeError("simulated process interruption")
            if self.outcome != "succeeded":
                return {"outcome": self.outcome, "http_status": None}
            return response(501)
        assert request["method"] == "GET"
        assert isinstance(json.loads(request["body"]), dict)
        if path.endswith("Poses_getcurrent"):
            return response({"pos_id": 91})
        if path.endswith("Places_getlist"):
            return response([{"place_id": 101, "place_type": 101, "place_num": "1"}])
        if path.endswith("Accounts_getlist"):
            assert json.loads(request["body"]) == {"filters": {"place_id": 101, "status": 0}, "length": 2}
            return response([{"account_id": 9}] if self.occupied else [])
        if path.endswith("Accounts_get"):
            return response({"account_id": 501, "place_id": 101,
                             "account_alias": self.alias, "status": int(self.closed)})
        raise AssertionError(path)


def setup_live(tmp_path, schema_revision="0011"):
    remote = Remote()
    storage, service, clock = _service(tmp_path, remote, schema_revision)
    if schema_revision != "0011":
        # Build the historical fixture without invoking new-version features.
        service._queue_parent = lambda *args: None
        service._validate_consumption = lambda *args: None
    service.handle("set_barsy_delivery_mode", {"enabled": True}, _context("administrator", "enable"))
    _save_table(service, 101, 10, "table")
    child = _approved_children(service, 1)[0]
    if schema_revision == "0011":
        with storage.transaction() as connection:
            connection.execute("UPDATE barsy_parent_links SET state = 'confirmed', remote_client_id = 601")
    service.handle("assign_identifier", {"child_id": child, "opaque_identifier": "synthetic-live"}, _context("operator", "bracelet"))
    service.application.configuration["READER_DEVICE_ID"] = "dev_" + "a" * 32
    scan = {"event_id": "evt_" + "b" * 32, "device_id": "dev_" + "a" * 32,
            "event_type": "identifier.scan.v1", "occurred_at": "2026-08-30T20:50:00+00:00",
            "payload": {"schema_version": 1, "capability_id": "identifier.scan.v1",
                        "opaque_identifier": "synthetic-live", "reader_id": "synthetic-reader",
                        "adapter_kind": "mock", "sequence": 1, "device_health": "ok", "scan_metadata": {}}}
    visit = service.handle("process_identifier_scan", scan, _context("internal", "scan"))
    return storage, service, remote, scan, visit


def status(service):
    result = service.handle("get_barsy_integration_status", {}, _context("administrator"))
    contract = json.loads((MODULE_ROOT / "application-extension.json").read_text(encoding="utf-8"))
    schema = next(o["output_schema"] for o in contract["operations"] if o["operation_id"] == "get_barsy_integration_status")
    validate_operation_payload(result, schema)
    return result["commands"][0]


def tick(service):
    return service.handle("deliver_barsy_commands", {}, _context("internal", "job"))


def close(service, visit):
    service.handle("close_visit", {"visit_id": visit["visit_id"], "occurred_at": "2026-08-30T21:20:00+00:00"}, _context("operator", "exit"))


def test_scan_delivers_once_and_release_requires_verified_remote_close(tmp_path):
    storage, service, remote, scan, visit = setup_live(tmp_path)
    assert status(service)["state"] == "prepared"
    assert not remote.posts
    assert tick(service) == {"processed": 1}
    assert service.handle("process_identifier_scan", scan, _context("internal", "scan-retry")) == visit
    assert tick(service) == {"processed": 0}
    assert len(remote.posts) == 1
    command = status(service)
    assert command["state"] == "confirmed"
    assert command["remote_account_id"] == "501"
    assert "synthetic-live" not in json.dumps(remote.posts)
    close(service, visit)
    assert status(service)["binding_state"] == "allocated"
    payload = {"command_id": command["command_id"], "account_id": 501}
    assert service.handle("reconcile_barsy_account", payload, _context("administrator", "check-open"))["status"] == "confirmed"
    remote.closed = True
    assert service.handle("reconcile_barsy_account", payload, _context("administrator", "check-closed"))["status"] == "released"
    assert len(remote.posts) == 1


@pytest.mark.parametrize("outcome", ["ambiguous", "retryable", "rejected", "crash"])
def test_unknown_mutation_result_is_never_replayed_after_restart(tmp_path, outcome):
    storage, service, remote, scan, visit = setup_live(tmp_path)
    remote.outcome = outcome
    if outcome == "crash":
        with pytest.raises(RuntimeError):
            tick(service)
    else:
        tick(service)
    restarted = type(service)(service.application)
    tick(restarted)
    assert len(remote.posts) == 1
    assert status(restarted)["state"] == "ambiguous"
    close(restarted, visit)
    command = status(restarted)
    with pytest.raises(ValueError, match="unsent"):
        restarted.handle("reconcile_barsy_account", {"command_id": command["command_id"], "account_id": None}, _context("administrator", "cannot-cancel-sent"))


def test_occupied_remote_place_is_not_opened_and_unsent_exit_can_release(tmp_path):
    storage, service, remote, scan, visit = setup_live(tmp_path)
    remote.occupied = True
    tick(service)
    assert status(service)["state"] == "retryable"
    assert not remote.posts
    close(service, visit)
    tick(service)
    command = status(service)
    result = service.handle("reconcile_barsy_account", {"command_id": command["command_id"], "account_id": None}, _context("administrator", "cancel-unsent"))
    assert result == {"status": "released"}
    assert not remote.posts


def test_reconciliation_rejects_other_account_and_wrong_audience(tmp_path):
    storage, service, remote, scan, visit = setup_live(tmp_path)
    tick(service)
    payload = {"command_id": status(service)["command_id"], "account_id": 501}
    remote.alias = "unrelated account"
    with pytest.raises(ValueError, match="does not match"):
        service.handle("reconcile_barsy_account", payload, _context("administrator", "wrong"))
    with pytest.raises(ValueError, match="audience"):
        service.handle("reconcile_barsy_account", payload, _context("operator", "wrong-role"))
    with pytest.raises(ValueError, match="allocated"):
        service.handle("set_barsy_delivery_mode", {"enabled": False}, _context("administrator", "disable"))


@pytest.mark.parametrize("ended", [False, True])
def test_upgrade_recovers_legacy_unsent_command_once(tmp_path, ended):
    from test_migration import _migrations_module

    storage, service, remote, scan, visit = setup_live(tmp_path, "0009")
    command = status(service)
    with storage.transaction() as connection:
        connection.execute(
            "UPDATE barsy_timing_commands SET state = 'ambiguous', error_code = 'confirmation_required' WHERE command_id = ?",
            (command["command_id"],),
        )
    if ended:
        close(service, visit)
    migrations = _migrations_module().get_migrations()
    storage.migrate(migrations, "0010")
    assert status(service)["state"] == "prepared"
    storage.migrate(migrations, "0011")
    service = type(service)(service.application)
    with storage.transaction() as connection:
        guardian_id = connection.execute("SELECT guardian_id FROM guardians").fetchone()[0]
        service._queue_parent(connection, guardian_id)
        connection.execute("UPDATE barsy_parent_links SET state = 'confirmed', remote_client_id = 601")
    remote.outcome = "ambiguous"
    tick(service)
    if ended:
        assert not remote.posts
        assert status(service)["error_code"] == "visit_already_closed"
        assert service.handle("reconcile_barsy_account", {
            "command_id": command["command_id"], "account_id": None,
        }, _context("administrator", "release-upgraded")) == {"status": "released"}
    else:
        assert len(remote.posts) == 1
        assert status(service)["state"] == "ambiguous"
        storage.migrate(migrations, "0011")
        tick(type(service)(service.application))
        assert len(remote.posts) == 1
        assert status(service)["state"] == "ambiguous"


@pytest.mark.parametrize("state,account,error", [
    ("confirmed", "501", None),
    ("ambiguous", "501", "confirmation_required"),
    ("ambiguous", None, "other_failure"),
    ("manual_review", None, "visit_already_closed"),
])
def test_upgrade_preserves_other_command_states(tmp_path, state, account, error):
    from test_migration import _migrations_module

    storage, service, remote, scan, visit = setup_live(tmp_path, "0009")
    with storage.transaction() as connection:
        connection.execute(
            "UPDATE barsy_timing_commands SET state = ?, remote_account_id = ?, error_code = ?",
            (state, account, error),
        )
    before = status(service)
    storage.migrate(_migrations_module().get_migrations(), "0010")
    assert status(service) == before
    assert not remote.posts


def test_delivery_through_real_connector_broker(tmp_path, monkeypatch):
    from types import SimpleNamespace
    import backend.database  # Register ORM relationships without changing Core.
    from backend.services import application_connectors as broker

    storage, service, remote, scan, visit = setup_live(tmp_path)
    contract = json.loads((MODULE_ROOT / "application-extension.json").read_text(encoding="utf-8"))
    definition = SimpleNamespace(**contract["connectors"][0])
    binding = SimpleNamespace(destination_origin="https://barsy.example.invalid", secret_reference_id=1)
    installation = SimpleNamespace(id=91, enabled=True, status="active")
    secret = SimpleNamespace(application_installation_id=91)
    monkeypatch.setattr(broker, "_connector_definition", lambda *args: definition)
    monkeypatch.setattr(broker, "decrypt_secret_reference", lambda value: {
        "username": "synthetic", "password": "synthetic-not-a-credential",
    })

    class Database:
        def __init__(self):
            self.reads = 0
        def scalar(self, query):
            self.reads += 1
            return None if self.reads == 1 else binding
        def get(self, *args):
            return secret
        def add(self, attempt):
            self.attempt = attempt
        def commit(self):
            pass

    sent = []
    def transport(method, url, **kwargs):
        sent.append((method, url, kwargs))
        assert url == "https://barsy.example.invalid/endpoints/json/Accounts_create"
        assert kwargs["allow_redirects"] is False
        return SimpleNamespace(content=b"501", status_code=200, headers={})

    original = remote.connector_request
    def through_broker(connector_id, **request):
        if request["method"] != "POST":
            return original(connector_id, **request)
        return broker.execute_connector_request(
            Database(), installation, connector_id=connector_id,
            transport=transport, **request,
        )
    remote.connector_request = through_broker
    # Demonstrate the 0.4.11 defect using the actual pre-network validator.
    with pytest.raises(broker.ApplicationConnectorError, match="identity is invalid"):
        broker.execute_connector_request(
            None, installation, connector_id="barsy_api", request_id=status(service)["command_id"],
            method="POST", path="/endpoints/json/Accounts_create", headers={},
            body=b"{}", idempotency_key="synthetic", transport=transport,
        )
    assert not sent
    tick(service)
    assert status(service)["state"] == "confirmed"
    assert status(service)["remote_account_id"] == "501"
    tick(service)
    assert len(sent) == 1
    body = json.loads(sent[0][2]["data"])
    assert sent[0][2]["headers"]["Idempotency-Key"] == body["account"]["uuid"]
