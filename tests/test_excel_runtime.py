import io

import pandas as pd

from shoir_excel_runtime import process_fast


def test_process_fast_loads_workbook_without_building_exports():
    buf = io.BytesIO()
    with pd.ExcelWriter(buf, engine="xlsxwriter") as writer:
        pd.DataFrame(
            [
                ["Operations export", None],
                ["SKU", "Demand"],
                [" A-01 ", "1,200"],
                ["A-02", "950"],
            ]
        ).to_excel(writer, index=False, header=False, sheet_name="Orders")

    result = process_fast(buf.getvalue(), "orders.xlsx")

    assert list(result["cleaned_sheets"]) == ["Orders"]
    frame = result["cleaned_sheets"]["Orders"]
    assert frame["SKU"].tolist() == ["A-01", "A-02"]
    assert frame["Demand"].tolist() == [1200, 950]
    assert result["xlsx"] is None
    assert result["bundle"] is None
    assert result["signature"]


def test_multi_sheet_export_is_a_valid_separate_workbook_with_raw_archives():
    import hashlib
    import json
    import zipfile

    from openpyxl import load_workbook
    from shoir_excel_runtime import prepare_exports

    source_buffer = io.BytesIO()
    with pd.ExcelWriter(source_buffer, engine="xlsxwriter") as writer:
        pd.DataFrame(
            [["Production export", None], ["Line", "Output"], ["A", 100], ["B", 120]]
        ).to_excel(writer, index=False, header=False, sheet_name="Production")
        pd.DataFrame(
            [["Downtime report", None], ["Line", "Minutes"], ["A", 15], ["B", 8]]
        ).to_excel(writer, index=False, header=False, sheet_name="Downtime")

    original_bytes = source_buffer.getvalue()
    original_hash = hashlib.sha256(original_bytes).hexdigest()
    result = process_fast(original_bytes, "plant-data.xlsx")

    assert list(result["cleaned_sheets"]) == ["Production", "Downtime"]
    assert result["cleaned_sheets"]["Production"]["Output"].tolist() == [100, 120]
    assert result["cleaned_sheets"]["Downtime"]["Minutes"].tolist() == [15, 8]
    assert result["xlsx"] is None
    assert result["bundle"] is None

    prepare_exports(result)

    # Export creates a separate artifact; the uploaded source bytes are immutable.
    assert hashlib.sha256(original_bytes).hexdigest() == original_hash
    assert isinstance(result["xlsx"], bytes) and result["xlsx"]
    assert isinstance(result["bundle"], bytes) and result["bundle"]

    workbook = load_workbook(io.BytesIO(result["xlsx"]), data_only=False, read_only=False)
    assert "START HERE" in workbook.sheetnames
    assert "EXECUTIVE DASHBOARD" in workbook.sheetnames
    assert "SOURCE METADATA" in workbook.sheetnames
    assert "CLEAN - Production" in workbook.sheetnames
    assert "CLEAN - Downtime" in workbook.sheetnames
    assert workbook["RAW - Production"].sheet_state == "hidden"
    assert workbook["RAW - Downtime"].sheet_state == "hidden"
    assert workbook["CLEAN - Production"]["A7"].value == "A"
    assert workbook["CLEAN - Production"]["B7"].value == 100
    workbook.close()

    with zipfile.ZipFile(io.BytesIO(result["xlsx"])) as xlsx_archive:
        assert xlsx_archive.testzip() is None
    with zipfile.ZipFile(io.BytesIO(result["bundle"])) as evidence_archive:
        assert evidence_archive.testzip() is None
        names = set(evidence_archive.namelist())
        assert "shoir_ie_industrial_excel_workbook.xlsx" in names
        assert "manifest.json" in names
        assert "raw_csv/Production.csv" in names
        assert "clean_csv/Production.csv" in names
        manifest = json.loads(evidence_archive.read("manifest.json"))
        assert manifest["source_sheets"] == ["Production", "Downtime"]
        assert manifest["cleaned_sheets"] == ["Production", "Downtime"]


def test_process_fast_rejects_unsupported_large_upload_before_parsing():
    raw = b"x" * (75 * 1024 * 1024 + 1)
    try:
        process_fast(raw, "too_large.xlsx")
    except ValueError as exc:
        assert "limited to 75 mb" in str(exc).lower()
    else:
        raise AssertionError("Large uploads must be rejected before workbook parsing.")

def test_excel_intelligence_copilot_requires_approval_and_keeps_source_read_only(monkeypatch):
    import zipfile

    import pytest
    import streamlit as st

    from shoir_excel_runtime import (
        build_excel_intelligence_plan,
        execute_excel_intelligence_plan,
    )

    source = pd.DataFrame(
        {
            "Line": ["A", "B", "C"],
            "Throughput": [100, 120, 115],
            "Operating Cost": [50.0, 55.0, 53.0],
        }
    )
    original = source.copy(deep=True)
    prompt = "Summarise throughput and operating cost"
    plan = build_excel_intelligence_plan(prompt, "Production", source)

    assert plan["plan"]["requires_approval"] is True
    assert plan["external_model_used"] is False
    assert len(plan["request_fingerprint"]) == 64

    monkeypatch.delenv("SHOIR_EXCEL_INTELLIGENCE_MINIMUM_TIER", raising=False)
    monkeypatch.setattr(
        st,
        "session_state",
        {
            "authenticated": True,
            "current_user": "shoir-e2e-excel-copilot",
            "workspace_id": "test-workspace",
        },
    )

    with pytest.raises(PermissionError, match="Explicit approval"):
        execute_excel_intelligence_plan(
            prompt, "Production", source, plan,
            "shoir-e2e-excel-copilot", "Enterprise", approved=False,
        )

    with pytest.raises(PermissionError, match="subscription"):
        execute_excel_intelligence_plan(
            prompt, "Production", source, plan,
            "shoir-e2e-excel-copilot", "Starter", approved=True,
        )

    with pytest.raises(ValueError, match="stale"):
        execute_excel_intelligence_plan(
            prompt + " with a different instruction",
            "Production", source, plan,
            "shoir-e2e-excel-copilot", "Enterprise", approved=True,
        )

    run = execute_excel_intelligence_plan(
        prompt, "Production", source, plan,
        "shoir-e2e-excel-copilot", "Enterprise", approved=True,
    )

    pd.testing.assert_frame_equal(source, original)
    assert run["planner"] == "Shoir-IE deterministic Copilot orchestrator"
    assert run["external_model_used"] is False
    assert run["source_sheet"] == "Production"
    assert run["evidence_manifest"]["approval_required"] is True
    with zipfile.ZipFile(io.BytesIO(run["export"]), "r") as archive:
        assert "copilot_analysis.xlsx" in archive.namelist()
        assert "inspection.json" in archive.namelist()
        assert "evidence_manifest.json" in archive.namelist()
