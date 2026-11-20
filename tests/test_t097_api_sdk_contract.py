from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]


def test_t097_edge_enforces_a_backward_compatible_versioned_api_contract():
    edge = (ROOT / "supabase/functions/shoir-persistence/index.ts").read_text(encoding="utf-8")
    assert 'const apiVersion = String(body.api_version || "v1").trim();' in edge
    assert 'if (apiVersion !== "v1")' in edge
    assert 'supported_versions: ["v1"]' in edge
    assert 'if (action === "platform_record_save")' in edge
    assert 'if (action === "platform_record_list")' in edge
    assert 'if (action === "workspace_load")' in edge


def test_t097_openapi_and_sdk_do_not_claim_public_availability_or_ship_secrets():
    readme = (ROOT / "sdk/typescript/README.md").read_text(encoding="utf-8")
    spec = (ROOT / "sdk/typescript/openapi.yaml").read_text(encoding="utf-8")
    sdk = (ROOT / "sdk/typescript/index.mjs").read_text(encoding="utf-8")
    assert "not yet published to npm" in readme
    assert "not a published public API" in spec
    assert 'redirect: "error"' in sdk
    assert 'credentials: "omit"' in sdk
    assert 'api_version: API_VERSION' in sdk
