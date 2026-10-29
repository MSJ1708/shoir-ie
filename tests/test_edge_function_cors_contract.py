"""Source contracts for the exact-origin Edge Function CORS handler."""
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
INDEX = ROOT / "supabase" / "functions" / "shoir-persistence" / "index.ts"
SECURITY = ROOT / "supabase" / "functions" / "shoir-persistence" / "security.ts"


def test_handler_rejects_unapproved_origins_and_returns_safe_preflight():
    index = INDEX.read_text(encoding="utf-8")
    handler = index.split("Deno.serve(async (req) => {", 1)[1]
    assert 'const origin = req.headers.get("origin")' in handler
    assert 'parseAllowedBrowserOrigins(\n    Deno.env.get("SHOIR_ALLOWED_BROWSER_ORIGINS")' in handler
    assert "if (!isAllowedBrowserOrigin(origin, allowedOrigins))" in handler
    assert 'return response({ error: "Origin not allowed." }, 403, origin, allowedOrigins)' in handler
    assert "status: 204" in handler
    assert "headers: corsHeadersForOrigin(origin)" in handler
    assert 'if (req.method !== "POST")' in handler
    assert 'return sendResponse({ error: "Method not allowed." }, 405)' in handler


def test_response_helper_never_emits_wildcard_and_applies_origin_vary():
    index = INDEX.read_text(encoding="utf-8")
    security = SECURITY.read_text(encoding="utf-8")
    assert '"Access-Control-Allow-Origin": "*"' not in index
    assert "headers: corsHeadersForOrigin(origin)" in index
    assert '"Vary": "Origin"' in security
    assert '"Access-Control-Allow-Methods": "POST, OPTIONS"' in security
    assert 'headers.set("Access-Control-Allow-Origin", origin)' in security
    assert "raw === undefined" in security
    assert '"https://shoir-ie-app.streamlit.app"' in security
    assert '"https://shoirieverified.streamlit.app"' in security
    assert "!VERIFIED_BROWSER_ORIGINS.has(entry)" in security


def test_staging_and_production_allowlists_are_not_combined_in_shared_source():
    security = SECURITY.read_text(encoding="utf-8")
    index = INDEX.read_text(encoding="utf-8")
    assert "SHOIR_ALLOWED_BROWSER_ORIGINS" in index
    assert "parseAllowedBrowserOrigins(undefined)" in index
    assert 'url.origin !== entry' in security
    assert 'url.protocol !== "https:"' in security
    assert "VERIFIED_BROWSER_ORIGINS" in security
    assert "unverified" not in security.casefold()
