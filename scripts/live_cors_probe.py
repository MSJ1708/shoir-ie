#!/usr/bin/env python3
"""Live, non-mutating CORS checks for the deployed staging Shoir-IE Edge Function.

This probe intentionally sends only OPTIONS requests and a POST with a rejected
Origin. It never sends credentials and refuses production endpoint targets.
"""
from __future__ import annotations

import os
import sys
from urllib.error import HTTPError, URLError
from urllib.parse import urlsplit
from urllib.request import Request, urlopen

STAGING_PROJECT_REF = "hfhrosthswcybccepmak"
EDGE_PATH = "/functions/v1/shoir-persistence"
STAGING_APP_HOSTS = {
    "shoirieverified.streamlit.app",
    "shoir-ie-atvvfsacfxvqtrka37owfx.streamlit.app",
}


def _origin_from_env() -> str:
    raw = os.environ.get("SHOIR_CORS_ALLOWED_ORIGIN", "").strip()
    expected_host = os.environ.get("SHOIR_E2E_EXPECTED_STAGING_APP_HOST", "").strip().lower().rstrip(".")
    if not raw or not expected_host:
        raise ValueError("Staging app URL and expected staging host are required.")
    parsed = urlsplit(raw)
    if parsed.scheme != "https" or not parsed.hostname:
        raise ValueError("The allowed staging app origin must be an absolute HTTPS URL.")
    if parsed.username or parsed.password or parsed.query or parsed.fragment:
        raise ValueError("The allowed staging app origin must not contain credentials, query, or fragment.")
    if parsed.path not in ("", "/") or parsed.port not in (None, 443):
        raise ValueError("The allowed staging app URL must identify only an HTTPS origin.")
    host = parsed.hostname.lower().rstrip(".")
    if host not in STAGING_APP_HOSTS or host != expected_host:
        raise ValueError("The configured origin does not match an approved staging app host.")
    return f"https://{host}"


def _edge_url_from_env() -> str:
    raw = os.environ.get("SHOIR_CORS_EDGE_URL", "").strip()
    if not raw:
        raise ValueError("The staging Edge Function URL is required.")
    parsed = urlsplit(raw)
    expected_host = f"{STAGING_PROJECT_REF}.supabase.co"
    if (
        parsed.scheme != "https"
        or parsed.hostname != expected_host
        or parsed.path.rstrip("/") != EDGE_PATH
        or parsed.username
        or parsed.password
        or parsed.query
        or parsed.fragment
        or parsed.port not in (None, 443)
    ):
        raise ValueError("Refusing a non-staging or malformed Edge Function target.")
    return raw.rstrip("/")


def _request(url: str, method: str, headers: dict[str, str], body: bytes | None = None) -> tuple[int, dict[str, str]]:
    request = Request(url, data=body, headers=headers, method=method)
    try:
        with urlopen(request, timeout=20) as response:
            return response.getcode(), {k.lower(): v for k, v in response.headers.items()}
    except HTTPError as exc:
        try:
            return exc.code, {k.lower(): v for k, v in exc.headers.items()}
        finally:
            exc.close()
    except (URLError, TimeoutError, OSError):
        # Do not print URLs, credentials, proxy details, or unbounded exception data.
        raise RuntimeError("Live staging HTTP probe could not connect; inspect runner network/DNS and the staging endpoint.") from None


def _assert_response(
    label: str,
    actual_status: int,
    headers: dict[str, str],
    expected_status: int,
    expected_origin: str | None,
) -> None:
    if actual_status != expected_status:
        raise AssertionError(f"{label}: expected HTTP {expected_status}, received {actual_status}.")
    actual_origin = headers.get("access-control-allow-origin")
    if actual_origin == "*":
        raise AssertionError(f"{label}: wildcard Access-Control-Allow-Origin is forbidden.")
    if actual_origin != expected_origin:
        raise AssertionError(
            f"{label}: expected Access-Control-Allow-Origin "
            f"{expected_origin!r}, received {actual_origin!r}."
        )


def run_probe() -> int:
    try:
        edge_url = _edge_url_from_env()
        allowed_origin = _origin_from_env()
        evil_origin = "https://shoir-ie-cors-probe.invalid"
        cases = [
            (
                "approved-origin-preflight",
                "OPTIONS",
                {
                    "Origin": allowed_origin,
                    "Access-Control-Request-Method": "POST",
                    "Access-Control-Request-Headers": "content-type,authorization",
                },
                None,
                204,
                allowed_origin,
            ),
            (
                "rejected-origin-preflight",
                "OPTIONS",
                {
                    "Origin": evil_origin,
                    "Access-Control-Request-Method": "POST",
                    "Access-Control-Request-Headers": "content-type",
                },
                None,
                403,
                None,
            ),
            (
                "missing-origin-preflight",
                "OPTIONS",
                {},
                None,
                204,
                None,
            ),
            (
                "rejected-origin-post",
                "POST",
                {"Origin": evil_origin, "Content-Type": "application/json"},
                b'{"action":"unknown"}',
                403,
                None,
            ),
        ]
        for label, method, headers, body, expected_status, expected_origin in cases:
            actual_status, actual_headers = _request(edge_url, method, headers, body)
            _assert_response(label, actual_status, actual_headers, expected_status, expected_origin)
            print(f"PASS {label}")
        print("PASS live staging CORS probe (no credentials or account mutations)")
        return 0
    except (ValueError, AssertionError, RuntimeError) as exc:
        print(f"FAIL live staging CORS probe: {exc}", file=sys.stderr)
        return 1


if __name__ == "__main__":
    raise SystemExit(run_probe())
