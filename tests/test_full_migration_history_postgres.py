"""Replay the versioned Shoir-IE SQL history on a disposable local PostgreSQL database.

The test refuses non-local servers and only accepts the isolated shoir_test service
used by the Subscription transaction integration workflow. Supabase-managed Auth
and Storage schemas are represented by minimal local compatibility tables; this
is migration-history integration evidence, not a hosted Supabase staging replay.
"""
from __future__ import annotations

import json
import os
from pathlib import Path
from urllib.parse import unquote, urlparse

import pytest

try:
    import psycopg2
except ImportError:  # pragma: no cover
    psycopg2 = None

DATABASE_URL = os.environ.get("SHOIR_TEST_POSTGRES_URL", "")
ROOT = Path(__file__).resolve().parents[1]
MIGRATIONS = ROOT / "supabase" / "migrations"
TARGET_DATABASE = "shoir_migration_replay_test"
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
pytestmark = pytest.mark.skipif(
    not DATABASE_URL or psycopg2 is None,
    reason="requires the isolated local shoir_test PostgreSQL integration workflow",
)


def _parsed_url():
    parsed = urlparse(DATABASE_URL)
    if parsed.hostname not in {"localhost", "127.0.0.1", "::1"}:
        pytest.fail("Refusing migration replay against a non-local PostgreSQL server.")
    if (parsed.path or "").lstrip("/") != "shoir_test":
        pytest.fail("Refusing migration replay outside the disposable shoir_test database.")
    return parsed


def _connect_base():
    _parsed_url()
    return psycopg2.connect(DATABASE_URL, connect_timeout=5)


def _target_url() -> str:
    parsed = _parsed_url()
    return parsed._replace(path=f"/{TARGET_DATABASE}").geturl()


def _fetchone(conn, sql: str, args=()):
    with conn.cursor() as cursor:
        cursor.execute(sql, args)
        return cursor.fetchone()


def test_versioned_migration_history_replays_from_clean_local_postgres():
    parsed = _parsed_url()
    migration_files = sorted(MIGRATIONS.glob("*.sql"))
    versions = [path.name.split("_", 1)[0] for path in migration_files]
    assert versions == EXPECTED_VERSIONS, (
        "Tracked migration source history has a missing, unexpected or out-of-order "
        f"version. Expected {EXPECTED_VERSIONS}; found {versions}."
    )

    base = _connect_base()
    try:
        base.autocommit = True
        with base.cursor() as cursor:
            cursor.execute(
                "DO $$ BEGIN CREATE ROLE anon; EXCEPTION WHEN duplicate_object THEN NULL; END $$;"
            )
            cursor.execute(
                "DO $$ BEGIN CREATE ROLE authenticated; EXCEPTION WHEN duplicate_object THEN NULL; END $$;"
            )
            cursor.execute(
                "DO $$ BEGIN CREATE ROLE service_role; EXCEPTION WHEN duplicate_object THEN NULL; END $$;"
            )
            # Supabase service_role has BYPASSRLS in the hosted platform. This
            # adjustment is confined to the disposable local PostgreSQL service.
            cursor.execute("ALTER ROLE service_role BYPASSRLS;")
            cursor.execute(f'DROP DATABASE IF EXISTS "{TARGET_DATABASE}" WITH (FORCE);')
            cursor.execute(f'CREATE DATABASE "{TARGET_DATABASE}";')
        target = psycopg2.connect(_target_url(), connect_timeout=5)
        try:
            with target.cursor() as cursor:
                # Minimal local shims for Supabase-managed Storage schema objects.
                # These are test-only tables, contain no production data, and model
                # only the columns required by the tracked Storage migrations.
                cursor.execute("CREATE SCHEMA storage;")
                cursor.execute(
                    """
                    CREATE TABLE storage.buckets (
                        id text PRIMARY KEY,
                        name text NOT NULL UNIQUE,
                        public boolean NOT NULL DEFAULT false,
                        file_size_limit bigint,
                        allowed_mime_types text[]
                    );
                    """
                )
                cursor.execute(
                    """
                    CREATE TABLE storage.objects (
                        id uuid PRIMARY KEY DEFAULT gen_random_uuid(),
                        bucket_id text NOT NULL,
                        name text NOT NULL,
                        owner_id text,
                        created_at timestamptz NOT NULL DEFAULT now(),
                        UNIQUE (bucket_id, name)
                    );
                    ALTER TABLE storage.objects ENABLE ROW LEVEL SECURITY;
                    GRANT USAGE, CREATE ON SCHEMA storage TO service_role;
                    GRANT ALL ON ALL TABLES IN SCHEMA storage TO service_role;
                    GRANT ALL ON ALL SEQUENCES IN SCHEMA storage TO service_role;
                    GRANT USAGE, CREATE ON SCHEMA public TO service_role;
                    ALTER DEFAULT PRIVILEGES FOR ROLE postgres IN SCHEMA public
                        GRANT ALL ON TABLES TO service_role;
                    ALTER DEFAULT PRIVILEGES FOR ROLE postgres IN SCHEMA public
                        GRANT ALL ON SEQUENCES TO service_role;
                    ALTER DEFAULT PRIVILEGES FOR ROLE postgres IN SCHEMA storage
                        GRANT ALL ON TABLES TO service_role;
                    ALTER DEFAULT PRIVILEGES FOR ROLE postgres IN SCHEMA storage
                        GRANT ALL ON SEQUENCES TO service_role;
                    """
                )
            target.commit()

            for migration in migration_files:
                sql = migration.read_text(encoding="utf-8")
                if not sql.strip():
                    pytest.fail(f"Migration file is empty: {migration.name}")
                with target.cursor() as cursor:
                    cursor.execute(sql)
                target.commit()

            # Required schema objects and the correct versioned function contracts.
            expected_tables = {
                "shoir_accounts",
                "shoir_pending_credentials",
                "shoir_sessions",
                "shoir_subscription_requests",
                "shoir_referrals",
                "shoir_workspace_states",
                "shoir_login_throttle",
                "shoir_platform_meta",
                "shoir_platform_records",
                "shoir_platform_events",
                "shoir_platform_artifacts",
                "shoir_platform_jobs",
            }
            rows = _fetchone(
                target,
                """
                SELECT array_agg(table_name::text ORDER BY table_name)
                FROM information_schema.tables
                WHERE table_schema='public' AND table_type='BASE TABLE';
                """,
            )[0]
            actual_tables = set(rows or [])
            assert expected_tables.issubset(actual_tables), (
                f"Migration replay missed required tables: {sorted(expected_tables - actual_tables)}"
            )

            required_columns = {
                "shoir_sessions": {"scope", "token_hash", "username_lc", "expires_at"},
                "shoir_accounts": {"username_lc", "password_hash", "role", "tier", "subscription_expires_at"},
                "shoir_subscription_requests": {"id", "request_type", "status", "approved_at", "terms_accepted", "terms_version", "accepted_at"},
                "shoir_referrals": {"referrer_username_lc", "referred_username_lc", "referral_code", "status", "qualified_at"},
            }
            for table, expected in required_columns.items():
                columns = _fetchone(
                    target,
                    """
                    SELECT array_agg(column_name::text ORDER BY column_name)
                    FROM information_schema.columns
                    WHERE table_schema='public' AND table_name=%s;
                    """,
                    (table,),
                )[0]
                assert expected.issubset(set(columns or [])), (
                    f"Migration replay is missing columns from {table}: {sorted(expected - set(columns or []))}"
                )

            unique_code_index = _fetchone(
                target,
                """
                SELECT i.indisunique
                FROM pg_index i
                JOIN pg_class idx ON idx.oid = i.indexrelid
                JOIN pg_class tbl ON tbl.oid = i.indrelid
                JOIN pg_namespace ns ON ns.oid = tbl.relnamespace
                WHERE ns.nspname = 'public'
                  AND tbl.relname = 'shoir_accounts'
                  AND idx.relname = 'idx_shoir_accounts_affiliate_code_unique';
                """,
            )
            assert unique_code_index == (True,), (
                "Populated referral codes must be protected by a unique partial index."
            )

            for table in ("shoir_accounts", "shoir_pending_credentials", "shoir_sessions",
                          "shoir_subscription_requests", "shoir_referrals", "shoir_workspace_states", "shoir_login_throttle"):
                assert _fetchone(
                    target,
                    """
                    SELECT c.relrowsecurity
                    FROM pg_class c JOIN pg_namespace n ON n.oid=c.relnamespace
                    WHERE n.nspname='public' AND c.relname=%s;
                    """,
                    (table,),
                )[0] is True, f"RLS is not enabled on {table}"

                assert _fetchone(
                    target,
                    "SELECT has_table_privilege('anon', %s, 'SELECT');",
                    (f"public.{table}",),
                )[0] is False, f"anon has a direct SELECT grant on {table}"
                assert _fetchone(
                    target,
                    "SELECT has_table_privilege('authenticated', %s, 'SELECT');",
                    (f"public.{table}",),
                )[0] is False, f"authenticated has a direct SELECT grant on {table}"

            assert _fetchone(
                target,
                "SELECT public IS FALSE FROM storage.buckets WHERE id='subscription-payment-proofs';",
            )[0] is True, "Subscription payment proof bucket is not private after replay."

            for signature in (
                "public.shoir_check_login_throttle(text,text,integer,integer,integer)",
                "public.shoir_finalize_subscription_request(bigint,text)",
                "public.shoir_create_registration_request(text,text,text,text,text,text,text,text)",
            ):
                assert _fetchone(
                    target,
                    "SELECT to_regprocedure(%s) IS NOT NULL;",
                    (signature,),
                )[0] is True, f"Required database function is missing after replay: {signature}"
                assert _fetchone(
                    target,
                    "SELECT has_function_privilege('service_role', %s::regprocedure, 'EXECUTE');",
                    (signature,),
                )[0] is True, f"service_role cannot execute required function: {signature}"
                assert _fetchone(
                    target,
                    "SELECT has_function_privilege('anon', %s::regprocedure, 'EXECUTE');",
                    (signature,),
                )[0] is False, f"anon can execute privileged function: {signature}"
                assert _fetchone(
                    target,
                    "SELECT has_function_privilege('authenticated', %s::regprocedure, 'EXECUTE');",
                    (signature,),
                )[0] is False, f"authenticated can execute privileged function: {signature}"

            # Exercise the RPCs as the same least-privilege service_role used
            # by the Edge Function, not as the postgres migration owner.
            username = "shoir-e2e-replay"
            password_hash = ("a" * 32) + "$" + ("b" * 64)
            # psycopg2 connections default to autocommit=False; keep the current transaction mode.
            try:
                with target.cursor() as cursor:
                    cursor.execute("SET ROLE service_role;")
                    cursor.execute(
                        """
                        SELECT public.shoir_create_registration_request(
                            %s, %s, %s, %s, %s, %s, %s, %s
                        );
                        """,
                        (
                            username,
                            username.lower(),
                            password_hash,
                            "migration-replay@example.invalid",
                            "Starter Tier ($29)",
                            "STC Pay (QR)",
                            "SYNTHETIC-REPLAY-REFERENCE",
                            "storage://subscription-payment-proofs/renewals/synthetic.png",
                        ),
                    )
                    request_result = cursor.fetchone()[0]
                    replay_request = request_result if isinstance(request_result, dict) else json.loads(request_result)
                    replay_request_id = int(replay_request["request_id"])
                    cursor.execute("SAVEPOINT shoir_missing_consent_approval")
                    with pytest.raises(psycopg2.Error) as blocked_approval:
                        cursor.execute(
                            "UPDATE public.shoir_subscription_requests SET status='Approved' WHERE id=%s;",
                            (replay_request_id,),
                        )
                    assert blocked_approval.value.pgcode == "23514"
                    cursor.execute("ROLLBACK TO SAVEPOINT shoir_missing_consent_approval")
                    cursor.execute(
                        """
                        UPDATE public.shoir_subscription_requests
                           SET terms_accepted=TRUE,
                               terms_version='2026-10-21-beta-v1',
                               privacy_policy_version='2026-10-21-v1',
                               refund_policy_version='2026-10-23-v2',
                               cookie_policy_version='2026-10-21-v1',
                               accepted_at=NOW()
                         WHERE id=%s;
                        """,
                        (replay_request_id,),
                    )
                    cursor.execute(
                        "SELECT public.shoir_finalize_subscription_request(%s, 'Approved');",
                        (replay_request_id,),
                    )
                    approval_result = cursor.fetchone()[0]
                    cursor.execute("RESET ROLE;")
                target.commit()
            except Exception:
                target.rollback()
                raise
            if isinstance(request_result, str):
                request_result = json.loads(request_result)
            assert request_result.get("ok") is True
            request_id = int(request_result["request_id"])
            if isinstance(approval_result, str):
                approval_result = json.loads(approval_result)
            assert approval_result.get("ok") is True
            assert approval_result.get("status") == "Approved"
            assert _fetchone(
                target,
                "SELECT status FROM public.shoir_subscription_requests WHERE id=%s;",
                (request_id,),
            )[0] == "Approved"
            assert _fetchone(
                target,
                "SELECT count(*) FROM public.shoir_accounts WHERE username_lc=%s;",
                (username,),
            )[0] == 1
        finally:
            target.close()
    finally:
        # The replay database is uniquely test-named and entirely disposable.
        if not base.closed:
            try:
                base.autocommit = True
                with base.cursor() as cursor:
                    cursor.execute(f'DROP DATABASE IF EXISTS "{TARGET_DATABASE}" WITH (FORCE);')
            finally:
                base.close()
