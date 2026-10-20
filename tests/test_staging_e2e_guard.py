"""Unit tests for staging-only authenticated E2E URL validation."""
import pytest

from scripts.staging_e2e_guard import STAGING_PROJECT_REF, validate_app_url, validate_edge_url


def test_accepts_approved_staging_edge_endpoint():
    value = f"https://{STAGING_PROJECT_REF}.supabase.co/functions/v1/shoir-persistence"
    assert validate_edge_url(value) == value


@pytest.mark.parametrize("value", [
    "https://gcsamrdaeraxieaagsta.supabase.co/functions/v1/shoir-persistence",
    "http://hfhrosthswcybccepmak.supabase.co/functions/v1/shoir-persistence",
    "https://hfhrosthswcybccepmak.supabase.co/rest/v1/",
    "",
])
def test_rejects_wrong_or_insecure_edge_targets(value):
    with pytest.raises(ValueError):
        validate_edge_url(value)


def test_accepts_explicit_staging_app_host():
    assert validate_app_url(
        "https://shoir-ie-staging.streamlit.app/",
        "shoir-ie-staging.streamlit.app",
    ) == "https://shoir-ie-staging.streamlit.app/"


@pytest.mark.parametrize(("url", "expected_host"), [
    ("https://shoir-ie-app.streamlit.app/", "shoir-ie-app.streamlit.app"),
    ("http://shoir-ie-staging.streamlit.app/", "shoir-ie-staging.streamlit.app"),
    ("https://different.streamlit.app/", "shoir-ie-staging.streamlit.app"),
    ("", "shoir-ie-staging.streamlit.app"),
    ("https://shoir-ie-staging.streamlit.app/?target=prod", "shoir-ie-staging.streamlit.app"),
])
def test_rejects_production_http_or_mismatched_app_targets(url, expected_host):
    with pytest.raises(ValueError):
        validate_app_url(url, expected_host)


def test_accepts_publishable_key():
    from scripts.staging_e2e_guard import validate_publishable_key

    assert validate_publishable_key("sb_publishable_example123") == "sb_publishable_example123"


@pytest.mark.parametrize("value", ["sb_publishable_bad key", "sb_publishable_bad\u200bkey"])
def test_rejects_malformed_publishable_key(value):
    from scripts.staging_e2e_guard import validate_publishable_key

    with pytest.raises(ValueError):
        validate_publishable_key(value)
