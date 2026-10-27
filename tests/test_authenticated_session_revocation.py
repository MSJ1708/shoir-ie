"""Tests for live staging session revocation acceptance without external calls."""
from pathlib import Path
import sys

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "scripts"))

from authenticated_release_gate import verify_session_revocation


VALID_SESSION_ERROR = "A transaction/payment reference is required for renewal review."


class FakeAPI:
    def __init__(self, responses):
        self.responses = list(responses)
        self.calls = []

    def call(self, action, payload):
        self.calls.append((action, dict(payload)))
        response = self.responses.pop(0)
        if isinstance(response, Exception):
            raise response
        return response


def session_response_sequence(reuse_response=(401, {"error": "Unauthorized session."})):
    return [
        (400, {"error": VALID_SESSION_ERROR}),
        (200, {"ok": True, "revoked": True}),
        reuse_response,
    ]


def test_session_revocation_requires_same_token_to_be_denied_after_logout():
    api = FakeAPI(session_response_sequence())

    passed, detail = verify_session_revocation(
        api, "shoir-e2e-expired", "synthetic-disposable-token"
    )

    assert passed is True
    assert "HTTP 401" in detail
    assert [action for action, _ in api.calls] == [
        "renew_request",
        "logout",
        "renew_request",
    ]
    # This no-write renewal probe supports renewal-scoped tokens for expired
    # accounts and must not include a transaction ID or proof payload.
    assert api.calls[0][1] == {
        "username": "shoir-e2e-expired",
        "token": "synthetic-disposable-token",
    }
    assert api.calls[2][1] == api.calls[0][1]


def test_revocation_probe_fails_closed_if_session_was_not_valid_before_logout():
    api = FakeAPI([(401, {"error": "Unauthorized session."})])

    passed, detail = verify_session_revocation(
        api, "shoir-e2e-active", "synthetic-token"
    )

    assert passed is False
    assert "Pre-logout" in detail
    assert [action for action, _ in api.calls] == ["renew_request"]


def test_revocation_probe_requires_logout_to_confirm_token_deletion():
    api = FakeAPI([
        (400, {"error": VALID_SESSION_ERROR}),
        (200, {"ok": True, "revoked": False}),
    ])

    passed, detail = verify_session_revocation(
        api, "shoir-e2e-active", "synthetic-token"
    )

    assert passed is False
    assert "did not confirm revocation" in detail
    assert [action for action, _ in api.calls] == ["renew_request", "logout"]


def test_revocation_probe_fails_if_same_token_still_reaches_authenticated_validation():
    api = FakeAPI(session_response_sequence(
        reuse_response=(400, {"error": VALID_SESSION_ERROR})
    ))

    passed, detail = verify_session_revocation(
        api, "shoir-e2e-active", "synthetic-token"
    )

    assert passed is False
    assert "was not denied" in detail


def test_revocation_probe_fails_closed_on_transport_error():
    api = FakeAPI([RuntimeError("synthetic transport failure")])

    passed, detail = verify_session_revocation(
        api, "shoir-e2e-active", "synthetic-token"
    )

    assert passed is False
    assert "RuntimeError" in detail
    # Error details must not include the token or raw transport message.
    assert "synthetic-token" not in detail
    assert "synthetic transport failure" not in detail
