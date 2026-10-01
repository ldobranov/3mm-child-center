"""Cashier-only gateway and real extension workflow; simulated Barsy only."""
import pytest

from backend.tests.test_application_access import environment, headers
from backend.routes import application_extensions
from test_package import _builder_module
from test_operator_accounts import setup, start, tick, finish, invoke


def test_payment_only_staff_cannot_manage_visits_or_clients(monkeypatch, tmp_path):
    client, db, engine, _, user, _, _, admin_token, staff_token = environment(
        monkeypatch, tmp_path, blob=_builder_module().build_package())
    calls = []
    monkeypatch.setattr(application_extensions, "_invoke", lambda *args: calls.append(args) or {})
    base = "/api/v1/application-extensions/org.3mm.child-center"
    try:
        assert client.post(f"{base}/permissions/grants", json={"user_id": user.id, "permission_id": "payments_manage"}, headers=headers(admin_token)).status_code == 201
        access = client.get(f"{base}/access", headers=headers(staff_token)).json()
        assert "cashier_desk" in access["allowed_route_ids"]
        assert not {"operator_desk", "active_visits", "visit_history", "administration"}.intersection(access["allowed_route_ids"])
        expected = {"list_checkout_accounts", "get_checkout_account", "preview_account_payment", "pay_account", "verify_account_closure"}
        # Public kiosk operations may also be listed; none grants staff powers.
        assert expected.issubset(set(access["allowed_operation_ids"]))
        for operation in expected:
            assert client.post(f"{base}/operator/operations/{operation}", json={"payload": {}, "idempotency_key": "synthetic-cashier"}, headers=headers(staff_token)).status_code == 200
        count = len(calls)
        for operation in ("list_operator_accounts", "get_operator_account", "list_active_visits", "list_visit_history", "list_operator_clients", "register_client", "approve_registration", "assign_identifier", "start_visit", "close_visit", "add_account_consumption", "retry_account_command", "close_test_account", "cancel_pending_admission", "set_stay_article", "export_personal_data"):
            assert operation not in access["allowed_operation_ids"]
            assert client.post(f"{base}/operator/operations/{operation}", json={"payload": {}, "idempotency_key": "synthetic-denied"}, headers=headers(staff_token)).status_code == 403
        assert len(calls) == count
    finally:
        db.close()
        engine.dispose()


def test_checkout_reads_are_read_only_and_reuse_payment_workflow(tmp_path):
    _, service, clock, remote, children = setup(tmp_path)
    visit = start(service, clock, children[0]); tick(service)
    before = len(remote.posts)
    assert invoke(service, "list_checkout_accounts", {"offset": 0}) == invoke(service, "list_operator_accounts", {"offset": 0})
    assert invoke(service, "get_checkout_account", {"visit_id": visit}) == {"choices": [], "commands": []}
    assert len(remote.posts) == before
    with pytest.raises(ValueError, match="Finish playing"):
        invoke(service, "preview_account_payment", {"visit_id": visit}, key="early-preview")
    for audience in ("kiosk", "internal"):
        for op, payload in (("list_checkout_accounts", {"offset": 0}), ("get_checkout_account", {"visit_id": visit})):
            with pytest.raises(ValueError, match="audience"):
                invoke(service, op, payload, audience)
    finish(service, clock, visit)
    detail = invoke(service, "get_checkout_account", {"visit_id": visit})
    assert detail["choices"] == [] and detail["commands"][0]["kind"] == "time"
    q = invoke(service, "preview_account_payment", {"visit_id": visit}, key="cashier-preview")
    payload = {"quote_id": q["quote_id"], "paymethod_id": 1, "confirmed": True}
    first = invoke(service, "pay_account", payload, key="cashier-payment")
    assert invoke(service, "pay_account", payload, key="cashier-payment") == first
    tick(service)
    assert invoke(service, "list_checkout_accounts", {"offset": 0})["items"] == []
    assert sum(1 for _, body in remote.posts if body.get("flag_close_account") == 1) == 1
