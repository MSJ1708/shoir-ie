from datetime import datetime, timedelta, timezone

from durable_account_store import account_is_expired, renewed_expiry


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
