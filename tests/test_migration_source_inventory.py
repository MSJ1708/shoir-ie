"""Fast source-integrity checks for the versioned Supabase migration set."""

from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
MIGRATIONS = ROOT / "supabase" / "migrations"
EXPECTED_VERSIONS = [
    "20260925093314",
    "20260925093546",
    "20260925093748",
    "20260925094637",
    "20260925125508",
    "20260925131100",
    "20260929185528",
    "20260929190456",
    "20261018194225",
    "20261018204013",
    "20261018204217",
    "20261018204857",
    "20261019124815",
    "20261019140600",
    "20261021130000",
    "20261022110000",
    "20261023130000",
    "20261026110000",
]


def test_all_recorded_migration_versions_have_tracked_source_files():
    files = sorted(MIGRATIONS.glob("*.sql"))
    versions = [path.name.split("_", 1)[0] for path in files]
    assert versions == EXPECTED_VERSIONS, (
        "A versioned Supabase migration is missing, unexpected or misordered. "
        f"Expected {EXPECTED_VERSIONS}; found {versions}."
    )


def test_bootstrap_migration_does_not_embed_static_master_admin_credentials():
    source = (MIGRATIONS / "20260925093748_seed_shoir_admin_account.sql").read_text(
        encoding="utf-8"
    ).casefold()
    assert "select 1;" in source
    assert "insert into shoir_accounts" not in source
    assert "password_hash" not in source
    assert "557e828e5d76f4cf" not in source


def test_transactional_subscription_migration_is_present_and_guarded():
    source = (
        MIGRATIONS
        / "20261019140600_atomic_subscription_request_decisions.sql"
    ).read_text(encoding="utf-8")
    assert "FOR UPDATE" in source
    assert "p_decision NOT IN ('Approved', 'Declined')" in source
    assert "shoir_create_registration_request" in source
    assert "REVOKE ALL ON FUNCTION public.shoir_finalize_subscription_request" in source


def test_beta_acceptance_guard_migration_enforces_all_current_notice_versions():
    source = (MIGRATIONS / "20261022110000_enforce_beta_legal_acceptance.sql").read_text(encoding="utf-8")
    assert "BEFORE UPDATE OF status" in source
    assert "privacy_policy_version IS DISTINCT FROM" in source
    assert "refund_policy_version IS DISTINCT FROM" in source
    assert "cookie_policy_version IS DISTINCT FROM" in source
    assert "accepted_at IS NULL" in source


def test_refund_policy_v2_guard_migration_requires_current_refund_version():
    source = (MIGRATIONS / "20261023130000_refresh_refund_policy_acceptance_version.sql").read_text(encoding="utf-8")
    assert "refund_policy_version IS DISTINCT FROM '2026-10-23-v2'" in source
    assert "BEFORE UPDATE OF status" in source


def test_additive_referral_migration_does_not_rewrite_existing_account_identifiers():
    source = (
        MIGRATIONS / "20261026110000_safe_beta_legal_referrals.sql"
    ).read_text(encoding="utf-8").casefold()
    # Comments and safe lookup indexes may mention the existing code column.
    # The invariant is that this additive migration performs no data rewrite.
    executable_sql = "\n".join(line.split("--", 1)[0] for line in source.splitlines())
    assert "create table if not exists public.shoir_referrals" in executable_sql
    assert "update public.shoir_accounts" not in executable_sql
    assert "set affiliate_code" not in executable_sql
    assert "set updated_at" not in executable_sql
    assert "create unique index if not exists idx_shoir_accounts_affiliate_code_trimmed_unique" in executable_sql
    assert "on public.shoir_accounts (lower(btrim(affiliate_code)))" in executable_sql
    assert "where affiliate_code is not null and btrim(affiliate_code) <> ''" in executable_sql
    assert "revoke all on table public.shoir_referrals from public, anon, authenticated" in executable_sql
