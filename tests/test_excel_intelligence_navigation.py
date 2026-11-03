"""Regression tests for Excel Intelligence routing and entitlement controls."""
from __future__ import annotations

from pathlib import Path

from industrial_platform import PLATFORM_CATALOG
from industrial_platform_excellence import MODULE_MATRIX
from shoir_application_shell import _module_choices, _module_target_section, module_group
from shoir_excel_entitlements import (
    excel_intelligence_allowed,
    excel_intelligence_entitlement_config,
    excel_intelligence_minimum_tier,
)


ROOT = Path(__file__).resolve().parents[1]
MODULE_NAME = "Excel Intelligence"


def test_excel_intelligence_is_listed_under_workbench_data():
    rows = [row for row in MODULE_MATRIX if row[1] == MODULE_NAME]
    assert len(rows) == 1
    assert rows[0][0] == "Data"
    assert rows[0][2] == excel_intelligence_minimum_tier()

    choices = _module_choices(
        [MODULE_NAME],
        "DATA",
        "",
        {MODULE_NAME: {"category": "Data Platform"}},
    )
    assert choices == [MODULE_NAME]


def test_excel_intelligence_uses_the_shared_data_navigation_group():
    # Workbench modules have their own module matrix; this feature is deliberately
    # not inserted into the fixed 96-module paid subscription catalogue.
    metadata = {MODULE_NAME: {"category": "Data Platform"}}
    assert module_group(MODULE_NAME, metadata) == "Data"
    assert _module_target_section(MODULE_NAME, metadata) == "DATA"


def test_excel_intelligence_access_uses_a_configurable_server_side_tier(monkeypatch):
    monkeypatch.delenv("SHOIR_EXCEL_INTELLIGENCE_MINIMUM_TIER", raising=False)
    assert excel_intelligence_minimum_tier() == "Enterprise"
    assert not excel_intelligence_allowed("Starter")
    assert not excel_intelligence_allowed("Professional")
    assert excel_intelligence_allowed("Enterprise")
    assert excel_intelligence_allowed("Enterprise Plus")
    # Research Pack inherits Enterprise features under the existing product policy.
    assert excel_intelligence_allowed("Research Pack")

    from shoir_excel_entitlements import apply_excel_intelligence_entitlement
    assert "Excel Intelligence" in apply_excel_intelligence_entitlement(["Excel Data Cleaning & Import"], "Enterprise")
    assert "Excel Intelligence" not in apply_excel_intelligence_entitlement(["Excel Data Cleaning & Import"], "Professional")

    monkeypatch.setenv("SHOIR_EXCEL_INTELLIGENCE_MINIMUM_TIER", "Professional")
    assert excel_intelligence_minimum_tier() == "Professional"
    assert excel_intelligence_allowed("Professional")
    assert not excel_intelligence_allowed("Mid-Tier Pro")
    assert "Excel Intelligence" in apply_excel_intelligence_entitlement(["Excel Data Cleaning & Import"], "Professional")
    assert not apply_excel_intelligence_entitlement(["Excel Intelligence"], "Mid-Tier Pro")


def test_invalid_excel_intelligence_tier_configuration_fails_closed(monkeypatch):
    monkeypatch.setenv("SHOIR_EXCEL_INTELLIGENCE_MINIMUM_TIER", "not-a-real-package")
    config = excel_intelligence_entitlement_config()
    assert config["valid"] is False
    assert config["minimum_tier"] == "Enterprise Plus"
    assert config["warning"]
    assert not excel_intelligence_allowed("Enterprise")
    assert excel_intelligence_allowed("Enterprise Plus")


def test_workbench_and_renderer_are_explicitly_wired_to_the_existing_safe_engine():
    workbench = (ROOT / "pages" / "Industrial_Engineering_Workbench.py").read_text(encoding="utf-8")
    platform = (ROOT / "industrial_platform.py").read_text(encoding="utf-8")
    assert 'if selected == "Excel Intelligence":' in workbench
    assert 'render_module(selected, RAW_TIER, USER)' in workbench
    assert 'if module=="Excel Intelligence":' in platform
    assert "excel_intelligence_allowed(tier)" in platform
    assert "render_excel_intelligence_safe(tier, username)" in platform


def test_excel_intelligence_renderer_requires_authenticated_non_guest_session():
    platform = (ROOT / "industrial_platform.py").read_text(encoding="utf-8")
    route = platform.split('if module=="Excel Intelligence":', 1)[1].split(
        'if module=="Excel Data Cleaning & Import":', 1
    )[0]
    assert 'st.session_state.get("authenticated") is not True' in route
    assert 'actor.casefold() in {"", "guest", "guest visitor", "anonymous"}' in route
    assert 'Sign in with an active Shoir-IE account' in route


def test_office_addin_does_not_post_workbook_data_without_authenticated_api():
    taskpane = (ROOT / "excel_addin" / "taskpane.js").read_text(encoding="utf-8")
    readme = (ROOT / "excel_addin" / "README.md").read_text(encoding="utf-8")
    assert "Excel.run" in taskpane
    assert "10,000 cells" in taskpane
    assert "fetch(" not in taskpane
    assert "/api/workbook/import" not in taskpane
    manifest = (ROOT / "excel_addin" / "manifest.xml").read_text(encoding="utf-8")
    assert "<Permissions>ReadDocument</Permissions>" in manifest
    assert "does not POST workbook contents to a server" in readme
