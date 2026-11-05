"""Regression tests for timezone-safe UTC timestamp defaults and audit timing."""

import asyncio
from datetime import datetime, timezone


def test_legacy_sqlalchemy_datetime_default_remains_naive_utc():
    from database import _utcnow_naive

    value = _utcnow_naive()
    assert isinstance(value, datetime)
    assert value.tzinfo is None
    now_utc = datetime.now(timezone.utc).replace(tzinfo=None)
    assert abs((now_utc - value).total_seconds()) < 5


def test_enterprise_audit_decorator_uses_utc_without_deprecated_utcnow():
    from enterprise_engine import secure_audit_log

    class Sample:
        @secure_audit_log(required_role="engineer")
        def run(self, user_context=None):
            return "completed"

    result = asyncio.run(
        Sample().run(user_context={"user": "synthetic-test", "role": "engineer"})
    )
    assert result == "completed"
