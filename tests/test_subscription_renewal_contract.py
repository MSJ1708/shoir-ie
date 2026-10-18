from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
APP_SOURCE = (ROOT / "app.py").read_text(encoding="utf-8")
EDGE_SOURCE = (ROOT / "supabase" / "functions" / "shoir-persistence" / "index.ts").read_text(encoding="utf-8")
ADMIN_TIER_MIGRATION = (
    ROOT / "supabase" / "migrations" /
    "20261018194225_renewal_scoped_sessions_and_admin_plus_tier.sql"
).read_text(encoding="utf-8")
PLATFORM_RLS_MIGRATION = (
    ROOT / "supabase" / "migrations" /
    "20261018204013_explicit_server_only_platform_policies.sql"
).read_text(encoding="utf-8")
PAYMENT_PROOF_MIGRATION = (
    ROOT / "supabase" / "migrations" /
    "20261018204217_private_subscription_payment_proofs.sql"
).read_text(encoding="utf-8")
PAYMENT_PROOF_RLS_MIGRATION = (
    ROOT / "supabase" / "migrations" /
    "20261018204857_restrict_payment_proof_storage_to_server.sql"
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
    assert '@st.fragment(run_every="60s")' in APP_SOURCE
    assert 'active_subscription_renewal_form' in APP_SOURCE
    assert 'Enter the payment transaction/reference' in APP_SOURCE
    assert 'Transaction / Payment Reference' in APP_SOURCE
    assert '_encode_renewal_proof' in APP_SOURCE
    assert '512 * 1024' in APP_SOURCE
    assert 'edge_admin_payment_proof_url' in APP_SOURCE
    assert 'admin_payment_proof_url_session' in EDGE_SOURCE
    assert 'transactionId=String(body.transaction_id||"").trim()' in EDGE_SOURCE
    assert 'createBucket(PAYMENT_PROOF_BUCKET' in EDGE_SOURCE
    assert 'public: false' in EDGE_SOURCE
    assert 'Enterprise Plus Tier ($399)' in APP_SOURCE
    assert 'Research Pack ($30 add-on)' in APP_SOURCE


def test_admin_tier_change_does_not_rewrite_identity_or_expiry():
    assert "SET tier = 'Enterprise Plus Tier ($399)'" in ADMIN_TIER_MIGRATION
    assert "WHERE username_lc = 'sho'" in ADMIN_TIER_MIGRATION
    assert "AND role = 'Enterprise Admin'" in ADMIN_TIER_MIGRATION
    assert "SET role =" not in ADMIN_TIER_MIGRATION
    assert "password_hash =" not in ADMIN_TIER_MIGRATION
    assert "subscription_expires_at =" not in ADMIN_TIER_MIGRATION



def test_payment_proofs_are_private_and_server_reviewed():
    assert 'const PAYMENT_PROOF_BUCKET = "subscription-payment-proofs"' in EDGE_SOURCE
    assert 'createBucket(PAYMENT_PROOF_BUCKET' in EDGE_SOURCE
    assert 'public: false' in EDGE_SOURCE
    assert 'createSignedUrl(objectPath,300)' in EDGE_SOURCE
    assert 'await adminSession(String(body.username),String(body.token))' in EDGE_SOURCE
    assert 'MAX_PAYMENT_PROOF_BYTES = 512 * 1024' in EDGE_SOURCE
    assert 'Payment proof content does not match its declared file type.' in EDGE_SOURCE
    assert 'public = false' in PAYMENT_PROOF_MIGRATION
    assert 'file_size_limit = 524288' in PAYMENT_PROOF_MIGRATION
    assert 'AS RESTRICTIVE' in PAYMENT_PROOF_RLS_MIGRATION
    assert "bucket_id <> 'subscription-payment-proofs'" in PAYMENT_PROOF_RLS_MIGRATION
    assert 'WITH CHECK (bucket_id <> ' + "'subscription-payment-proofs'" + ')' in PAYMENT_PROOF_RLS_MIGRATION
    assert "USING (false) WITH CHECK (false)" in PLATFORM_RLS_MIGRATION
    for table in (
        "shoir_platform_artifacts",
        "shoir_platform_events",
        "shoir_platform_jobs",
        "shoir_platform_meta",
        "shoir_platform_records",
    ):
        assert f"ON public.{table}" in PLATFORM_RLS_MIGRATION


def test_admin_receipt_ui_handles_pdf_and_private_storage():
    assert 'edge_admin_payment_proof_url(' in APP_SOURCE
    assert 'st.link_button("Open private payment receipt (expires in 5 minutes)"' in APP_SOURCE
    assert 'Download payment receipt' in APP_SOURCE
    assert '_encode_renewal_proof' in APP_SOURCE
