from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
APP_SOURCE = (ROOT / "app.py").read_text(encoding="utf-8")
EDGE_SOURCE = (ROOT / "supabase" / "functions" / "shoir-persistence" / "index.ts").read_text(encoding="utf-8")
ADMIN_TIER_MIGRATION = (
    ROOT / "supabase" / "migrations" /
    "20261018194225_renewal_scoped_sessions_and_admin_plus_tier.sql"
).read_text(encoding="utf-8")


def test_expired_login_enters_renewal_only_flow():
    assert 'st.session_state["renewal_mode"] = True' in APP_SOURCE
    assert 'st.session_state["renewal_session_token"] = renewal_token' in APP_SOURCE
    assert 'if st.session_state.get("renewal_mode") and not st.session_state.get("current_user"):' in APP_SOURCE
    assert 'edge_renew_request(' in APP_SOURCE
    assert 'Submit renewal request' in APP_SOURCE
    assert 'Back to sign in' in APP_SOURCE


def test_renewal_sessions_are_short_lived_and_scoped():
    assert 'createSession(row.username_lc,"renewal",60*60*1000)' in EDGE_SOURCE
    assert 'requiredScope:"workspace"|"renewal"|"either"="workspace"' in EDGE_SOURCE
    assert 'scope=data.scope||"workspace"' in EDGE_SOURCE
    assert 'if(requiredScope==="workspace"&&row.username_lc!=="sho"&&isExpired(row.subscription_expires_at))' in EDGE_SOURCE
    assert 'getSession(String(body.token),String(body.username),"either")' in EDGE_SOURCE


def test_workspace_reads_and_writes_require_workspace_scope():
    assert 'if(action==="workspace_load"){await getSession(String(body.token),String(body.username));' in EDGE_SOURCE
    assert 'if(action==="workspace_save"){await getSession(String(body.token),String(body.username));' in EDGE_SOURCE
    assert 'async function adminSession(username:string,token:string){const row=await getSession(token,username);' in EDGE_SOURCE


def test_visible_subscription_countdown_and_renewal_controls_exist():
    assert 'Subscription & Renewal' in APP_SOURCE
    assert 'Time remaining' in APP_SOURCE
    assert 'Subscription: ' in APP_SOURCE
    assert 'active_subscription_renewal_form' in APP_SOURCE
    assert 'Enterprise Plus Tier ($399)' in APP_SOURCE
    assert 'Research Pack ($30 add-on)' in APP_SOURCE


def test_admin_tier_change_does_not_rewrite_identity_or_expiry():
    assert "SET tier = 'Enterprise Plus Tier ($399)'" in ADMIN_TIER_MIGRATION
    assert "WHERE username_lc = 'sho'" in ADMIN_TIER_MIGRATION
    assert "AND role = 'Enterprise Admin'" in ADMIN_TIER_MIGRATION
    assert "SET role =" not in ADMIN_TIER_MIGRATION
    assert "password_hash =" not in ADMIN_TIER_MIGRATION
    assert "subscription_expires_at =" not in ADMIN_TIER_MIGRATION
