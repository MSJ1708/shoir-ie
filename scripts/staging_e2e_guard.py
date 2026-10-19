#!/usr/bin/env python3
"""Fail-closed environment guard for authenticated Shoir-IE E2E tests."""
from __future__ import annotations

import os
import re
from urllib.parse import urlsplit

STAGING_PROJECT_REF = "hfhrosthswcybccepmak"
PRODUCTION_PROJECT_REF = "gcsamrdaeraxieaagsta"
PRODUCTION_APP_HOSTS = {"shoir-ie-app.streamlit.app"}
EDGE_PATH = "/functions/v1/shoir-persistence"


def _https_url(value: str, label: str):
    value = value.strip()
    if not value:
        raise ValueError(f"{label} is required; refusing to guess a target environment.")
    try:
        parsed = urlsplit(value)
        port = parsed.port
    except ValueError as exc:
        raise ValueError(f"{label} is not a valid URL.") from exc
    if parsed.scheme.casefold() != "https" or not parsed.hostname:
        raise ValueError(f"{label} must be an absolute HTTPS URL.")
    if parsed.username or parsed.password or parsed.query or parsed.fragment:
        raise ValueError(f"{label} must not contain credentials, query parameters, or a fragment.")
    if port not in (None, 443):
        raise ValueError(f"{label} must use standard HTTPS port 443.")
    return parsed


def validate_edge_url(value: str) -> str:
    if STAGING_PROJECT_REF == PRODUCTION_PROJECT_REF:
        raise ValueError("Staging and production project identifiers must be different.")
    parsed = _https_url(value, "SHOIR_E2E_EDGE_URL")
    expected_host = f"{STAGING_PROJECT_REF}.supabase.co"
    if parsed.hostname.casefold() != expected_host:
        raise ValueError("SHOIR_E2E_EDGE_URL must point to the approved Shoir-IE staging Supabase project.")
    if parsed.path.rstrip("/") != EDGE_PATH:
        raise ValueError("SHOIR_E2E_EDGE_URL must target the shoir-persistence Edge Function endpoint.")
    return value.strip().rstrip("/")


def validate_app_url(value: str, expected_host: str) -> str:
    expected_host = expected_host.strip().casefold().rstrip(".")
    if not expected_host or "://" in expected_host or "/" in expected_host or ":" in expected_host:
        raise ValueError("SHOIR_E2E_EXPECTED_STAGING_APP_HOST must contain only the staging hostname, without scheme or path.")
    if not re.fullmatch(r"[a-z0-9](?:[a-z0-9.-]*[a-z0-9])?", expected_host):
        raise ValueError("SHOIR_E2E_EXPECTED_STAGING_APP_HOST is not a valid hostname.")
    if expected_host in PRODUCTION_APP_HOSTS:
        raise ValueError("The production Streamlit host cannot be used for authenticated E2E tests.")
    parsed = _https_url(value, "SHOIR_E2E_APP_URL")
    host = parsed.hostname.casefold().rstrip(".")
    if host in PRODUCTION_APP_HOSTS:
        raise ValueError("SHOIR_E2E_APP_URL points to the production Streamlit app; staging is required.")
    if host != expected_host:
        raise ValueError("SHOIR_E2E_APP_URL hostname does not match SHOIR_E2E_EXPECTED_STAGING_APP_HOST.")
    return value.strip().rstrip("/") + "/"


def validate_edge_from_env() -> str:
    return validate_edge_url(os.environ.get("SHOIR_E2E_EDGE_URL", ""))


def validate_app_from_env() -> str:
    return validate_app_url(
        os.environ.get("SHOIR_E2E_APP_URL", ""),
        os.environ.get("SHOIR_E2E_EXPECTED_STAGING_APP_HOST", ""),
    )


def validate_all_from_env() -> None:
    validate_edge_from_env()
    validate_app_from_env()


if __name__ == "__main__":
    validate_all_from_env()
    print("Staging target preflight passed. Target URLs are intentionally not printed.")
