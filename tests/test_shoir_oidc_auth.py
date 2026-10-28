"""Unit tests for fail-closed Streamlit OIDC configuration and token access."""
from __future__ import annotations

from shoir_oidc_auth import (
    get_verified_streamlit_id_token,
    oidc_claims_display_name,
    oidc_configuration_status,
)


def _valid_secrets():
    return {
        "auth": {
            "redirect_uri": "https://shoir-ie-app.streamlit.app/oauth2callback",
            "cookie_secret": "synthetic-test-cookie-secret-not-for-deployment",
            "expose_tokens": "id",
            "enterprise": {
                "client_id": "synthetic-client",
                "client_secret": "synthetic-client-secret",
                "server_metadata_url": "https://idp.example.invalid/.well-known/openid-configuration",
            },
        }
    }


def test_oidc_configuration_requires_every_shared_and_provider_setting():
    status = oidc_configuration_status(_valid_secrets())
    assert status["configured"] is True
    assert status["ready"] is True
    assert status["missing_shared"] == ()
    assert status["missing_provider"] == ()


def test_oidc_configuration_fails_closed_without_id_token_exposure():
    secrets = _valid_secrets()
    secrets["auth"]["expose_tokens"] = "access"
    status = oidc_configuration_status(secrets)
    assert status["ready"] is False
    assert "expose_tokens includes id" in status["missing_shared"]


def test_oidc_configuration_fails_closed_when_provider_or_shared_values_are_missing():
    secrets = _valid_secrets()
    secrets["auth"].pop("cookie_secret")
    secrets["auth"]["enterprise"].pop("client_secret")
    status = oidc_configuration_status(secrets)
    assert status["ready"] is False
    assert "cookie_secret" in status["missing_shared"]
    assert "client_secret" in status["missing_provider"]


def test_oidc_status_never_returns_secret_values():
    status = oidc_configuration_status(_valid_secrets())
    serialized = repr(status)
    assert "synthetic-client-secret" not in serialized
    assert "synthetic-test-cookie-secret" not in serialized


class _TokenProxy:
    def __init__(self, token: str):
        self._token = token

    def __getitem__(self, key: str) -> str:
        if key != "id":
            raise KeyError(key)
        return self._token


class _User:
    is_logged_in = True

    def __init__(self, token: str, email: str = ""):
        self.tokens = _TokenProxy(token)
        self._email = email

    def get(self, key: str, default=None):
        return self._email if key == "email" else default


def test_id_token_helper_only_returns_bounded_token_for_logged_in_user():
    assert get_verified_streamlit_id_token(_User("a" * 64)) == "a" * 64
    assert get_verified_streamlit_id_token(_User("x" * 16_385)) == ""


def test_id_token_helper_never_returns_token_for_logged_out_or_missing_user():
    user = _User("synthetic-token")
    user.is_logged_in = False
    assert get_verified_streamlit_id_token(user) == ""
    assert get_verified_streamlit_id_token(object()) == ""


def test_oidc_display_hint_is_limited_and_not_used_for_authorization():
    user = _User("unused-token", email="approved-user@example.invalid")
    assert oidc_claims_display_name(user) == "approved-user@example.invalid"
