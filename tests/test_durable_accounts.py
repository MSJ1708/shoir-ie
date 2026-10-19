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


def test_renewal_approval_preserves_existing_account_identity_and_renews_expiry():
    """Protect the old account/workspace instead of creating a replacement account."""
    from pathlib import Path

    root = Path(__file__).resolve().parents[1]
    edge_source = (root / "supabase/functions/shoir-persistence/index.ts").read_text(encoding="utf-8")

    assert _source_contract_contains(edge_source, 'request.request_type==="Renewal"&&existing?expiry30(existing.subscription_expires_at):expiry30()')
    assert _source_contract_contains(edge_source, 'const passwordHash=existing?.password_hash||pendingCred?.password_hash;')
    assert _source_contract_contains(edge_source, 'created_at:existing?.created_at||now')
    assert _source_contract_contains(edge_source, 'username_lc:request.username_lc')
    assert _source_contract_contains(edge_source, 'if(action==="renew_request")')



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
    migration = (root / "supabase/migrations/20261019123300_server_side_login_rate_limits.sql").read_text(encoding="utf-8")

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
