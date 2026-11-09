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
    # The test suite may import the same source module under distinct
    # module names; compare the callable contract rather than Python object
    # identity across duplicate module loads.
    for default in (
        PasscodeDB.__table__.c.created_at.default.arg,
        SimulationLogDB.__table__.c.executed_at.default.arg,
    ):
        assert callable(default)
        assert default.__name__ == _utcnow_naive.__name__
        assert default.__module__.endswith("database")
        generated = default(None)
        assert isinstance(generated, datetime)
        assert generated.tzinfo is None
        assert abs((datetime.now(timezone.utc).replace(tzinfo=None) - generated).total_seconds()) < 5


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
