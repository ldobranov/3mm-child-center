"""Operator-finalized stays, exact interval arithmetic and bounded Barsy delivery."""
from datetime import datetime
from decimal import Decimal
import json

import pytest
from backend.services.application_extensions import validate_operation_payload
from test_cc4_barsy_pool import _service, _approved_children, _context, _load, MODULE_ROOT
from test_cc3_visits import _scan, DEVICE_ID
from test_live_barsy import response, setup_live


class BillingRemote:
    def __init__(self):
        self.posts = []
        self.outcome = "succeeded"
        self.precision = 3
        self.interval = None
        self.active_time_orders = '0'
        self.time_calculation = 0
        self.amount_override = None

    def connector_request(self, connector_id, **request):
        assert connector_id == "barsy_api"
        payload = json.loads(request["body"])
        path = request["path"]
        if request["method"] == "POST":
            assert path.endswith("Accounts_create")
            assert set(payload["account"]) == {"uuid", "client_id", "account_alias"}
            assert set(payload["rows"][0]) == {"article_id", "amount"}
            assert payload["account"]["client_id"] == 601
            assert request["request_id"] == "connector_" + payload["account"]["uuid"].replace("-", "")
            self.posts.append(payload)
            if self.outcome == "crash":
                raise RuntimeError("Synthetic interruption")
            return response(501) if self.outcome == "succeeded" else {"outcome": self.outcome}
        if path.endswith("Articles_getlist"):
            return response([{"article_id": payload["filters"]["article_id"], "article_name": "Synthetic hourly play", "amount_type_id": 4, "article_type": 1}])
        if path.endswith("Amounttypes_getlist"):
            return response([{"amount_type_id": 4, "time_interval": self.interval, "value_precision": self.precision}])
        if path.endswith("Poses_getcurrent"):
            return response({"pos_id": 91})
        if path.endswith("Accounts_get"):
            body = self.posts[-1]
            return response({"account_id": 501, "client_id": 601, "account_alias": body["account"]["account_alias"],
                             "time_calculation": self.time_calculation,
                             "orders": [{"article_id": body["rows"][0]["article_id"], "amount": self.amount_override or body["rows"][0]["amount"], "active_time_orders": self.active_time_orders}]})
        raise AssertionError(path)


def invoke(service, operation, payload, audience="operator", key=None):
    contract = json.loads((MODULE_ROOT / "application-extension.json").read_text(encoding="utf-8"))
    op = next(o for o in contract["operations"] if o["operation_id"] == operation)
    validate_operation_payload(payload, op["input_schema"])
    result = service.handle(operation, payload, _context(audience, key))
    validate_operation_payload(result, op["output_schema"])
    return result


def setup(tmp_path, live=True):
    remote = BillingRemote()
    storage, service, clock = _service(tmp_path, remote, "0012")
    child = _approved_children(service, 1)[0]
    service.application.configuration["READER_DEVICE_ID"] = DEVICE_ID
    invoke(service, "assign_identifier", {"child_id": child, "opaque_identifier": "synthetic-stay"}, key="assign")
    invoke(service, "set_stay_article", {"article_id": 26}, "administrator", "article")
    if live:
        invoke(service, "set_barsy_delivery_mode", {"enabled": True}, "administrator", "live")
    with storage.transaction() as c:
        c.execute("UPDATE barsy_parent_links SET state = 'confirmed', remote_client_id = 601")
    return storage, service, clock, remote, child


def scan(service, clock, number, timestamp):
    clock.current = datetime.fromisoformat(timestamp)
    return invoke(service, "process_identifier_scan", _scan(f"evt_{number:032x}", timestamp, "synthetic-stay"), "internal", f"scan-{number}")


def bills(service):
    return invoke(service, "get_stay_billing", {"offset": 0}, "administrator")["items"]


def tick(service):
    return invoke(service, "deliver_barsy_commands", {}, "internal", "tick")


def test_pause_resume_total_rounding_operator_finish_and_single_account(tmp_path):
    storage, service, clock, remote, child = setup(tmp_path)
    first = scan(service, clock, 1, "2026-08-30T21:00:00+00:00")
    assert remote.posts == []
    assert scan(service, clock, 2, "2026-08-30T21:12:20+00:00")["status"] == "paused"
    clock.current = datetime.fromisoformat("2026-08-30T21:20:00+00:00")
    active = invoke(service, "list_active_visits", {"cursor": None, "limit": 100})["items"]
    assert len(active) == 1 and active[0]["phase"] == "paused" and active[0]["elapsed_seconds"] == 740
    history_query = {"query": "", "date_from": None, "date_to": None, "cursor": None, "limit": 100}
    assert invoke(service, "list_visit_history", history_query)["items"] == []
    resumed = scan(service, clock, 3, "2026-08-30T21:30:00+00:00")
    assert resumed == {"status": "resumed", "visit_id": first["visit_id"]}
    assert scan(service, clock, 4, "2026-08-30T21:47:50+00:00")["status"] == "paused"
    assert scan(service, clock, 4, "2026-08-30T21:47:50+00:00")["status"] == "paused"
    payload = {"visit_id": first["visit_id"], "occurred_at": "2026-08-30T22:00:00+00:00"}
    closed = invoke(service, "close_visit", payload, key="finish")
    assert closed["duration_seconds"] == 1810
    assert invoke(service, "close_visit", payload, key="finish") == closed
    with pytest.raises(ValueError, match="closed"):
        invoke(service, "close_visit", payload, key="other-finish")
    assert len(invoke(service, "list_visit_history", history_query)["items"]) == 1
    assert bills(service)[0]["rounded_minutes"] == 31
    assert bills(service)[0]["quantity"] == "0.517"
    assert tick(service) == {"processed": 1}
    assert bills(service)[0]["state"] == "confirmed"
    assert Decimal(str(remote.posts[0]["rows"][0]["amount"])) == Decimal("0.517")
    assert remote.posts[0]["account"]["account_alias"].endswith(" | Synthetic Pool Child 1")
    tick(service)
    assert len(remote.posts) == 1
    with storage.transaction() as c:
        assert c.execute("SELECT COUNT(*) FROM stay_intervals").fetchone()[0] == 2
        assert c.execute("SELECT COUNT(*) FROM visit_barsy_bindings").fetchone()[0] == 0
        assert c.execute("PRAGMA foreign_key_check").fetchall() == []


@pytest.mark.parametrize("seconds,expected", [(0, 0), (0.000001, 1), (59.999999, 1), (60, 1), (60.000001, 2), (3600, 60)])
def test_finish_inside_rounds_once_including_microseconds(tmp_path, seconds, expected):
    from datetime import timedelta
    _, service, clock, remote, _ = setup(tmp_path)
    start = scan(service, clock, 1, "2026-08-30T21:00:00+00:00")
    end = (clock.current + timedelta(seconds=seconds)).isoformat()
    invoke(service, "close_visit", {"visit_id": start["visit_id"], "occurred_at": end}, key="finish")
    assert bills(service)[0]["rounded_minutes"] == expected
    tick(service)
    assert len(remote.posts) == (1 if expected else 0)


@pytest.mark.parametrize("outcome", ["ambiguous", "rejected", "crash"])
def test_uncertain_delivery_never_repeats_after_restart(tmp_path, outcome):
    storage, service, clock, remote, _ = setup(tmp_path)
    start = scan(service, clock, 1, "2026-08-30T21:00:00+00:00")
    invoke(service, "close_visit", {"visit_id": start["visit_id"], "occurred_at": "2026-08-30T21:30:00+00:00"}, key="finish")
    remote.outcome = outcome
    if outcome == "crash":
        with pytest.raises(RuntimeError):
            tick(service)
    else:
        tick(service)
    restarted = type(service)(service.application)
    for _ in range(3):
        tick(restarted)
    assert len(remote.posts) == 1
    bill = bills(restarted)[0]
    assert bill["state"] == "ambiguous"
    invoke(restarted, "reconcile_stay_bill", {"bill_id": bill["bill_id"], "account_id": 501}, "administrator", "verify")
    assert bills(restarted)[0]["state"] == "confirmed"


def test_invalid_units_access_and_configuration_snapshot(tmp_path):
    _, service, clock, remote, _ = setup(tmp_path)
    for audience in ("kiosk", "operator", "internal"):
        with pytest.raises(ValueError, match="audience"):
            invoke(service, "set_stay_article", {"article_id": 26}, audience, "denied")
    for interval, precision in [(1, 3), (60, 3), (None, 0), (None, 2)]:
        remote.interval, remote.precision = interval, precision
        with pytest.raises(ValueError):
            invoke(service, "set_stay_article", {"article_id": 27}, "administrator", "invalid")
    remote.interval, remote.precision = None, 3
    first = scan(service, clock, 1, "2026-08-30T21:00:00+00:00")
    invoke(service, "close_visit", {"visit_id": first["visit_id"], "occurred_at": "2026-08-30T21:30:00+00:00"}, key="finish")
    invoke(service, "set_stay_article", {"article_id": 27}, "administrator", "new-article")
    tick(service)
    assert remote.posts[0]["rows"][0]["article_id"] == 26


def test_mock_never_sends_and_pauses_survive_restart(tmp_path):
    storage, service, clock, remote, child = setup(tmp_path, live=False)
    first = scan(service, clock, 1, "2026-08-30T21:00:00+00:00")
    scan(service, clock, 2, "2026-08-30T21:01:00+00:00")
    service = type(service)(service.application)
    assert invoke(service, "list_active_visits", {"cursor": None, "limit": 100})["items"][0]["phase"] == "paused"
    with storage.transaction() as c:
        registration_id = c.execute("SELECT registration_id FROM children WHERE child_id = ?", (child,)).fetchone()[0]
    with pytest.raises(ValueError, match="active visit"):
        invoke(service, "delete_client", {"registration_id": registration_id, "reason": "administrator_request"}, "administrator", "delete")
    invoke(service, "close_visit", {"visit_id": first["visit_id"], "occurred_at": "2026-08-30T21:30:00+00:00"}, key="finish")
    invoke(service, "set_barsy_delivery_mode", {"enabled": True}, "administrator", "enable")
    tick(service)
    assert bills(service)[0]["state"] == "mock_confirmed" and remote.posts == []


def test_upgrade_preserves_legacy_accounts_without_rebilling(tmp_path):
    storage, legacy, remote, scan_payload, visit = setup_live(tmp_path)
    tick(legacy)
    migrations = _load("stay_upgrade_migrations", "service/child_center_application/migrations.py")
    storage.migrate(migrations.get_migrations(), "0012")
    storage.migrate(migrations.get_migrations(), "0012")
    service = type(legacy)(legacy.application)
    assert invoke(service, "list_active_visits", {"cursor": None, "limit": 100})["items"][0]["phase"] == "legacy"
    invoke(service, "close_visit", {"visit_id": visit["visit_id"], "occurred_at": "2026-08-30T21:00:00+00:00"}, key="legacy-finish")
    assert bills(service) == [] and len(remote.posts) == 1
    with storage.transaction() as c:
        assert c.execute("PRAGMA foreign_key_check").fetchall() == []


@pytest.mark.parametrize("mismatch", ["amount", "timer"])
def test_remote_quantity_or_timer_mismatch_requires_review(tmp_path, mismatch):
    _, service, clock, remote, _ = setup(tmp_path)
    start = scan(service, clock, 1, "2026-08-30T21:00:00+00:00")
    invoke(service, "close_visit", {"visit_id": start["visit_id"], "occurred_at": "2026-08-30T21:30:00+00:00"}, key="finish")
    if mismatch == "amount":
        remote.amount_override = 1
    else:
        remote.time_calculation = 1
    tick(service)
    bill = bills(service)[0]
    assert bill["state"] == "ambiguous" and bill["remote_account_id"] == 501
    with pytest.raises(ValueError, match="does not match"):
        invoke(service, "reconcile_stay_bill", {"bill_id": bill["bill_id"], "account_id": 501}, "administrator", "verify")
    tick(service)
    assert len(remote.posts) == 1


def test_late_scans_subminute_intervals_and_new_stay_after_finish(tmp_path):
    storage, service, clock, _, child = setup(tmp_path)
    start = scan(service, clock, 1, "2026-08-30T21:00:00+00:00")
    scan(service, clock, 2, "2026-08-30T21:00:00.600000+00:00")
    scan(service, clock, 3, "2026-08-30T21:01:00+00:00")
    assert scan(service, clock, 4, "2026-08-30T21:00:30+00:00")["status"] == "late_event"
    scan(service, clock, 5, "2026-08-30T21:01:59.500000+00:00")
    finish = {"visit_id": start["visit_id"], "occurred_at": "2026-08-30T21:02:00+00:00"}
    for audience in ("kiosk", "internal"):
        with pytest.raises(ValueError, match="audience"):
            invoke(service, "close_visit", finish, audience, "forbidden")
    invoke(service, "close_visit", finish, key="finish")
    # 0.6 + 59.5 seconds must NOT truncate each interval to whole seconds.
    assert bills(service)[0]["rounded_minutes"] == 2
    assert scan(service, clock, 6, "2026-08-30T21:03:00+00:00")["status"] == "unknown_identifier"
    invoke(service, "assign_identifier", {"child_id": child, "opaque_identifier": "synthetic-stay", "expected_assignment_id": None}, key="next-bracelet")
    next_stay = scan(service, clock, 7, "2026-08-30T21:04:00+00:00")
    assert next_stay["status"] == "started" and next_stay["visit_id"] != start["visit_id"]
    assert len(invoke(service, "list_active_visits", {"cursor": None, "limit": 100})["items"]) == 1


def test_live_finish_without_article_is_atomic_and_retryable(tmp_path):
    storage, service, clock, remote, _ = setup(tmp_path)
    with storage.transaction() as c:
        c.execute("UPDATE stay_billing_settings SET article_id = NULL, label = NULL, quantity_precision = NULL")
    first = scan(service, clock, 1, "2026-08-30T21:00:00+00:00")
    scan(service, clock, 2, "2026-08-30T21:01:00+00:00")
    payload = {"visit_id": first["visit_id"], "occurred_at": "2026-08-30T21:02:00+00:00"}
    with pytest.raises(ValueError, match="Select the hourly"):
        invoke(service, "close_visit", payload, key="finish")
    assert bills(service) == []
    assert invoke(service, "list_active_visits", {"cursor": None, "limit": 100})["items"][0]["phase"] == "paused"
    invoke(service, "set_stay_article", {"article_id": 26}, "administrator", "select")
    invoke(service, "close_visit", payload, key="finish")
    assert bills(service)[0]["rounded_minutes"] == 1


@pytest.mark.parametrize("row_timer", ['1', None])
def test_row_timer_metadata_is_ignored_when_account_timer_is_zero(tmp_path, row_timer):
    _, service, clock, remote, _ = setup(tmp_path)
    first = scan(service, clock, 1, "2026-08-30T21:00:00+00:00")
    invoke(service, "close_visit", {"visit_id": first["visit_id"], "occurred_at": "2026-08-30T21:30:00+00:00"}, key="finish")
    remote.active_time_orders = row_timer
    tick(service)
    bill = bills(service)[0]
    assert bill["state"] == "confirmed" and remote.time_calculation == 0
    with pytest.raises(ValueError, match="unsent"):
        invoke(service, "retry_stay_bill", {"bill_id": bill["bill_id"]}, key="unsafe-retry")
    tick(service)
    assert len(remote.posts) == 1


def test_operator_can_read_and_reprepare_only_unsent_bill(tmp_path):
    _, service, clock, remote, _ = setup(tmp_path)
    first = scan(service, clock, 1, "2026-08-30T21:00:00+00:00")
    invoke(service, "close_visit", {"visit_id": first["visit_id"], "occurred_at": "2026-08-30T21:30:00+00:00"}, key="finish")
    remote.interval = 60
    tick(service)
    result = invoke(service, "list_stay_bills", {"offset": 0})
    bill = result["items"][0]
    assert bill["state"] == "retryable" and not remote.posts
    assert bill["child_display_name"] == "Synthetic Pool Child 1"
    for audience in ("kiosk", "internal"):
        with pytest.raises(ValueError, match="audience"):
            invoke(service, "list_stay_bills", {"offset": 0}, audience)
        with pytest.raises(ValueError, match="audience"):
            invoke(service, "retry_stay_bill", {"bill_id": bill["bill_id"]}, audience, "denied")
    remote.interval = None
    invoke(service, "set_stay_article", {"article_id": 27}, "administrator", "replacement")
    payload = {"bill_id": bill["bill_id"]}
    assert invoke(service, "retry_stay_bill", payload, key="retry") == {"status": "prepared"}
    assert invoke(service, "retry_stay_bill", payload, key="retry") == {"status": "prepared"}
    tick(service)
    assert len(remote.posts) == 1 and remote.posts[0]["rows"] == [{"article_id": 27, "amount": 0.5}]
    with pytest.raises(ValueError, match="unsent"):
        invoke(service, "retry_stay_bill", payload, key="second-retry")
    with pytest.raises(ValueError, match="audience"):
        invoke(service, "reconcile_stay_bill", {**payload, "account_id": 501}, key="operator-verify")


def test_upgrade_marks_old_confirmation_for_read_only_review(tmp_path):
    storage, service, clock, remote, _ = setup(tmp_path)
    first = scan(service, clock, 1, "2026-08-30T21:00:00+00:00")
    invoke(service, "close_visit", {"visit_id": first["visit_id"], "occurred_at": "2026-08-30T21:30:00+00:00"}, key="finish")
    tick(service)
    migration = _load("stay_timer_review_migrations", "service/child_center_application/migrations.py")
    storage.migrate(migration.get_migrations(), "0013")
    bill = bills(service)[0]
    assert bill["state"] == "ambiguous" and bill["remote_account_id"] == 501
    tick(service)
    assert len(remote.posts) == 1
    invoke(service, "reconcile_stay_bill", {"bill_id": bill["bill_id"], "account_id": 501}, "administrator", "review")
    storage.migrate(migration.get_migrations(), "0013")
    assert bills(service)[0]["state"] == "confirmed"
