from datetime import datetime, timedelta, timezone

from durable_account_store import account_is_expired, renewed_expiry


def test_account_is_expired_at_boundary():
    now = datetime(2026, 9, 22, tzinfo=timezone.utc)
    assert account_is_expired(now, now)
    assert not account_is_expired(now + timedelta(seconds=1), now)


def test_renewal_starts_from_later_of_now_or_expiry():
    now = datetime(2026, 9, 22, tzinfo=timezone.utc)
    expired = now - timedelta(days=2)
    future = now + timedelta(days=5)
    assert renewed_expiry(expired, 30, now) == now + timedelta(days=30)
    assert renewed_expiry(future, 30, now) == future + timedelta(days=30)


def test_edge_backend_is_built_in():
    from durable_account_store import edge_backend_configured, durable_backend_configured
    assert edge_backend_configured() is True
    assert durable_backend_configured() is True


def test_master_admin_enterprise_plus_entitlement_contract():
    """Guard the local seed and server-side entitlement without resetting admin credentials."""
    from pathlib import Path

    root = Path(__file__).resolve().parents[1]
    app_source = (root / "app.py").read_text(encoding="utf-8")
    edge_source = (root / "supabase/functions/shoir-persistence/index.ts").read_text(encoding="utf-8")

    assert '("sho", admin_pass_hash, "Enterprise Admin", "Enterprise Plus Tier ($399)",' in app_source
    assert '(admin_pass_hash, "Enterprise Admin", "Enterprise Plus Tier ($399)", "mohsuhailji@gmail.com")' in app_source
    assert '("Enterprise Admin", "Enterprise Plus Tier ($399)", "mohsuhailji@gmail.com")' in app_source
    assert 'const isMasterAdmin = row.username_lc==="sho"&&row.role==="Enterprise Admin";' in edge_source
    assert 'const effectiveTier=isMasterAdmin?adminTier:row.tier;' in edge_source
    assert 'if(requiredScope==="workspace"&&!(row.username_lc==="sho"&&row.role==="Enterprise Admin")' in edge_source
    assert 'if(row.username_lc!=="sho"||row.role!=="Enterprise Admin")throw new Error("Admin authorization failed.");' in edge_source
    assert 'st.sidebar.caption("SUBSCRIPTION COUNTDOWN")' in app_source
    assert 'st.session_state.get("subscription_expires_at")' in app_source
    assert 'and _current_username.casefold() != "sho"' in app_source


def test_renewal_approval_preserves_existing_account_identity_and_renews_expiry():
    """Protect the old account/workspace instead of creating a replacement account."""
    from pathlib import Path

    root = Path(__file__).resolve().parents[1]
    edge_source = (root / "supabase/functions/shoir-persistence/index.ts").read_text(encoding="utf-8")

    assert 'request.request_type==="Renewal"&&existing?expiry30(existing.subscription_expires_at):expiry30()' in edge_source
    assert 'const passwordHash=existing?.password_hash||pendingCred?.password_hash;' in edge_source
    assert 'created_at:existing?.created_at||now' in edge_source
    assert 'username_lc:request.username_lc' in edge_source
    assert 'if(action==="renew_request")' in edge_source
