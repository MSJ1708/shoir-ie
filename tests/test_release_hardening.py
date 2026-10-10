from io import BytesIO
from pathlib import Path
import re

import pandas as pd
import pytest

from shoir_tier_capabilities import MODULE_EXPLORER_TIERS, TIER_ORDER
from shoir_upgrade import build_excel_report, read_uploaded_workbook
from shoir_excel_runtime import _clear_previous_upload, _record_upload_failure
from workspace_persistence import _workspace_change_signature, load_user_workspace, save_user_workspace
from shoir_enterprise_integration import _registry_frame, _registry_key, _write_registry_frame
from industrial_platform import export_pdf, export_pptx
from pptx import Presentation


def _xlsx_bytes() -> bytes:
    buffer = BytesIO()
    with pd.ExcelWriter(buffer, engine="xlsxwriter") as writer:
        pd.DataFrame({"SKU": ["00123", "00456"], "Quantity": [4, 8]}).to_excel(
            writer, sheet_name="Production", index=False
        )
        pd.DataFrame({"Station": ["A", "B"], "Downtime": [2.5, 3.0]}).to_excel(
            writer, sheet_name="Maintenance", index=False
        )
    return buffer.getvalue()


def test_workspace_change_signature_detects_in_place_dataframe_edits():
    frame = pd.DataFrame({"value": [1, 2, 3]})
    state = {"df": frame}
    before = _workspace_change_signature(state)
    assert _workspace_change_signature(state) == before

    # This is the failure mode the former identity/shape/schema-only signature missed.
    frame.loc[1, "value"] = 99
    after = _workspace_change_signature(state)
    assert after != before


def test_workspace_change_signature_detects_changes_past_long_collection_prefix():
    records = [{"subject": ("x" * 180), "status": "Open"} for _ in range(12)]
    state = {"ei_registry_v1_activity": records}
    before = _workspace_change_signature(state)
    # The changed value appears after more than 1,000 characters of repr output.
    state["ei_registry_v1_activity"][-1]["status"] = "Done"
    after = _workspace_change_signature(state)
    assert after != before


def test_workspace_change_signature_detects_in_place_series_edits():
    series = pd.Series([10, 20, 30], name="demand")
    state = {"demand_series": series}
    before = _workspace_change_signature(state)
    series.iloc[1] = 999
    assert _workspace_change_signature(state) != before


def test_workspace_save_persists_in_place_dataframe_edits(tmp_path):
    db = str(tmp_path / "workspace.db")
    frame = pd.DataFrame({"SKU": ["00123", "00456"], "Quantity": [4, 8]})
    state = {"df": frame}
    assert save_user_workspace("Alice", state, db)

    # A same-object edit used to be mistaken for a no-op and skipped.
    frame.loc[0, "Quantity"] = 12
    assert save_user_workspace("Alice", state, db)

    restored = {}
    assert load_user_workspace("Alice", restored, db)
    assert int(restored["df"].loc[0, "Quantity"]) == 12


def test_csv_import_preserves_leading_zero_identifiers():
    result = read_uploaded_workbook(b"SKU,Quantity\n00123,4\n", "plant.csv")
    assert list(result) == ["CSV"]
    assert str(result["CSV"].iloc[0]["SKU"]) == "00123"
    assert str(result["CSV"].iloc[0]["Quantity"]) == "4"


def test_tsv_and_text_import_detect_delimiters_and_preserve_ids():
    tsv = read_uploaded_workbook(b"SKU\tQuantity\n00123\t4\n", "plant.tsv")
    assert list(tsv) == ["TSV"]
    assert str(tsv["TSV"].iloc[0]["SKU"]) == "00123"
    assert int(tsv["TSV"].iloc[0]["Quantity"]) == 4

    text = read_uploaded_workbook(b"SKU|Quantity\n00456|8\n", "plant.txt")
    assert list(text) == ["TXT"]
    assert str(text["TXT"].iloc[0]["SKU"]) == "00456"
    assert int(text["TXT"].iloc[0]["Quantity"]) == 8


@pytest.mark.parametrize("filename", ["plant.xlsx", "plant.xlsm"])
def test_excel_import_supports_ooxml_and_multiple_sheets(filename):
    result = read_uploaded_workbook(_xlsx_bytes(), filename)
    assert set(result) == {"Production", "Maintenance"}
    assert str(result["Production"].iloc[0]["SKU"]) == "00123"
    assert int(result["Maintenance"].iloc[1]["Downtime"]) == 3


def test_excel_report_export_is_a_readable_workbook_with_unique_safe_sheet_names():
    source = pd.DataFrame({"SKU": ["00123"], "Quantity": [4]})
    payload = build_excel_report(
        "Release check",
        [("Ops/Output", source), ("Ops/Output", source)],
        audit=[{"Action": "Import", "Details": "Test record"}],
    )
    assert payload[:2] == b"PK"
    workbook = pd.ExcelFile(BytesIO(payload))
    assert "OpsOutput" in workbook.sheet_names
    assert "OpsOutput (2)" in workbook.sheet_names
    assert "Cleaning Audit" in workbook.sheet_names
    round_trip = pd.read_excel(workbook, sheet_name="OpsOutput", skiprows=3, dtype=object)
    assert str(round_trip.iloc[0]["SKU"]) == "00123"


def test_failed_replacement_upload_clears_stale_excel_download():
    state = {
        "excel_studio_safe_signature": "old-file",
        "excel_studio_safe_result": {"filename": "old.xlsx", "xlsx": b"old workbook"},
    }
    _clear_previous_upload(state)
    assert state["excel_studio_safe_result"] is None
    assert "excel_studio_safe_signature" not in state

    message = _record_upload_failure(state, "bad-file", ValueError("unsupported format"))
    assert message == "ValueError: unsupported format"
    assert state["excel_studio_safe_result"] is None
    assert "excel_studio_safe_signature" not in state
    assert state["excel_studio_safe_error_signature"] == "bad-file"
    assert "unsupported format" in state["excel_studio_safe_error"]


def test_module_explorer_lists_all_subscription_tiers():
    assert MODULE_EXPLORER_TIERS == ("All capabilities", *TIER_ORDER)
    assert {"Professional", "Enterprise", "Enterprise Plus", "Research Pack"}.issubset(
        set(MODULE_EXPLORER_TIERS)
    )


def test_unsupported_and_empty_imports_fail_with_actionable_messages():
    with pytest.raises(ValueError, match="empty"):
        read_uploaded_workbook(b"", "empty.csv")
    with pytest.raises(ValueError, match="Supported imports"):
        read_uploaded_workbook(b"some data", "plant.json")


@pytest.mark.parametrize(
    ("kind", "record"),
    [
        ("connectors", {
            "connector_id": "MES-01", "name": "Plant MES", "system_type": "MES",
            "endpoint": "https://mes.example.invalid", "status": "Validation-ready",
            "last_validated": None, "notes": "Test record", "updated_at": "2026-10-10T00:00:00+00:00",
        }),
        ("activity", {
            "id": 123456789, "kind": "Review", "subject": "Validate routing assumptions",
            "details": "Check the baseline", "assignee": "engineer", "reviewer": "manager",
            "status": "Open", "created_at": "2026-10-10T00:00:00+00:00",
        }),
        ("assets", {
            "asset_id": "DATA-123", "filename": "plant.xlsx", "sheet": "Production",
            "rows": 12, "columns": 4, "sha256": "a" * 64,
            "created_at": "2026-10-10T00:00:00+00:00",
        }),
    ],
)
def test_enterprise_integration_registry_survives_workspace_round_trip(tmp_path, kind, record):
    db = str(tmp_path / "registry-workspace.db")
    state = {}
    _write_registry_frame(kind, "Alice", "Plant-North", pd.DataFrame([record]), state=state)
    registry_key = _registry_key(kind, "Alice", "Plant-North")
    assert registry_key in state

    # Workspace snapshots must carry registry rows; a SQLite-only cache would
    # be lost on hosted deployments that use remote workspace persistence.
    assert save_user_workspace("Alice", state, db)
    restored = {}
    assert load_user_workspace("Alice", restored, db)
    frame = _registry_frame(kind, "Alice", "Plant-North", state=restored)
    assert len(frame) == 1
    for column, value in record.items():
        if value is not None:
            assert str(frame.iloc[0][column]) == str(value)

    assert _registry_key(kind, "Bob", "Plant-North") != registry_key
    assert _registry_key(kind, "Alice", "Plant-South") != registry_key
    # Match SQLite's case-sensitive workspace predicate; these must not share cached rows.
    assert _registry_key(kind, "Alice", "plant-north") != registry_key


def test_subscription_navigation_matches_declared_platform_tiers():
    root = Path(__file__).resolve().parents[1]
    app_source = (root / "app.py").read_text(encoding="utf-8")
    platform_source = (root / "industrial_platform.py").read_text(encoding="utf-8")

    def direct_items(variable, source):
        lines = source.splitlines()
        start_line = next((i for i, item in enumerate(lines) if item.startswith(f"{variable} =")), None)
        assert start_line is not None, f"Could not locate {variable} declaration"
        joined = "\n".join(lines[start_line:])
        literal = joined.split("[", 1)[1].split("]", 1)[0]
        return re.findall(r'"([^"]+)"', literal)

    starter = set(direct_items("tier1_features", app_source))
    mid_tier = starter | set(direct_items("tier2_features", app_source))
    professional = mid_tier | set(direct_items("professional_features", app_source))
    enterprise = professional | set(direct_items("tier3_features", app_source))
    enterprise_plus = enterprise | set(direct_items("tier4_features", app_source))
    research = enterprise | set(direct_items("research_pack_features", app_source))
    available_by_tier = {
        "Starter": starter,
        "Mid-Tier Pro": mid_tier,
        "Professional": professional,
        "Enterprise": enterprise,
        "Enterprise Plus": enterprise_plus,
        "Research Pack": research,
    }

    # The product catalog is the access contract used by platform_tier_allows();
    # the app navigation must introduce each catalog module at the same tier.
    catalog_start = platform_source.index("PLATFORM_CATALOG = [")
    catalog_end = platform_source.index("\nTIER_FEATURES =", catalog_start)
    catalog_source = platform_source[catalog_start:catalog_end]
    catalog_entries = re.findall(
        r'\{"tier"\s*:\s*"([^"]+)"\s*,\s*"category"\s*:\s*"[^"]+"\s*,\s*"name"\s*:\s*"([^"]+)"',
        catalog_source,
    )
    assert len(catalog_entries) >= 30, "Platform catalog parser did not find the expected module catalogue"

    ordered_tiers = list(available_by_tier)
    errors = []
    for declared_tier, module in catalog_entries:
        first_menu_tier = next(
            (tier for tier in ordered_tiers if module in available_by_tier[tier]),
            None,
        )
        if first_menu_tier != declared_tier:
            errors.append(f"{module}: catalog={declared_tier}, first navigation tier={first_menu_tier}")
    assert not errors, "Module entitlement/navigation mismatch:\n" + "\n".join(errors)

    # Non-catalog first-class platform surfaces have dedicated app dispatch too.
    assert "Industrial Operating System" in enterprise
    assert "Industrial Operating System" in app_source
    assert "Industrial Data Platform" in enterprise
    assert "Scenario Versioning & Comparison" in mid_tier
    assert "Localization & Multi-Currency" in mid_tier

def test_enterprise_pdf_and_powerpoint_exports_are_valid_artifacts():
    tables = [("KPIs", pd.DataFrame({"Metric": ["OEE", "Scrap"], "Value": [82.5, 1.2]}))]
    pdf_payload = export_pdf("Release export verification", tables)
    assert pdf_payload.startswith(b"%PDF-")
    assert len(pdf_payload) > 500

    pptx_payload = export_pptx("Release export verification", tables)
    assert pptx_payload[:2] == b"PK"
    presentation = Presentation(BytesIO(pptx_payload))
    assert len(presentation.slides) >= 2
