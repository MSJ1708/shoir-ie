import workspace_persistence as wp


def test_managed_backend_never_falls_back_to_local_sqlite(monkeypatch):
    monkeypatch.setattr(wp, "durable_backend_configured", lambda: True)
    monkeypatch.setattr(wp, "load_remote_workspace", lambda username: None)

    def fail_local(*args, **kwargs):
        raise AssertionError("local SQLite fallback should not run in managed mode")

    monkeypatch.setattr(wp, "ensure_workspace_state_db", fail_local)

    restored = {}
    assert wp.load_user_workspace("Alice", restored) is False
    assert restored == {}


def test_managed_save_never_writes_local_sqlite(monkeypatch):
    monkeypatch.setattr(wp, "durable_backend_configured", lambda: True)
    monkeypatch.setattr(wp, "save_remote_workspace", lambda username, payload: True)

    def fail_local(*args, **kwargs):
        raise AssertionError("local SQLite fallback should not run in managed mode")

    monkeypatch.setattr(wp, "ensure_workspace_state_db", fail_local)

    assert wp.save_user_workspace("Alice", {"selected_nav": "Dashboard"}) is True
