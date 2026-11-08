"""Regression coverage for UTC timestamps in legacy SQLAlchemy DateTime columns."""

import asyncio
from datetime import datetime, timezone


def test_legacy_sqlalchemy_datetime_default_is_naive_utc():
    from database import PasscodeDB, SimulationLogDB, _utcnow_naive

    value = _utcnow_naive()
    assert isinstance(value, datetime)
    assert value.tzinfo is None
    now_utc = datetime.now(timezone.utc).replace(tzinfo=None)
    assert abs((now_utc - value).total_seconds()) < 5
    assert PasscodeDB.__table__.c.created_at.default.arg is _utcnow_naive
    assert SimulationLogDB.__table__.c.executed_at.default.arg is _utcnow_naive


def test_enterprise_audit_decorator_supports_synchronous_operations():
    from enterprise_engine import secure_audit_log

    class Sample:
        @secure_audit_log(required_role="engineer")
        def run(self, user_context=None):
            return "completed"

    result = asyncio.run(
        Sample().run(user_context={"user": "synthetic-test", "role": "engineer"})
    )
    assert result == "completed"
