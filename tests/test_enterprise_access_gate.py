import streamlit as st

import shoir_enterprise_layer as ent


def _session(monkeypatch, *, username="alice", role="User", **extras):
    state = {
        "current_user": username,
        "user_role": role,
        "authenticated": True,
        **extras,
    }
    monkeypatch.setattr(st, "session_state", state)
    monkeypatch.setattr(
        ent,
        "security_policy",
        lambda _username, _workspace: {"require_mfa": False},
    )
    return state


def test_access_gate_uses_authoritative_user_role_without_owner_fallback(monkeypatch):
    _session(monkeypatch, role="User", current_role="Owner")
    decision = ent.security_access_check("alice", "read")
    assert decision["allowed"] is True
    assert decision["role"] == "User"
    assert decision["role"] != "Owner"


def test_access_gate_rejects_requested_identity_mismatch(monkeypatch):
    _session(
        monkeypatch,
        username="alice",
        role="Owner",
        decision_approved=True,
    )
    decision = ent.security_access_check(
        "bob", "connector_sync", require_approval=True
    )
    assert decision["allowed"] is False
    assert any("does not match" in reason for reason in decision["reasons"])


def test_access_gate_requires_authenticated_session_and_real_role(monkeypatch):
    # A stale secondary role must not override an explicitly empty canonical role.
    _session(monkeypatch, role="", current_role="Owner")
    decision = ent.security_access_check("alice", "approve")
    assert not decision["allowed"]
    assert any("account role" in reason for reason in decision["reasons"])

    _session(monkeypatch, role="User", authenticated=False)
    decision = ent.security_access_check("alice", "read")
    assert not decision["allowed"]
    assert any("authenticated session" in reason for reason in decision["reasons"])

    _session(monkeypatch, role="", current_role="")
    decision = ent.security_access_check("alice", "read")
    assert not decision["allowed"]
    assert any("account role" in reason for reason in decision["reasons"])


def test_missing_canonical_role_cannot_fall_back_to_legacy_owner_or_admin(monkeypatch):
    state = {
        "current_user": "alice",
        "authenticated": True,
        "current_role": "Owner",
        "role": "admin",
    }
    monkeypatch.setattr(st, "session_state", state)
    monkeypatch.setattr(
        ent,
        "security_policy",
        lambda _username, _workspace: {"require_mfa": False},
    )
    decision = ent.security_access_check("alice", "approve")
    assert not decision["allowed"]
    assert decision["role"] == ""
    assert any("account role" in reason for reason in decision["reasons"])


def test_security_maturity_does_not_use_legacy_role_without_canonical_role(monkeypatch):
    import durable_account_store as durable

    monkeypatch.setattr(
        st,
        "session_state",
        {"current_user": "alice", "authenticated": True, "current_role": "Owner", "role": "Admin"},
    )
    monkeypatch.setattr(
        ent,
        "security_policy",
        lambda _username, _workspace: {"require_mfa": False, "oidc_enabled": False},
    )
    monkeypatch.setattr(ent, "postgres_backend_configured", lambda: False)
    monkeypatch.setattr(durable, "durable_backend_configured", lambda: False)
    statuses = ent.security_maturity_status("alice").set_index("Control")["State"].to_dict()
    assert statuses["RBAC"] == "Not verified"


def test_read_only_role_cannot_write_or_execute(monkeypatch):
    _session(monkeypatch, role="Viewer")
    assert ent.security_access_check("alice", "read")["allowed"]
    for action in ("write", "execute", "connector_sync"):
        decision = ent.security_access_check("alice", action)
        assert not decision["allowed"]
        assert any("read-only" in reason for reason in decision["reasons"])


def test_administrator_actions_require_an_administrator_role(monkeypatch):
    _session(monkeypatch, role="User")
    decision = ent.security_access_check("alice", "approve")
    assert not decision["allowed"]
    assert any("administrator or owner" in reason for reason in decision["reasons"])
    audit_decision = ent.security_access_check("alice", "view_audit_log")
    assert not audit_decision["allowed"]
    assert any("administrator or owner" in reason for reason in audit_decision["reasons"])

    _session(monkeypatch, role="Enterprise Admin")
    assert ent.security_access_check("alice", "approve")["allowed"]
    assert ent.security_access_check("alice", "view_audit_log")["allowed"]


def test_mfa_and_human_approval_fail_closed(monkeypatch):
    state = _session(monkeypatch, role="User", decision_approved=False)
    monkeypatch.setattr(
        ent,
        "security_policy",
        lambda _username, _workspace: {"require_mfa": True},
    )
    decision = ent.security_access_check("alice", "connector_sync", require_approval=True)
    assert not decision["allowed"]
    assert any("MFA" in reason for reason in decision["reasons"])
    assert any("approval" in reason for reason in decision["reasons"])

    state["mfa_verified"] = True
    state["decision_approved"] = True
    assert ent.security_access_check(
        "alice", "connector_sync", require_approval=True
    )["allowed"]


def test_unknown_actions_and_security_policy_failures_are_denied(monkeypatch):
    _session(monkeypatch, role="User")
    assert not ent.security_access_check("alice", "invented_action")["allowed"]

    def unavailable_policy(_username, _workspace):
        raise RuntimeError("database unavailable")

    monkeypatch.setattr(ent, "security_policy", unavailable_policy)
    decision = ent.security_access_check("alice", "read")
    assert not decision["allowed"]
    assert any("policy could not be loaded" in reason for reason in decision["reasons"])


def test_enforce_action_gate_raises_for_identity_mismatch(monkeypatch):
    _session(monkeypatch, username="alice", role="Owner")
    try:
        ent.enforce_action_gate("bob", "connector_sync", require_approval=True)
    except PermissionError as exc:
        assert "does not match" in str(exc)
    else:
        raise AssertionError("Expected an authorization failure for another account")


def test_security_maturity_does_not_claim_provider_connection_or_full_verification(monkeypatch):
    import durable_account_store as durable

    state = _session(monkeypatch, role="User", mfa_verified=True)
    monkeypatch.setattr(
        ent,
        "security_policy",
        lambda _username, _workspace: {"require_mfa": True, "oidc_enabled": True},
    )
    monkeypatch.setattr(ent, "postgres_backend_configured", lambda: False)
    monkeypatch.setattr(durable, "durable_backend_configured", lambda: False)

    statuses = ent.security_maturity_status("alice").set_index("Control")["State"].to_dict()
    assert statuses["RBAC"] == "Session role present"
    assert statuses["Workspace isolation"] == "Partial"
    assert statuses["Audit / artifacts"] == "Available"
    assert statuses["Cloud persistence"] == "Local only"
    assert statuses["SSO / OIDC"] == "Configured"
    assert statuses["SSO / OIDC"] != "Connected"
    assert statuses["MFA"] == "Session flag set"
    assert statuses["MFA"] != "Connected"
    assert statuses["Secure uploads"] == "Checks present"
    assert statuses["Secrets"] == "Configured"
    assert state["authenticated"] is True


def test_security_maturity_handles_unavailable_policy_without_crashing(monkeypatch):
    _session(monkeypatch, role="User")

    def unavailable_policy(_username, _workspace):
        raise RuntimeError("policy store unavailable")

    monkeypatch.setattr(ent, "security_policy", unavailable_policy)
    status = ent.security_maturity_status("alice").set_index("Control")["State"]
    assert status["SSO / OIDC"] == "Policy unavailable"
    assert status["MFA"] == "Policy unavailable"
