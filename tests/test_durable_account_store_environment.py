"""Contracts for fail-closed Streamlit Supabase environment routing."""
import base64
import json

import pytest

import durable_account_store as store


def _legacy_key(role: str) -> str:
    body = base64.urlsafe_b64encode(json.dumps({"role": role}).encode()).decode().rstrip("=")
    return f"header.{body}.signature"


def test_legacy_production_default_remains_unchanged():
    url, key = store._resolve_supabase_edge_config("production")
    assert url == store.PRODUCTION_SUPABASE_EDGE_URL
    assert key == store.PRODUCTION_SUPABASE_PUBLISHABLE_KEY


def test_staging_requires_explicit_matching_endpoint_and_public_key():
    url, key = store._resolve_supabase_edge_config(
        "staging",
        store.STAGING_SUPABASE_EDGE_URL,
        "sb_publishable_staging_test_key",
    )
    assert url == store.STAGING_SUPABASE_EDGE_URL
    assert key == "sb_publishable_staging_test_key"


@pytest.mark.parametrize(
    ("url", "key"),
    [
        ("", ""),
        (store.STAGING_SUPABASE_EDGE_URL, ""),
        ("", "sb_publishable_staging_test_key"),
        (store.PRODUCTION_SUPABASE_EDGE_URL, "sb_publishable_production_key"),
        ("http://hfhrosthswcybccepmak.supabase.co/functions/v1/shoir-persistence", "sb_publishable_staging_key"),
        ("https://hfhrosthswcybccepmak.supabase.co/rest/v1", "sb_publishable_staging_key"),
        ("https://hfhrosthswcybccepmak.supabase.co/functions/v1/shoir-persistence?route=production", "sb_publishable_staging_key"),
    ],
)
def test_staging_rejects_missing_or_mismatched_config(url, key):
    with pytest.raises(RuntimeError):
        store._resolve_supabase_edge_config("staging", url, key)


def test_production_rejects_staging_endpoint_override():
    with pytest.raises(RuntimeError):
        store._resolve_supabase_edge_config(
            "production",
            store.STAGING_SUPABASE_EDGE_URL,
            "sb_publishable_staging_test_key",
        )


def test_invalid_environment_fails_closed():
    with pytest.raises(RuntimeError):
        store._resolve_supabase_edge_config("development")


def test_only_publishable_or_legacy_anon_keys_are_accepted():
    assert store._validate_supabase_publishable_key("sb_publishable_staging_test_key")
    assert store._validate_supabase_publishable_key(_legacy_key("anon"))
    with pytest.raises(RuntimeError):
        store._validate_supabase_publishable_key("sb_secret_staging_test_key")
    with pytest.raises(RuntimeError):
        store._validate_supabase_publishable_key(_legacy_key("service_role"))


def test_direct_database_url_settings_are_detected(monkeypatch):
    monkeypatch.delenv("SHOIR_DATABASE_URL", raising=False)
    monkeypatch.delenv("SUPABASE_DB_URL", raising=False)
    monkeypatch.delenv("DATABASE_URL", raising=False)
    assert store._configured_direct_database_url() == ""
    monkeypatch.setenv("DATABASE_URL", "postgresql://production.example.invalid/db")
    assert store._configured_direct_database_url() == "postgresql://production.example.invalid/db"
