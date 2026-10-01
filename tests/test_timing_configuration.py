"""Independent timing profiles; unavailable remote timing cannot be activated."""
import pytest

from test_cc4_barsy_pool import _service, _approved_children, _load, _context
from test_stays import BillingRemote, invoke


def setup(tmp_path):
    remote = BillingRemote()
    storage, service, clock = _service(tmp_path, remote, "0014")
    return storage, service, remote


def read(service):
    return invoke(service, "get_timing_configuration", {}, "administrator")


def save(service, mode, article_id, key):
    return invoke(service, "set_timing_profile", {"mode": mode, "article_id": article_id}, "administrator", key)


def test_independent_profiles_validated_and_restart_preserves_draft(tmp_path):
    storage, service, remote = setup(tmp_path)
    assert read(service)["active_mode"] == "local_quantity"
    save(service, "local_quantity", 11, "local")
    with pytest.raises(ValueError, match="automatic time reporting"):
        save(service, "barsy_timer", 22, "wrong-timed")
    remote.interval = 60
    save(service, "barsy_timer", 22, "remote")
    assert save(service, "barsy_timer", 22, "remote") == {"status": "updated"}
    with pytest.raises(ValueError, match="Idempotency"):
        save(service, "barsy_timer", 23, "remote")
    with pytest.raises(ValueError, match="without automatic"):
        save(service, "local_quantity", 22, "wrong-local")
    config = read(service)
    assert config["local_quantity"]["article_id"] == 11
    assert config["barsy_timer"]["article_id"] == 22
    assert config["barsy_timer"]["time_interval"] == 60
    assert config["barsy_timer"]["available"] is False
    assert config["active_mode"] == "local_quantity"
    restarted = type(service)(service.application)
    assert read(restarted) == config
    assert remote.posts == []
    with storage.transaction() as connection:
        assert connection.execute("SELECT COUNT(*) FROM domain_audit_events WHERE event_type = 'timing.profile_saved'").fetchone()[0] == 2
        assert connection.execute("PRAGMA foreign_key_check").fetchall() == []


def test_remote_activation_rejected_even_with_configured_timed_article(tmp_path):
    _, service, remote = setup(tmp_path)
    remote.interval = 60
    save(service, "barsy_timer", 22, "remote")
    with pytest.raises(ValueError, match="stop API"):
        invoke(service, "activate_timing_mode", {"mode": "barsy_timer"}, "administrator", "activate")
    assert read(service)["active_mode"] == "local_quantity"
    assert remote.posts == []


def test_local_activation_and_clear_require_configuration(tmp_path):
    _, service, _ = setup(tmp_path)
    with pytest.raises(ValueError, match="Select a local"):
        invoke(service, "activate_timing_mode", {"mode": "local_quantity"}, "administrator", "empty")
    save(service, "local_quantity", 11, "local")
    assert invoke(service, "activate_timing_mode", {"mode": "local_quantity"}, "administrator", "activate") == {"status": "updated"}
    save(service, "barsy_timer", None, "clear-draft")
    assert read(service)["barsy_timer"]["article_id"] is None


def test_active_stay_locks_local_settings_but_not_inactive_draft(tmp_path):
    storage, service, remote = setup(tmp_path)
    save(service, "local_quantity", 11, "local")
    child = _approved_children(service, 1)[0]
    visit = invoke(service, "start_visit", {"child_id": child, "assignment_id": None, "occurred_at": "2026-08-30T21:00:00+00:00"}, key="entry")
    assert read(service)["can_change_active_profile"] is False
    with pytest.raises(ValueError, match="Finish open stays"):
        save(service, "local_quantity", 33, "change")
    with pytest.raises(ValueError, match="Finish open stays"):
        invoke(service, "set_stay_article", {"article_id": 33}, "administrator", "legacy-change")
    with pytest.raises(ValueError, match="Finish open stays"):
        invoke(service, "activate_timing_mode", {"mode": "local_quantity"}, "administrator", "activate")
    remote.interval = 60
    save(service, "barsy_timer", 22, "draft")
    with storage.transaction() as connection:
        assert connection.execute("SELECT inside_since FROM stay_sessions WHERE visit_id = ?", (visit["visit_id"],)).fetchone()[0] is not None
    assert read(service)["local_quantity"]["article_id"] == 11


@pytest.mark.parametrize("audience", ["kiosk", "operator", "internal"])
@pytest.mark.parametrize("operation,payload", [
    ("get_timing_configuration", {}),
    ("set_timing_profile", {"mode": "local_quantity", "article_id": 11}),
    ("activate_timing_mode", {"mode": "local_quantity"}),
])
def test_configuration_is_admin_only(tmp_path, audience, operation, payload):
    _, service, remote = setup(tmp_path)
    with pytest.raises(ValueError, match="audience"):
        invoke(service, operation, payload, audience, "denied")
    assert remote.posts == []


def test_strict_direct_requests_and_idempotency(tmp_path):
    _, service, _ = setup(tmp_path)
    with pytest.raises(ValueError, match="idempotency"):
        save(service, "local_quantity", 11, None)
    for payload in ({"mode": "other", "article_id": 11}, {"mode": "local_quantity", "article_id": True},
                    {"mode": "barsy_timer", "article_id": 22, "stop_url": "https://example.invalid"}):
        with pytest.raises(ValueError):
            service.handle("set_timing_profile", payload, _context("administrator", "invalid"))


def test_forward_upgrade_preserves_existing_stay_and_billing_settings(tmp_path):
    remote = BillingRemote()
    storage, service, _ = _service(tmp_path, remote, "0013")
    invoke(service, "set_stay_article", {"article_id": 11}, "administrator", "local")
    child = _approved_children(service, 1)[0]
    invoke(service, "start_visit", {"child_id": child, "assignment_id": None, "occurred_at": "2026-08-30T21:00:00+00:00"}, key="entry")
    with storage.transaction() as c:
        before = [tuple(r) for r in c.execute("SELECT * FROM stay_sessions")]
    migrations = _load("timing_migrations", "service/child_center_application/migrations.py").get_migrations()
    storage.migrate(migrations, "0014")
    storage.migrate(migrations, "0014")
    with storage.transaction() as c:
        assert before == [tuple(r) for r in c.execute("SELECT * FROM stay_sessions")]
        assert c.execute("SELECT COUNT(*) FROM timing_configuration").fetchone()[0] == 1
    assert read(service)["local_quantity"]["article_id"] == 11
    assert remote.posts == []
