"""Synthetic-only directory, consumption permissions and remote release tests."""
import json

import pytest

from test_cc4_barsy_pool import _service, _approved_children, _context
from test_live_barsy import Remote, response, setup_live, status, tick, close


class DirectoryRemote(Remote):
    def __init__(self):
        super().__init__()
        self.parent_posts = []
        self.parent = None
        self.parent_outcome = "succeeded"
        self.existing = False
        self.foreign_parent = False
        self.articles = [{"article_id": 11, "article_name": "Synthetic drink"}]

    def connector_request(self, connector_id, **request):
        path = request["path"]
        body = json.loads(request.get("body", b"{}"))
        if path.endswith("Clients_createsmart"):
            self.parent_posts.append(body)
            self.parent = {**body["client"], "client_id": 601}
            assert set(body["client"]) == {"client_name", "tel", "email", "client_code"}
            from backend.services.application_connectors import REQUEST_ID_PATTERN
            assert REQUEST_ID_PATTERN.fullmatch(request["request_id"])
            if self.parent_outcome != "succeeded":
                return {"outcome": self.parent_outcome}
            return response(601)
        if path.endswith("Clients_getlist"):
            return response([self.parent] if self.existing and self.parent else [])
        if path.endswith("Clients_get"):
            return response({**(self.parent or {}), **({"tel": "different"} if self.foreign_parent else {})})
        if path.endswith("Articles_getlist"):
            assert request["method"] == "GET"
            assert body["filters"]["delete_flag"] == 0
            assert body["filters"]["is_for_sale"] == 1
            assert body["extra_properties"] == {"common": "min"}
            return response(self.articles)
        return super().connector_request(connector_id, **request)


def directory(tmp_path):
    remote = DirectoryRemote()
    storage, service, clock = _service(tmp_path, remote)
    child = _approved_children(service, 1)[0]
    with storage.transaction() as connection:
        parent = dict(connection.execute("SELECT * FROM guardians").fetchone())
    return storage, service, remote, parent, child


def enable(service):
    service.handle("set_barsy_delivery_mode", {"enabled": True}, _context("administrator", "live"))


def test_approval_queues_parent_but_mock_never_exports(tmp_path):
    storage, service, remote, parent, child = directory(tmp_path)
    tick(service)
    assert not remote.parent_posts
    enable(service)
    tick(service)
    tick(service)
    assert len(remote.parent_posts) == 1
    assert remote.parent_posts[0]["client"]["client_name"] == parent["display_name"]
    assert child not in json.dumps(remote.parent_posts)
    result = service.handle("list_barsy_parent_links", {"offset": 0}, _context("administrator"))
    assert result["items"][0]["remote_client_id"] == 601
    assert result["items"][0]["state"] == "confirmed"


def test_parent_sync_precedes_child_account_and_replay_does_not_duplicate(tmp_path):
    from test_cc4_barsy_pool import _save_table
    storage, service, remote, parent, child = directory(tmp_path)
    enable(service)
    _save_table(service, 101, 10, "table")
    payload = {"child_id": child, "assignment_id": None, "occurred_at": "2026-08-30T20:50:00+00:00"}
    visit = service.handle("start_visit", payload, _context("operator", "parent-visit"))
    tick(service)
    assert len(remote.parent_posts) == 1 and not remote.posts
    tick(service)
    assert len(remote.posts) == 1
    assert remote.posts[0]["account"]["client_id"] == 601
    assert remote.posts[0]["account"]["account_alias"].endswith(" | Synthetic Pool Child 1")
    assert service.handle("start_visit", payload, _context("operator", "parent-visit")) == visit
    tick(service)
    assert len(remote.parent_posts) == len(remote.posts) == 1


def test_new_operation_output_contracts_are_valid(tmp_path):
    from backend.services.application_extensions import validate_operation_payload
    from test_cc4_barsy_pool import MODULE_ROOT
    storage, service, remote, parent, child = directory(tmp_path)
    operations = {op["operation_id"]: op for op in json.loads((MODULE_ROOT / "application-extension.json").read_text(encoding="utf-8"))["operations"]}
    for name, payload, audience in [
        ("list_consumption_choices", {}, "kiosk"),
        ("discover_consumption_articles", {"query": "", "offset": 0}, "administrator"),
        ("list_barsy_parent_links", {"offset": 0}, "administrator"),
        ("set_consumption_article", {"article_id": 11, "enabled": True}, "administrator"),
        ("sync_barsy_parent", {"guardian_id": parent["guardian_id"], "client_id": None}, "administrator"),
    ]:
        operation = operations[name]
        validate_operation_payload(payload, operation["input_schema"])
        result = service.handle(name, payload, _context(audience, name))
        validate_operation_payload(result, operation["output_schema"])
        with pytest.raises(Exception):
            validate_operation_payload({**payload, "unexpected": True}, operation["input_schema"])


@pytest.mark.parametrize("outcome", ["ambiguous", "retryable", "rejected"])
def test_parent_unknown_response_never_reposts_and_marker_can_recover(tmp_path, outcome):
    storage, service, remote, parent, child = directory(tmp_path)
    enable(service)
    remote.parent_outcome = outcome
    tick(service)
    service = type(service)(service.application)
    tick(service)
    assert len(remote.parent_posts) == 1
    remote.existing = True
    tick(service)
    result = service.handle("list_barsy_parent_links", {"offset": 0}, _context("administrator"))
    assert result["items"][0]["state"] == "confirmed"
    assert len(remote.parent_posts) == 1


def test_same_name_different_contacts_cannot_be_linked(tmp_path):
    storage, service, remote, parent, child = directory(tmp_path)
    enable(service)
    remote.foreign_parent = True
    tick(service)
    result = service.handle("list_barsy_parent_links", {"offset": 0}, _context("administrator"))
    assert result["items"][0]["state"] == "manual_review"
    with pytest.raises(ValueError, match="does not match"):
        service.handle("sync_barsy_parent", {"guardian_id": parent["guardian_id"], "client_id": 601}, _context("administrator", "wrong-parent"))
    assert len(remote.parent_posts) == 1


def test_catalogue_selection_is_local_bounded_and_kiosk_safe(tmp_path):
    storage, service, remote, parent, child = directory(tmp_path)
    assert service.handle("list_consumption_choices", {}, _context("kiosk")) == {"items": []}
    result = service.handle("discover_consumption_articles", {"query": "", "offset": 0}, _context("administrator"))
    assert result == {"items": [{"article_id": 11, "label": "Synthetic drink", "enabled": False}], "has_more": False}
    payload = {"article_id": 11, "enabled": True}
    service.handle("set_consumption_article", payload, _context("administrator", "article"))
    service.handle("set_consumption_article", payload, _context("administrator", "article"))
    assert service.handle("list_consumption_choices", {}, _context("kiosk")) == {"items": [{"code": "barsy_11", "label": "Synthetic drink"}]}
    with storage.transaction() as connection:
        service._validate_consumption(connection, ["barsy_11"])
        with pytest.raises(ValueError):
            service._validate_consumption(connection, ["barsy_999"])
    service.handle("set_consumption_article", {"article_id": 11, "enabled": False}, _context("administrator", "disable-article"))
    with storage.transaction() as connection:
        with pytest.raises(ValueError):
            service._validate_consumption(connection, ["barsy_11"])
        service._validate_consumption(connection, ["legacy"], ["legacy"])
    assert not remote.posts and not remote.parent_posts


@pytest.mark.parametrize("rows", [[{}], [{"article_id": 11, "article_name": ""}], [{"article_id": 11, "article_name": "A"}] * 2])
def test_invalid_catalogue_never_changes_choices(tmp_path, rows):
    storage, service, remote, parent, child = directory(tmp_path)
    remote.articles = rows
    with pytest.raises(ValueError):
        service.handle("set_consumption_article", {"article_id": 11, "enabled": True}, _context("administrator", "invalid"))
    assert service.handle("list_consumption_choices", {}, _context("kiosk")) == {"items": []}


@pytest.mark.parametrize("operation,payload", [
    ("list_barsy_parent_links", {"offset": 0}),
    ("sync_barsy_parent", {"guardian_id": "guardian_" + "a" * 32, "client_id": None}),
    ("discover_consumption_articles", {"query": "", "offset": 0}),
    ("set_consumption_article", {"article_id": 11, "enabled": True}),
])
def test_directory_mutations_and_parent_data_are_not_available_to_kiosk(tmp_path, operation, payload):
    storage, service, remote, parent, child = directory(tmp_path)
    with pytest.raises(ValueError, match="audience"):
        service.handle(operation, payload, _context("kiosk", "denied"))


def test_ended_visit_auto_releases_only_after_matching_remote_close(tmp_path):
    storage, service, remote, scan, visit = setup_live(tmp_path)
    tick(service)
    assert "Synthetic Pool Child" in remote.alias
    close(service, visit)
    tick(service)
    assert status(service)["binding_state"] == "allocated"
    remote.closed = True
    saved_alias = remote.alias
    remote.alias = "another account"
    tick(service)
    assert status(service)["binding_state"] == "allocated"
    remote.alias = saved_alias
    tick(service)
    assert status(service)["binding_state"] == "released"
    tick(service)
    assert len(remote.posts) == 1


def test_remote_close_does_not_release_active_local_visit(tmp_path):
    storage, service, remote, scan, visit = setup_live(tmp_path)
    tick(service)
    remote.closed = True
    tick(service)
    assert status(service)["binding_state"] == "allocated"
