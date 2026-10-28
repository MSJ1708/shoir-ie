"""Contract guards for the schema-compatible production-v8 security hotfix."""
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
HOTFIX = ROOT / "supabase" / "production-hotfix-v8"
INDEX = HOTFIX / "index.ts"
SECURITY = HOTFIX / "security.ts"
DENO_TESTS = HOTFIX / "security_test.ts"


def test_v8_hotfix_removes_wildcard_cors_and_login_time_admin_repair():
    source = INDEX.read_text(encoding="utf-8")
    assert '"Access-Control-Allow-Origin": "*"' not in source
    assert "corsHeadersForOrigin(origin)" in source
    assert "isAllowedBrowserOrigin(origin)" in source
    assert "Origin not allowed." in source
    assert "status: 204" in source
    assert "hasCanonicalMasterAdminInvariant" in source
    assert ".update({ tier: adminTier, updated_at: new Date().toISOString() })" not in source
    assert "protected administrator configuration requires manual review" in source.casefold()


def test_v8_hotfix_does_not_depend_on_missing_production_schema():
    source = INDEX.read_text(encoding="utf-8")
    assert 'from("shoir_referrals")' not in source
    assert "terms_accepted" not in source
    assert "privacy_policy_version" not in source
    assert "refund_policy_version" not in source
    assert "cookie_policy_version" not in source


def test_v8_hotfix_has_explicit_origin_and_admin_regression_cases():
    security = SECURITY.read_text(encoding="utf-8")
    tests = DENO_TESTS.read_text(encoding="utf-8")
    assert "https://shoir-ie-app.streamlit.app" in security
    assert "Access-Control-Allow-Origin" in security
    assert 'origin === null' in security
    assert "2099-01-01T00:00:00Z" in security
    assert "unapproved origin" in tests
    assert "reserved administrator invariant read-only" in tests
