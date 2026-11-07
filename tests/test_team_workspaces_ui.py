from __future__ import annotations

from streamlit.testing.v1 import AppTest

import durable_account_store as store


ORG_ID = "00000000-0000-4000-8000-000000000001"


def _app(tmp_path):
    page = tmp_path / "team_workspaces_app_test.py"
    page.write_text(
        "from shoir_team_workspaces import render_team_workspaces\n"
        "render_team_workspaces()\n",
        encoding="utf-8",
    )
    app = AppTest.from_file(page, default_timeout=30)
    app.session_state["current_user"] = "shoir-e2e-owner"
    app.session_state["remote_session_token"] = "synthetic-session-token"
    app.session_state["authenticated"] = True
    app.session_state["user_tier"] = "Enterprise Plus Tier ($399)"
    return app


def test_team_workspace_ui_is_fail_closed_outside_staging(monkeypatch, tmp_path):
    monkeypatch.setattr(store, "APP_ENVIRONMENT", "production")

    def forbidden_call(*args, **kwargs):
        raise AssertionError("The production UI must not call staging organization APIs.")

    monkeypatch.setattr(store, "edge_organization_action", forbidden_call)
    app = _app(tmp_path)
    app.run()

    assert not app.exception, "\\n".join(str(item.value) for item in app.exception)
    assert any(
        "enabled only in the authorized staging environment" in str(item.value)
        for item in app.info
    )


def test_team_workspace_owner_can_read_all_organization_surfaces(monkeypatch, tmp_path):
    monkeypatch.setattr(store, "APP_ENVIRONMENT", "staging")
    calls = []

    def fake_action(action, username, token, **payload):
        calls.append((action, username, token, payload))
        assert username == "shoir-e2e-owner"
        assert token == "synthetic-session-token"
        if action == "org_list_session":
            return {
                "ok": True,
                "organizations": [{
                    "organization_id": ORG_ID,
                    "display_name": "Synthetic Plant",
                    "org_type": "team",
                    "role": "owner",
                }],
            }
        if action == "org_workspace_list_session":
            assert payload["organization_id"] == ORG_ID
            return {"ok": True, "role": "owner", "workspaces": [{
                "workspace_id": "00000000-0000-4000-8000-000000000002",
                "display_name": "General",
                "status": "active",
                "created_at": "2026-11-07T00:00:00Z",
            }]}
        if action == "org_member_list_session":
            return {"ok": True, "role": "owner", "members": [
                {"username_lc": "shoir-e2e-owner", "role": "owner", "status": "active"},
                {"username_lc": "shoir-e2e-engineer", "role": "engineer", "status": "active"},
            ]}
        if action == "org_invitation_list_session":
            return {"ok": True, "invitations": [
                {"invitation_id": "00000000-0000-4000-8000-000000000003",
                 "target_username_lc": "shoir-e2e-viewer", "role": "viewer",
                 "expires_at": "2026-11-14T00:00:00Z"}
            ]}
        if action == "org_audit_list_session":
            return {"ok": True, "events": [
                {"event_type": "organization.created", "actor_username_lc": "shoir-e2e-owner"}
            ]}
        raise AssertionError(f"Unexpected organization action in read-only test: {action}")

    monkeypatch.setattr(store, "edge_organization_action", fake_action)
    app = _app(tmp_path)
    app.run()

    assert not app.exception, "\\n".join(str(item.value) for item in app.exception)
    called = [item[0] for item in calls]
    assert called == [
        "org_list_session",
        "org_workspace_list_session",
        "org_member_list_session",
        "org_invitation_list_session",
        "org_audit_list_session",
    ]


def test_team_workspace_viewer_cannot_access_management_api_surfaces(monkeypatch, tmp_path):
    monkeypatch.setattr(store, "APP_ENVIRONMENT", "staging")
    calls = []

    def fake_action(action, username, token, **payload):
        calls.append(action)
        if action == "org_list_session":
            return {
                "ok": True,
                "organizations": [{
                    "organization_id": ORG_ID,
                    "display_name": "Synthetic Read Only",
                    "org_type": "team",
                    "role": "viewer",
                }],
            }
        if action == "org_workspace_list_session":
            return {"ok": True, "role": "viewer", "workspaces": []}
        if action == "org_member_list_session":
            return {"ok": True, "role": "viewer", "members": [
                {"username_lc": "shoir-e2e-viewer", "role": "viewer", "status": "active"}
            ]}
        raise AssertionError(f"Viewer UI attempted a management action: {action}")

    monkeypatch.setattr(store, "edge_organization_action", fake_action)
    app = _app(tmp_path)
    app.run()

    assert not app.exception, "\\n".join(str(item.value) for item in app.exception)
    assert calls == [
        "org_list_session",
        "org_workspace_list_session",
        "org_member_list_session",
    ]
    assert any("Invitation management is restricted" in str(item.value) for item in app.info)
    assert not any(action.startswith("org_invitation") for action in calls)
    assert "org_audit_list_session" not in calls


def test_team_workspace_ui_requires_authenticated_remote_session(monkeypatch, tmp_path):
    monkeypatch.setattr(store, "APP_ENVIRONMENT", "staging")
    calls = []
    monkeypatch.setattr(
        store,
        "edge_organization_action",
        lambda *args, **kwargs: calls.append(args) or {"ok": True, "organizations": []},
    )
    app = _app(tmp_path)
    app.session_state["authenticated"] = False
    app.run()

    assert not app.exception, "\\n".join(str(item.value) for item in app.exception)
    assert calls == []
    assert any("Sign in with an active Shoir-IE account" in str(item.value) for item in app.warning)


def test_team_owner_must_confirm_before_closing_organization(monkeypatch, tmp_path):
    monkeypatch.setattr(store, "APP_ENVIRONMENT", "staging")
    calls = []

    def fake_action(action, username, token, **payload):
        calls.append((action, payload))
        if action == "org_list_session":
            return {"ok": True, "organizations": [{
                "organization_id": ORG_ID,
                "display_name": "Synthetic Close Test",
                "org_type": "team",
                "role": "owner",
            }]}
        if action == "org_workspace_list_session":
            return {"ok": True, "role": "owner", "workspaces": []}
        if action == "org_member_list_session":
            return {"ok": True, "role": "owner", "members": [
                {"username_lc": "shoir-e2e-owner", "role": "owner", "status": "active"}
            ]}
        if action == "org_invitation_list_session":
            return {"ok": True, "invitations": []}
        if action == "org_audit_list_session":
            return {"ok": True, "events": []}
        if action == "org_close_session":
            assert payload["organization_id"] == ORG_ID
            return {"ok": True, "result": {"status": "closed"}}
        raise AssertionError(f"Unexpected action in close test: {action}")

    monkeypatch.setattr(store, "edge_organization_action", fake_action)
    app = _app(tmp_path)
    app.run()
    assert not app.exception, "\\n".join(str(item.value) for item in app.exception)

    close_button = app.button(key="team_org_close_submit")
    assert close_button.disabled
    app.checkbox(key="shoir_active_organization_confirm_close").set_value(True)
    app.run()
    assert not app.exception, "\\n".join(str(item.value) for item in app.exception)
    assert not app.button(key="team_org_close_submit").disabled

    app.button(key="team_org_close_submit").click()
    app.run()
    assert not app.exception, "\\n".join(str(item.value) for item in app.exception)
    assert any(action == "org_close_session" for action, _ in calls)



def test_owner_can_suspend_and_restore_member_with_backend_enforcement(monkeypatch, tmp_path):
    monkeypatch.setattr(store, "APP_ENVIRONMENT", "staging")
    membership_status = {"value": "active"}
    calls = []

    def fake_action(action, username, token, **payload):
        calls.append(action)
        if action == "org_list_session":
            return {"ok": True, "organizations": [{
                "organization_id": ORG_ID,
                "display_name": "Synthetic Lifecycle",
                "org_type": "team",
                "role": "owner",
            }]}
        if action == "org_workspace_list_session":
            return {"ok": True, "role": "owner", "workspaces": []}
        if action == "org_member_list_session":
            return {"ok": True, "role": "owner", "members": [
                {"username_lc": "shoir-e2e-owner", "role": "owner", "status": "active"},
                {"username_lc": "shoir-e2e-member", "role": "viewer", "status": membership_status["value"]},
            ]}
        if action == "org_invitation_list_session":
            return {"ok": True, "invitations": []}
        if action == "org_audit_list_session":
            return {"ok": True, "events": []}
        if action == "org_member_suspend_session":
            assert payload["target_username_lc"] == "shoir-e2e-member"
            membership_status["value"] = "suspended"
            return {"ok": True, "result": {"status": "suspended"}}
        if action == "org_member_restore_session":
            assert payload["target_username_lc"] == "shoir-e2e-member"
            membership_status["value"] = "active"
            return {"ok": True, "result": {"status": "active"}}
        raise AssertionError(f"Unexpected action in membership lifecycle test: {action}")

    monkeypatch.setattr(store, "edge_organization_action", fake_action)
    app = _app(tmp_path)
    app.run()
    assert not app.exception, "\\n".join(str(item.value) for item in app.exception)
    assert app.button(key="team_member_suspend_submit").disabled is False

    app.button(key="team_member_suspend_submit").click()
    app.run()
    assert not app.exception, "\\n".join(str(item.value) for item in app.exception)
    assert membership_status["value"] == "suspended"
    assert "org_member_suspend_session" in calls
    assert not app.button(key="team_member_restore_submit").disabled

    app.button(key="team_member_restore_submit").click()
    app.run()
    assert not app.exception, "\\n".join(str(item.value) for item in app.exception)
    assert membership_status["value"] == "active"
    assert "org_member_restore_session" in calls



def test_application_keeps_existing_workspace_membership_renderer_and_adds_org_ui_only_in_staging():
    from pathlib import Path

    source = (Path(__file__).resolve().parents[1] / "app.py").read_text(encoding="utf-8")
    start = source.index('elif mod == "Team Workspaces & RBAC":')
    end = source.index('elif mod in {x["name"] for x in PLATFORM_CATALOG}:', start)
    route = source[start:end]

    assert "render_industrial_module(" in route
    assert "Organization-managed teams (staging)" in route
    legacy_source = (Path(__file__).resolve().parents[1] / "industrial_platform.py").read_text(encoding="utf-8")
    legacy_start = legacy_source.index('elif module=="Team Workspaces & RBAC":')
    legacy_end = legacy_source.index('elif module=="Executive Report Center":', legacy_start)
    legacy_block = legacy_source[legacy_start:legacy_end]
    assert "Legacy local membership metadata only" in legacy_block
    assert "do not grant or revoke" in legacy_block
    assert "Organization-managed teams (staging)" in route
    assert "APP_ENVIRONMENT" in route
    assert route.count("render_industrial_module(") >= 2
    assert "from shoir_team_workspaces import render_team_workspaces" in route
    assert "else:" in route



def test_active_shared_workspace_has_confirmed_latest_revision_reload_path():
    from pathlib import Path

    source = (Path(__file__).resolve().parents[1] / "shoir_team_workspaces.py").read_text(encoding="utf-8")
    start = source.index("def _render_active_workspace_return(")
    end = source.index("def render_team_workspaces(", start)
    block = source[start:end]

    assert "Reloading discards unsaved changes" in block
    assert "team_workspace_confirm_reload" in block
    assert "team_workspace_reload_shared" in block
    assert "disabled=not confirm_reload" in block
    assert "clear_loaded_workspace_state(st.session_state)" in block
    assert 'st.session_state.pop("_workspace_save_error", None)' in block
    assert "st.rerun()" in block
