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


def test_subscription_navigation_matches_declared_platform_tiers():
    source = (Path(__file__).resolve().parents[1] / "app.py").read_text(encoding="utf-8")

    def direct_items(variable):
        match = re.search(rf"^{variable}\\s*=.*?\\[([^\\]]*)\\]", source, flags=re.MULTILINE | re.DOTALL)
        assert match, f"Could not locate {variable} tier declaration"
        return re.findall(r"[\"']([^\"']+)[\"']", match.group(1))

    # Features explicitly introduced at Mid-Tier Pro must not be hidden until Professional.
    tier2 = set(direct_items("tier2_features"))
    assert "Scenario Versioning & Comparison" in tier2
    assert "Localization & Multi-Currency" in tier2

    # Enterprise catalog items must be reachable from the Enterprise module list.
    tier3 = set(direct_items("tier3_features"))
    assert "Industrial Operating System" in tier3
    assert "Industrial Data Platform" in tier3
