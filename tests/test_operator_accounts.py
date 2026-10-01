"""Synthetic Barsy only: never calls a real POS or fiscal device."""
import copy
import json
from datetime import timedelta
from decimal import Decimal

import pytest

from test_cc4_barsy_pool import _service, _approved_children, _save_table, _context
from test_stays import invoke
from test_live_barsy import response


class Remote:
    def __init__(self):
        self.accounts = {}
        self.posts = []
        self.busy_places = set()
        self.outcome = "succeeded"
        self.timed = False

    def connector_request(self, connector_id, **request):
        data = json.loads(request["body"])
        method = request["path"].rsplit("/", 1)[1]
        if request["method"] == "POST":
            self.posts.append((method, copy.deepcopy(data)))
            if method == "Accounts_create":
                identity = 501 + len(self.accounts)
                self.accounts[identity] = {**data["account"], "account_id": identity, "status": 0, "orders": [],
                    "time_calculation": "0", "currency_id": 1, "currency_rate": 1, "total_remain": 0, "total_real": 0, "total_paid": 0, "fx": None}
            elif method == "Accounts_place":
                identity = data["account_id"]
                account = self.accounts[identity]
                assert account["status"] == 0
                for row in data["orders"]:
                    assert set(row) == {"article_id", "amount"}
                    account["orders"].append({**row, "active_time_orders": "1" if self.timed else "0"})
                account["total_real"] = float(sum((Decimal(str(r["amount"])) * 60 for r in account["orders"]), Decimal(0)))
                account["total_remain"] = account["total_real"] - account["total_paid"]
                if data["flag_close_account"]:
                    assert len(data["payments"]) == 1
                    account.update(status=1, total_paid=account["total_real"], total_remain=0, fx=1)
            else:
                raise AssertionError(method)
            if self.outcome == "crash":
                raise RuntimeError("Synthetic crash after accepted POST")
            return response(identity) if self.outcome == "succeeded" else {"outcome": self.outcome}
        if method == "Poses_getcurrent":
            return response({"pos_id": 91})
        if method == "Places_getlist":
            return response([{"place_id": p, "place_type": 101} for p in (6, 7)])
        if method == "Accounts_getlist":
            place = data["filters"]["place_id"]
            return response([{"account_id": 900}] if place in self.busy_places else [a for a in self.accounts.values() if a["place_id"] == place and a["status"] == 0])
        if method == "Accounts_get":
            return response(copy.deepcopy(self.accounts[data["account_id"]]))
        if method == "Articles_getlist":
            return response([{"article_id": data["filters"]["article_id"], "article_name": "Synthetic article", "amount_type_id": 4, "article_type": 1}])
        if method == "Amounttypes_getlist":
            return response([{"amount_type_id": 4, "time_interval": None, "value_precision": 3}])
        if method == "Paymentmethods_getlist":
            return response([{"paymethod_id": 1, "name": "Synthetic cash", "type_id": 1, "fx": 1, "provider_id": None, "require_info": None, "currencies": None},
                             {"paymethod_id": 2, "name": "Synthetic card", "type_id": 5, "fx": 1, "provider_id": None, "require_info": None, "currencies": None}])
        if method == "Currencies_getlist":
            return response([{"currency_id": 1, "currency_code": "EUR"}])
        raise AssertionError(method)


def setup(tmp_path):
    remote = Remote()
    storage, service, clock = _service(tmp_path, remote, "0015")
    children = _approved_children(service, 2)
    invoke(service, "set_stay_article", {"article_id": 26}, "administrator", "article")
    _save_table(service, 6, 0, "table6")
    _save_table(service, 7, 1, "table7")
    invoke(service, "set_barsy_delivery_mode", {"enabled": True}, "administrator", "live")
    with storage.transaction() as c:
        c.execute("UPDATE barsy_parent_links SET state = 'confirmed', remote_client_id = 601")
        c.execute("INSERT INTO barsy_consumption_choices VALUES (11, 'Synthetic drink', 1, ?)", (service._now(),))
        c.execute("INSERT INTO barsy_consumption_choices VALUES (12, 'Synthetic restricted drink', 1, ?)", (service._now(),))
        c.execute("UPDATE children SET allowed_consumption_codes_json = '[\"barsy_11\"]'")
    return storage, service, clock, remote, children


def tick(service, count=12):
    for i in range(count):
        service.handle("deliver_barsy_commands", {}, _context("internal", f"tick-{i}"))


def start(service, clock, child):
    return invoke(service, "start_visit", {"child_id": child, "assignment_id": None, "occurred_at": clock.now().isoformat()}, key="entry-" + child)["visit_id"]


def finish(service, clock, visit):
    clock.current += timedelta(seconds=61)
    invoke(service, "close_visit", {"visit_id": visit, "occurred_at": clock.now().isoformat()}, key="finish-" + visit)
    tick(service)


def test_first_entry_capacity_pause_consumption_finish_and_payment(tmp_path):
    storage, service, clock, remote, children = setup(tmp_path)
    remote.busy_places.add(6)
    visit = start(service, clock, children[0])
    active = invoke(service, "list_active_visits", {"cursor": None, "limit": 100})["items"][0]
    assert active["phase"] == "pending" and active["elapsed_seconds"] == 0
    assert active["barsy_table"]["barsy_place_id"] == 7
    with pytest.raises(ValueError, match="free in Barsy"):
        start(service, clock, children[1])
    tick(service)
    assert len(remote.posts) == 1 and remote.posts[0][0] == "Accounts_create"
    assert remote.posts[0][1]["account"]["client_id"] == 601
    assert remote.posts[0][1]["rows"] == []
    assert invoke(service, "list_active_visits", {"cursor": None, "limit": 100})["items"][0]["phase"] == "inside"
    detail = invoke(service, "get_operator_account", {"visit_id": visit})
    assert {r["article_id"]: r["allowed_for_child"] for r in detail["choices"]} == {11: True, 12: False}
    with pytest.raises(ValueError, match="not allowed"):
        invoke(service, "add_account_consumption", {"visit_id": visit, "article_id": 12, "quantity": "1", "consumer": "child"}, key="forbidden")
    payload = {"visit_id": visit, "article_id": 11, "quantity": "1", "consumer": "child"}
    queued = invoke(service, "add_account_consumption", payload, key="drink")
    assert invoke(service, "add_account_consumption", payload, key="drink") == queued
    tick(service)
    assert remote.posts[-1][0] == "Accounts_place" and remote.posts[-1][1]["account_id"] == 501
    finish(service, clock, visit)
    assert len(remote.accounts) == 1
    assert remote.posts[-1][1]["orders"] == [{"article_id": 26, "amount": 0.033}]
    assert invoke(service, "list_operator_accounts", {"offset": 0})["items"][0]["visit_state"] == "closed"
    q = invoke(service, "preview_account_payment", {"visit_id": visit}, key="quote")
    pay = {"quote_id": q["quote_id"], "paymethod_id": 1, "confirmed": True}
    result = invoke(service, "pay_account", pay, key="pay")
    assert invoke(service, "pay_account", pay, key="pay") == result
    tick(service)
    assert invoke(service, "list_operator_accounts", {"offset": 0})["items"] == []
    assert remote.posts[-1][1]["flag_close_account"] == 1
    assert remote.posts[-1][1]["payments"][0]["original_paid_sum"] == float(q["amount"])
    assert len(remote.posts) == 4
    with storage.transaction() as c:
        assert c.execute("PRAGMA foreign_key_check").fetchall() == []


@pytest.mark.parametrize("kind", ["consumption", "payment"])
def test_lost_reply_never_replays_or_releases_table(tmp_path, kind):
    storage, service, clock, remote, children = setup(tmp_path)
    visit = start(service, clock, children[0]); tick(service)
    if kind == "payment":
        finish(service, clock, visit)
        q = invoke(service, "preview_account_payment", {"visit_id": visit}, key="q")
        invoke(service, "pay_account", {"quote_id": q["quote_id"], "paymethod_id": 1, "confirmed": True}, key="p")
    else:
        invoke(service, "add_account_consumption", {"visit_id": visit, "article_id": 11, "quantity": "1", "consumer": "child"}, key="d")
    remote.outcome = "timeout"
    tick(service)
    count = len(remote.posts)
    restarted = type(service)(service.application)
    tick(restarted, 20)
    assert len(remote.posts) == count
    assert invoke(restarted, "list_operator_accounts", {"offset": 0})["items"][0]["pending"] is True
    cmd = invoke(restarted, "get_operator_account", {"visit_id": visit})["commands"][0]
    assert cmd["state"] == "ambiguous"
    with pytest.raises(ValueError, match="definitely unsent"):
        invoke(restarted, "retry_account_command", {"command_id": cmd["command_id"]}, key="retry")


def test_payment_quote_expires_and_changed_total_is_never_charged(tmp_path):
    _, service, clock, remote, children = setup(tmp_path)
    visit = start(service, clock, children[0]); tick(service); finish(service, clock, visit)
    q = invoke(service, "preview_account_payment", {"visit_id": visit}, key="q")
    clock.current += timedelta(minutes=3)
    with pytest.raises(ValueError, match="expired"):
        invoke(service, "pay_account", {"quote_id": q["quote_id"], "paymethod_id": 1, "confirmed": True}, key="p")
    q = invoke(service, "preview_account_payment", {"visit_id": visit}, key="q2")
    invoke(service, "pay_account", {"quote_id": q["quote_id"], "paymethod_id": 1, "confirmed": True}, key="p2")
    before = len(remote.posts)
    remote.accounts[501]["total_real"] += 1
    tick(service)
    assert len(remote.posts) == before
    assert invoke(service, "get_operator_account", {"visit_id": visit})["commands"][0]["state"] == "failed"


@pytest.mark.parametrize("audience", ["kiosk", "internal"])
def test_operator_commerce_denies_other_audiences(tmp_path, audience):
    _, service, _, remote, _ = setup(tmp_path)
    for operation, payload in [("list_operator_accounts", {"offset": 0}), ("get_operator_account", {"visit_id": "visit_" + "a" * 32}),
        ("preview_account_payment", {"visit_id": "visit_" + "a" * 32}), ("pay_account", {"quote_id": "quote_" + "a" * 32, "paymethod_id": 1, "confirmed": True})]:
        with pytest.raises(ValueError, match="audience"):
            invoke(service, operation, payload, audience, "denied-" + operation)
    assert remote.posts == []


def test_pause_and_reentry_keep_one_account_and_round_total_once(tmp_path):
    from test_cc3_visits import _scan, DEVICE_ID
    _, service, clock, remote, children = setup(tmp_path)
    service.application.configuration["READER_DEVICE_ID"] = DEVICE_ID
    invoke(service, "assign_identifier", {"child_id": children[0], "opaque_identifier": "synthetic-stay"}, key="assign")
    def scan(number):
        return invoke(service, "process_identifier_scan", _scan(f"evt_{number:032x}", clock.now().isoformat(), "synthetic-stay"), "internal", f"scan-{number}")
    visit = scan(1)["visit_id"]
    tick(service)
    clock.current += timedelta(seconds=20)
    assert scan(2)["status"] == "paused"
    clock.current += timedelta(minutes=10)
    assert scan(3) == {"status": "resumed", "visit_id": visit}
    assert len(remote.posts) == 1
    clock.current += timedelta(seconds=20)
    assert scan(4)["status"] == "paused"
    assert scan(4)["status"] == "paused"
    invoke(service, "close_visit", {"visit_id": visit, "occurred_at": clock.now().isoformat()}, key="finish")
    tick(service)
    assert len(remote.accounts) == 1
    assert remote.posts[-1][1]["orders"] == [{"article_id": 26, "amount": 0.017}]
    assert invoke(service, "list_operator_accounts", {"offset": 0})["items"][0]["visit_state"] == "closed"


def test_crash_after_payment_and_manual_verification_do_not_repeat_post(tmp_path):
    _, service, clock, remote, children = setup(tmp_path)
    visit = start(service, clock, children[0]); tick(service); finish(service, clock, visit)
    q = invoke(service, "preview_account_payment", {"visit_id": visit}, key="q")
    invoke(service, "pay_account", {"quote_id": q["quote_id"], "paymethod_id": 1, "confirmed": True}, key="p")
    remote.outcome = "crash"
    with pytest.raises(RuntimeError, match="Synthetic crash"):
        tick(service)
    count = len(remote.posts)
    restarted = type(service)(service.application)
    tick(restarted, 20)
    assert len(remote.posts) == count
    assert invoke(restarted, "verify_account_closure", {"visit_id": visit, "reviewed": True}, key="verify") == {"status": "released"}
    tick(restarted)
    assert len(remote.posts) == count
    assert invoke(restarted, "list_operator_accounts", {"offset": 0})["items"] == []


def test_cancel_unsent_admission_but_never_an_unknown_opening(tmp_path):
    storage, service, clock, remote, children = setup(tmp_path)
    visit = start(service, clock, children[0])
    invoke(service, "cancel_pending_admission", {"visit_id": visit}, key="cancel")
    tick(service)
    assert remote.posts == []
    with storage.transaction() as c:
        assert c.execute("SELECT state FROM visits WHERE visit_id = ?", (visit,)).fetchone()[0] == "void"
    other = start(service, clock, children[1])
    remote.outcome = "timeout"
    tick(service)
    with pytest.raises(ValueError, match="definitely unsent"):
        invoke(service, "cancel_pending_admission", {"visit_id": other}, key="unsafe-cancel")
    tick(service)
    assert len(remote.posts) == 1


def test_upgrade_preserves_historical_stays_without_rebilling(tmp_path):
    from test_migration import _migrations_module
    storage, old, clock = _service(tmp_path, Remote(), "0014")
    child = _approved_children(old, 1)[0]
    visit = start(old, clock, child)
    with storage.transaction() as c:
        original = dict(c.execute("SELECT * FROM stay_sessions WHERE visit_id = ?", (visit,)).fetchone())
    storage.migrate(_migrations_module().get_migrations(), "0015")
    storage.migrate(_migrations_module().get_migrations(), "0015")
    with storage.transaction() as c:
        assert dict(c.execute("SELECT * FROM stay_sessions WHERE visit_id = ?", (visit,)).fetchone()) == original
        assert c.execute("SELECT COUNT(*) FROM stay_accounts").fetchone()[0] == 0
        assert c.execute("SELECT COUNT(*) FROM account_commands").fetchone()[0] == 0
        assert c.execute("PRAGMA foreign_key_check").fetchall() == []
