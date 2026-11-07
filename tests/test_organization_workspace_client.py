from __future__ import annotations

import pytest

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
