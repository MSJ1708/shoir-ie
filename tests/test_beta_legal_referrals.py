"""Source invariants for Shoir-IE beta safeguards."""
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
APP = (ROOT / "app.py").read_text(encoding="utf-8")
TERMS = (ROOT / "docs" / "TERMS_AND_CONDITIONS.md").read_text(encoding="utf-8")
PRIVACY = (ROOT / "docs" / "PRIVACY_POLICY.md").read_text(encoding="utf-8")
REFUND = (ROOT / "docs" / "REFUND_POLICY.md").read_text(encoding="utf-8")
README = (ROOT / "README.md").read_text(encoding="utf-8")
EDGE = (ROOT / "supabase" / "functions" / "shoir-persistence" / "index.ts").read_text(encoding="utf-8")
MIGRATION = (ROOT / "supabase" / "migrations" / "20261021130000_shoir_beta_legal_referrals.sql").read_text(encoding="utf-8")
GUARD = (ROOT / "supabase" / "migrations" / "20261022110000_enforce_beta_legal_acceptance.sql").read_text(encoding="utf-8")
STORE = (ROOT / "durable_account_store.py").read_text(encoding="utf-8")


def test_beta_terms_disclose_limits_and_preserve_mandatory_rights():
    assert "BETA — Shoir-IE is still in testing." in APP
    assert "beta testing and active development" in TERMS.lower()
    assert "independently validate source data" in TERMS.lower()
    assert "safety-critical" in TERMS.lower()
    assert "nothing in these terms excludes or limits liability" in TERMS.lower()
    assert "Kingdom of Saudi Arabia" in TERMS
    assert "No contract wording can guarantee that a claim will never be brought" in TERMS


def test_referral_codes_only_record_attribution():
    lowered = APP.lower()
    assert "both you and the new user receive a 15% discount" not in lowered
    assert "1 free 15% month" not in lowered
    assert "no discount, free month, commission, cash payment or other reward is currently offered or guaranteed" in lowered
    assert 'action === "referral_summary_session"' in EDGE
    assert "shoir_referrals" in EDGE
    assert "def edge_referral_summary(username: str, token: str)" in STORE


def test_signup_acceptance_is_versioned_and_enforced_by_the_database():
    for field in ("terms_version", "privacy_policy_version", "refund_policy_version", "cookie_policy_version"):
        assert field in APP
        assert field in EDGE
        assert field in STORE
    assert "terms_accepted" in EDGE
    assert "accepted_at" in EDGE
    assert "accepted_at" in MIGRATION
    assert "accepted_at" in STORE
    assert "shoir_require_legal_acceptance_before_approval" in GUARD


def test_privacy_and_refund_notices_are_truthful_about_providers_and_payment():
    assert "Streamlit" in PRIVACY
    assert "Supabase" in PRIVACY
    assert "Anthropic" in PRIVACY
    assert "may occur outside the Kingdom of Saudi Arabia" in PRIVACY
    assert "We do not promise that third-party providers never retain prompts" in PRIVACY
    assert "manually reviewed" in REFUND.lower()
    assert "BETA — TESTING IN PROGRESS" in README
    assert "docs/TERMS_AND_CONDITIONS.md" in README
    assert "docs/PRIVACY_POLICY.md" in README
