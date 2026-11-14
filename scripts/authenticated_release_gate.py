#!/usr/bin/env python3
"""On-demand authenticated backend release gate for dedicated disposable test accounts.

Never run this against customer or administrator accounts. The script refuses
usernames outside the shoir-e2e- prefix, does not print passwords/tokens, and
restores the active test workspace after its save/reload probe.
"""
from __future__ import annotations

import json
import os
import secrets
import sys
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

import requests

from staging_e2e_guard import validate_edge_from_env

REPORT_PATH = Path(os.environ.get("SHOIR_E2E_REPORT", "artifacts/authenticated-release-gate/backend-report.json"))
PREFIX = "shoir-e2e-"
TIMEOUT = 20
RESULTS: list[dict[str, Any]] = []


def record(case: str, account_class: str, passed: bool | None, detail: str) -> None:
    status = "PASS" if passed is True else "FAIL" if passed is False else "SKIP"
    RESULTS.append({
        "case": case,
        "account_class": account_class,
        "status": status,
        "detail": detail,
    })
    print(f"[{status}] {case} ({account_class}): {detail}")


# A passing aggregate must include every required logical case and account class.
# The workspace-load and workspace-round-trip cases are explicitly recorded below.
REQUIRED_CASES = frozenset({
    ("active_login", "active"),
    ("invalid_password", "active"),
    ("second_login", "second"),
    ("starter_tier", "starter"),
    ("admin_action_denied", "active"),
    ("cross_owner_load_denied", "active"),
    ("cross_owner_save_denied", "active"),
    ("workspace_load", "active"),
    ("workspace_round_trip", "active"),
    ("workspace_save", "active"),
    ("workspace_relogin_restore", "active"),
    ("workspace_restore", "active"),
    ("organization_create", "active"),
    ("organization_create_second", "active"),
    ("organization_workspace_create", "active"),
    ("organization_invitation_create", "active"),
    ("organization_invitation_accept", "second"),
    ("organization_member_read", "active"),
    ("organization_viewer_workspace_read", "second"),
    ("organization_viewer_write_denied", "second"),
    ("organization_suspend_member", "active"),
    ("organization_suspended_access_denied", "second"),
    ("organization_restore_member", "active"),
    ("organization_restored_access_allowed", "second"),
    ("organization_invitation_replay_denied", "second"),
    ("organization_cross_tenant_denied", "second"),
    ("organization_admin_role_set", "active"),
    ("organization_admin_workspace_write", "second"),
    ("organization_admin_invitation_create", "second"),
    ("organization_admin_self_promotion_denied", "second"),
    ("organization_engineer_role_set", "active"),
    ("organization_engineer_write_denied", "second"),
    ("organization_approver_role_set", "active"),
    ("organization_approver_write_denied", "second"),
    ("organization_member_remove", "active"),
    ("organization_removed_access_denied", "second"),
    ("organization_invitation_revoke", "active"),
    ("organization_revoked_invitation_denied", "second"),
    ("organization_cleanup_org_1", "active"),
    ("organization_cleanup_org_2", "active"),
    ("expired_login_renewal_only", "expired"),
    ("expired_workspace_load_denied", "expired"),
    ("expired_workspace_save_denied", "expired"),
    ("renewal_requires_reference", "expired"),
    ("login_throttle_blocks_excess_attempts", "synthetic"),
    ("inactive_account_denied", "inactive"),
    ("session_revocation", "active"),
    ("session_revocation", "active-fresh"),
    ("session_revocation", "second"),
    ("session_revocation", "starter"),
    ("session_revocation", "expired"),
})


def summarize_results(
    results: list[dict[str, Any]],
    required_cases: set[tuple[str, str]] | frozenset[tuple[str, str]] | None = None,
) -> tuple[str, int]:
    """Return an honest aggregate status and process code for the release gate.

    Explicit failures are FAIL. Skipped/unknown statuses or absent mandatory
    case/account-class records are BLOCKED, never a successful release gate.
    """
    statuses = [str(item.get("status") or "SKIP").upper() for item in results]
    required = REQUIRED_CASES if required_cases is None else frozenset(required_cases)
    observed = {
        (str(item.get("case") or ""), str(item.get("account_class") or ""))
        for item in results
    }
    missing_cases = sorted(required - observed)
    if "FAIL" in statuses:
        return "FAIL", 1
    if not statuses or any(status != "PASS" for status in statuses) or missing_cases:
        return "BLOCKED", 2
    return "PASS", 0


def require_env(name: str) -> str:
    value = os.environ.get(name, "").strip()
    if not value:
        raise ValueError(f"Required environment value is missing: {name}")
    return value


def validate_test_username(name: str, label: str) -> str:
    value = name.strip()
    if not value.casefold().startswith(PREFIX):
        raise ValueError(f"{label} must start with {PREFIX!r}; refusing to risk a customer/admin account.")
    return value


class EdgeAPI:
    def __init__(self, url: str, publishable_key: str) -> None:
        self.url = url.rstrip("/")
        self.headers = {
            "apikey": publishable_key,
            "Content-Type": "application/json",
        }
        # Supabase's current sb_publishable_* keys are not JWTs and must be
        # sent in the apikey header only. Legacy anon JWTs still need Bearer auth.
        if not publishable_key.startswith("sb_publishable_"):
            self.headers["Authorization"] = f"Bearer {publishable_key}"

    def call(self, action: str, payload: dict[str, Any]) -> tuple[int, dict[str, Any]]:
        body = dict(payload)
        body["action"] = action
        response = requests.post(self.url, json=body, headers=self.headers, timeout=TIMEOUT)
        try:
            data = response.json()
        except Exception:
            data = {}
        if not isinstance(data, dict):
            data = {"error": "The staging API returned a non-object JSON response."}
        return response.status_code, data


def safe_call(api: EdgeAPI, case: str, account_class: str, action: str, payload: dict[str, Any]):
    try:
        status, data = api.call(action, payload)
        return status, data
    except Exception as exc:
        record(case, account_class, False, f"Edge request failed ({type(exc).__name__}); response body suppressed.")
        return None, {}


def login_failure_detail(status: int | None, data: dict[str, Any], expected: str) -> str:
    """Return actionable authentication diagnostics without exposing secrets or raw API bodies."""
    if status is None:
        return f"{expected}; the Edge request did not return a valid HTTP response."
    error = str(data.get("error") or "")
    if status == 401 and error == "Invalid username or password.":
        return (
            f"{expected}; HTTP 401 means the staging API rejected the credentials or account state. "
            "The dedicated E2E password may be out of sync with the staging account. "
            "Run scripts/recover_staging_e2e_credentials.py on the trusted workstation; "
            "do not create duplicate accounts or modify production."
        )
    if status == 429:
        return f"{expected}; HTTP 429 indicates the staging login throttle is active. Stop retries and let the window expire."
    if status == 503:
        return f"{expected}; HTTP 503 indicates staging authentication protection is unavailable. Inspect the Edge Function and login-throttle RPC."
    if status == 403 and error == "SUBSCRIPTION_EXPIRED":
        return f"{expected}; HTTP 403 reports an expired subscription, not an active workspace session."
    if status == 200:
        return f"{expected}; HTTP 200 was returned but the session/tier metadata did not satisfy the release-gate contract."
    return f"{expected}; staging Edge API returned unexpected HTTP {status}. Response details were suppressed."


def verify_session_revocation(api: EdgeAPI, username: str, token: str) -> tuple[bool, str]:
    """Prove a disposable session is valid, revoke it, then prove reuse is denied.

    The renewal probe omits its payment reference deliberately. A valid workspace
    or renewal-scoped session reaches the endpoint's no-write validation and
    returns HTTP 400 before any request or payment proof is persisted. After
    logout the same token must receive HTTP 401, including for expired accounts
    whose valid token is limited to renewal scope.
    """
    payload = {"username": username, "token": token}
    expected_validation_error = "A transaction/payment reference is required for renewal review."

    try:
        before_status, before_data = api.call("renew_request", payload)
    except Exception as exc:
        return False, f"Pre-logout session probe failed ({type(exc).__name__}); response details suppressed."
    if before_status != 400 or before_data.get("error") != expected_validation_error:
        return False, f"Pre-logout session probe did not reach the expected no-write validation (HTTP {before_status}); details suppressed."

    try:
        logout_status, logout_data = api.call("logout", payload)
    except Exception as exc:
        return False, f"Logout failed ({type(exc).__name__}); response details suppressed."
    if logout_status != 200 or logout_data.get("ok") is not True or logout_data.get("revoked") is not True:
        return False, f"Logout did not confirm revocation (HTTP {logout_status}); response details suppressed."

    try:
        reuse_status, reuse_data = api.call("renew_request", payload)
    except Exception as exc:
        return False, f"Post-logout token-reuse probe failed ({type(exc).__name__}); response details suppressed."
    if reuse_status != 401 or reuse_data.get("error") != "Unauthorized session.":
        return False, f"Post-logout token reuse was not denied as unauthorized (HTTP {reuse_status}); response details suppressed."

    return True, "Logout revoked the dedicated session; reuse of the same token was rejected with HTTP 401."




def verify_organization_lifecycle(
    api: EdgeAPI,
    owner_username: str,
    owner_token: str,
    member_username: str,
    member_token: str,
    starter_username: str,
    created: list[str | None],
) -> list[str | None]:
    """Run multi-account organization/RBAC acceptance with safe close cleanup."""

    def probe(
        case: str,
        account_class: str,
        status: int | None,
        data: dict[str, Any],
        *,
        expected_success: bool,
        detail: str,
    ) -> bool:
        passed = (
            status == 200
            and data.get("ok") is True
            and not data.get("error")
        ) if expected_success else (
            status is not None and status >= 400 and bool(data.get("error"))
        )
        record(case, account_class, passed, detail if passed else f"{detail} (HTTP {status}).")
        return passed

    if not owner_token or not member_token:
        for case, account_class in REQUIRED_CASES:
            if case.startswith("organization_") and case not in {"organization_cleanup_org_1", "organization_cleanup_org_2"} and not any(
                item["case"] == case and item["account_class"] == account_class
                for item in RESULTS
            ):
                record(case, account_class, None, "Skipped because the required disposable owner/member session was unavailable.")
        return created

    nonce = secrets.token_hex(6)
    org_ids: list[str] = []
    for index in (1, 2):
        status, data = safe_call(
            api,
            f"organization_create_{index}",
            "active",
            "org_create_session",
            {
                "username": owner_username,
                "token": owner_token,
                "display_name": f"Shoir E2E Org {index} {nonce}",
            },
        )
        organization = data.get("organization") if isinstance(data.get("organization"), dict) else {}
        organization_id = str(organization.get("organization_id") or "")
        passed = status == 200 and bool(organization_id) and data.get("ok") is True
        record(
            "organization_create" if index == 1 else "organization_create_second",
            "active",
            passed,
            "A disposable team organization was created under the authenticated Enterprise owner."
            if passed else f"Team organization creation failed (HTTP {status}); response details suppressed.",
        )
        if passed:
            org_ids.append(organization_id)
            created.append(organization_id)
        else:
            created.append(None)

    if len(org_ids) != 2:
        for case, account_class in REQUIRED_CASES:
            if case.startswith("organization_") and case not in {"organization_cleanup_org_1", "organization_cleanup_org_2"} and not any(
                item["case"] == case and item["account_class"] == account_class
                for item in RESULTS
            ):
                record(case, account_class, None, "Skipped because two disposable team organizations were not created.")
        return created

    first_org, second_org = org_ids
    status, data = safe_call(
        api, "organization_workspace_create_probe", "active",
        "org_workspace_create_session",
        {
            "username": owner_username,
            "token": owner_token,
            "organization_id": first_org,
            "display_name": f"Acceptance Workspace {nonce}",
        },
    )
    workspace = data.get("workspace") if isinstance(data.get("workspace"), dict) else {}
    workspace_created = status == 200 and data.get("ok") is True and bool(workspace.get("workspace_id"))
    record(
        "organization_workspace_create", "active", workspace_created,
        "Owner created a team workspace." if workspace_created else f"Owner workspace creation failed (HTTP {status}).",
    )

    status, data = safe_call(
        api, "organization_invitation_create_probe", "active",
        "org_invitation_create_session",
        {
            "username": owner_username,
            "token": owner_token,
            "organization_id": first_org,
            "target_username_lc": member_username,
            "role": "viewer",
            "lifetime_days": 7,
        },
    )
    invitation = data.get("invitation") if isinstance(data.get("invitation"), dict) else {}
    invitation_token = str(data.get("invitation_token") or "")
    invitation_id = str(invitation.get("invitation_id") or "")
    invite_created = status == 200 and data.get("ok") is True and bool(invitation_token) and bool(invitation_id)
    record(
        "organization_invitation_create", "active", invite_created,
        "Owner created a single-use invitation for the disposable second account."
        if invite_created else f"Invitation creation failed (HTTP {status}).",
    )

    accepted = False
    if invite_created:
        accept_status, accept_data = safe_call(
            api, "organization_accept_probe", "second",
            "org_invitation_accept_session",
            {
                "username": member_username,
                "token": member_token,
                "invitation_token": invitation_token,
            },
        )
        accepted = accept_status == 200 and accept_data.get("ok") is True and bool(accept_data.get("membership"))
        record(
            "organization_invitation_accept", "second", accepted,
            "The invited account accepted its own single-use invitation."
            if accepted else f"Invitation acceptance failed (HTTP {accept_status}).",
        )
    else:
        record("organization_invitation_accept", "second", None, "Skipped because no invitation token was issued.")

    if accepted:
        member_status, member_data = safe_call(
            api, "organization_member_list_probe", "active",
            "org_member_list_session",
            {"username": owner_username, "token": owner_token, "organization_id": first_org},
        )
        members = member_data.get("members") if isinstance(member_data.get("members"), list) else []
        member_row = next(
            (item for item in members if str(item.get("username_lc", "")).casefold() == member_username.casefold()),
            {},
        )
        record(
            "organization_member_read", "active",
            member_status == 200 and str(member_row.get("role") or "") == "viewer" and member_row.get("status") == "active",
            "Owner can see the invited member with its assigned Viewer role."
            if member_status == 200 and str(member_row.get("role") or "") == "viewer" and member_row.get("status") == "active"
            else f"Member list/role verification failed (HTTP {member_status}).",
        )

        read_status, read_data = safe_call(
            api, "organization_viewer_workspace_read_probe", "second",
            "org_workspace_list_session",
            {"username": member_username, "token": member_token, "organization_id": first_org},
        )
        probe(
            "organization_viewer_workspace_read", "second", read_status, read_data,
            expected_success=True,
            detail="Viewer can read only the team workspace it was invited into.",
        )

        write_status, write_data = safe_call(
            api, "organization_viewer_workspace_write_probe", "second",
            "org_workspace_create_session",
            {"username": member_username, "token": member_token, "organization_id": first_org, "display_name": "Forbidden Viewer Workspace"},
        )
        probe(
            "organization_viewer_write_denied", "second", write_status, write_data,
            expected_success=False,
            detail="Viewer workspace creation was denied by the backend.",
        )

        suspend_status, suspend_data = safe_call(
            api, "organization_suspend_member_probe", "active",
            "org_member_suspend_session",
            {"username": owner_username, "token": owner_token, "organization_id": first_org,
             "target_username_lc": member_username},
        )
        probe(
            "organization_suspend_member", "active", suspend_status, suspend_data,
            expected_success=True,
            detail="Owner suspended the member without revoking the member's global login session.",
        )
        suspended_access_status, suspended_access_data = safe_call(
            api, "organization_suspended_access_probe", "second",
            "org_workspace_list_session",
            {"username": member_username, "token": member_token, "organization_id": first_org},
        )
        probe(
            "organization_suspended_access_denied", "second",
            suspended_access_status, suspended_access_data,
            expected_success=False,
            detail="The still-valid member session is denied organization access while membership is suspended.",
        )

        restore_status, restore_data = safe_call(
            api, "organization_restore_member_probe", "active",
            "org_member_restore_session",
            {"username": owner_username, "token": owner_token, "organization_id": first_org,
             "target_username_lc": member_username},
        )
        probe(
            "organization_restore_member", "active", restore_status, restore_data,
            expected_success=True,
            detail="Owner restored the active account's suspended organization membership.",
        )
        restored_access_status, restored_access_data = safe_call(
            api, "organization_restored_access_probe", "second",
            "org_workspace_list_session",
            {"username": member_username, "token": member_token, "organization_id": first_org},
        )
        probe(
            "organization_restored_access_allowed", "second",
            restored_access_status, restored_access_data,
            expected_success=True,
            detail="The member can access the organization again after restoration.",
        )

        replay_status, replay_data = safe_call(
            api, "organization_invitation_replay_probe", "second",
            "org_invitation_accept_session",
            {"username": member_username, "token": member_token, "invitation_token": invitation_token},
        )
        probe(
            "organization_invitation_replay_denied", "second", replay_status, replay_data,
            expected_success=False,
            detail="Replaying an accepted single-use invitation was rejected.",
        )

        cross_status, cross_data = safe_call(
            api, "organization_cross_tenant_probe", "second",
            "org_workspace_list_session",
            {"username": member_username, "token": member_token, "organization_id": second_org},
        )
        probe(
            "organization_cross_tenant_denied", "second", cross_status, cross_data,
            expected_success=False,
            detail="A member of organization one cannot list organization two workspaces.",
        )

        role_status, role_data = safe_call(
            api, "organization_set_admin_probe", "active",
            "org_member_role_set_session",
            {"username": owner_username, "token": owner_token, "organization_id": first_org,
             "target_username_lc": member_username, "role": "admin"},
        )
        probe(
            "organization_admin_role_set", "active", role_status, role_data,
            expected_success=True,
            detail="Owner promoted the member to Admin.",
        )

        admin_write_status, admin_write_data = safe_call(
            api, "organization_admin_workspace_write_probe", "second",
            "org_workspace_create_session",
            {"username": member_username, "token": member_token, "organization_id": first_org,
             "display_name": f"Admin Workspace {nonce}"},
        )
        probe(
            "organization_admin_workspace_write", "second", admin_write_status, admin_write_data,
            expected_success=True,
            detail="Admin can create a workspace through the authorized backend.",
        )

        admin_invite_status, admin_invite_data = safe_call(
            api, "organization_admin_invitation_create_probe", "second",
            "org_invitation_create_session",
            {"username": member_username, "token": member_token, "organization_id": first_org,
             "target_username_lc": starter_username, "role": "viewer", "lifetime_days": 7},
        )
        admin_invitation = admin_invite_data.get("invitation") if isinstance(admin_invite_data.get("invitation"), dict) else {}
        admin_invitation_id = str(admin_invitation.get("invitation_id") or "")
        admin_invite_ok = (
            admin_invite_status == 200
            and admin_invite_data.get("ok") is True
            and bool(admin_invitation_id)
            and bool(admin_invite_data.get("invitation_token"))
        )
        record(
            "organization_admin_invitation_create", "second", admin_invite_ok,
            "Admin created a Viewer invitation for the third disposable account."
            if admin_invite_ok else f"Admin invitation creation failed (HTTP {admin_invite_status}).",
        )

        self_promote_status, self_promote_data = safe_call(
            api, "organization_admin_self_promotion_probe", "second",
            "org_member_role_set_session",
            {"username": member_username, "token": member_token, "organization_id": first_org,
             "target_username_lc": member_username, "role": "admin"},
        )
        probe(
            "organization_admin_self_promotion_denied", "second", self_promote_status, self_promote_data,
            expected_success=False,
            detail="Admin cannot self-promote or mutate its own privileged membership.",
        )

        role_status, role_data = safe_call(
            api, "organization_set_engineer_probe", "active",
            "org_member_role_set_session",
            {"username": owner_username, "token": owner_token, "organization_id": first_org,
             "target_username_lc": member_username, "role": "engineer"},
        )
        probe(
            "organization_engineer_role_set", "active", role_status, role_data,
            expected_success=True,
            detail="Owner changed the member role to Engineer.",
        )
        engineer_write_status, engineer_write_data = safe_call(
            api, "organization_engineer_workspace_write_probe", "second",
            "org_workspace_create_session",
            {"username": member_username, "token": member_token, "organization_id": first_org,
             "display_name": "Forbidden Engineer Workspace"},
        )
        probe(
            "organization_engineer_write_denied", "second", engineer_write_status, engineer_write_data,
            expected_success=False,
            detail="Engineer cannot create a team workspace without Owner/Admin permission.",
        )

        role_status, role_data = safe_call(
            api, "organization_set_approver_probe", "active",
            "org_member_role_set_session",
            {"username": owner_username, "token": owner_token, "organization_id": first_org,
             "target_username_lc": member_username, "role": "approver"},
        )
        probe(
            "organization_approver_role_set", "active", role_status, role_data,
            expected_success=True,
            detail="Owner changed the member role to Approver.",
        )
        approver_write_status, approver_write_data = safe_call(
            api, "organization_approver_workspace_write_probe", "second",
            "org_workspace_create_session",
            {"username": member_username, "token": member_token, "organization_id": first_org,
             "display_name": "Forbidden Approver Workspace"},
        )
        probe(
            "organization_approver_write_denied", "second", approver_write_status, approver_write_data,
            expected_success=False,
            detail="Approver cannot create a team workspace without Owner/Admin permission.",
        )

        remove_status, remove_data = safe_call(
            api, "organization_member_remove_probe", "active",
            "org_member_remove_session",
            {"username": owner_username, "token": owner_token, "organization_id": first_org,
             "target_username_lc": member_username},
        )
        probe(
            "organization_member_remove", "active", remove_status, remove_data,
            expected_success=True,
            detail="Owner removed the invited member from organization one.",
        )
        removed_status, removed_data = safe_call(
            api, "organization_removed_member_access_probe", "second",
            "org_workspace_list_session",
            {"username": member_username, "token": member_token, "organization_id": first_org},
        )
        probe(
            "organization_removed_access_denied", "second", removed_status, removed_data,
            expected_success=False,
            detail="Removed member can no longer access organization one.",
        )
    else:
        for case, account_class in REQUIRED_CASES:
            if case.startswith("organization_") and case not in {"organization_cleanup_org_1", "organization_cleanup_org_2"} and not any(
                item["case"] == case and item["account_class"] == account_class
                for item in RESULTS
            ):
                record(case, account_class, None, "Skipped because invitation acceptance did not complete.")

    revoked_invitation_token = ""
    if invitation_id:
        # The accepted invitation is immutable history. A fresh pending invitation
        # in organization two verifies revocation and refusal to consume a revoked token.
        revoke_create_status, revoke_create_data = safe_call(
            api, "organization_revocation_invitation_create_probe", "active",
            "org_invitation_create_session",
            {"username": owner_username, "token": owner_token, "organization_id": second_org,
             "target_username_lc": member_username, "role": "viewer", "lifetime_days": 7},
        )
        revoke_row = revoke_create_data.get("invitation") if isinstance(revoke_create_data.get("invitation"), dict) else {}
        revoke_id = str(revoke_row.get("invitation_id") or "")
        revoked_invitation_token = str(revoke_create_data.get("invitation_token") or "")
        revoke_created = revoke_create_status == 200 and revoke_create_data.get("ok") is True and bool(revoke_id) and bool(revoked_invitation_token)
        if revoke_created:
            revoke_status, revoke_data = safe_call(
                api, "organization_invitation_revoke_probe", "active",
                "org_invitation_revoke_session",
                {"username": owner_username, "token": owner_token, "organization_id": second_org,
                 "invitation_id": revoke_id},
            )
            probe(
                "organization_invitation_revoke", "active", revoke_status, revoke_data,
                expected_success=True,
                detail="Owner revoked a pending invitation in organization two.",
            )
            revoked_accept_status, revoked_accept_data = safe_call(
                api, "organization_revoked_invitation_accept_probe", "second",
                "org_invitation_accept_session",
                {"username": member_username, "token": member_token, "invitation_token": revoked_invitation_token},
            )
            probe(
                "organization_revoked_invitation_denied", "second", revoked_accept_status, revoked_accept_data,
                expected_success=False,
                detail="A revoked invitation token cannot be accepted.",
            )
        else:
            record("organization_invitation_revoke", "active", False, f"Pending invitation for revocation could not be created (HTTP {revoke_create_status}).")
            record("organization_revoked_invitation_denied", "second", None, "Skipped because no revocable invitation token was issued.")
    else:
        record("organization_invitation_revoke", "active", None, "Skipped because the initial invitation was not created.")
        record("organization_revoked_invitation_denied", "second", None, "Skipped because the initial invitation was not created.")

    return created

def main() -> int:
    REPORT_PATH.parent.mkdir(parents=True, exist_ok=True)
    try:
        edge_url = validate_edge_from_env()
        key = require_env("SHOIR_E2E_PUBLISHABLE_KEY")
        # HTTP header values must be ASCII/Latin-1 encodable. Supabase
        # publishable keys and legacy anon JWTs are ASCII; reject a pasted
        # non-ASCII character or hidden formatting before making live requests.
        if not key.isascii():
            raise ValueError(
                "SHOIR_E2E_PUBLISHABLE_KEY contains non-ASCII characters; replace it with the exact "
                "staging project's publishable/anon key copied as plain text, without quotes or hidden formatting."
            )
        active_user = validate_test_username(require_env("SHOIR_E2E_ACTIVE_USERNAME"), "active account")
        active_password = require_env("SHOIR_E2E_ACTIVE_PASSWORD")
        second_user = validate_test_username(require_env("SHOIR_E2E_SECOND_USERNAME"), "second account")
        second_password = require_env("SHOIR_E2E_SECOND_PASSWORD")
        starter_user = validate_test_username(require_env("SHOIR_E2E_STARTER_USERNAME"), "starter account")
        starter_password = require_env("SHOIR_E2E_STARTER_PASSWORD")
        expired_user = validate_test_username(require_env("SHOIR_E2E_EXPIRED_USERNAME"), "expired account")
        expired_password = require_env("SHOIR_E2E_EXPIRED_PASSWORD")
        active_expected_tier = os.environ.get("SHOIR_E2E_ACTIVE_EXPECTED_TIER", "Enterprise Plus Tier ($399)").strip()
    except ValueError as exc:
        print(f"[FAIL] Preflight: {exc}", file=sys.stderr)
        return 2

    if len({active_user.casefold(), second_user.casefold(), starter_user.casefold(), expired_user.casefold()}) != 4:
        print("[FAIL] Preflight: active, second, starter and expired test accounts must be distinct.", file=sys.stderr)
        return 2

    api = EdgeAPI(edge_url, key)

    # Non-persistent integration probes for the new legal/referral contract.
    # Missing/stale notice versions and unknown referral codes must be rejected
    # before a request row or payment proof is created.
    current_notices = {
        "terms_accepted": True,
        "terms_version": "2026-10-21-beta-v1",
        "privacy_policy_version": "2026-10-21-v1",
        "refund_policy_version": "2026-10-23-v2",
        "cookie_policy_version": "2026-10-21-v1",
    }

    def registration_probe(case: str, payload: dict[str, Any], expected_error: str) -> None:
        try:
            response_status, response_body = api.call("register_request", payload)
            error_text = str(response_body.get("error") or "")
            passed = response_status == 400 and expected_error.casefold() in error_text.casefold()
            record(
                case,
                "registration_gate",
                passed,
                "Registration request was rejected before persistence as expected."
                if passed
                else f"Expected HTTP 400 with the {expected_error!r} validation message; received HTTP {response_status}. Response body suppressed.",
            )
        except Exception as exc:
            record(
                case,
                "registration_gate",
                False,
                f"Edge request failed ({type(exc).__name__}); response body suppressed.",
            )

    registration_probe(
        "registration_requires_current_acceptance",
        {
            "username": "shoir-e2e-legal-probe",
            "password": "synthetic-test-only-password",
            "email": "shoir-e2e-legal-probe@example.invalid",
            "tier": "Starter Tier ($29)",
            "payment_method": "STC Pay (QR)",
            "transaction_id": "SYNTHETIC-NO-CONSENT-PROBE",
        },
        "current beta terms",
    )

    registration_probe(
        "registration_rejects_stale_policy_version",
        {
            "username": "shoir-e2e-stale-policy-probe",
            "password": "synthetic-test-only-password",
            "email": "shoir-e2e-stale-policy-probe@example.invalid",
            "tier": "Starter Tier ($29)",
            "payment_method": "STC Pay (QR)",
            "transaction_id": "SYNTHETIC-STALE-POLICY-PROBE",
            **current_notices,
            "privacy_policy_version": "obsolete-e2e-probe",
        },
        "current beta terms",
    )

    registration_probe(
        "registration_rejects_unknown_referral",
        {
            "username": "shoir-e2e-referral-probe",
            "password": "synthetic-test-only-password",
            "email": "shoir-e2e-referral-probe@example.invalid",
            "tier": "Starter Tier ($29)",
            "payment_method": "STC Pay (QR)",
            "transaction_id": "SYNTHETIC-REFERRAL-PROBE",
            **current_notices,
            "referral_code": "SHR-NOT-" + secrets.token_hex(6).upper(),
        },
        "referral code",
    )

    active_token = ""
    second_token = ""
    starter_token = ""
    expired_token = ""
    reload_token = ""
    original_workspace: str | None = None
    workspace_was_loaded = False
    write_started = False
    restore_expected = "{}"
    sentinel_key = "__shoir_e2e_release_probe__"
    sentinel_value = secrets.token_hex(16)
    created_organization_ids: list[str | None] = []
    created_organization_ids: list[str | None] = []

    try:
        # Active account login and entitlement are checked without exposing its username.
        status, data = safe_call(api, "active_login", "active", "login",
                                 {"username": active_user, "password": active_password})
        active_token = str(data.get("token") or "")
        record("active_login", "active",
               status == 200 and bool(active_token) and data.get("username", "").casefold() == active_user.casefold()
               and str(data.get("tier") or "").strip() == active_expected_tier
               and str(data.get("role") or "") != "Enterprise Admin",
               "Expected active non-admin session and configured tier." if (status == 200 and bool(active_token) and data.get("username", "").casefold() == active_user.casefold() and str(data.get("tier") or "").strip() == active_expected_tier and str(data.get("role") or "") != "Enterprise Admin") else login_failure_detail(status, data, "Active account login failed"))

        # Verify generic invalid-password behavior; use a random wrong value, never an actual secret.
        bad_status, bad = safe_call(api, "invalid_password", "active", "login",
                                    {"username": active_user, "password": "invalid-" + secrets.token_hex(12)})
        record("invalid_password", "active",
               bad_status == 401 and not bad.get("token") and bad.get("error") == "Invalid username or password.",
               "Invalid credentials rejected without issuing a session.")

        status2, data2 = safe_call(api, "second_login", "second", "login",
                                   {"username": second_user, "password": second_password})
        second_token = str(data2.get("token") or "")
        record("second_login", "second",
               status2 == 200 and bool(second_token) and str(data2.get("role") or "") != "Enterprise Admin",
               "Second dedicated non-admin account can authenticate." if (status2 == 200 and bool(second_token) and str(data2.get("role") or "") != "Enterprise Admin") else login_failure_detail(status2, data2, "Second account login failed"))

        status3, data3 = safe_call(api, "starter_login", "starter", "login",
                                   {"username": starter_user, "password": starter_password})
        starter_token = str(data3.get("token") or "")
        record("starter_tier", "starter",
               status3 == 200 and bool(starter_token) and "starter" in str(data3.get("tier") or "").casefold()
               and str(data3.get("role") or "") != "Enterprise Admin",
               "Starter tier is returned for the dedicated Starter test identity." if (status3 == 200 and bool(starter_token) and "starter" in str(data3.get("tier") or "").casefold() and str(data3.get("role") or "") != "Enterprise Admin") else login_failure_detail(status3, data3, "Starter account login failed"))

        try:
            verify_organization_lifecycle(
                api,
                active_user,
                active_token,
                second_user,
                second_token,
                starter_user,
                created_organization_ids,
            )
        except Exception as exc:
            record(
                "organization_lifecycle_unhandled_error",
                "active",
                False,
                f"Organization acceptance aborted safely ({type(exc).__name__}); response details suppressed.",
            )

        # An active non-admin must not invoke administrator APIs even with a valid token.
        if active_token:
            status, admin_data = safe_call(api, "admin_action_denied", "active", "admin_list_requests_session",
                                           {"username": active_user, "token": active_token})
            record("admin_action_denied", "active",
                   status is not None and status >= 400 and bool(admin_data.get("error")),
                   "Server-side administrator API rejects a non-admin token.")

        # Workspace access is bound to the session owner, not a caller-supplied username.
        if active_token and second_token:
            status, data = safe_call(api, "cross_owner_load_denied", "active", "workspace_load",
                                     {"username": second_user, "token": active_token})
            record("cross_owner_load_denied", "active",
                   status is not None and status >= 400 and bool(data.get("error")),
                   "A valid token cannot read a different account's workspace.")
            before_status, before_data = safe_call(api, "second_workspace_before", "second", "workspace_load",
                                                   {"username": second_user, "token": second_token})
            second_before = before_data.get("state_json") if before_status == 200 else None
            save_status, save_data = safe_call(api, "cross_owner_save_denied", "active", "workspace_save",
                                               {"username": second_user, "token": active_token,
                                                "state_json": json.dumps({"forbidden": sentinel_value})})
            after_status, after_data = safe_call(api, "second_workspace_after", "second", "workspace_load",
                                                  {"username": second_user, "token": second_token})
            record("cross_owner_save_denied", "active",
                   save_status is not None and save_status >= 400 and bool(save_data.get("error"))
                   and before_status == 200 and after_status == 200
                   and before_data.get("state_json") == after_data.get("state_json") == second_before,
                   "Cross-owner save is denied and the second account's stored workspace is unchanged.")

        # Persist one temporary marker, login again with a fresh session, read it,
        # then restore the account's original serialized workspace in every exit path.
        if active_token:
            status, data = safe_call(api, "active_workspace_before", "active", "workspace_load",
                                     {"username": active_user, "token": active_token})
            workspace_was_loaded = status == 200
            original_workspace = data.get("state_json") if workspace_was_loaded else None
            if not workspace_was_loaded:
                record("workspace_load", "active", False, "Could not load the active test workspace.")
            else:
                record("workspace_load", "active", True, "Active test workspace loaded under its authenticated owner.")

            if workspace_was_loaded and original_workspace is not None and (not isinstance(original_workspace, str) or len(original_workspace) > 1_000_000):
                record("workspace_round_trip", "active", False, "Workspace is not a small string suitable for a safe test-account probe.")
            elif workspace_was_loaded:
                try:
                    prior_state = json.loads(original_workspace) if original_workspace else {}
                    if not isinstance(prior_state, dict):
                        raise ValueError("Workspace is not a JSON object.")
                except Exception:
                    record("workspace_round_trip", "active", False, "Workspace is not a JSON object; refusing to overwrite it.")
                else:
                    record("workspace_round_trip", "active", True, "Workspace payload is a JSON object and is safe for a temporary round-trip probe.")
                    prior_state.pop(sentinel_key, None)
                    restore_expected = original_workspace if original_workspace else "{}"
                    probe_state = dict(prior_state)
                    probe_state[sentinel_key] = sentinel_value
                    status, result = safe_call(api, "workspace_save", "active", "workspace_save",
                                               {"username": active_user, "token": active_token,
                                                "state_json": json.dumps(probe_state, ensure_ascii=False)})
                    write_started = status == 200 and bool(result.get("ok"))
                    record("workspace_save", "active", write_started, "Temporary test marker write acknowledged." if write_started else "Temporary workspace write failed.")
                    if write_started:
                        fresh_status, fresh_login = safe_call(api, "fresh_login", "active", "login",
                                                              {"username": active_user, "password": active_password})
                        reload_token = str(fresh_login.get("token") or "")
                        read_status, restored = (None, {})
                        if fresh_status == 200 and reload_token:
                            read_status, restored = safe_call(api, "workspace_reload", "active", "workspace_load",
                                                              {"username": active_user, "token": reload_token})
                        state_text = restored.get("state_json") if read_status == 200 else None
                        try:
                            reloaded_state = json.loads(state_text) if state_text else {}
                        except Exception:
                            reloaded_state = {}
                        record("workspace_relogin_restore", "active",
                               fresh_status == 200 and read_status == 200 and reloaded_state.get(sentinel_key) == sentinel_value,
                               "Saved marker was visible after a new authenticated session." if reloaded_state.get(sentinel_key) == sentinel_value else "Marker did not survive a new authenticated session.")

                        if reload_token:
                            restore_status, restore_data = safe_call(api, "workspace_restore", "active", "workspace_save",
                                                                      {"username": active_user, "token": reload_token,
                                                                       "state_json": restore_expected})
                            restore_ok = restore_status == 200 and bool(restore_data.get("ok"))
                            record("workspace_restore", "active",
                                   restore_ok,
                                   "Original test workspace restored." if restore_ok else "Original workspace restoration failed; manual retry will run.")
                            write_started = not restore_ok

        # Expiry should produce only a renewal-scoped token, never workspace access.
        expired_status, expired_data = safe_call(api, "expired_login", "expired", "login",
                                                  {"username": expired_user, "password": expired_password})
        expired_token = str(expired_data.get("token") or "")
        expired_ok = expired_status == 403 and expired_data.get("error") == "SUBSCRIPTION_EXPIRED" and bool(expired_token) and expired_data.get("renewal_only") is True
        record("expired_login_renewal_only", "expired", expired_ok,
               "Expired account receives a renewal-only session, not a workspace session." if expired_ok else login_failure_detail(expired_status, expired_data, "Expired-account renewal-only login contract failed"))
        if expired_token:
            st_load, load_data = safe_call(api, "expired_workspace_load_denied", "expired", "workspace_load",
                                           {"username": expired_user, "token": expired_token})
            st_save, save_data = safe_call(api, "expired_workspace_save_denied", "expired", "workspace_save",
                                           {"username": expired_user, "token": expired_token, "state_json": "{}"})
            st_renew, renew_data = safe_call(api, "renewal_missing_reference", "expired", "renew_request",
                                             {"username": expired_user, "token": expired_token, "transaction_id": ""})
            record("expired_workspace_load_denied", "expired", st_load is not None and st_load >= 400 and bool(load_data.get("error")),
                   "Renewal-only token cannot read workspace data.")
            record("expired_workspace_save_denied", "expired", st_save is not None and st_save >= 400 and bool(save_data.get("error")),
                   "Renewal-only token cannot write workspace data.")
            record("renewal_requires_reference", "expired",
                   st_renew == 400 and "reference" in str(renew_data.get("error") or "").casefold(),
                   "Missing transaction reference is rejected before a renewal record is created.")

        if os.environ.get("SHOIR_E2E_VERIFY_LOGIN_THROTTLE", "").strip().casefold() in {"1", "true", "yes", "on"}:
            # Use a synthetic non-account identity so the test cannot lock a real
            # user's bucket. This uses 9 attempts from the runner IP bucket and
            # should only be enabled for an intentional release-gate run.
            throttle_user = PREFIX + "throttle-" + secrets.token_hex(8)
            observed = []
            for attempt_number in range(9):
                code, payload = safe_call(
                    api, "login_throttle_probe", "synthetic", "login",
                    {"username": throttle_user, "password": "invalid-" + secrets.token_hex(16)},
                )
                observed.append(code)
                if code is None:
                    break
            record(
                "login_throttle_blocks_excess_attempts",
                "synthetic",
                observed == [401] * 8 + [429],
                "Eight synthetic attempts were rejected generically and the ninth was rate-limited."
                if observed == [401] * 8 + [429]
                else "Rate-limit responses differed from the expected 8x401 then 429 sequence.",
            )
        else:
            record(
                "login_throttle_blocks_excess_attempts",
                "synthetic",
                None,
                "Skipped: set the GitHub Actions variable SHOIR_E2E_VERIFY_LOGIN_THROTTLE=true for an intentional live limiter probe.",
            )

        inactive_user = os.environ.get("SHOIR_E2E_INACTIVE_USERNAME", "").strip()
        inactive_password = os.environ.get("SHOIR_E2E_INACTIVE_PASSWORD", "")
        if inactive_user or inactive_password:
            if not inactive_user or not inactive_password:
                record("inactive_account_denied", "inactive", False, "Both inactive-account test credentials must be configured together.")
            else:
                try:
                    inactive_user = validate_test_username(inactive_user, "inactive account")
                    status, data = safe_call(api, "inactive_account_denied", "inactive", "login",
                                             {"username": inactive_user, "password": inactive_password})
                    record("inactive_account_denied", "inactive",
                           status == 401 and not data.get("token"),
                           "Inactive account credentials do not create a server session.")
                except ValueError as exc:
                    record("inactive_account_denied", "inactive", False, str(exc))
        else:
            record("inactive_account_denied", "inactive", None, "Skipped: configure a dedicated inactive test account to verify the server guard.")

    finally:
        # Close only the two organizations created by this run. The close RPC
        # preserves immutable audit events and does not delete account data.
        for org_index in (1, 2):
            cleanup_case = f"organization_cleanup_org_{org_index}"
            organization_id = (
                created_organization_ids[org_index - 1]
                if len(created_organization_ids) >= org_index
                else None
            )
            if organization_id and active_token:
                cleanup_status, cleanup_data = safe_call(
                    api,
                    cleanup_case,
                    "active",
                    "org_close_session",
                    {
                        "username": active_user,
                        "token": active_token,
                        "organization_id": organization_id,
                    },
                )
                cleanup_result = cleanup_data.get("result") if isinstance(cleanup_data.get("result"), dict) else {}
                cleanup_ok = (
                    cleanup_status == 200
                    and cleanup_data.get("ok") is True
                    and cleanup_result.get("status") == "closed"
                )
                record(
                    cleanup_case,
                    "active",
                    cleanup_ok,
                    "Disposable organization closed; workspaces archived, memberships removed and audit history preserved."
                    if cleanup_ok else f"Disposable organization cleanup failed (HTTP {cleanup_status}); manual staging cleanup is required.",
                )
            else:
                record(
                    cleanup_case,
                    "active",
                    None,
                    "Skipped because this run did not create the corresponding disposable organization.",
                )

        # Restore the original dedicated test workspace before revoking the
        # session needed to perform a retry. Never use a production/customer user.
        if write_started and workspace_was_loaded:
            restore_token = reload_token or active_token
            if restore_token:
                try:
                    status, data = api.call("workspace_save", {
                        "username": active_user,
                        "token": restore_token,
                        "state_json": restore_expected,
                    })
                    restored_ok = status == 200 and bool(data.get("ok"))
                    record("workspace_restore_retry", "active", restored_ok,
                           "Original test workspace restored on retry." if restored_ok else "Workspace restore retry failed; manual review is required.")
                    write_started = not restored_ok
                except Exception:
                    record("workspace_restore_retry", "active", False, "Workspace restore retry failed; manual review is required.")
            else:
                record("workspace_restore_retry", "active", False, "No valid test session remained to restore the workspace.")

        # Never leave probe sessions active after the test. For each issued token,
        # prove it works before logout, require deletion, then reuse it and require HTTP 401.
        for label, username, token in (
            ("active", active_user, active_token),
            ("active-fresh", active_user, reload_token),
            ("second", second_user, second_token),
            ("starter", starter_user, starter_token),
            ("expired", expired_user, expired_token),
        ):
            if token:
                passed, detail = verify_session_revocation(api, username, token)
                record("session_revocation", label, passed, detail)
            else:
                record("session_revocation", label, False, "No disposable session token was issued; revocation could not be verified.")

    overall, exit_code = summarize_results(RESULTS, REQUIRED_CASES)
    REPORT_PATH.write_text(json.dumps({
        "run_at_utc": datetime.now(timezone.utc).isoformat(),
        "target": edge_url,
        "overall": overall,
        "cases": RESULTS,
    }, indent=2), encoding="utf-8")
    print(f"Report written to {REPORT_PATH}")
    if overall == "BLOCKED":
        print("[BLOCKED] One or more mandatory release-gate cases were skipped or had no result.", file=sys.stderr)
    return exit_code


if __name__ == "__main__":
    raise SystemExit(main())
