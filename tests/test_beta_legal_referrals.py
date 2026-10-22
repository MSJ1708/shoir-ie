from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
APP = (ROOT / "app.py").read_text(encoding="utf-8")
TERMS = (ROOT / "docs" / "TERMS_AND_CONDITIONS.md").read_text(encoding="utf-8")
PRIVACY = (ROOT / "docs" / "PRIVACY_POLICY.md").read_text(encoding="utf-8")
EDGE = (ROOT / "supabase" / "functions" / "shoir-persistence" / "index.ts").read_text(encoding="utf-8")
MIGRATION = (
    ROOT / "supabase" / "migrations" / "20261021130000_shoir_beta_legal_referrals.sql"
).read_text(encoding="utf-8")
STORE = (ROOT / "durable_account_store.py").read_text(encoding="utf-8")
README = (ROOT / "README.md").read_text(encoding="utf-8")


def test_beta_status_and_independent_validation_are_visible():
    assert "BETA — Shoir-IE is still in testing." in APP
    assert "beta testing and active development" in TERMS.lower()
    assert "independently validate source data" in TERMS.lower()
    assert "safety-critical" in TERMS.lower()
    assert "nothing in these terms excludes or limits liability" in TERMS.lower()


def test_no_unsupported_referral_discount_or_fake_stats_remain_in_active_ui():
    lowered = APP.lower()
    assert "both you and the new user receive a 15% discount" not in lowered
    assert "total referrals:** <span class='blue-metric'>3" not in lowered
    assert "1 free 15% month" not in lowered
    assert "no discount, free month, commission, cash payment or other reward is currently offered or guaranteed" in lowered
    assert 'reg_referral_code = st.text_input("referral code (optional)"' in lowered


def test_registration_requires_and_records_versioned_acceptance():
    assert "not accepted_terms" in APP
    assert 'st.session_state.get("_registration_accepted_terms_version") != TERMS_VERSION' in APP
    assert '"terms_accepted": True' in APP
    assert '"terms_version": TERMS_VERSION' in APP
    assert "body.terms_accepted !== true" in EDGE
    assert 'String(body.terms_version || "") !== TERMS_VERSION' in EDGE
    assert "terms_accepted: true" in EDGE
    assert "legal_acceptance_recorded" in EDGE
    assert "accepted_at TIMESTAMPTZ" in MIGRATION
    assert "privacy_policy_version TEXT" in MIGRATION
    assert "privacy_policy_version" in STORE
    assert "refund_policy_version" in STORE
    assert "cookie_policy_version" in STORE
    assert "accepted_at" in STORE


def test_referral_codes_are_server_checked_attributed_and_qualified_manually():
    assert 'action === "referral_summary_session"' in EDGE
    assert "referrerUsernameLc" in EDGE
    assert '.from(\n          "shoir_referrals",\n        ).insert({' in EDGE
    assert 'status: "Qualified"' in EDGE
    assert 'status: "Declined"' in EDGE
    assert 'status: "Pending"' in EDGE
    assert 'def edge_referral_summary(username: str, token: str)' in STORE
    assert "referred_username_lc TEXT NOT NULL UNIQUE" in MIGRATION
    assert "shoir_referrals_no_self_referral" in MIGRATION
    assert "ALTER TABLE public.shoir_referrals ENABLE ROW LEVEL SECURITY" in MIGRATION
    assert "FROM PUBLIC, anon, authenticated" in MIGRATION


def test_privacy_notice_does_not_promise_no_third_party_processing():
    assert "Streamlit" in PRIVACY
    assert "Supabase" in PRIVACY
    assert "Anthropic" in PRIVACY
    assert "may occur outside the Kingdom of Saudi Arabia" in PRIVACY
    assert "We do not promise that third-party providers never retain prompts" in PRIVACY


def test_terms_have_a_real_governing_law_clause_and_no_template_placeholder():
    assert "Kingdom of Saudi Arabia" in TERMS
    assert "state the jurisdiction whose law governs this agreement" not in TERMS.lower()
    assert "No contract wording can guarantee that a claim will never be brought" in TERMS


def test_live_readme_is_marked_beta_and_links_notices():
    assert "BETA — TESTING IN PROGRESS" in README
    assert "docs/TERMS_AND_CONDITIONS.md" in README
    assert "docs/PRIVACY_POLICY.md" in README
    assert "docs/LEGAL_RISK_REGISTER.md" in README
