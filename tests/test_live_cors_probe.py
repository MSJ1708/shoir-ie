from __future__ import annotations

import pytest

from scripts.live_cors_probe import (
    _assert_response,
    _edge_url_from_env,
    _origin_from_env,
)


def test_edge_url_rejects_production_or_wrong_path(monkeypatch):
    monkeypatch.setenv(
        "SHOIR_CORS_EDGE_URL",
        "https://gcsamrdaeraxieaagsta.supabase.co/functions/v1/shoir-persistence",
    )
    with pytest.raises(ValueError, match="non-staging"):
        _edge_url_from_env()


def test_edge_url_accepts_only_staging_function(monkeypatch):
    monkeypatch.setenv(
        "SHOIR_CORS_EDGE_URL",
        "https://hfhrosthswcybccepmak.supabase.co/functions/v1/shoir-persistence/",
    )
    assert _edge_url_from_env() == (
        "https://hfhrosthswcybccepmak.supabase.co/functions/v1/shoir-persistence"
    )


def test_origin_requires_expected_staging_host(monkeypatch):
    monkeypatch.setenv("SHOIR_CORS_ALLOWED_ORIGIN", "https://shoirieverified.streamlit.app/")
    monkeypatch.setenv("SHOIR_E2E_EXPECTED_STAGING_APP_HOST", "shoirieverified.streamlit.app")
    assert _origin_from_env() == "https://shoirieverified.streamlit.app"


@pytest.mark.parametrize(
    ("status", "headers", "expected_status", "expected_origin"),
    [
        (204, {"access-control-allow-origin": "https://shoirieverified.streamlit.app"}, 204, "https://shoirieverified.streamlit.app"),
        (403, {}, 403, None),
    ],
)
def test_response_contract(status, headers, expected_status, expected_origin):
    _assert_response("case", status, headers, expected_status, expected_origin)


def test_response_contract_rejects_wildcard():
    with pytest.raises(AssertionError, match="wildcard"):
        _assert_response("case", 200, {"access-control-allow-origin": "*"}, 200, "*")


def test_response_contract_rejects_wrong_origin():
    with pytest.raises(AssertionError, match="received"):
        _assert_response(
            "case",
            204,
            {"access-control-allow-origin": "https://attacker.example"},
            204,
            "https://shoirieverified.streamlit.app",
        )
