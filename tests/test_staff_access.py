"""Characterize real platform authorization with the Child Center contract.

Temporary Core DB only; the supervised service/connector is never invoked.
These tests document today's boundary, not the proposed future role system.
"""
import json

import pytest

from backend.tests.test_application_access import environment, headers
from backend.routes import application_extensions
from backend.services.application_access import ApplicationPrincipal, can_access_application_route
from three_mm_protocol.application_extension import ApplicationExtensionV1
from test_package import _builder_module, MODULE_ROOT


@pytest.mark.parametrize("operation,permission", [
    ("list_operator_clients", "registrations_manage"),
    ("assign_identifier", "children_manage"),
    ("close_visit", "visits_manage"),
    ("list_visit_history", "visits_manage"),
    ("list_checkout_accounts", "payments_manage"),
    ("get_checkout_account", "payments_manage"),
    ("pay_account", "payments_manage"),
])
def test_staff_grant_and_revocation_checked_before_service(monkeypatch, tmp_path, operation, permission):
    client, db, engine, _, user, _, _, admin_token, staff_token = environment(
        monkeypatch, tmp_path, blob=_builder_module().build_package())
    calls = []
    monkeypatch.setattr(application_extensions, "_invoke", lambda *args: calls.append(args) or {"checked": True})
    base = "/api/v1/application-extensions/org.3mm.child-center"
    path = f"{base}/operator/operations/{operation}"
    request = {"payload": {}, "idempotency_key": "synthetic-access-check"}
    try:
        assert client.post(path, json=request, headers=headers(staff_token)).status_code == 403
        assert not calls
        access = client.get(f"{base}/access", headers=headers(staff_token))
        assert access.status_code == 200 and access.headers["cache-control"] == "no-store"
        assert operation not in access.json()["allowed_operation_ids"]
        assert client.post(f"{base}/permissions/grants", json={"user_id": user.id, "permission_id": permission}, headers=headers(admin_token)).status_code == 201
        assert client.post(path, json=request, headers=headers(staff_token)).status_code == 200
        assert operation in client.get(f"{base}/access", headers=headers(staff_token)).json()["allowed_operation_ids"]
        assert calls[-1][4]["user_id"] == user.id
        assert calls[-1][4]["permission_ids"] == [permission]
        assert client.delete(f"{base}/permissions/grants/{user.id}/{permission}", headers=headers(admin_token)).status_code == 200
        # Same token, like an already open browser; the next call must be denied.
        assert client.post(path, json=request, headers=headers(staff_token)).status_code == 403
        assert len(calls) == 1
        assert operation not in client.get(f"{base}/access", headers=headers(staff_token)).json()["allowed_operation_ids"]
    finally:
        db.close()
        engine.dispose()


def test_reception_cannot_pay_or_grant_itself_access(monkeypatch, tmp_path):
    client, db, engine, _, user, _, _, admin_token, staff_token = environment(
        monkeypatch, tmp_path, blob=_builder_module().build_package())
    calls = []
    monkeypatch.setattr(application_extensions, "_invoke", lambda *args: calls.append(args) or {})
    base = "/api/v1/application-extensions/org.3mm.child-center"
    try:
        for permission in ("registrations_manage", "children_manage", "configuration_manage"):
            assert client.post(f"{base}/permissions/grants", json={"user_id": user.id, "permission_id": permission}, headers=headers(admin_token)).status_code == 201
        for path in ("operator/operations/pay_account", "operations/set_stay_article"):
            assert client.post(f"{base}/{path}", json={"payload": {}, "idempotency_key": "synthetic-denied"}, headers=headers(staff_token)).status_code == 403
        assert client.post(f"{base}/permissions/grants", json={"user_id": user.id, "permission_id": "payments_manage"}, headers=headers(staff_token)).status_code == 403
        assert client.get(f"{base}/permissions", headers=headers(staff_token)).status_code == 403
        assert not calls
    finally:
        db.close()
        engine.dispose()


def test_desk_shell_is_authenticated_but_data_and_admin_remain_separate():
    definition = ApplicationExtensionV1.model_validate(json.loads((MODULE_ROOT / "application-extension.json").read_text(encoding="utf-8")))
    routes = {r.route_id: r for r in definition.routes}
    staff = ApplicationPrincipal(kind="user", user_id=2)
    def allowed(route, grants):
        return can_access_application_route(routes[route], staff, module_id=definition.module_id, permission_ids=frozenset(grants))
    assert not allowed("operator_desk", [])
    assert allowed("operator_desk", ["registrations_manage", "children_manage"])
    assert allowed("operator_desk", ["registrations_manage", "children_manage", "visits_manage"])
    assert not allowed("administration", ["configuration_manage", "privacy_manage"])
    assert allowed("cashier_desk", ["payments_manage"])
    assert not allowed("operator_desk", ["payments_manage"])
    assert not allowed("active_visits", ["payments_manage"])
    assert not allowed("cashier_desk", ["visits_manage"])
    assert allowed("visit_history", ["visits_manage"])
    assert not allowed("visit_history", ["registrations_manage", "children_manage"])
    assert not can_access_application_route(routes["operator_desk"], ApplicationPrincipal(kind="anonymous"), module_id=definition.module_id)
