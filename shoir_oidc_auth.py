"""Configuration helpers for optional Streamlit OIDC login.

No network calls or secret values are logged at import time. The actual ID token
is passed server-side to the Edge Function for independent signature validation.
"""
from __future__ import annotations

from collections.abc import Mapping
from typing import Any


REQUIRED_SHARED_AUTH_KEYS = ("redirect_uri", "cookie_secret")
REQUIRED_PROVIDER_KEYS = ("client_id", "client_secret", "server_metadata_url")


def _mapping(value: Any) -> Mapping[str, Any]:
    return value if isinstance(value, Mapping) else {}


def _nonempty_string(value: Any) -> bool:
    return isinstance(value, str) and bool(value.strip())


def oidc_configuration_status(secrets: Any) -> dict[str, Any]:
    """Return readiness without exposing client secrets or token values."""
    root = _mapping(secrets)
    auth = _mapping(root.get("auth"))
    provider = _mapping(auth.get("enterprise"))
    missing_shared = [
        key for key in REQUIRED_SHARED_AUTH_KEYS
        if not _nonempty_string(auth.get(key))
    ]
    missing_provider = [
        key for key in REQUIRED_PROVIDER_KEYS
        if not _nonempty_string(provider.get(key))
    ]
    exposed = auth.get("expose_tokens")
    if isinstance(exposed, str):
        exposed_tokens = {exposed.strip().lower()}
    elif isinstance(exposed, (list, tuple, set)):
        exposed_tokens = {
            token.strip().lower() for token in exposed
            if isinstance(token, str)
        }
    else:
        exposed_tokens = set()
    if "id" not in exposed_tokens:
        missing_shared.append("expose_tokens includes id")
    ready = not missing_shared and not missing_provider
    return {
        "configured": bool(auth) or bool(provider),
        "ready": ready,
        "missing_shared": tuple(missing_shared),
        "missing_provider": tuple(missing_provider),
        "provider_name": "enterprise",
    }


def get_verified_streamlit_id_token(user: Any) -> str:
    """Read the explicitly exposed ID token without ever displaying it."""
    try:
        if not bool(getattr(user, "is_logged_in", False)):
            return ""
        tokens = getattr(user, "tokens", None)
        token = tokens.get("id") if isinstance(tokens, Mapping) else tokens["id"]
        if not isinstance(token, str) or not token.strip() or len(token) > 16_384:
            return ""
        return token.strip()
    except Exception:
        return ""


def oidc_claims_display_name(user: Any) -> str:
    """Return a non-sensitive display hint only; server-side token claims are authoritative."""
    try:
        email = str(user.get("email", "") or "").strip()
        return email[:320] if email else ""
    except Exception:
        return ""
