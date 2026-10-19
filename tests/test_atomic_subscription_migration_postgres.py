"""Run the subscription-decision SQL against an isolated PostgreSQL instance.

This test is skipped in normal unit-test runs. The dedicated GitHub workflow
provides a disposable local PostgreSQL service; the database guard deliberately
refuses non-local or incorrectly named databases to prevent accidental writes
to shared/staging/production environments.
"""
from __future__ import annotations

import json
import os
from concurrent.futures import ThreadPoolExecutor
from threading import Barrier
from datetime import datetime, timedelta, timezone
from pathlib import Path
from urllib.parse import urlparse

import pytest

try:
    import psycopg2
except ImportError:  # pragma: no cover - optional outside the dedicated workflow
    psycopg2 = None

DATABASE_URL = os.environ.get("SHOIR_TEST_POSTGRES_URL", "")
ROOT = Path(__file__).resolve().parents[1]
MIGRATION = ROOT / "supabase/migrations/20261019140600_atomic_subscription_request_decisions.sql"

pytestmark = pytest.mark.skipif(
    not DATABASE_URL or psycopg2 is None,
    reason="requires the isolated subscription-transaction PostgreSQL workflow",
)


def _connect():
    parsed = urlparse(DATABASE_URL)
    if parsed.hostname not in {"localhost", "127.0.0.1", "::1"}:
        pytest.fail("Refusing to run migration integration test against a non-local database.")
    if (parsed.path or "").lstrip("/") != "shoir_test":
        pytest.fail("Refusing to run migration integration test outside the shoir_test database.")
    conn = psycopg2.connect(DATABASE_URL, connect_timeout=5)
    params = conn.get_dsn_parameters()
    if params.get("dbname") != "shoir_test" or params.get("host") not in {"localhost", "127.0.0.1", "::1"}:
        conn.close()
        pytest.fail("Refusing database connection: expected local shoir_test.")
    return conn


def _sql(query: str, args=(), fetchone=True):
    conn = _connect()
    try:
        with conn.cursor() as cur:
            cur.execute(query, args)
            result = cur.fetchone() if fetchone else None
        conn.commit()
        if not result:
            return None
        return result[0] if len(result) == 1 else result
    except Exception:
        conn.rollback()
        raise
    finally:
        conn.close()


def _registration(username: str, tier: str = "Starter Tier ($29)") -> dict:
    result = _sql(
        """
        SELECT public.shoir_create_registration_request(%s, %s, %s, %s, %s, %s, %s, %s)
        """,
        (
            username,
            username.lower(),
            ("a" * 32) + "$" + ("b" * 64),
            f"{username}@example.invalid",
            tier,
            "STC Pay (QR)",
            "SYNTHETIC-TEST-REFERENCE",
            "storage://subscription-payment-proofs/renewals/synthetic-test.png",
        ),
    )
    if isinstance(result, str):
        result = json.loads(result)
    assert isinstance(result, dict)
    assert result.get("ok") is True
    return result


def _decision(request_id: int, decision: str) -> dict:
    result = _sql(
        "SELECT public.shoir_finalize_subscription_request(%s, %s)",
        (request_id, decision),
    )
    if isinstance(result, str):
        result = json.loads(result)
    assert isinstance(result, dict)
    assert result.get("ok") is True
    return result


def test_atomic_subscription_migration_and_state_transitions():
    """Apply the migration and exercise real PostgreSQL constraints/transactions."""
    parsed = urlparse(DATABASE_URL)
    assert parsed.hostname in {"localhost", "127.0.0.1", "::1"}
    assert (parsed.path or "").lstrip("/") == "shoir_test"

    conn = _connect()
    try:
        conn.autocommit = True
        with conn.cursor() as cur:
            cur.execute(
                """
                DO $$ BEGIN CREATE ROLE anon; EXCEPTION WHEN duplicate_object THEN NULL; END $$;
                DO $$ BEGIN CREATE ROLE authenticated; EXCEPTION WHEN duplicate_object THEN NULL; END $$;
                DO $$ BEGIN CREATE ROLE service_role; EXCEPTION WHEN duplicate_object THEN NULL; END $$;

                CREATE TABLE public.shoir_accounts (
                    username text PRIMARY KEY,
                    username_lc text NOT NULL UNIQUE,
                    password_hash text NOT NULL,
                    role text,
                    tier text,
                    email text,
                    created_at timestamptz NOT NULL,
                    subscription_expires_at timestamptz NOT NULL,
                    linkedin text,
                    github text,
                    about_me text,
                    affiliate_code text,
                    active boolean NOT NULL DEFAULT true,
                    updated_at timestamptz NOT NULL DEFAULT now()
                );
                CREATE TABLE public.shoir_pending_credentials (
                    username_lc text PRIMARY KEY,
                    username text NOT NULL,
                    password_hash text NOT NULL,
                    email text,
                    updated_at timestamptz NOT NULL DEFAULT now()
                );
                CREATE TABLE public.shoir_subscription_requests (
                    id bigserial PRIMARY KEY,
                    username text NOT NULL,
                    username_lc text NOT NULL,
                    email text,
                    tier text,
                    request_type text NOT NULL DEFAULT 'New',
                    payment_method text,
                    transaction_id text,
                    screenshot_path text,
                    status text NOT NULL DEFAULT 'Pending',
                    requested_at timestamptz NOT NULL DEFAULT now(),
                    approved_at timestamptz,
                    updated_at timestamptz NOT NULL DEFAULT now()
                );
                """
            )
            cur.execute(MIGRATION.read_text(encoding="utf-8"))
    finally:
        conn.close()

    # Functions must be unavailable to browser roles and available only to the
    # privileged service role used by the Edge Function.
    permissions = _sql(
        """
        SELECT
          has_function_privilege('anon', 'public.shoir_finalize_subscription_request(bigint,text)', 'EXECUTE'),
          has_function_privilege('authenticated', 'public.shoir_finalize_subscription_request(bigint,text)', 'EXECUTE'),
          has_function_privilege('service_role', 'public.shoir_finalize_subscription_request(bigint,text)', 'EXECUTE'),
          has_function_privilege('anon', 'public.shoir_create_registration_request(text,text,text,text,text,text,text,text)', 'EXECUTE'),
          has_function_privilege('authenticated', 'public.shoir_create_registration_request(text,text,text,text,text,text,text,text)', 'EXECUTE'),
          has_function_privilege('service_role', 'public.shoir_create_registration_request(text,text,text,text,text,text,text,text)', 'EXECUTE')
        """,
        fetchone=True,
    )
    assert permissions == (False, False, True, False, False, True)

    # The backend must refuse a request with neither a payment reference nor
    # a private receipt; incomplete evidence cannot create a pending account.
    with pytest.raises(psycopg2.Error) as no_evidence:
        _sql(
            "SELECT public.shoir_create_registration_request(%s,%s,%s,%s,%s,%s,%s,%s)",
            (
                "shoir-e2e-postgres-no-evidence",
                "shoir-e2e-postgres-no-evidence",
                ("a" * 32) + "$" + ("b" * 64),
                "no-evidence@example.invalid",
                "Starter Tier ($29)",
                "STC Pay (QR)",
                None,
                None,
            ),
        )
    assert no_evidence.value.pgcode == "22023"

    # Registration writes credentials and a pending request as one function call.
    new = _registration("shoir-e2e-postgres-new")
    new_id = int(new["request_id"])
    status = _sql("SELECT status FROM public.shoir_subscription_requests WHERE id=%s", (new_id,))
    assert status == "Pending"
    assert _sql(
        "SELECT password_hash FROM public.shoir_pending_credentials WHERE username_lc=%s",
        ("shoir-e2e-postgres-new",),
    ) == ("a" * 32) + "$" + ("b" * 64)

    # Concurrent-style duplicate attempts are serialized and rejected.
    with pytest.raises(psycopg2.Error) as duplicate:
        _registration("shoir-e2e-postgres-new")
    assert duplicate.value.pgcode == "P0002"

    approved = _decision(new_id, "Approved")
    assert approved["status"] == "Approved"
    account = _sql(
        """
        SELECT username, role, tier, active, password_hash, created_at, subscription_expires_at
        FROM public.shoir_accounts WHERE username_lc=%s
        """,
        ("shoir-e2e-postgres-new",),
    )
    assert account[0] == "shoir-e2e-postgres-new"
    assert account[1] == "User"
    assert account[2] == "Starter Tier ($29)"
    assert account[3] is True
    assert account[4] == ("a" * 32) + "$" + ("b" * 64)
    assert account[6] > datetime.now(timezone.utc) + timedelta(days=29)

    # A non-pending/processed request cannot be decided twice.
    with pytest.raises(psycopg2.Error) as repeated_approval:
        _decision(new_id, "Approved")
    assert repeated_approval.value.pgcode == "P0002"

    rejected = _registration("shoir-e2e-postgres-decline")
    rejected_id = int(rejected["request_id"])
    declined = _decision(rejected_id, "Declined")
    assert declined["status"] == "Declined"
    assert _sql(
        "SELECT count(*) FROM public.shoir_accounts WHERE username_lc=%s",
        ("shoir-e2e-postgres-decline",),
    ) == 0
    with pytest.raises(psycopg2.Error) as repeated_decline:
        _decision(rejected_id, "Declined")
    assert repeated_decline.value.pgcode == "P0002"

    # Renewal preserves an existing user's identity/credentials/role/profile
    # while updating only subscription metadata.
    created = datetime(2022, 2, 3, 4, 5, tzinfo=timezone.utc)
    old_expiry = datetime.now(timezone.utc) - timedelta(days=20)
    _sql(
        """
        INSERT INTO public.shoir_accounts
          (username, username_lc, password_hash, role, tier, email, created_at,
           subscription_expires_at, linkedin, github, about_me, affiliate_code, active)
        VALUES (%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s)
        """,
        (
            "shoir-e2e-postgres-renewal",
            "shoir-e2e-postgres-renewal",
            "original-salted-test-hash",
            "User",
            "Professional Tier ($129)",
            "renewal@example.invalid",
            created,
            old_expiry,
            "https://example.invalid/profile",
            "https://example.invalid/repo",
            "preserve this profile",
            "TEST-AFFILIATE",
            True,
        ),
        fetchone=False,
    )
    request_id = _sql(
        """
        INSERT INTO public.shoir_subscription_requests
          (username, username_lc, email, tier, request_type, payment_method,
           transaction_id, screenshot_path, status)
        VALUES (%s,%s,%s,%s,'Renewal','STC Pay (QR)',%s,%s,'Pending')
        RETURNING id
        """,
        (
            "shoir-e2e-postgres-renewal",
            "shoir-e2e-postgres-renewal",
            "renewal@example.invalid",
            "Enterprise Plus Tier ($399)",
            "SYNTHETIC-RENEWAL-REFERENCE",
            "storage://subscription-payment-proofs/renewals/synthetic-renewal.png",
        ),
    )
    _decision(int(request_id), "Approved")
    renewed = _sql(
        """
        SELECT username, password_hash, role, created_at, tier, subscription_expires_at,
               linkedin, github, about_me, affiliate_code, active
        FROM public.shoir_accounts WHERE username_lc=%s
        """,
        ("shoir-e2e-postgres-renewal",),
    )
    assert renewed[0] == "shoir-e2e-postgres-renewal"
    assert renewed[1] == "original-salted-test-hash"
    assert renewed[2] == "User"
    assert renewed[3] == created
    assert renewed[4] == "Enterprise Plus Tier ($399)"
    assert renewed[5] > datetime.now(timezone.utc) + timedelta(days=29)
    assert renewed[6:10] == (
        "https://example.invalid/profile",
        "https://example.invalid/repo",
        "preserve this profile",
        "TEST-AFFILIATE",
    )
    assert renewed[10] is True

    # Race two registrations for the same normalized username using independent
    # PostgreSQL sessions. Exactly one may create the Pending request.
    concurrent_registration_user = "shoir-e2e-postgres-concurrent-registration"
    registration_barrier = Barrier(2)

    def register_concurrently():
        registration_barrier.wait(timeout=5)
        try:
            result = _registration(concurrent_registration_user)
            return ("success", result)
        except psycopg2.Error as exc:
            return ("error", exc.pgcode)

    with ThreadPoolExecutor(max_workers=2) as pool:
        registration_futures = [
            pool.submit(register_concurrently),
            pool.submit(register_concurrently),
        ]
        registration_results = [future.result(timeout=15) for future in registration_futures]

    assert sum(result[0] == "success" for result in registration_results) == 1
    registration_errors = [result[1] for result in registration_results if result[0] == "error"]
    assert registration_errors == ["P0002"]
    assert _sql(
        "SELECT count(*) FROM public.shoir_subscription_requests WHERE username_lc=%s AND request_type='New' AND status='Pending'",
        (concurrent_registration_user,),
    ) == 1
    assert _sql(
        "SELECT count(*) FROM public.shoir_pending_credentials WHERE username_lc=%s",
        (concurrent_registration_user,),
    ) == 1

    # Race two decisions for the same Pending request. The row lock and status
    # guard must allow one durable transition and reject the stale contender.
    decision_request = _registration("shoir-e2e-postgres-concurrent-decision")
    decision_request_id = int(decision_request["request_id"])
    decision_barrier = Barrier(2)

    def decide_concurrently():
        decision_barrier.wait(timeout=5)
        try:
            return ("success", _decision(decision_request_id, "Approved"))
        except psycopg2.Error as exc:
            return ("error", exc.pgcode)

    with ThreadPoolExecutor(max_workers=2) as pool:
        decision_futures = [
            pool.submit(decide_concurrently),
            pool.submit(decide_concurrently),
        ]
        decision_results = [future.result(timeout=15) for future in decision_futures]

    assert sum(result[0] == "success" for result in decision_results) == 1
    decision_errors = [result[1] for result in decision_results if result[0] == "error"]
    assert decision_errors == ["P0002"]
    assert _sql(
        "SELECT status FROM public.shoir_subscription_requests WHERE id=%s",
        (decision_request_id,),
    ) == "Approved"
    assert _sql(
        "SELECT count(*) FROM public.shoir_accounts WHERE username_lc=%s",
        ("shoir-e2e-postgres-concurrent-decision",),
    ) == 1

    # Force a failure after the approval function has inserted/updated the
    # account but before the request transition succeeds. PostgreSQL must roll
    # back both writes as one transaction, leaving the request Pending and no
    # account created. The trigger is test-only and is always removed.
    rollback_request = _registration("shoir-e2e-postgres-rollback")
    rollback_request_id = int(rollback_request["request_id"])
    rollback_user = "shoir-e2e-postgres-rollback"
    _sql(
        "UPDATE public.shoir_subscription_requests SET transaction_id=%s WHERE id=%s",
        ("SYNTHETIC-ROLLBACK-REFERENCE", rollback_request_id),
        fetchone=False,
    )
    _sql(
        """
        CREATE OR REPLACE FUNCTION public.shoir_test_force_approval_rollback()
        RETURNS trigger LANGUAGE plpgsql AS $$
        BEGIN
            IF NEW.status = 'Approved'
               AND NEW.transaction_id = 'SYNTHETIC-ROLLBACK-REFERENCE' THEN
                RAISE EXCEPTION 'synthetic approval failure for rollback test'
                    USING ERRCODE = 'P0001';
            END IF;
            RETURN NEW;
        END;
        $$;
        """,
        fetchone=False,
    )
    _sql(
        """
        CREATE TRIGGER shoir_test_force_approval_rollback
        BEFORE UPDATE ON public.shoir_subscription_requests
        FOR EACH ROW EXECUTE FUNCTION public.shoir_test_force_approval_rollback();
        """,
        fetchone=False,
    )
    try:
        with pytest.raises(psycopg2.Error) as forced_failure:
            _decision(rollback_request_id, "Approved")
        assert forced_failure.value.pgcode == "P0001"
        assert _sql(
            "SELECT status FROM public.shoir_subscription_requests WHERE id=%s",
            (rollback_request_id,),
        ) == "Pending"
        assert _sql(
            "SELECT count(*) FROM public.shoir_accounts WHERE username_lc=%s",
            (rollback_user,),
        ) == 0
    finally:
        _sql(
            "DROP TRIGGER IF EXISTS shoir_test_force_approval_rollback ON public.shoir_subscription_requests",
            fetchone=False,
        )
        _sql(
            "DROP FUNCTION IF EXISTS public.shoir_test_force_approval_rollback()",
            fetchone=False,
        )

    # Once the synthetic failure hook is removed, the same request remains
    # processable; this proves the failed transaction did not leave a half-state.
    recovered = _decision(rollback_request_id, "Approved")
    assert recovered["status"] == "Approved"
    assert _sql(
        "SELECT status FROM public.shoir_subscription_requests WHERE id=%s",
        (rollback_request_id,),
    ) == "Approved"
    assert _sql(
        "SELECT count(*) FROM public.shoir_accounts WHERE username_lc=%s",
        (rollback_user,),
    ) == 1
