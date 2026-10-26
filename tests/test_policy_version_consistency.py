"""Prevent policy-version drift across public documents, UI copies and server guards."""
from __future__ import annotations

import re
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
APP = (ROOT / "app.py").read_text(encoding="utf-8")
EDGE = (ROOT / "supabase" / "functions" / "shoir-persistence" / "index.ts").read_text(encoding="utf-8")
GATE = (ROOT / "scripts" / "authenticated_release_gate.py").read_text(encoding="utf-8")
APPROVAL_MIGRATION = (
    ROOT / "supabase" / "migrations" / "20261023130000_refresh_refund_policy_acceptance_version.sql"
).read_text(encoding="utf-8")
RISK_REGISTER = (ROOT / "docs" / "LEGAL_RISK_REGISTER.md").read_text(encoding="utf-8")

POLICIES = {
    "TERMS_VERSION": {
        "document": "TERMS_AND_CONDITIONS.md",
        "embedded": "TERMS_AND_CONDITIONS_TEXT",
        "edge_column": "terms_version",
        "gate_key": "terms_version",
    },
    "PRIVACY_POLICY_VERSION": {
        "document": "PRIVACY_POLICY.md",
        "embedded": "PRIVACY_POLICY_TEXT",
        "edge_column": "privacy_policy_version",
        "gate_key": "privacy_policy_version",
    },
    "REFUND_POLICY_VERSION": {
        "document": "REFUND_POLICY.md",
        "embedded": "REFUND_POLICY_TEXT",
        "edge_column": "refund_policy_version",
        "gate_key": "refund_policy_version",
    },
    "COOKIE_POLICY_VERSION": {
        "document": "COOKIE_POLICY.md",
        "embedded": "COOKIE_POLICY_TEXT",
        "edge_column": "cookie_policy_version",
        "gate_key": "cookie_policy_version",
    },
}


def _version_from_text(text: str, source: str) -> str:
    match = re.search(r"(?m)^\*\*Version:\*\*\s+([^\s]+)", text)
    assert match, f"Could not find a version declaration in {source}"
    return match.group(1).strip().rstrip(chr(96))


def _assignment(source: str, name: str, filename: str) -> str:
    pattern = rf'(?m)^\s*(?:const\s+)?{re.escape(name)}\s*=\s*"([^"]+)"'
    match = re.search(pattern, source)
    assert match, f"Could not find {name} in {filename}"
    return match.group(1)


def _embedded_policy_version(name: str) -> str:
    pattern = rf'(?ms)^{re.escape(name)}\s*=\s*"""(.*?)"""'
    match = re.search(pattern, APP)
    assert match, f"Could not find embedded policy text {name} in app.py"
    return _version_from_text(match.group(1), f"app.py:{name}")


def test_public_policy_documents_match_application_constants_and_embedded_copies():
    for constant, spec in POLICIES.items():
        document_path = ROOT / "docs" / spec["document"]
        document_version = _version_from_text(
            document_path.read_text(encoding="utf-8"),
            str(document_path.relative_to(ROOT)),
        )
        assert _assignment(APP, constant, "app.py") == document_version
        assert _embedded_policy_version(spec["embedded"]) == document_version


def test_edge_enforcement_and_latest_approval_guard_match_published_policy_versions():
    for constant, spec in POLICIES.items():
        version = _assignment(APP, constant, "app.py")
        assert _assignment(EDGE, constant, "shoir-persistence/index.ts") == version
        column = spec["edge_column"]
        guard = re.search(
            rf"NEW\.{re.escape(column)}\s+IS DISTINCT FROM\s+'([^']+)'",
            APPROVAL_MIGRATION,
        )
        assert guard, f"Latest approval guard has no version check for {column}"
        assert guard.group(1) == version, f"Approval guard drift for {column}"


def test_authenticated_staging_registration_probe_uses_current_policy_versions():
    for constant, spec in POLICIES.items():
        version = _assignment(APP, constant, "app.py")
        gate_key = spec["gate_key"]
        pattern = rf'"{re.escape(gate_key)}"\s*:\s*"{re.escape(version)}"'
        assert re.search(pattern, GATE), (
            f"Authenticated release probe is missing current {gate_key}"
        )


def test_legal_risk_register_lists_current_policy_versions():
    for constant, spec in POLICIES.items():
        version = _assignment(APP, constant, "app.py")
        expected = f"({spec['document']}) — version {version}"
        assert expected in RISK_REGISTER, (
            f"Legal risk register is stale for {spec['document']}"
        )
