import re
from datetime import datetime, timedelta, timezone

def _source_contract_contains(source: str, fragment: str) -> bool:
    normalized_source = re.sub(r"\s+", "", source)
    normalized_fragment = re.sub(r"\s+", "", fragment)
    normalized_source = re.sub(r",(?=[)\]}])", "", normalized_source)
    normalized_fragment = re.sub(r",(?=[)\]}])", "", normalized_fragment)
    return normalized_fragment in normalized_source


from durable_account_store import account_is_expired, renewed_expiry
import durable_account_store as das


def test_account_is_expired_at_boundary():
    now = datetime(2026, 9, 22, tzinfo=timezone.utc)
    assert account_is_expired(now, now)
    assert not account_is_expired(now + timedelta(seconds=1), now)


def test_renewal_starts_from_later_of_now_or_expiry():
    now = datetime(2026, 9, 22, tzinfo=timezone.utc)
    expired = now - timedelta(days=2)
    future = now + timedelta(days=5)
    assert renewed_expiry(expired, 30, now) == now + timedelta(days=30)
    assert renewed_expiry(future, 30, now) == future + timedelta(days=30)


def test_edge_backend_is_built_in():
    from durable_account_store import edge_backend_configured, durable_backend_configured
    assert edge_backend_configured() is True
    assert durable_backend_configured() is True


def test_master_admin_enterprise_plus_entitlement_contract():
    """Guard the local seed and server-side entitlement without resetting admin credentials."""
    from pathlib import Path

    root = Path(__file__).resolve().parents[1]
    app_source = (root / "app.py").read_text(encoding="utf-8")
    edge_source = (root / "supabase/functions/shoir-persistence/index.ts").read_text(encoding="utf-8")

    assert '("sho", admin_pass_hash, "Enterprise Admin", "Enterprise Plus Tier ($399)",' in app_source
    assert '(admin_pass_hash, "Enterprise Admin", "Enterprise Plus Tier ($399)", "mohsuhailji@gmail.com")' in app_source
    assert '("Enterprise Admin", "Enterprise Plus Tier ($399)", "mohsuhailji@gmail.com")' in app_source
    assert _source_contract_contains(edge_source, 'const isMasterAdmin = row.username_lc==="sho"&&row.role==="Enterprise Admin";')
    assert _source_contract_contains(edge_source, 'const effectiveTier=isMasterAdmin?adminTier:row.tier;')
    assert _source_contract_contains(edge_source, 'if(requiredScope==="workspace"&&!(row.username_lc==="sho"&&row.role==="Enterprise Admin")')
    assert _source_contract_contains(edge_source, 'if(row.username_lc!=="sho"||row.role!=="Enterprise Admin")')


def test_renewal_approval_is_atomic_and_preserves_existing_account_identity():
    """The decision transaction preserves existing account identity and rejects processed requests."""
    from pathlib import Path

    root = Path(__file__).resolve().parents[1]
    edge_source = (root / "supabase/functions/shoir-persistence/index.ts").read_text(encoding="utf-8")
    migration = (
        root / "supabase/migrations/20261019140600_atomic_subscription_request_decisions.sql"
    ).read_text(encoding="utf-8")

    assert _source_contract_contains(
        edge_source,
        'supabase.rpc("shoir_finalize_subscription_request",{p_request_id:request.id,p_decision:"Approved"})',
    )
    assert "FOR UPDATE" in migration
    assert "request_row.status IS DISTINCT FROM 'Pending'" in migration
    assert "ON CONFLICT (username_lc) DO UPDATE SET" in migration
    assert "password_hash = current_account.password_hash" in migration
    assert "role = current_account.role" in migration
    assert "created_at = current_account.created_at" in migration
    assert "subscription_expires_at = EXCLUDED.subscription_expires_at" in migration
    assert "GRANT EXECUTE ON FUNCTION public.shoir_finalize_subscription_request(bigint, text)" in migration


def test_remote_research_upsert_rejects_cross_owner_conflict(monkeypatch):
    class FakeCursor:
        def __init__(self):
            self.rowcount = 0
            self.query = ""
            self.params = None

        def __enter__(self):
            return self

        def __exit__(self, exc_type, exc, tb):
            return False

        def execute(self, query, params=None):
            self.query = query
            self.params = params
            # A zero rowcount simulates PostgreSQL's ON CONFLICT ... WHERE
            # owner predicate rejecting an existing record owned by someone else.
            self.rowcount = 0

    class FakeConnection:
        def __init__(self):
            self.fake_cursor = FakeCursor()
            self.committed = False

        def __enter__(self):
            return self

        def __exit__(self, exc_type, exc, tb):
            return False

        def cursor(self, *args, **kwargs):
            return self.fake_cursor

        def commit(self):
            self.committed = True

    fake_connection = FakeConnection()
    monkeypatch.setattr(das, "postgres_backend_configured", lambda: True)
    monkeypatch.setattr(das, "ensure_remote_research_schema", lambda: None)
    monkeypatch.setattr(das, "_pg_connect", lambda: fake_connection)

    import pytest
    with pytest.raises(PermissionError, match="not owned"):
        das.upsert_remote_research_study({
            "study_id": "SHARED-STUDY-ID",
            "research_id": "RSH-BOB",
            "owner": "bob",
            "title": "Overwrite attempt",
            "protocol": {"objective": "should not replace another user's study"},
        })

    sql = fake_connection.fake_cursor.query
    assert "ON CONFLICT (study_id) DO UPDATE SET" in sql
    assert "WHERE shoir_research_studies.owner_lc = EXCLUDED.owner_lc" in sql
    assert fake_connection.committed is False



def test_edge_logout_revokes_only_the_requested_account_session(monkeypatch):
    calls = []

    def fake_edge_call(action, payload):
        calls.append((action, payload))
        return {"ok": True, "revoked": True}

    monkeypatch.setattr(das, "_edge_call", fake_edge_call)
    result = das.edge_logout("shoir-e2e-active", "temporary-token")

    assert result == {"ok": True, "revoked": True}
    assert calls == [("logout", {"username": "shoir-e2e-active", "token": "temporary-token"})]


def test_edge_login_contract_denies_inactive_accounts_and_supports_session_revocation():
    from pathlib import Path

    root = Path(__file__).resolve().parents[1]
    edge_source = (root / "supabase/functions/shoir-persistence/index.ts").read_text(encoding="utf-8")
    app_source = (root / "app.py").read_text(encoding="utf-8")

    assert _source_contract_contains(edge_source, 'if(!row||row.active===false||!await verifyPassword(row.password_hash,password))')
    assert _source_contract_contains(edge_source, 'if(action==="logout")')
    assert _source_contract_contains(edge_source, '.eq("token_hash",tokenHash).eq("username_lc",usernameLc).select("token_hash")')
    assert 'edge_logout(_logout_user, _logout_token)' in app_source
    assert 'if _shell_surface == "logout":' in app_source
    assert 'edge_logout(_renew_username, _renew_token)' in app_source



def test_login_throttle_contract_is_server_only_and_atomic():
    from pathlib import Path

    root = Path(__file__).resolve().parents[1]
    edge_source = (root / "supabase/functions/shoir-persistence/index.ts").read_text(encoding="utf-8")
    migration = (root / "supabase/migrations/20261019124815_server_side_login_rate_limits.sql").read_text(encoding="utf-8")

    assert _source_contract_contains(edge_source, 'loginThrottleBuckets(usernameLc,req)')
    assert _source_contract_contains(edge_source, 'checkLoginThrottle(bucket.key_hash,bucket.max_attempts,"attempt")')
    assert _source_contract_contains(edge_source, 'response({error:"Too many sign-in attempts. Please wait and try again."},429)')
    assert _source_contract_contains(edge_source, 'response({error:"Authentication protection is temporarily unavailable. Please retry shortly."},503)')
    assert 'SECURITY INVOKER' in migration
    assert 'pg_advisory_xact_lock' in migration
    assert 'ALTER TABLE public.shoir_login_throttle ENABLE ROW LEVEL SECURITY' in migration
    assert 'REVOKE ALL ON TABLE public.shoir_login_throttle FROM anon, authenticated' in migration
    assert 'REVOKE EXECUTE ON FUNCTION public.shoir_check_login_throttle' in migration
    assert 'TO service_role' in migration



def test_edge_register_request_sends_proof_bytes_not_local_path(tmp_path, monkeypatch):
    import base64

    receipt = b"fake-test-receipt-bytes"
    proof_path = tmp_path / "receipt.png"
    proof_path.write_bytes(receipt)
    calls = []

    def fake_edge_call(action, payload):
        calls.append((action, payload))
        return {"ok": True, "request_id": 123, "status": "Pending"}

    monkeypatch.setattr(das, "_edge_call", fake_edge_call)
    result = das.edge_register_request({
        "username": "shoir-e2e-registration",
        "password": "a-long-test-password",
        "email": "e2e@example.invalid",
        "tier": "Starter Tier ($29)",
        "payment_method": "STC Pay (QR)",
        "transaction_id": "SYNTHETIC-REFERENCE",
        "screenshot_path": str(proof_path),
    })

    assert result["ok"] is True
    assert calls[0][0] == "register_request"
    assert calls[0][1]["proof_base64"] == base64.b64encode(receipt).decode("ascii")
    assert calls[0][1]["proof_content_type"] == "image/png"
    assert "screenshot_path" not in calls[0][1]


def test_edge_register_request_rejects_oversized_payment_proof(tmp_path, monkeypatch):
    proof_path = tmp_path / "receipt.png"
    proof_path.write_bytes(b"x" * (512 * 1024 + 1))
    monkeypatch.setattr(das, "_edge_call", lambda action, payload: (_ for _ in ()).throw(AssertionError("must not call Edge")))

    import pytest
    with pytest.raises(ValueError, match="512 KiB"):
        das.edge_register_request({
            "username": "shoir-e2e-registration",
            "password": "a-long-test-password",
            "email": "e2e@example.invalid",
            "tier": "Starter Tier ($29)",
            "payment_method": "STC Pay (QR)",
            "screenshot_path": str(proof_path),
        })
