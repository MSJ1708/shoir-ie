"""Regression tests for Excel Intelligence routing and entitlement controls."""
from __future__ import annotations

from pathlib import Path

from industrial_platform_excellence import MODULE_MATRIX, module_availability
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

    enterprise_rows = module_availability("Enterprise")
    enterprise_row = enterprise_rows.loc[enterprise_rows["Module"] == MODULE_NAME].iloc[0]
    assert enterprise_row["Category"] == "Data"
    assert bool(enterprise_row["Available"]) is True

    professional_rows = module_availability("Professional")
    professional_row = professional_rows.loc[professional_rows["Module"] == MODULE_NAME].iloc[0]
    assert bool(professional_row["Available"]) is False


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

    monkeypatch.setenv("SHOIR_EXCEL_INTELLIGENCE_MINIMUM_TIER", "Professional")
    assert excel_intelligence_minimum_tier() == "Professional"
    assert excel_intelligence_allowed("Professional")
    assert not excel_intelligence_allowed("Mid-Tier Pro")


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
    assert "render_excel_intelligence_safe(tier, username, enable_copilot=True)" in platform

    runtime = (ROOT / "shoir_excel_runtime.py").read_text(encoding="utf-8")
    assert "def _render_excel_dataframe(" in runtime
    assert "MAX_RENDER_PREVIEW_ROWS = 2_000" in runtime
    assert "def _safe_excel_display_frame(" in runtime
    assert "pd.array(" in runtime
    assert "MAX_RENDER_JSON_CHARS = 250_000" in runtime
    assert "def _render_excel_json(" in runtime
    assert "MAX_RENDER_CHART_POINTS = 20_000" in runtime
    assert "def _render_excel_plotly_figure(" in runtime
    assert "def scan_source_formulas(" in runtime
    assert "Inspect source formulas" in runtime
    assert "MAX_FORMULA_SCAN_CELLS" in runtime
    assert "formula_inventory=formula_inventory" in runtime


def test_premium_excel_runtime_rechecks_entitlement_and_preserves_starter_route():
    runtime = (ROOT / "shoir_excel_runtime.py").read_text(encoding="utf-8")
    renderer = runtime.split(
        "def render_excel_intelligence_safe(", 1
    )[1].split("def process_upload_for_data_hub(", 1)[0]
    assert "if enable_copilot:" in renderer
    assert "excel_intelligence_allowed(tier)" in renderer
    assert 'session_actor.casefold() != actor.casefold()' in renderer
    assert 'if not tier_allows(tier, "Starter")' in renderer
    assert "Preserve the separate Starter Excel Data Cleaning & Import module." in renderer


def test_excel_intelligence_renderer_requires_authenticated_non_guest_session():
    platform = (ROOT / "industrial_platform.py").read_text(encoding="utf-8")
    route = platform.split('if module=="Excel Intelligence":', 1)[1].split(
        'if module=="Excel Data Cleaning & Import":', 1
    )[0]
    assert '_industrial_platform_session_state().get("authenticated") is not True' in route
    assert 'actor.casefold() in {"", "guest", "guest visitor", "anonymous"}' in route
    assert 'session_actor.casefold() != actor.casefold()' in route
    assert 'Sign in with an active Shoir-IE account' in route


def test_enterprise_user_can_open_excel_intelligence_from_workbench_data(monkeypatch):
    import durable_account_store as account_store
    from streamlit.testing.v1 import AppTest

    monkeypatch.setattr(account_store, "edge_backend_configured", lambda: True)
    monkeypatch.setattr(
        account_store,
        "edge_session_entitlement",
        lambda username, token: {
            "ok": True,
            "username": username,
            "tier": "Enterprise Tier",
            "active": True,
            "expires_at": "2099-01-01T00:00:00Z",
        },
    )

    page = ROOT / "pages" / "Industrial_Engineering_Workbench.py"
    app = AppTest.from_file(page, default_timeout=90)
    app.session_state["current_user"] = "excel-intelligence-route-test"
    app.session_state["authenticated"] = True
    app.session_state["user_tier"] = "Enterprise"
    app.session_state["remote_session_token"] = "synthetic-session-token"
    app.run(timeout=90)
    assert not app.exception, "\\n".join(str(error.value) for error in app.exception)

    app.selectbox(key="workbench_category").select("Data")
    app.run(timeout=90)
    assert not app.exception, "\\n".join(str(error.value) for error in app.exception)

    module_selector = app.selectbox(key="workbench_module_selector")
    assert "Data · Excel Intelligence" in module_selector.options
    module_selector.select("Data · Excel Intelligence")
    app.run(timeout=90)

    assert not app.exception, "\\n".join(str(error.value) for error in app.exception)
    assert app.session_state["workbench_module_selector"] == "Data · Excel Intelligence"
    assert any("No workbook" in str(item.value) or "Upload" in str(item.value) for item in app.info)


def test_professional_user_sees_excel_intelligence_locked_in_workbench_data():
    from streamlit.testing.v1 import AppTest

    page = ROOT / "pages" / "Industrial_Engineering_Workbench.py"
    app = AppTest.from_file(page, default_timeout=90)
    app.session_state["current_user"] = "excel-intelligence-professional-test"
    app.session_state["authenticated"] = True
    app.session_state["user_tier"] = "Professional"
    app.run(timeout=90)
    assert not app.exception, "\\n".join(str(error.value) for error in app.exception)

    app.selectbox(key="workbench_category").select("Data")
    app.run(timeout=90)
    selector = app.selectbox(key="workbench_module_selector")
    assert "Data · Excel Intelligence" in selector.options
    selector.select("Data · Excel Intelligence")
    app.run(timeout=90)

    assert not app.exception, "\\n".join(str(error.value) for error in app.exception)
    assert app.session_state["workbench_module_selector"] == "Data · Excel Intelligence"
    enterprise_row = module_availability("Professional").loc[
        lambda rows: rows["Module"] == MODULE_NAME
    ].iloc[0]
    assert enterprise_row["Required Tier"] == "Enterprise"
    assert bool(enterprise_row["Available"]) is False
    assert not any("Shoir-IE Excel Intelligence" in str(item.value) for item in app.markdown)


def test_excel_intelligence_registers_a_visual_table_for_the_shared_visualizer():
    from shoir_live_visuals import _module_visual_keys
    assert "excel_studio_visual_df" in _module_visual_keys(MODULE_NAME)


def test_office_addin_uses_a_local_approval_gated_operation_allowlist():
    taskpane = (ROOT / "excel_addin" / "taskpane.js").read_text(encoding="utf-8")
    planner = (ROOT / "excel_addin" / "planner.js").read_text(encoding="utf-8")
    html = (ROOT / "excel_addin" / "taskpane.html").read_text(encoding="utf-8")
    readme = (ROOT / "excel_addin" / "README.md").read_text(encoding="utf-8")

    assert "Excel.run" in taskpane
    assert 'range.load(["values", "formulas", "numberFormat"])' in taskpane
    assert "ShoirExcelPlanner.buildPlan" in taskpane
    assert "visiblePlan" in taskpane
    assert "dataFingerprint" not in taskpane.split("function setPlan(plan)", 1)[1].split("async function selectedRangePayload", 1)[0]
    assert "requiresWriteApproval" in taskpane
    assert "USER_APPROVED_RESULTS_SHEET" in taskpane
    assert "copyFrom(range, Excel.RangeCopyType.all)" in taskpane
    assert "sourceWorksheetPreserved: true" in taskpane
    assert "formulaCells: profile.formulaCells" in taskpane
    assert "resultSheet.charts.add" in taskpane
    assert "AVERAGE" in taskpane and "SUM" in taskpane
    assert "formulaLikeTextSkipped" in taskpane
    assert "Office.FileType.Compressed" in taskpane
    assert "isSetSupported(\"CompressedFile\")" in taskpane
    assert "maxDownloadBytes = 100 * 1024 * 1024" in taskpane
    assert "receivedBytes !== Number(file.size)" in taskpane
    assert "planExecutionInProgress" in taskpane
    assert "downloadInProgress" in taskpane
    assert "MAX_SELECTION_SERIALIZED_BYTES = 8 * 1024 * 1024" in taskpane
    assert "approximateBytes > MAX_SELECTION_SERIALIZED_BYTES" in taskpane
    assert "downloadReadyLink.href = workbookObjectUrl" in taskpane
    assert "selectionSummary(latestPayload)" in taskpane
    assert "setPlan(null);" in taskpane
    assert "Do not turn previously inert text into executable spreadsheet logic" in taskpane
    assert "fetch(" not in taskpane
    assert "/api/workbook/import" not in taskpane

    assert "MAX_CELLS = 10000" in planner
    assert 'type: "trim_text"' in planner
    assert 'type: "add_summary_formulas"' in planner
    assert 'type: "create_column_chart"' in planner
    assert "remove duplicates" in planner
    assert "requiresWriteApproval" in planner

    assert 'id="instruction"' in html
    assert 'id="buildPlan"' in html
    assert 'id="approveWorkbookEdits"' in html
    assert 'id="downloadReadyLink"' in html
    assert "planner.js" in html

    manifest = (ROOT / "excel_addin" / "manifest.xml").read_text(encoding="utf-8")
    assert "<Permissions>ReadWriteDocument</Permissions>" in manifest
    assert '<Sets DefaultMinVersion="1.9">' in manifest
    assert '<Set Name="ExcelApi"/>' in manifest
    assert "does not upload workbook contents" in readme
    assert "Excel for the web" in readme
    assert "Save a backup" in readme
