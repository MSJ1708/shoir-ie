"""Regression guard for production hotfix privileged-session fail-closed behavior."""
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
SOURCE = ROOT / "supabase" / "production-hotfix-v8" / "index.ts"


def test_admin_session_rechecks_global_protected_admin_invariant():
    source = SOURCE.read_text(encoding="utf-8")
    start = source.index("async function adminSession(")
    end = source.index("\n}", start) + 2
    admin_session = source[start:end]

    assert "canonicalMasterAdminConfigurationIsValid()" in admin_session
    assert "Authentication protection is temporarily unavailable." in admin_session
    assert "supabase.from(\"shoir_accounts\").update" not in admin_session

def test_subscription_approval_cannot_overwrite_the_protected_administrator():
    source = SOURCE.read_text(encoding="utf-8")
    start = source.index('if (\n      action === "admin_approve_session"')
    end = source.index('if (action === "admin_decline_session")', start)
    approval = source[start:end]

    assert "const protectedTarget =" in approval
    assert "isProtectedAdministratorTarget(" in approval
    assert "if (protectedTarget)" in approval
    assert "}, 403);" in approval
    assert approval.index("if (protectedTarget)") < approval.index(".upsert(payload")
