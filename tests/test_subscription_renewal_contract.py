import re
from pathlib import Path

def _source_contract_contains(source: str, fragment: str) -> bool:
    normalized_source = re.sub(r"\s+", "", source)
    normalized_fragment = re.sub(r"\s+", "", fragment)
    normalized_source = re.sub(r",(?=[)\]}])", "", normalized_source)
    normalized_fragment = re.sub(r",(?=[)\]}])", "", normalized_fragment)
    return normalized_fragment in normalized_source



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
    assert 'subscription_expired_notice' in APP_SOURCE
    assert 'Sign in using the same account to open its renewal page' in APP_SOURCE


def test_renewal_sessions_are_short_lived_and_scoped():
    assert _source_contract_contains(EDGE_SOURCE, 'createSession(row.username_lc,"renewal",60*60*1000)')
    assert _source_contract_contains(EDGE_SOURCE, 'requiredScope:"workspace"|"renewal"|"either"="workspace"')
    assert _source_contract_contains(EDGE_SOURCE, 'scope=data.scope||"workspace"')
    assert _source_contract_contains(EDGE_SOURCE, 'if(requiredScope==="workspace"&&!(row.username_lc==="sho"&&row.role==="Enterprise Admin")&&isExpired(row.subscription_expires_at))')
    assert _source_contract_contains(EDGE_SOURCE, 'getSession(String(body.token),String(body.username),"either")')


def test_workspace_reads_and_writes_require_workspace_scope():
    assert _source_contract_contains(EDGE_SOURCE, 'if(action==="workspace_load"){await getSession(String(body.token),String(body.username));')
    assert _source_contract_contains(EDGE_SOURCE, 'if(action==="workspace_save"){await getSession(String(body.token),String(body.username));')
    assert _source_contract_contains(EDGE_SOURCE, 'async function adminSession(username:string,token:string){const row=await getSession(token,username);')


def test_visible_subscription_countdown_and_renewal_controls_exist():
    assert 'Subscription & Renewal' in APP_SOURCE
    assert 'Time remaining' in APP_SOURCE
    assert 'Subscription: ' in APP_SOURCE
    assert '@st.fragment(run_every="60s")' in APP_SOURCE
    assert '_sidebar_remaining <= 0' in APP_SOURCE
    assert 'save_user_workspace(_expired_user, st.session_state)' in APP_SOURCE
    assert 'st.session_state["subscription_expired_notice"] = True' in APP_SOURCE
    assert 'active_subscription_renewal_form' in APP_SOURCE
    assert 'Payment method: STC Pay QR' in APP_SOURCE
    assert '_active_renew_qr = Image.open("stc_pay_qr.png")' in APP_SOURCE
    assert 'Enter the payment transaction/reference' in APP_SOURCE
    assert 'Transaction / Payment Reference' in APP_SOURCE
    assert '_encode_renewal_proof' in APP_SOURCE
    assert '512 * 1024' in APP_SOURCE
    assert 'edge_admin_payment_proof_url' in APP_SOURCE
    assert _source_contract_contains(EDGE_SOURCE, 'admin_payment_proof_url_session')
    assert _source_contract_contains(EDGE_SOURCE, 'transactionId=String(body.transaction_id||"").trim()')
    assert _source_contract_contains(EDGE_SOURCE, 'Administrator subscription is not eligible for customer renewal.')
    assert _source_contract_contains(EDGE_SOURCE, 'createBucket(PAYMENT_PROOF_BUCKET')
    assert _source_contract_contains(EDGE_SOURCE, 'public: false')
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
    assert _source_contract_contains(EDGE_SOURCE, 'const PAYMENT_PROOF_BUCKET = "subscription-payment-proofs"')
    assert _source_contract_contains(EDGE_SOURCE, 'createBucket(PAYMENT_PROOF_BUCKET')
    assert _source_contract_contains(EDGE_SOURCE, 'public: false')
    assert _source_contract_contains(EDGE_SOURCE, 'createSignedUrl(objectPath,300)')
    assert _source_contract_contains(EDGE_SOURCE, 'await adminSession(String(body.username),String(body.token))')
    assert _source_contract_contains(EDGE_SOURCE, 'MAX_PAYMENT_PROOF_BYTES = 512 * 1024')
    assert _source_contract_contains(EDGE_SOURCE, 'Payment proof content does not match its declared file type.')
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
    assert 'except ImportError:' in APP_SOURCE
    assert 'Private receipt preview is not available in this deployment version.' in APP_SOURCE
    assert 'st.link_button("Open private payment receipt (expires in 5 minutes)"' in APP_SOURCE
    assert 'Download payment receipt' in APP_SOURCE
    assert '_encode_renewal_proof' in APP_SOURCE


def test_admin_decline_uses_atomic_pending_request_decision():
    decline_branch = EDGE_SOURCE.split(
        'if (action === "admin_decline_session") {', 1
    )[1].split(
        'return response({ error: "Unknown action." }, 400);', 1
    )[0]
    migration = (
        ROOT / "supabase" / "migrations" /
        "20261019140600_atomic_subscription_request_decisions.sql"
    ).read_text(encoding="utf-8")

    assert "Number.isSafeInteger(id)" in decline_branch
    assert "id <= 0" in decline_branch
    assert _source_contract_contains(
        decline_branch,
        'supabase.rpc("shoir_finalize_subscription_request",{p_request_id:id,p_decision:"Declined"})',
    )
    assert "Pending request not found or already processed." in decline_branch
    assert "FOR UPDATE" in migration
    assert "request_row.status IS DISTINCT FROM 'Pending'" in migration
    assert "REVOKE ALL ON FUNCTION public.shoir_finalize_subscription_request(bigint, text)" in migration
    assert "GRANT EXECUTE ON FUNCTION public.shoir_finalize_subscription_request(bigint, text)" in migration


def test_subscription_decision_migration_is_transactional_and_pending_only():
    migration = (
        ROOT / "supabase" / "migrations" /
        "20261019140600_atomic_subscription_request_decisions.sql"
    ).read_text(encoding="utf-8")

    assert "SECURITY INVOKER" in migration
    assert "SELECT *" in migration and "FOR UPDATE" in migration
    assert "status = 'Declined'" in migration
    assert "status = 'Approved'" in migration
    assert "status = 'Pending'" in migration
    assert "ON CONFLICT (username_lc) DO UPDATE SET" in migration
    assert "password_hash = current_account.password_hash" in migration
    assert "role = current_account.role" in migration
    assert "created_at = current_account.created_at" in migration
    assert "INTERVAL '30 days'" in migration





def test_registration_submit_validates_proof_before_any_persistence():
    registration_block = APP_SOURCE.split(
        'if st.button("Send Verification Request", type="primary", key="btn_send_request"):', 1
    )[1].split(
        "# TAB 3: EXPLORE THE MODULES", 1
    )[0]

    assert registration_block.index("_encode_renewal_proof(uploaded_screenshot)") < registration_block.index("INSERT INTO pending_payments")
    assert registration_block.index("insert_remote_request({") < registration_block.index("INSERT INTO pending_payments")
    assert '"proof_base64": _registration_proof_base64' in registration_block
    assert '"proof_content_type": _registration_proof_content_type' in registration_block
    assert "Password must be between 8 and 128 characters." in registration_block


def test_registration_preflight_does_not_disclose_durable_account_existence():
    edge_block = EDGE_SOURCE.split(
        'if (action === "account_exists") {', 1
    )[1].split(
        'if (action === "register_request") {', 1
    )[0]
    registration_block = APP_SOURCE.split(
        'if st.button("Send Verification Request", type="primary", key="btn_send_request"):', 1
    )[1].split(
        "# TAB 3: EXPLORE THE MODULES", 1
    )[0]

    assert "return response({ exists: false });" in edge_block
    assert "getAccount(" not in edge_block
    assert "shoir_subscription_requests" not in edge_block
    assert "(not _durable_accounts_ready and local_account_exists(reg_name))" in registration_block
