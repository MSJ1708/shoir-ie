"""Staging-gated organisation and team workspace UI.

The module delegates all authorization to the session-authenticated persistence
Edge Function. It never connects to Supabase with a browser/service credential.
"""
from __future__ import annotations

from typing import Any

import pandas as pd
import streamlit as st

import durable_account_store as account_store


_ROLE_LABELS = {
    "owner": "Owner",
    "admin": "Admin",
    "engineer": "Engineer",
    "approver": "Approver",
    "viewer": "Viewer",
}
_MEMBER_ROLES = ("admin", "engineer", "approver", "viewer")
_STATE_PREFIX = "shoir_active_organization_"


def _actor() -> tuple[str, str]:
    username = str(st.session_state.get("current_user") or "").strip()
    token = str(st.session_state.get("remote_session_token") or "").strip()
    authenticated = bool(st.session_state.get("authenticated"))
    if not authenticated or not username or username.casefold() in {
        "guest",
        "guest visitor",
        "anonymous",
    } or not token:
        raise PermissionError("Sign in with an active Shoir-IE account to use team workspaces.")
    return username, token


def _call(action: str, username: str, token: str, **payload: Any) -> dict[str, Any]:
    result = account_store.edge_organization_action(
        action,
        username,
        token,
        **payload,
    )
    if not isinstance(result, dict):
        raise RuntimeError("The organization service returned an invalid response.")
    if result.get("ok") is False or result.get("error"):
        raise RuntimeError(str(result.get("error") or "The organization request was rejected."))
    return result


def _error(message: str, exc: Exception) -> None:
    # Keep provider/SQL details out of the customer UI while preserving an
    # actionable, non-secret diagnostic identifier for support.
    st.error(message)
    st.caption(f"Request type: {type(exc).__name__}. No client-side permission was granted.")


def _refresh_organizations(username: str, token: str) -> list[dict[str, Any]]:
    response = _call("org_list_session", username, token)
    organizations = response.get("organizations", [])
    if not isinstance(organizations, list):
        raise RuntimeError("The organization service returned an invalid organization list.")
    valid = [item for item in organizations if isinstance(item, dict) and item.get("organization_id")]
    st.session_state[_STATE_PREFIX + "organizations"] = valid
    st.session_state[_STATE_PREFIX + "loaded_for"] = username.casefold()
    return valid


def _clear_organization_cache() -> None:
    for key in (
        _STATE_PREFIX + "organizations",
        _STATE_PREFIX + "loaded_for",
        _STATE_PREFIX + "selected_id",
        _STATE_PREFIX + "workspaces",
        _STATE_PREFIX + "members",
        _STATE_PREFIX + "invitations",
        _STATE_PREFIX + "audit",
        _STATE_PREFIX + "invite_once",
        _STATE_PREFIX + "accept_token",
        _STATE_PREFIX + "confirm_close",
    ):
        st.session_state.pop(key, None)


def _clear_active_organization_workspace() -> None:
    # Clear team values before dropping the scope marker; otherwise the
    # personal-workspace loader could mistake stale team state for personal state.
    try:
        from workspace_persistence import clear_loaded_workspace_state
        clear_loaded_workspace_state(st.session_state)
    except Exception:
        # Clear only the known persisted key list as a fail-closed fallback.
        prior_keys = st.session_state.get("_workspace_loaded_keys", [])
        if isinstance(prior_keys, list):
            for key in prior_keys:
                if isinstance(key, str):
                    st.session_state.pop(key, None)
        st.session_state.pop("_shoir_persist_change_signature", None)
        st.session_state.pop("_workspace_org_revision", None)
        st.session_state.pop("_workspace_org_updated_at", None)
        st.session_state["_workspace_loaded_for_user"] = None
    st.session_state.pop(_STATE_PREFIX + "workspace", None)
    st.session_state.pop("_workspace_loaded_scope", None)


def _render_active_workspace_return(username: str) -> None:
    context = st.session_state.get(_STATE_PREFIX + "workspace")
    if not isinstance(context, dict):
        return
    st.info(
        "The application is currently using the shared organization workspace "
        f"'{context.get('display_name') or context.get('organization_workspace_id')}'."
    )
    with st.expander("Reload the latest shared revision", expanded=False):
        st.warning(
            "Reloading discards unsaved changes in this browser session and restores "
            "the latest saved shared workspace revision."
        )
        confirm_reload = st.checkbox(
            "I understand that unsaved shared changes will be discarded.",
            key="team_workspace_confirm_reload",
        )
        if st.button(
            "Reload from shared workspace",
            disabled=not confirm_reload,
            key="team_workspace_reload_shared",
            use_container_width=True,
        ):
            try:
                from workspace_persistence import clear_loaded_workspace_state
                clear_loaded_workspace_state(st.session_state)
                st.session_state.pop("_workspace_save_error", None)
                st.session_state.pop("_workspace_load_error", None)
                st.rerun()
            except Exception as exc:
                _error("The shared workspace could not be reloaded safely.", exc)

    save_col, discard_col = st.columns(2)
    with save_col:
        if st.button(
            "Save and return to personal workspace",
            key="team_workspace_return_personal",
            use_container_width=True,
        ):
            try:
                from workspace_persistence import save_user_workspace
                if not save_user_workspace(username, st.session_state):
                    st.error(
                        "The current shared workspace could not be confirmed as saved. "
                        "Your active workspace has not been switched."
                    )
                else:
                    _clear_active_organization_workspace()
                    st.rerun()
            except Exception as exc:
                _error("Could not save the active shared workspace.", exc)
    with discard_col:
        if st.button(
            "Disconnect without saving shared changes",
            key="team_workspace_disconnect_personal",
            use_container_width=True,
        ):
            _clear_active_organization_workspace()
            st.rerun()


def render_team_workspaces() -> None:
    """Render team collaboration inside the existing application module."""
    st.title("Team Workspaces & RBAC")
    st.caption(
        "Organization membership, invitation and workspace operations use the "
        "server-validated Shoir-IE session. Backend permissions apply to every action."
    )

    # The organization migration and Edge actions currently exist in staging
    # only. Do not even attempt an API call from production or local development.
    if str(account_store.APP_ENVIRONMENT).casefold() != "staging":
        st.info(
            "Team collaboration is currently enabled only in the authorized staging "
            "environment. Production remains on the previous personal-workspace model."
        )
        return

    username = str(st.session_state.get("current_user") or "").strip()
    try:
        username, token = _actor()
    except PermissionError as exc:
        st.warning(str(exc))
        return

    tier = str(st.session_state.get("user_tier") or "Starter")
    if "enterprise" not in tier.casefold():
        st.warning("Team organizations require an active Enterprise subscription.")
        return

    _render_active_workspace_return(username)

    state_key = _STATE_PREFIX + "organizations"
    loaded_key = _STATE_PREFIX + "loaded_for"
    organizations = st.session_state.get(state_key)
    if not isinstance(organizations, list) or st.session_state.get(loaded_key) != username.casefold():
        try:
            organizations = _refresh_organizations(username, token)
        except Exception as exc:
            _error("Shoir-IE could not load your organization memberships.", exc)
            return

    left, right = st.columns([1, 1])
    with left:
        if st.button("Refresh organizations", key="team_org_refresh", use_container_width=True):
            try:
                _refresh_organizations(username, token)
                st.rerun()
            except Exception as exc:
                _error("Organization refresh failed.", exc)
    with right:
        st.metric("Active organization memberships", len(organizations))

    create_tab, join_tab = st.tabs(["Organizations", "Join an organization"])
    with create_tab:
        with st.form("team_org_create_form", clear_on_submit=True):
            new_name = st.text_input(
                "New team organization name",
                max_chars=120,
                key="team_org_create_name",
            )
            create_org = st.form_submit_button(
                "Create organization",
                type="primary",
                use_container_width=True,
                key="team_org_create_submit",
            )
        if create_org:
            try:
                response = _call(
                    "org_create_session",
                    username,
                    token,
                    display_name=new_name,
                )
                organization = response.get("organization") or {}
                st.success(
                    f"Organization created: {organization.get('display_name') or new_name}. "
                    "You are its owner and a General workspace was created."
                )
                _clear_organization_cache()
                st.rerun()
            except Exception as exc:
                _error("Organization creation was not completed.", exc)

    with join_tab:
        st.caption(
            "Enter the one-time invitation token supplied by your organization owner or admin. "
            "The token is checked against your signed-in account by the server."
        )
        with st.form("team_org_accept_invitation_form", clear_on_submit=True):
            invitation_token = st.text_input(
                "Invitation token",
                type="password",
                max_chars=64,
                key=_STATE_PREFIX + "accept_token",
            )
            accept_invitation = st.form_submit_button(
                "Accept invitation",
                type="primary",
                use_container_width=True,
                key="team_org_accept_submit",
            )
        if accept_invitation:
            try:
                _call(
                    "org_invitation_accept_session",
                    username,
                    token,
                    invitation_token=invitation_token,
                )
                st.success("Invitation accepted. Your organization membership is now active.")
                _clear_organization_cache()
                st.rerun()
            except Exception as exc:
                _error("Invitation could not be accepted.", exc)

    if not organizations:
        st.info("You do not belong to an active team organization yet. Create one or accept an invitation.")
        return

    by_id = {
        str(item["organization_id"]): item
        for item in organizations
        if isinstance(item, dict) and item.get("organization_id")
    }
    ids = list(by_id)
    selected_key = _STATE_PREFIX + "selected_id"
    if st.session_state.get(selected_key) not in ids:
        st.session_state[selected_key] = ids[0]
    organization_id = st.selectbox(
        "Active organization",
        options=ids,
        format_func=lambda value: (
            f"{by_id[value].get('display_name', 'Organization')} · "
            f"{_ROLE_LABELS.get(str(by_id[value].get('role', '')).lower(), 'Member')}"
        ),
        key=selected_key,
    )
    organization = by_id[organization_id]
    role = str(organization.get("role") or "").casefold()
    can_manage = role in {"owner", "admin"}
    is_owner = role == "owner"
    st.caption(
        f"Organization type: {organization.get('org_type', 'team')} · "
        f"Your role: {_ROLE_LABELS.get(role, 'Member')}"
    )

    workspace_tab, member_tab, invitation_tab, audit_tab = st.tabs(
        ["Workspaces", "Members", "Invitations", "Audit history"]
    )

    with workspace_tab:
        try:
            workspace_response = _call(
                "org_workspace_list_session",
                username,
                token,
                organization_id=organization_id,
            )
            workspaces = workspace_response.get("workspaces", [])
            if not isinstance(workspaces, list):
                raise RuntimeError("The organization service returned an invalid workspace list.")
            st.session_state[_STATE_PREFIX + "workspaces"] = workspaces
            st.dataframe(
                pd.DataFrame([
                    {
                        "Workspace": item.get("display_name", ""),
                        "Status": item.get("status", ""),
                        "Created": item.get("created_at", ""),
                    }
                    for item in workspaces if isinstance(item, dict)
                ]),
                use_container_width=True,
                hide_index=True,
            )

            openable_workspaces = [
                item for item in workspaces
                if isinstance(item, dict)
                and item.get("workspace_id")
                and item.get("status") == "active"
            ]
            if openable_workspaces:
                with st.form("team_workspace_open_form"):
                    workspace_to_open = st.selectbox(
                        "Shared workspace to activate in the Shoir-IE workbook",
                        options=[str(item["workspace_id"]) for item in openable_workspaces],
                        format_func=lambda value: next(
                            str(item.get("display_name") or value)
                            for item in openable_workspaces
                            if str(item["workspace_id"]) == value
                        ),
                        key="team_workspace_open_id",
                    )
                    open_workspace = st.form_submit_button(
                        "Open as active workspace",
                        type="primary",
                        key="team_workspace_open_submit",
                    )
                if open_workspace:
                    try:
                        from workspace_persistence import save_user_workspace
                        if not save_user_workspace(username, st.session_state):
                            st.error(
                                "The current workspace was not confirmed as saved. "
                                "The active workspace has not been changed."
                            )
                        else:
                            selected_workspace = next(
                                item for item in openable_workspaces
                                if str(item["workspace_id"]) == workspace_to_open
                            )
                            st.session_state[_STATE_PREFIX + "workspace"] = {
                                "organization_id": organization_id,
                                "organization_workspace_id": workspace_to_open,
                                "display_name": str(selected_workspace.get("display_name") or "Shared workspace"),
                            }
                            st.session_state.pop("_shoir_persist_change_signature", None)
                            st.session_state.pop("_workspace_loaded_scope", None)
                            st.rerun()
                    except Exception as exc:
                        _error("The active workspace could not be switched safely.", exc)
        except Exception as exc:
            workspaces = []
            _error("Workspace list could not be loaded.", exc)

        if can_manage:
            with st.form("team_workspace_create_form", clear_on_submit=True):
                workspace_name = st.text_input(
                    "New workspace name",
                    max_chars=120,
                    key="team_workspace_create_name",
                )
                create_workspace = st.form_submit_button("Create workspace", key="team_workspace_create_submit")
            if create_workspace:
                try:
                    _call(
                        "org_workspace_create_session",
                        username,
                        token,
                        organization_id=organization_id,
                        display_name=workspace_name,
                    )
                    st.success("Workspace created.")
                    st.rerun()
                except Exception as exc:
                    _error("Workspace creation was not completed.", exc)

            archivable = [
                item for item in workspaces
                if isinstance(item, dict) and item.get("workspace_id")
            ]
            if archivable:
                with st.form("team_workspace_archive_form"):
                    workspace_to_archive = st.selectbox(
                        "Workspace to archive",
                        options=[str(item["workspace_id"]) for item in archivable],
                        format_func=lambda value: next(
                            str(item.get("display_name") or value)
                            for item in archivable
                            if str(item["workspace_id"]) == value
                        ),
                        key="team_workspace_archive_id",
                    )
                    archive_workspace = st.form_submit_button("Archive workspace", key="team_workspace_archive_submit")
                if archive_workspace:
                    try:
                        _call(
                            "org_workspace_archive_session",
                            username,
                            token,
                            organization_id=organization_id,
                            organization_workspace_id=workspace_to_archive,
                        )
                        st.success("Workspace archived.")
                        st.rerun()
                    except Exception as exc:
                        _error("Workspace could not be archived.", exc)
        else:
            st.caption("Workspace changes require an Owner or Admin role.")

        if is_owner and str(organization.get("org_type") or "").casefold() == "team":
            with st.expander("Close this team organization", expanded=False):
                st.warning(
                    "Closing the organization revokes pending invitations, archives its workspaces, "
                    "removes active memberships and preserves the immutable audit history. "
                    "This cannot be undone from the application."
                )
                confirm_close = st.checkbox(
                    "I understand this closes the organization for all members.",
                    key=_STATE_PREFIX + "confirm_close",
                )
                if st.button(
                    "Close organization",
                    type="secondary",
                    disabled=not confirm_close,
                    key="team_org_close_submit",
                    use_container_width=True,
                ):
                    try:
                        _call(
                            "org_close_session",
                            username,
                            token,
                            organization_id=organization_id,
                        )
                        st.success("Organization closed. Audit history has been retained.")
                        _clear_organization_cache()
                        st.rerun()
                    except Exception as exc:
                        _error("Organization could not be closed.", exc)

    with member_tab:
        try:
            member_response = _call(
                "org_member_list_session",
                username,
                token,
                organization_id=organization_id,
            )
            members = member_response.get("members", [])
            if not isinstance(members, list):
                raise RuntimeError("The organization service returned an invalid member list.")
            st.session_state[_STATE_PREFIX + "members"] = members
            st.dataframe(
                pd.DataFrame([
                    {
                        "Username": item.get("username_lc", ""),
                        "Role": _ROLE_LABELS.get(str(item.get("role") or "").casefold(), item.get("role", "")),
                        "Status": item.get("status", ""),
                        "Joined": item.get("joined_at", ""),
                    }
                    for item in members if isinstance(item, dict)
                ]),
                use_container_width=True,
                hide_index=True,
            )
        except Exception as exc:
            members = []
            _error("Organization members could not be loaded.", exc)

        active_members = [
            item for item in members
            if isinstance(item, dict)
            and item.get("status") == "active"
            and item.get("username_lc")
            and str(item.get("role") or "").casefold() != "owner"
        ]
        manageable_members = [
            item for item in active_members
            if is_owner or str(item.get("role") or "").casefold() != "admin"
        ]
        target_users = [str(item["username_lc"]) for item in manageable_members]
        suspended_members = [
            item for item in members
            if isinstance(item, dict)
            and item.get("status") == "suspended"
            and item.get("username_lc")
            and str(item.get("role") or "").casefold() != "owner"
            and (is_owner or str(item.get("role") or "").casefold() != "admin")
        ]
        suspended_users = [str(item["username_lc"]) for item in suspended_members]
        if can_manage:
            if target_users:
                allowed_roles = _MEMBER_ROLES if is_owner else ("engineer", "approver", "viewer")
                with st.form("team_member_role_form"):
                    role_target = st.selectbox("Member", options=target_users, key="team_member_role_target")
                    new_role = st.selectbox(
                        "New role",
                        options=list(allowed_roles),
                        format_func=lambda value: _ROLE_LABELS[value],
                        key="team_member_new_role",
                    )
                    change_role = st.form_submit_button("Update member role", key="team_member_role_submit")
                if change_role:
                    try:
                        _call(
                            "org_member_role_set_session",
                            username,
                            token,
                            organization_id=organization_id,
                            target_username_lc=role_target,
                            role=new_role,
                        )
                        st.success("Member role updated.")
                        st.rerun()
                    except Exception as exc:
                        _error("Member role was not changed.", exc)

                with st.form("team_member_remove_form"):
                    remove_target = st.selectbox("Member to remove", options=target_users, key="team_member_remove_target")
                    remove_member = st.form_submit_button("Remove member", key="team_member_remove_submit")
                if remove_member:
                    try:
                        _call(
                            "org_member_remove_session",
                            username,
                            token,
                            organization_id=organization_id,
                            target_username_lc=remove_target,
                        )
                        st.success("Member removed from this organization.")
                        st.rerun()
                    except Exception as exc:
                        _error("Member removal was not completed.", exc)

                with st.form("team_member_suspend_form"):
                    suspend_target = st.selectbox("Member to suspend", options=target_users, key="team_member_suspend_target")
                    suspend_member = st.form_submit_button("Suspend member", key="team_member_suspend_submit")
                if suspend_member:
                    try:
                        _call(
                            "org_member_suspend_session",
                            username,
                            token,
                            organization_id=organization_id,
                            target_username_lc=suspend_target,
                        )
                        st.success("Member suspended. Existing sessions no longer have organization access.")
                        st.rerun()
                    except Exception as exc:
                        _error("Member could not be suspended.", exc)

                if is_owner:
                    with st.form("team_owner_transfer_form"):
                        new_owner = st.selectbox("Transfer ownership to", options=target_users, key="team_owner_transfer_target")
                        transfer_owner = st.form_submit_button("Transfer ownership", key="team_owner_transfer_submit")
                    if transfer_owner:
                        try:
                            _call(
                                "org_owner_transfer_session",
                                username,
                                token,
                                organization_id=organization_id,
                                target_username_lc=new_owner,
                            )
                            st.success("Ownership transfer completed.")
                            _clear_organization_cache()
                            st.rerun()
                        except Exception as exc:
                            _error("Ownership transfer was not completed.", exc)
            else:
                st.caption("No active members are available for role, suspension or removal changes.")

            if suspended_users:
                with st.form("team_member_restore_form"):
                    restore_target = st.selectbox(
                        "Suspended member to restore",
                        options=suspended_users,
                        key="team_member_restore_target",
                    )
                    restore_member = st.form_submit_button(
                        "Restore member access",
                        key="team_member_restore_submit",
                    )
                if restore_member:
                    try:
                        _call(
                            "org_member_restore_session",
                            username,
                            token,
                            organization_id=organization_id,
                            target_username_lc=restore_target,
                        )
                        st.success("Member restored. Organization access is active again.")
                        st.rerun()
                    except Exception as exc:
                        _error("Member could not be restored.", exc)
        else:
            st.info("Member management requires an organization Owner or Admin role.")

    with invitation_tab:
        if can_manage:
            with st.form("team_invitation_create_form", clear_on_submit=True):
                invite_username = st.text_input(
                    "Existing Shoir-IE username to invite",
                    max_chars=128,
                    key="team_invitation_username",
                )
                invite_role = st.selectbox(
                    "Invitation role",
                    options=list(_MEMBER_ROLES if is_owner else ("engineer", "approver", "viewer")),
                    format_func=lambda value: _ROLE_LABELS[value],
                    key="team_invitation_role",
                )
                invite_lifetime = st.number_input(
                    "Invitation lifetime (days)",
                    min_value=1,
                    max_value=30,
                    value=7,
                    step=1,
                    key="team_invitation_lifetime",
                )
                create_invite = st.form_submit_button("Create invitation", key="team_invitation_create_submit")
            if create_invite:
                try:
                    response = _call(
                        "org_invitation_create_session",
                        username,
                        token,
                        organization_id=organization_id,
                        target_username_lc=invite_username,
                        role=invite_role,
                        lifetime_days=int(invite_lifetime),
                    )
                    invitation = response.get("invitation") or {}
                    invitation_secret = str(response.get("invitation_token") or "")
                    if not invitation_secret:
                        raise RuntimeError("The invitation was created without returning its one-time token.")
                    st.session_state[_STATE_PREFIX + "invite_once"] = {
                        "organization_id": organization_id,
                        "token": invitation_secret,
                        "invitation_id": invitation.get("invitation_id"),
                    }
                    st.success("Invitation created. Copy its one-time token now and share it securely with the named user.")
                except Exception as exc:
                    _error("Invitation was not created.", exc)

            one_time = st.session_state.get(_STATE_PREFIX + "invite_once")
            if isinstance(one_time, dict) and one_time.get("organization_id") == organization_id:
                st.warning("This token is shown only in this signed-in session. It is not sent by email.")
                st.code(str(one_time.get("token") or ""), language="text")
                if st.button("Hide one-time invitation token", key="team_invitation_hide_token"):
                    st.session_state.pop(_STATE_PREFIX + "invite_once", None)
                    st.rerun()

            try:
                invitation_response = _call(
                    "org_invitation_list_session",
                    username,
                    token,
                    organization_id=organization_id,
                )
                invitations = invitation_response.get("invitations", [])
                if not isinstance(invitations, list):
                    raise RuntimeError("The organization service returned an invalid invitation list.")
                st.session_state[_STATE_PREFIX + "invitations"] = invitations
                st.dataframe(
                    pd.DataFrame([
                        {
                            "Username": item.get("target_username_lc", ""),
                            "Role": _ROLE_LABELS.get(str(item.get("role") or "").casefold(), item.get("role", "")),
                            "Expires": item.get("expires_at", ""),
                            "Accepted": bool(item.get("used_at")),
                            "Revoked": bool(item.get("revoked_at")),
                        }
                        for item in invitations if isinstance(item, dict)
                    ]),
                    use_container_width=True,
                    hide_index=True,
                )
            except Exception as exc:
                invitations = []
                _error("Organization invitations could not be loaded.", exc)

            revocable = [
                item for item in invitations
                if isinstance(item, dict)
                and item.get("invitation_id")
                and not item.get("used_at")
                and not item.get("revoked_at")
            ]
            if revocable:
                with st.form("team_invitation_revoke_form"):
                    invitation_id = st.selectbox(
                        "Pending invitation to revoke",
                        options=[str(item["invitation_id"]) for item in revocable],
                        format_func=lambda value: next(
                            str(item.get("target_username_lc") or value)
                            for item in revocable
                            if str(item["invitation_id"]) == value
                        ),
                        key="team_invitation_revoke_id",
                    )
                    revoke_invite = st.form_submit_button("Revoke invitation", key="team_invitation_revoke_submit")
                if revoke_invite:
                    try:
                        _call(
                            "org_invitation_revoke_session",
                            username,
                            token,
                            organization_id=organization_id,
                            invitation_id=invitation_id,
                        )
                        st.success("Invitation revoked.")
                        st.rerun()
                    except Exception as exc:
                        _error("Invitation could not be revoked.", exc)
        else:
            st.info("Invitation management is restricted to organization Owners and Admins.")

    with audit_tab:
        if can_manage:
            try:
                audit_response = _call(
                    "org_audit_list_session",
                    username,
                    token,
                    organization_id=organization_id,
                    limit=100,
                )
                events = audit_response.get("events", [])
                if not isinstance(events, list):
                    raise RuntimeError("The organization service returned an invalid audit list.")
                st.dataframe(
                    pd.DataFrame([
                        {
                            "Event": item.get("event_type", ""),
                            "Actor": item.get("actor_username_lc", ""),
                            "Subject": item.get("subject_username_lc", ""),
                            "When": item.get("created_at", ""),
                        }
                        for item in events if isinstance(item, dict)
                    ]),
                    use_container_width=True,
                    hide_index=True,
                )
            except Exception as exc:
                _error("Organization audit history could not be loaded.", exc)
        else:
            st.info("Audit history is restricted to organization Owners and Admins.")
