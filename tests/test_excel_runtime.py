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
