"""Regression checks for the Streamlit server's CORS/XSRF and host allowlists."""
from __future__ import annotations

import tomllib
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
CONFIG = ROOT / ".streamlit" / "config.toml"
REQUIREMENTS = ROOT / "requirements.txt"

EXPECTED_ORIGINS = {
    "https://shoir-ie-app.streamlit.app",
    "https://shoirieverified.streamlit.app",
    "https://shoir-ie-atvvfsacfxvqtrka37owfx.streamlit.app",
    "http://127.0.0.1:8501",
    "http://localhost:8501",
}
EXPECTED_HOSTS = {
    "shoir-ie-app.streamlit.app",
    "shoirieverified.streamlit.app",
    "shoir-ie-atvvfsacfxvqtrka37owfx.streamlit.app",
    "127.0.0.1",
    "localhost",
}


def test_streamlit_cors_xsrf_and_origin_host_allowlists_are_enabled():
    config = tomllib.loads(CONFIG.read_text(encoding="utf-8"))
    server = config["server"]

    assert server.get("enableCORS") is True
    assert server.get("enableXsrfProtection") is True
    allowed_origins = set(server.get("corsAllowedOrigins", []))
    allowed_hosts = set(server.get("allowedHosts", []))
    assert EXPECTED_ORIGINS <= allowed_origins
    assert EXPECTED_HOSTS <= allowed_hosts
    assert "*" not in allowed_origins
    assert "*" not in allowed_hosts


def test_streamlit_version_range_supports_the_security_config():
    requirements = REQUIREMENTS.read_text(encoding="utf-8")
    assert "streamlit>=1.61,<2" in requirements.replace(" ", "")
