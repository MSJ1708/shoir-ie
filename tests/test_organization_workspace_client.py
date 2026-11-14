from __future__ import annotations

import pytest
from types import SimpleNamespace

import durable_account_store as store


def test_organization_action_refuses_production_environment(monkeypatch):
    monkeypatch.setattr(store, "APP_ENVIRONMENT", "production")
    monkeypatch.setattr(store, "edge_backend_configured", lambda: True)
    called = []
    monkeypatch.setattr(store, "_edge_call", lambda *args, **kwargs: called.append(args))
    with pytest.raises(RuntimeError, match="SHOIR_ENVIRONMENT=staging"):
        store.edge_organization_action(
            "org_list_session",
            "synthetic-user",
            "synthetic-session-token",
        )
    assert called == []


def test_organization_action_refuses_missing_staging_backend(monkeypatch):
    monkeypatch.setattr(store, "APP_ENVIRONMENT", "staging")
    monkeypatch.setattr(store, "edge_backend_configured", lambda: False)
    with pytest.raises(RuntimeError, match="endpoint is not configured"):
        store.edge_organization_action(
            "org_list_session",
            "synthetic-user",
            "synthetic-session-token",
        )


@pytest.mark.parametrize(
    ("username", "token"),
    [("", "token"), ("synthetic-user", ""), ("", "")],
)
def test_organization_action_requires_named_actor_and_session(monkeypatch, username, token):
    monkeypatch.setattr(store, "APP_ENVIRONMENT", "staging")
    monkeypatch.setattr(store, "edge_backend_configured", lambda: True)
    with pytest.raises(PermissionError, match="authenticated organization session"):
        store.edge_organization_action("org_list_session", username, token)


def test_organization_action_uses_only_allowlisted_actions_and_preserves_session_scope(monkeypatch):
    monkeypatch.setattr(store, "APP_ENVIRONMENT", "staging")
    monkeypatch.setattr(store, "edge_backend_configured", lambda: True)
    calls = []
    monkeypatch.setattr(
        store,
        "_edge_call",
        lambda action, payload: calls.append((action, payload)) or {"ok": True},
    )

    result = store.edge_organization_action(
        "org_workspace_list_session",
        "Synthetic-User",
        "synthetic-session-token",
        organization_id="00000000-0000-4000-8000-000000000001",
    )
    assert result == {"ok": True}
    assert calls == [
        (
            "org_workspace_list_session",
            {
                "username": "Synthetic-User",
                "token": "synthetic-session-token",
                "organization_id": "00000000-0000-4000-8000-000000000001",
            },
        )
    ]

    with pytest.raises(ValueError, match="not supported"):
        store.edge_organization_action(
            "org_arbitrary_sql",
            "Synthetic-User",
            "synthetic-session-token",
        )


def test_organization_close_uses_the_allowlisted_staging_session_action(monkeypatch):
    monkeypatch.setattr(store, "APP_ENVIRONMENT", "staging")
    monkeypatch.setattr(store, "edge_backend_configured", lambda: True)
    calls = []
    monkeypatch.setattr(
        store,
        "_edge_call",
        lambda action, payload: calls.append((action, payload)) or {"ok": True},
    )
    result = store.edge_organization_action(
        "org_close_session",
        "Synthetic-Owner",
        "synthetic-session-token",
        organization_id="00000000-0000-4000-8000-000000000001",
    )
    assert result == {"ok": True}
    assert calls == [(
        "org_close_session",
        {
            "username": "Synthetic-Owner",
            "token": "synthetic-session-token",
            "organization_id": "00000000-0000-4000-8000-000000000001",
        },
    )]



@pytest.mark.parametrize(
    "action",
    ["org_member_suspend_session", "org_member_restore_session"],
)
def test_member_suspend_and_restore_use_allowlisted_staging_session_actions(
    monkeypatch, action
):
    monkeypatch.setattr(store, "APP_ENVIRONMENT", "staging")
    monkeypatch.setattr(store, "edge_backend_configured", lambda: True)
    calls = []
    monkeypatch.setattr(
        store,
        "_edge_call",
        lambda called_action, payload: calls.append((called_action, payload)) or {"ok": True},
    )

    result = store.edge_organization_action(
        action,
        "Synthetic-Owner",
        "synthetic-session-token",
        organization_id="00000000-0000-4000-8000-000000000001",
        target_username_lc="shoir-e2e-member",
    )
    assert result == {"ok": True}
    assert calls == [(
        action,
        {
            "username": "Synthetic-Owner",
            "token": "synthetic-session-token",
            "organization_id": "00000000-0000-4000-8000-000000000001",
            "target_username_lc": "shoir-e2e-member",
        },
    )]



def test_shared_workspace_save_and_load_use_org_ids_and_revision(monkeypatch):
    session = {
        "remote_session_token": "synthetic-session-token",
        "shoir_active_organization_workspace": {
            "organization_id": "00000000-0000-4000-8000-000000000001",
            "organization_workspace_id": "00000000-0000-4000-8000-000000000002",
        },
        "_workspace_org_revision": 0,
    }
    monkeypatch.setattr(store, "st", SimpleNamespace(session_state=session))
    monkeypatch.setattr(store, "APP_ENVIRONMENT", "staging")
    monkeypatch.setattr(store, "edge_backend_configured", lambda: True)
    calls = []

    def fake_edge(action, payload):
        calls.append((action, dict(payload)))
        if action == "workspace_save":
            return {"ok": True, "revision": 1, "updated_at": "2026-11-07T17:00:00Z"}
        if action == "workspace_load":
            return {
                "ok": True,
                "state_json": '{"demand":125}',
                "revision": 1,
                "updated_at": "2026-11-07T17:00:00Z",
            }
        raise AssertionError(f"Unexpected action: {action}")

    monkeypatch.setattr(store, "_edge_call", fake_edge)

    assert store.save_remote_workspace("shoir-e2e-owner", '{"demand":125}') is True
    assert session["_workspace_org_revision"] == 1
    assert store.load_remote_workspace("shoir-e2e-owner") == '{"demand":125}'
    assert calls[0][0] == "workspace_save"
    assert calls[0][1]["organization_id"].endswith("0001")
    assert calls[0][1]["organization_workspace_id"].endswith("0002")
    assert calls[0][1]["expected_revision"] == 0
    assert calls[1][0] == "workspace_load"
    assert calls[1][1]["organization_id"].endswith("0001")
    assert session["_workspace_org_revision"] == 1


def test_shared_workspace_persistence_fails_closed_outside_staging(monkeypatch):
    session = {
        "remote_session_token": "synthetic-session-token",
        "shoir_active_organization_workspace": {
            "organization_id": "00000000-0000-4000-8000-000000000001",
            "organization_workspace_id": "00000000-0000-4000-8000-000000000002",
        },
        "_workspace_org_revision": 0,
    }
    monkeypatch.setattr(store, "st", SimpleNamespace(session_state=session))
    monkeypatch.setattr(store, "APP_ENVIRONMENT", "production")
    monkeypatch.setattr(store, "edge_backend_configured", lambda: True)
    calls = []
    monkeypatch.setattr(store, "_edge_call", lambda *args, **kwargs: calls.append(args))

    with pytest.raises(RuntimeError, match="authorized staging"):
        store.save_remote_workspace("shoir-e2e-owner", "{}")
    with pytest.raises(RuntimeError, match="authorized staging"):
        store.load_remote_workspace("shoir-e2e-owner")
    assert calls == []


def test_shared_workspace_persistence_refuses_missing_session_token(monkeypatch):
    session = {
        "shoir_active_organization_workspace": {
            "organization_id": "00000000-0000-4000-8000-000000000001",
            "organization_workspace_id": "00000000-0000-4000-8000-000000000002",
        },
    }
    monkeypatch.setattr(store, "st", SimpleNamespace(session_state=session))
    monkeypatch.setattr(store, "APP_ENVIRONMENT", "staging")
    monkeypatch.setattr(store, "edge_backend_configured", lambda: True)
    calls = []
    monkeypatch.setattr(store, "_edge_call", lambda *args, **kwargs: calls.append(args))

    assert store.save_remote_workspace("shoir-e2e-owner", "{}") is False
    assert store.load_remote_workspace("shoir-e2e-owner") is None
    assert calls == []



def test_active_shared_workspace_revalidates_session_and_role_every_call(monkeypatch):
    session = {
        "remote_session_token": "synthetic-session-token",
        "shoir_active_organization_workspace": {
            "organization_id": "00000000-0000-4000-8000-000000000001",
            "organization_workspace_id": "00000000-0000-4000-8000-000000000002",
        },
    }
    monkeypatch.setattr(store, "st", SimpleNamespace(session_state=session))
    monkeypatch.setattr(store, "APP_ENVIRONMENT", "staging")
    monkeypatch.setattr(store, "edge_backend_configured", lambda: True)
    calls = []
    monkeypatch.setattr(
        store,
        "_edge_call",
        lambda action, payload: calls.append((action, dict(payload))) or {"ok": True},
    )

    assert store.validate_remote_organization_workspace_access("shoir-e2e-member") is True
    assert calls == [(
        "workspace_access_check",
        {
            "username": "shoir-e2e-member",
            "token": "synthetic-session-token",
            "organization_id": "00000000-0000-4000-8000-000000000001",
            "organization_workspace_id": "00000000-0000-4000-8000-000000000002",
        },
    )]


def test_active_shared_workspace_access_check_fails_closed_when_membership_is_denied(monkeypatch):
    session = {
        "remote_session_token": "synthetic-session-token",
        "shoir_active_organization_workspace": {
            "organization_id": "00000000-0000-4000-8000-000000000001",
            "organization_workspace_id": "00000000-0000-4000-8000-000000000002",
        },
    }
    monkeypatch.setattr(store, "st", SimpleNamespace(session_state=session))
    monkeypatch.setattr(store, "APP_ENVIRONMENT", "staging")
    monkeypatch.setattr(store, "edge_backend_configured", lambda: True)
    calls = []
    monkeypatch.setattr(
        store,
        "_edge_call",
        lambda action, payload: calls.append(action) or {"ok": False},
    )

    with pytest.raises(PermissionError, match="could not be verified"):
        store.validate_remote_organization_workspace_access("shoir-e2e-member")
    assert calls == ["workspace_access_check"]


def test_shared_workspace_access_check_requires_explicit_staging_and_session(monkeypatch):
    session = {
        "remote_session_token": "synthetic-session-token",
        "shoir_active_organization_workspace": {
            "organization_id": "00000000-0000-4000-8000-000000000001",
            "organization_workspace_id": "00000000-0000-4000-8000-000000000002",
        },
    }
    monkeypatch.setattr(store, "st", SimpleNamespace(session_state=session))
    monkeypatch.setattr(store, "APP_ENVIRONMENT", "production")
    monkeypatch.setattr(store, "edge_backend_configured", lambda: True)
    calls = []
    monkeypatch.setattr(store, "_edge_call", lambda *args, **kwargs: calls.append(args))

    with pytest.raises(RuntimeError, match="outside the configured staging"):
        store.validate_remote_organization_workspace_access("shoir-e2e-member")
    assert calls == []
