"""Daily desk lifecycle; all clients and connector responses are synthetic."""
from datetime import timedelta

import pytest

from test_operator_accounts import setup, tick
from test_stays import invoke
from test_cc3_visits import _scan, DEVICE_ID


def assign(service, child, code, key, expected=None):
    return invoke(service, "assign_identifier", {
        "child_id": child, "opaque_identifier": code,
        "expected_assignment_id": expected,
    }, key=key)


def active_assignments(storage, child):
    with storage.transaction() as c:
        return c.execute("SELECT assignment_id FROM identifier_assignments WHERE child_id = ? AND retired_at IS NULL", (child,)).fetchall()


def scan(service, clock, number, code="synthetic-daily", occurred_at=None):
    service.application.configuration["READER_DEVICE_ID"] = DEVICE_ID
    return invoke(service, "process_identifier_scan", _scan(f"evt_{number:032x}", occurred_at or clock.now().isoformat(), code), "internal", f"daily-scan-{number}")


def test_finish_detaches_without_payment_and_replay_preserves_new_owner(tmp_path):
    storage, service, clock, remote, children = setup(tmp_path)
    assign(service, children[0], "synthetic-daily", "assign")
    assert invoke(service, "list_active_visits", {"cursor": None, "limit": 100})["items"] == []
    visit = scan(service, clock, 1)["visit_id"]
    tick(service)
    clock.current += timedelta(seconds=60, microseconds=1)
    assert scan(service, clock, 2)["status"] == "paused"
    assert len(active_assignments(storage, children[0])) == 1
    finished = {"visit_id": visit, "occurred_at": clock.now().isoformat()}
    result = invoke(service, "close_visit", finished, key="finish")
    assert result["duration_seconds"] == 60 and result["rounded_minutes"] == 2
    assert active_assignments(storage, children[0]) == []
    tick(service)
    account = invoke(service, "list_operator_accounts", {"offset": 0})["items"][0]
    assert account["visit_state"] == "closed" and remote.accounts[501]["status"] == 0
    with storage.transaction() as c:
        assert c.execute("SELECT state FROM visit_barsy_bindings WHERE visit_id = ?", (visit,)).fetchone()[0] == "allocated"
    history = invoke(service, "list_visit_history", {"query": "", "date_from": None, "date_to": None, "cursor": None, "limit": 100})
    assert history["items"][0]["rounded_minutes"] == 2
    old_time = clock.now().isoformat()
    clock.current += timedelta(minutes=1)
    assign(service, children[1], "synthetic-daily", "next-owner")
    assert invoke(service, "close_visit", finished, key="finish") == result
    assert len(active_assignments(storage, children[1])) == 1
    assert scan(service, clock, 3, occurred_at=old_time)["status"] == "late_event"
    assert invoke(service, "list_active_visits", {"cursor": None, "limit": 100})["items"] == []
    assert scan(service, clock, 4)["status"] == "started"
    with storage.transaction() as c:
        assert c.execute("PRAGMA foreign_key_check").fetchall() == []


def test_replace_is_atomic_and_preserves_stay(tmp_path):
    storage, service, clock, _, children = setup(tmp_path)
    assign(service, children[0], "synthetic-daily", "first")
    first_id = active_assignments(storage, children[0])[0][0]
    assign(service, children[1], "synthetic-occupied", "occupied")
    visit = scan(service, clock, 1)["visit_id"]
    tick(service)
    with pytest.raises(ValueError):
        assign(service, children[0], "synthetic-occupied", "conflict", first_id)
    assert active_assignments(storage, children[0])[0][0] == first_id
    with pytest.raises(ValueError, match="changed"):
        assign(service, children[0], "synthetic-new", "stale")
    clock.current += timedelta(seconds=30)
    replacement = assign(service, children[0], "synthetic-new", "replace", first_id)
    assert assign(service, children[0], "synthetic-new", "replace", first_id) == replacement
    assert scan(service, clock, 2)["status"] == "unknown_identifier"
    assert scan(service, clock, 3, "synthetic-new") == {"status": "paused", "visit_id": visit}
    invoke(service, "close_visit", {"visit_id": visit, "occurred_at": clock.now().isoformat()}, key="finish")
    assert active_assignments(storage, children[0]) == []
    assert len(active_assignments(storage, children[1])) == 1


def test_operator_search_status_contacts_and_permissions(tmp_path):
    storage, service, _, remote, _ = setup(tmp_path)
    query = {"query": "", "status": "approved", "cursor": None, "limit": 1}
    for search in ("Synthetic Pool Guardian", "Synthetic Pool Child 2", "+359000000009"):
        result = invoke(service, "list_operator_clients", {**query, "query": search})
        assert len(result["items"]) == 1
        assert result["items"][0]["status"] == "approved"
    assert invoke(service, "list_operator_clients", {**query, "status": "submitted"})["items"] == []
    for search in ("%", "_", "nonexistent"):
        assert invoke(service, "list_operator_clients", {**query, "query": search})["items"] == []
    for audience in ("kiosk", "internal"):
        with pytest.raises(ValueError, match="audience"):
            invoke(service, "list_operator_clients", query, audience)
    with pytest.raises(ValueError, match="audience"):
        invoke(service, "list_clients", {k: v for k, v in query.items() if k != "status"})
    assert remote.posts == []
    with storage.transaction() as c:
        c.execute("UPDATE guardians SET display_name = 'Синтетичен Родител', email = 'synthetic@example.invalid'")
    for search in ("синтетичен родител", "SYNTHETIC@EXAMPLE.INVALID"):
        assert len(invoke(service, "list_operator_clients", {**query, "query": search})["items"]) == 1


def test_frequent_client_detail_is_bounded_and_keeps_active_bracelet(tmp_path):
    storage, service, clock, _, children = setup(tmp_path)
    assigned = assign(service, children[0], "synthetic-current", "current")
    with storage.transaction() as c:
        registration = c.execute("SELECT registration_id FROM children WHERE child_id = ?", (children[0],)).fetchone()[0]
        later = (clock.now() + timedelta(seconds=1)).isoformat()
        c.executemany("INSERT INTO identifier_assignments(assignment_id, child_id, opaque_identifier, assigned_at, created_by, created_at, retired_at, retire_reason) VALUES (?, ?, ?, ?, '91', ?, ?, 'manual')", [
            (f"assign_{i:032x}", children[0], f"synthetic-old-{i}", later, later, later) for i in range(105)
        ])
    result = invoke(service, "get_registration", {"registration_id": registration})
    child = next(c for c in result["children"] if c["child_id"] == children[0])
    assert len(child["identifier_assignments"]) == 100
    assert child["identifier_assignments"][0]["assignment_id"] == assigned["assignment_id"]
