"""Prevent insecure Streamlit CORS/XSRF defaults from returning."""
from __future__ import annotations

import tomllib
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
CONFIG = ROOT / ".streamlit" / "config.toml"

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


def test_streamlit_cors_and_xsrf_are_enabled_with_narrow_origin_and_host_allowlists():
    config = tomllib.loads(CONFIG.read_text(encoding="utf-8"))
    server = config["server"]

    assert server.get("enableCORS") is True, (
        "Disabling Streamlit CORS allows wildcard-origin HTTP and WebSocket access."
    )
    assert server.get("enableXsrfProtection") is True
    assert set(server.get("corsAllowedOrigins", [])) == EXPECTED_ORIGINS
    assert set(server.get("allowedHosts", [])) == EXPECTED_HOSTS
    assert "*" not in server.get("allowedHosts", [])
