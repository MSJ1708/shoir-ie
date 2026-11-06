"""Replay the versioned Shoir-IE SQL history on a disposable local PostgreSQL database.

The test refuses non-local servers and only accepts the isolated shoir_test service
used by the Subscription transaction integration workflow. Supabase-managed Auth
and Storage schemas are represented by minimal local compatibility tables; this
is migration-history integration evidence, not a hosted Supabase staging replay.
"""
from __future__ import annotations

import datetime
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
    "20261104183132",
    "20261104184453",
    "20261104192112",
    "20261104192857",
    "20261105101231",
    "20261105111832",
    "20261106120000",
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


SAFE_MIGRATION_TARGET_DATABASE = "shoir_safe_referral_preservation_test"


def test_additive_referral_migration_preserves_existing_codes_and_timestamps():
    """Exercise the additive migration against existing synthetic account rows."""
    _parsed_url()
    base = _connect_base()
    target = None
    try:
        base.autocommit = True
        with base.cursor() as cursor:
            cursor.execute(
                "SELECT rolname FROM pg_roles WHERE rolname = ANY(%s);",
                (["anon", "authenticated", "service_role"],),
            )
            existing_roles = {row[0] for row in cursor.fetchall()}
            for role in ("anon", "authenticated", "service_role"):
                if role not in existing_roles:
                    cursor.execute(f"CREATE ROLE {role};")
            cursor.execute("ALTER ROLE service_role BYPASSRLS;")
            cursor.execute(
                f'DROP DATABASE IF EXISTS "{SAFE_MIGRATION_TARGET_DATABASE}" WITH (FORCE);'
            )
            cursor.execute(f'CREATE DATABASE "{SAFE_MIGRATION_TARGET_DATABASE}";')

        parsed = _parsed_url()
        target_url = parsed._replace(
            path=f"/{SAFE_MIGRATION_TARGET_DATABASE}"
        ).geturl()
        target = psycopg2.connect(target_url, connect_timeout=5)
        with target.cursor() as cursor:
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

        # Build the account/request schema immediately before the historical
        # data-rewriting referral migration. Do not execute that historical file.
        base_migrations = [
            migration for migration in sorted(MIGRATIONS.glob("*.sql"))
            if migration.name.split("_", 1)[0] < "20261021130000"
        ]
        assert base_migrations, "No pre-referral schema migrations were found."
        for migration in base_migrations:
            sql = migration.read_text(encoding="utf-8")
            if not sql.strip():
                pytest.fail(f"Migration file is empty: {migration.name}")
            with target.cursor() as cursor:
                cursor.execute(sql)
            target.commit()

        with target.cursor() as cursor:
            cursor.executemany(
                """
                INSERT INTO public.shoir_accounts (
                    username, username_lc, password_hash, role, tier, email,
                    created_at, subscription_expires_at, affiliate_code, active, updated_at
                ) VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s);
                """,
                [
                    (
                        "keep-code", "keep-code", ("a" * 32) + "$" + ("b" * 64),
                        "User", "Starter Tier ($29)", "keep-code@example.invalid",
                        "2020-01-01T00:00:00Z", "2099-01-01T00:00:00Z",
                        "KEEP-CASE-001", True, "2021-01-02T03:04:05Z",
                    ),
                    (
                        "blank-code-a", "blank-code-a", ("c" * 32) + "$" + ("d" * 64),
                        "User", "Starter Tier ($29)", "blank-a@example.invalid",
                        "2020-02-01T00:00:00Z", "2099-01-01T00:00:00Z",
                        "", True, "2021-02-03T04:05:06Z",
                    ),
                    (
                        "blank-code-b", "blank-code-b", ("e" * 32) + "$" + ("f" * 64),
                        "User", "Starter Tier ($29)", "blank-b@example.invalid",
                        "2020-03-01T00:00:00Z", "2099-01-01T00:00:00Z",
                        None, True, "2021-03-04T05:06:07Z",
                    ),
                    (
                        "legacy-code", "legacy-code", ("g" * 32) + "$" + ("h" * 64),
                        "User", "Starter Tier ($29)", "legacy@example.invalid",
                        "2020-04-01T00:00:00Z", "2099-01-01T00:00:00Z",
                        "AFF-LEGACY-15", True, "2021-04-05T06:07:08Z",
                    ),
                ],
            )
        target.commit()

        before = _fetchone(
            target,
            """
            SELECT array_agg(
                ROW(username_lc, affiliate_code, updated_at)::text
                ORDER BY username_lc
            )
            FROM public.shoir_accounts;
            """,
        )[0]

        safe_migration = MIGRATIONS / "20261026110000_safe_beta_legal_referrals.sql"
        with target.cursor() as cursor:
            cursor.execute(safe_migration.read_text(encoding="utf-8"))
        target.commit()

        after = _fetchone(
            target,
            """
            SELECT array_agg(
                ROW(username_lc, affiliate_code, updated_at)::text
                ORDER BY username_lc
            )
            FROM public.shoir_accounts;
            """,
        )[0]
        assert after == before, (
            "The additive migration rewrote existing affiliate_code or updated_at values."
        )

        index = _fetchone(
            target,
            """
            SELECT i.indisunique, pg_get_expr(i.indpred, i.indrelid),
                   pg_get_indexdef(i.indexrelid)
            FROM pg_index i
            JOIN pg_class idx ON idx.oid = i.indexrelid
            JOIN pg_class tbl ON tbl.oid = i.indrelid
            JOIN pg_namespace ns ON ns.oid = tbl.relnamespace
            WHERE ns.nspname = 'public'
              AND tbl.relname = 'shoir_accounts'
              AND idx.relname = 'idx_shoir_accounts_affiliate_code_trimmed_unique';
            """,
        )
        assert (
            index
            and index[0] is True
            and "affiliate_code IS NOT NULL" in index[1]
            and "lower(btrim(affiliate_code))" in index[2].casefold()
        ), (
            "The additive migration must create a unique partial index for "
            "whitespace-normalized populated codes."
        )

        # A case-insensitive duplicate must be rejected by PostgreSQL itself,
        # not just by an application-level pre-check.
        with target.cursor() as cursor:
            cursor.execute("SAVEPOINT referral_duplicate_guard")
            with pytest.raises(psycopg2.Error) as duplicate_error:
                cursor.execute(
                    "UPDATE public.shoir_accounts SET affiliate_code=%s WHERE username_lc=%s;",
                    (" KEEP-CASE-001 ", "legacy-code"),
                )
            assert duplicate_error.value.pgcode == "23505"
            cursor.execute("ROLLBACK TO SAVEPOINT referral_duplicate_guard")
        target.commit()

        after_duplicate_attempt = _fetchone(
            target,
            """
            SELECT array_agg(
                ROW(username_lc, affiliate_code, updated_at)::text
                ORDER BY username_lc
            )
            FROM public.shoir_accounts;
            """,
        )[0]
        assert after_duplicate_attempt == before, (
            "A rejected duplicate attempt must not change any account code or timestamp."
        )
    finally:
        if target is not None:
            target.close()
        if not base.closed:
            try:
                base.autocommit = True
                with base.cursor() as cursor:
                    cursor.execute(
                        f'DROP DATABASE IF EXISTS "{SAFE_MIGRATION_TARGET_DATABASE}" WITH (FORCE);'
                    )
            finally:
                base.close()


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
                  AND idx.relname = 'idx_shoir_accounts_affiliate_code_trimmed_unique';
                """,
            )
            assert unique_code_index == (True,), (
                "Populated referral codes must be protected by a unique partial index."
            )

            internal_tables = (
                "artifacts", "twin_assets", "twin_snapshots", "twin_scenarios",
                "connector_health", "jobs", "collaboration", "knowledge",
                "monitoring_rules", "monitoring_events", "report_provenance", "security",
            )
            for table in internal_tables:
                rls_state = _fetchone(
                    target,
                    """
                    SELECT c.relrowsecurity
                    FROM pg_class c
                    JOIN pg_namespace n ON n.oid=c.relnamespace
                    WHERE n.nspname='shoir_internal' AND c.relname=%s;
                    """,
                    (table,),
                )
                assert rls_state == (True,), f"RLS is not enabled on shoir_internal.{table}"
                assert _fetchone(
                    target,
                    "SELECT has_table_privilege('anon', %s, 'SELECT');",
                    (f"shoir_internal.{table}",),
                )[0] is False, f"anon has a direct SELECT grant on shoir_internal.{table}"
                assert _fetchone(
                    target,
                    "SELECT has_table_privilege('authenticated', %s, 'SELECT');",
                    (f"shoir_internal.{table}",),
                )[0] is False, f"authenticated has a direct SELECT grant on shoir_internal.{table}"

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

            dataset_version_signature = (
                "public.shoir_platform_register_dataset_version("
                "text,text,text,text,text,text,bigint,integer,jsonb,jsonb,text,text,text,text)"
            )
            dataset_version_function = _fetchone(
                target,
                """
                SELECT p.prosecdef, p.proconfig,
                       has_function_privilege('anon', p.oid, 'EXECUTE'),
                       has_function_privilege('authenticated', p.oid, 'EXECUTE'),
                       has_function_privilege('service_role', p.oid, 'EXECUTE')
                FROM pg_proc p
                JOIN pg_namespace n ON n.oid=p.pronamespace
                WHERE n.nspname='public'
                  AND p.proname='shoir_platform_register_dataset_version'
                  AND pg_get_function_identity_arguments(p.oid) =
                      'p_workspace_key text, p_dataset_id text, p_name text, p_source_name text, p_data_hash text, p_version_fingerprint text, p_row_count bigint, p_column_count integer, p_schema_json jsonb, p_transformations_json jsonb, p_actor text, p_version_record_id text, p_head_record_id text, p_event_id text';
                """,
            )
            assert dataset_version_function is not None, (
                "Atomic dataset version registration function is missing after replay."
            )
            assert dataset_version_function[0] is True, (
                "Dataset version registration must run as SECURITY DEFINER."
            )
            assert "search_path=pg_catalog, public" in (dataset_version_function[1] or []), (
                "Dataset version registration must pin its search_path."
            )
            assert dataset_version_function[2] is False
            assert dataset_version_function[3] is False
            assert dataset_version_function[4] is True

            dataset_storage_bucket = _fetchone(
                target,
                "SELECT public, file_size_limit FROM storage.buckets WHERE id='shoir-industrial-datasets';",
            )
            assert dataset_storage_bucket == (False, 52428800), (
                "Industrial dataset storage must be private and limited to 50 MiB."
            )
            storage_policy = _fetchone(
                target,
                """
                SELECT qual, with_check
                FROM pg_policies
                WHERE schemaname='storage' AND tablename='objects'
                  AND policyname='private_subscription_payment_proofs_only_server';
                """,
            )
            assert storage_policy is not None
            assert "shoir-industrial-datasets" in storage_policy[0]
            assert "shoir-industrial-datasets" in storage_policy[1]

            storage_function = _fetchone(
                target,
                """
                SELECT p.prosecdef, p.proconfig,
                       has_function_privilege('anon', p.oid, 'EXECUTE'),
                       has_function_privilege('authenticated', p.oid, 'EXECUTE'),
                       has_function_privilege('service_role', p.oid, 'EXECUTE')
                FROM pg_proc p
                JOIN pg_namespace n ON n.oid=p.pronamespace
                WHERE n.nspname='public'
                  AND p.proname='shoir_platform_register_dataset_version_with_storage';
                """,
            )
            assert storage_function is not None
            assert storage_function[0] is True
            assert "search_path=pg_catalog, public" in (storage_function[1] or [])
            assert storage_function[2:4] == (False, False)
            assert storage_function[4] is True

            workspace_key = "a" * 32
            dataset_id = "DS-AABBCCDDEEFF"
            first_data_hash = "b" * 64
            first_fingerprint = "c" * 64
            first_registration = _fetchone(
                target,
                """
                SELECT dataset_id, version, data_hash, version_fingerprint,
                       version_record_id, created_new_version
                FROM public.shoir_platform_register_dataset_version(
                    %s,%s,%s,%s,%s,%s,%s,%s,%s::jsonb,%s::jsonb,%s,%s,%s,%s
                );
                """,
                (
                    workspace_key, dataset_id, "Production", "synthetic.csv",
                    first_data_hash, first_fingerprint, 100, 3,
                    '{"asset_id":{"dtype":"object"}}', '[{"operation":"import"}]',
                    "synthetic-test", "SPR-" + "1" * 24, "SPR-" + "2" * 24,
                    "SPE-" + "3" * 24,
                ),
            )
            assert first_registration[0:2] == (dataset_id, 1)
            assert first_registration[2:4] == (first_data_hash, first_fingerprint)
            assert first_registration[5] is True

            retry_registration = _fetchone(
                target,
                """
                SELECT dataset_id, version, version_record_id, created_new_version
                FROM public.shoir_platform_register_dataset_version(
                    %s,%s,%s,%s,%s,%s,%s,%s,%s::jsonb,%s::jsonb,%s,%s,%s,%s
                );
                """,
                (
                    workspace_key, dataset_id, "Production", "synthetic.csv",
                    first_data_hash, first_fingerprint, 100, 3,
                    '{"asset_id":{"dtype":"object"}}', '[{"operation":"import"}]',
                    "synthetic-test", "SPR-" + "4" * 24, "SPR-" + "5" * 24,
                    "SPE-" + "6" * 24,
                ),
            )
            assert retry_registration[0:2] == (dataset_id, 1)
            assert retry_registration[2] == first_registration[4]
            assert retry_registration[3] is False

            second_data_hash = "d" * 64
            second_fingerprint = "e" * 64
            second_registration = _fetchone(
                target,
                """
                SELECT dataset_id, version, data_hash, version_fingerprint,
                       created_new_version
                FROM public.shoir_platform_register_dataset_version(
                    %s,%s,%s,%s,%s,%s,%s,%s,%s::jsonb,%s::jsonb,%s,%s,%s,%s
                );
                """,
                (
                    workspace_key, dataset_id, "Production", "synthetic.csv",
                    second_data_hash, second_fingerprint, 120, 3,
                    '{"asset_id":{"dtype":"object"}}', '[{"operation":"clean"}]',
                    "synthetic-test", "SPR-" + "7" * 24, "SPR-" + "8" * 24,
                    "SPE-" + "9" * 24,
                ),
            )
            assert second_registration == (
                dataset_id, 2, second_data_hash, second_fingerprint, True
            )
            version_count = _fetchone(
                target,
                """
                SELECT count(*) FROM public.shoir_platform_records
                WHERE workspace_key=%s AND record_type='dataset_version'
                  AND entity_key IN (%s, %s);
                """,
                (workspace_key, dataset_id + ":v1", dataset_id + ":v2"),
            )
            assert version_count == (2,)
            head = _fetchone(
                target,
                """
                SELECT payload_json->>'version'
                FROM public.shoir_platform_records
                WHERE workspace_key=%s AND record_type='dataset' AND entity_key=%s;
                """,
                (workspace_key, dataset_id),
            )
            assert head == ("2",)

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

            # Exercise the organisation tenant model using synthetic accounts
            # and the same service_role used by the Edge Function.
            enterprise_users = (
                "e2e-org-successor",
                "e2e-org-viewer",
                "e2e-org-engineer",
                "e2e-org-pending",
                "e2e-org-other",
            )
            with target.cursor() as cursor:
                cursor.execute(
                    """
                    UPDATE public.shoir_accounts
                       SET tier='Enterprise Tier ($299)',
                           subscription_expires_at=NOW() + interval '365 days'
                     WHERE username_lc=%s;
                    """,
                    (username,),
                )
                for synthetic_user in enterprise_users:
                    cursor.execute(
                        """
                        INSERT INTO public.shoir_accounts(
                            username, username_lc, password_hash, role, tier,
                            email, created_at, subscription_expires_at, active
                        )
                        VALUES (
                            %s, %s, %s, 'User',
                            CASE WHEN %s IN ('e2e-org-successor','e2e-org-other')
                                 THEN 'Enterprise Tier ($299)'
                                 ELSE 'Starter Tier ($29)' END,
                            %s, NOW(), NOW() + interval '365 days', TRUE
                        );
                        """,
                        (
                            synthetic_user,
                            synthetic_user,
                            password_hash,
                            synthetic_user,
                            synthetic_user + "@example.invalid",
                        ),
                    )
                target.commit()

                cursor.execute("SET ROLE service_role;")
                assert _fetchone(
                    target,
                    "SELECT has_table_privilege('service_role', 'public.shoir_organization_audit_events', 'INSERT');",
                )[0] is True
                assert _fetchone(
                    target,
                    "SELECT has_table_privilege('service_role', 'public.shoir_organization_audit_events', 'UPDATE');",
                )[0] is False
                assert _fetchone(
                    target,
                    "SELECT has_table_privilege('service_role', 'public.shoir_organization_audit_events', 'DELETE');",
                )[0] is False
                for signature in (
                    "public.shoir_org_create(text,text)",
                    "public.shoir_org_invitation_create(text,uuid,text,text,text,timestamp with time zone)",
                    "public.shoir_org_invitation_accept(text,text)",
                    "public.shoir_org_invitation_revoke(text,uuid,uuid)",
                    "public.shoir_org_workspace_archive(text,uuid,uuid)",
                    "public.shoir_org_resolve_workspace(text,uuid,uuid,text)",
                ):
                    assert _fetchone(
                        target,
                        "SELECT has_function_privilege('service_role', %s::regprocedure, 'EXECUTE');",
                        (signature,),
                    )[0] is True, f"service_role cannot execute {signature}"
                    assert _fetchone(
                        target,
                        "SELECT has_function_privilege('anon', %s::regprocedure, 'EXECUTE');",
                        (signature,),
                    )[0] is False, f"anon can execute privileged organisation RPC {signature}"
                    assert _fetchone(
                        target,
                        "SELECT has_function_privilege('authenticated', %s::regprocedure, 'EXECUTE');",
                        (signature,),
                    )[0] is False, f"authenticated can execute privileged organisation RPC {signature}"

                cursor.execute(
                    "SELECT public.shoir_org_create(%s, %s);",
                    (username, "Synthetic Replay Organization"),
                )
                org_result = cursor.fetchone()[0]
                org = org_result if isinstance(org_result, dict) else json.loads(org_result)
                organization_id = str(org["organization_id"])
                general_workspace_id = str(org["workspace_id"])

                cursor.execute(
                    "SELECT public.shoir_org_workspace_create(%s, %s::uuid, %s);",
                    (username, organization_id, "Line 3"),
                )
                workspace_result = cursor.fetchone()[0]
                workspace = workspace_result if isinstance(workspace_result, dict) else json.loads(workspace_result)
                secondary_workspace_id = str(workspace["workspace_id"])

                # A suspended organization must not accumulate newly-created
                # workspaces that cannot subsequently be resolved or accessed.
                cursor.execute("SAVEPOINT shoir_org_suspended_workspace_create;")
                cursor.execute(
                    "UPDATE public.shoir_organizations SET status='suspended' WHERE organization_id=%s::uuid;",
                    (organization_id,),
                )
                with pytest.raises(psycopg2.Error) as suspended_workspace:
                    cursor.execute(
                        "SELECT public.shoir_org_workspace_create(%s,%s::uuid,%s);",
                        (username, organization_id, "Must Not Exist"),
                    )
                assert suspended_workspace.value.pgcode == "42501"
                cursor.execute("ROLLBACK TO SAVEPOINT shoir_org_suspended_workspace_create;")

                cursor.execute(
                    "SELECT public.shoir_org_invitation_create(%s,%s::uuid,%s,%s,%s,%s::timestamptz);",
                    (
                        username,
                        organization_id,
                        "e2e-org-viewer",
                        "viewer",
                        "a" * 64,
                        (datetime.datetime.now(datetime.timezone.utc) + datetime.timedelta(days=7)).isoformat(),
                    ),
                )
                cursor.execute(
                    "SELECT public.shoir_org_invitation_accept(%s,%s);",
                    ("e2e-org-viewer", "a" * 64),
                )
                viewer_membership = cursor.fetchone()[0]
                assert viewer_membership["role"] == "viewer"

                cursor.execute(
                    "SELECT organization_id, workspace_id, workspace_key, member_role "
                    "FROM public.shoir_org_resolve_workspace(%s,%s::uuid,%s::uuid,%s);",
                    ("e2e-org-viewer", organization_id, general_workspace_id, "read"),
                )
                assert cursor.fetchone()[3] == "viewer"

                # NULL is not a valid permission: SQL three-valued logic must
                # not allow it to skip the explicit permission allow-list.
                cursor.execute("SAVEPOINT shoir_org_null_permission;")
                with pytest.raises(psycopg2.Error) as null_permission:
                    cursor.execute(
                        "SELECT * FROM public.shoir_org_resolve_workspace(%s,%s::uuid,%s::uuid,%s);",
                        ("e2e-org-viewer", organization_id, general_workspace_id, None),
                    )
                assert null_permission.value.pgcode == "22023"
                cursor.execute("ROLLBACK TO SAVEPOINT shoir_org_null_permission;")

                cursor.execute("SAVEPOINT shoir_org_viewer_write_denied;")
                with pytest.raises(psycopg2.Error) as viewer_write_denied:
                    cursor.execute(
                        "SELECT * FROM public.shoir_org_resolve_workspace(%s,%s::uuid,%s::uuid,%s);",
                        ("e2e-org-viewer", organization_id, general_workspace_id, "write"),
                    )
                assert viewer_write_denied.value.pgcode == "42501"
                cursor.execute("ROLLBACK TO SAVEPOINT shoir_org_viewer_write_denied;")

                cursor.execute("SAVEPOINT shoir_org_null_role;")
                with pytest.raises(psycopg2.Error) as null_role:
                    cursor.execute(
                        "SELECT public.shoir_org_member_role_set(%s,%s::uuid,%s,%s);",
                        (username, organization_id, "e2e-org-viewer", None),
                    )
                assert null_role.value.pgcode == "22023"
                cursor.execute("ROLLBACK TO SAVEPOINT shoir_org_null_role;")

                cursor.execute(
                    "SELECT public.shoir_org_member_role_set(%s,%s::uuid,%s,%s);",
                    (username, organization_id, "e2e-org-viewer", "engineer"),
                )
                cursor.execute(
                    "SELECT member_role FROM public.shoir_org_resolve_workspace(%s,%s::uuid,%s::uuid,%s);",
                    ("e2e-org-viewer", organization_id, general_workspace_id, "write"),
                )
                assert cursor.fetchone()[0] == "engineer"

                cursor.execute(
                    "SELECT public.shoir_org_invitation_create(%s,%s::uuid,%s,%s,%s,%s::timestamptz);",
                    (
                        username,
                        organization_id,
                        "e2e-org-pending",
                        "viewer",
                        "b" * 64,
                        (datetime.datetime.now(datetime.timezone.utc) + datetime.timedelta(days=7)).isoformat(),
                    ),
                )
                pending_result = cursor.fetchone()[0]
                pending_invitation = (
                    pending_result
                    if isinstance(pending_result, dict)
                    else json.loads(pending_result)
                )
                pending_invitation_id = str(pending_invitation["invitation_id"])
                cursor.execute(
                    "SELECT public.shoir_org_invitation_revoke(%s,%s::uuid,%s::uuid);",
                    (username, organization_id, pending_invitation_id),
                )
                cursor.execute("SAVEPOINT shoir_org_revoked_invite;")
                with pytest.raises(psycopg2.Error) as revoked_invite:
                    cursor.execute(
                        "SELECT public.shoir_org_invitation_accept(%s,%s);",
                        ("e2e-org-pending", "b" * 64),
                    )
                assert revoked_invite.value.pgcode == "42501"
                cursor.execute("ROLLBACK TO SAVEPOINT shoir_org_revoked_invite;")

                cursor.execute(
                    "SELECT public.shoir_org_workspace_archive(%s,%s::uuid,%s::uuid);",
                    (username, organization_id, secondary_workspace_id),
                )
                cursor.execute("SAVEPOINT shoir_org_last_workspace;")
                with pytest.raises(psycopg2.Error) as last_workspace:
                    cursor.execute(
                        "SELECT public.shoir_org_workspace_archive(%s,%s::uuid,%s::uuid);",
                        (username, organization_id, general_workspace_id),
                    )
                assert last_workspace.value.pgcode == "23514"
                cursor.execute("ROLLBACK TO SAVEPOINT shoir_org_last_workspace;")

                # A separate organisation must not be visible through another
                # organisation's membership, even when the workspace UUID is known.
                cursor.execute(
                    "SELECT public.shoir_org_create(%s, %s);",
                    ("e2e-org-other", "Other Synthetic Organization"),
                )
                other_result = cursor.fetchone()[0]
                other_org = other_result if isinstance(other_result, dict) else json.loads(other_result)
                other_organization_id = str(other_org["organization_id"])
                other_workspace_id = str(other_org["workspace_id"])
                cursor.execute("SAVEPOINT shoir_org_cross_tenant;")
                with pytest.raises(psycopg2.Error) as cross_tenant:
                    cursor.execute(
                        "SELECT * FROM public.shoir_org_resolve_workspace(%s,%s::uuid,%s::uuid,%s);",
                        ("e2e-org-viewer", other_organization_id, other_workspace_id, "read"),
                    )
                assert cross_tenant.value.pgcode == "42501"
                cursor.execute("ROLLBACK TO SAVEPOINT shoir_org_cross_tenant;")

                # Transfer can happen only to an active Enterprise account which
                # is already a member. Invite and accept the successor first.
                cursor.execute(
                    "SELECT public.shoir_org_invitation_create(%s,%s::uuid,%s,%s,%s,%s::timestamptz);",
                    (
                        username,
                        organization_id,
                        "e2e-org-successor",
                        "engineer",
                        "c" * 64,
                        (datetime.datetime.now(datetime.timezone.utc) + datetime.timedelta(days=7)).isoformat(),
                    ),
                )
                cursor.execute(
                    "SELECT public.shoir_org_invitation_accept(%s,%s);",
                    ("e2e-org-successor", "c" * 64),
                )
                cursor.execute(
                    "SELECT public.shoir_org_owner_transfer(%s,%s::uuid,%s);",
                    (username, organization_id, "e2e-org-successor"),
                )
                cursor.execute(
                    "SELECT owner_username_lc FROM public.shoir_organizations WHERE organization_id=%s::uuid;",
                    (organization_id,),
                )
                assert cursor.fetchone()[0] == "e2e-org-successor"
                cursor.execute(
                    "SELECT role FROM public.shoir_organization_memberships WHERE organization_id=%s::uuid AND username_lc=%s;",
                    (organization_id, username),
                )
                assert cursor.fetchone()[0] == "admin"
                cursor.execute("RESET ROLE;")
                target.commit()

            # Even the database owner cannot update/delete audit history through
            # ordinary SQL; the append-only trigger rejects both operations.
            audit_event_id = _fetchone(
                target,
                "SELECT event_id FROM public.shoir_organization_audit_events WHERE organization_id=%s::uuid ORDER BY created_at LIMIT 1;",
                (organization_id,),
            )[0]
            for operation in ("UPDATE", "DELETE"):
                with target.cursor() as cursor:
                    cursor.execute("SAVEPOINT shoir_org_audit_immutable;")
                    with pytest.raises(psycopg2.Error) as immutable_audit:
                        if operation == "UPDATE":
                            cursor.execute(
                                "UPDATE public.shoir_organization_audit_events SET event_type='tampered.event' WHERE event_id=%s;",
                                (audit_event_id,),
                            )
                        else:
                            cursor.execute(
                                "DELETE FROM public.shoir_organization_audit_events WHERE event_id=%s;",
                                (audit_event_id,),
                            )
                    assert immutable_audit.value.pgcode == "55000"
                    cursor.execute("ROLLBACK TO SAVEPOINT shoir_org_audit_immutable;")
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
