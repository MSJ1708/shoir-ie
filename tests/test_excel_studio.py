import io

import pandas as pd
from openpyxl import load_workbook

from shoir_excel_studio import clean_dataframe, process_uploaded_workbook

def test_clean_dataframe_handles_messy_export_conservatively():
    table = pd.DataFrame([
        [" Alice ", "0012", "12.5%", "2026-01-05"],
        [" Alice ", "0012", "12.5%", "2026-01-05"],
        ["Bob", "0013", "25%", "2026-01-06"],
    ], columns=["Name", "Order ID", "Rate", "Date"])
    cleaned, audit = clean_dataframe(table)
    assert cleaned.columns.tolist() == ["Name", "Order ID", "Rate", "Date"]
    assert len(cleaned) == 2
    assert cleaned.loc[0, "Name"] == "Alice"
    assert cleaned.loc[0, "Order ID"] == "0012"
    assert abs(float(cleaned.loc[0, "Rate"]) - 0.125) < 1e-9
    assert pd.api.types.is_datetime64_any_dtype(cleaned["Date"])
    assert any(item["Action"] == "Remove duplicate rows" for item in audit)

def test_process_uploaded_workbook_assembles_traceable_xlsx():
    buf = io.BytesIO()
    with pd.ExcelWriter(buf, engine="xlsxwriter") as writer:
        pd.DataFrame([
            ["Operations report", None, None],
            [" SKU ", "Demand", "Date"],
            [" A-01 ", "1,200", "2026-02-01"],
            [" A-02 ", "950", "2026-02-02"],
        ]).to_excel(writer, index=False, header=False, sheet_name="Raw Export")
    result = process_uploaded_workbook(buf.getvalue(), "messy_operations.xlsx")
    cleaned = result["cleaned_sheets"]["Raw Export"]
    assert cleaned.loc[0, "SKU"] == "A-01"
    assert int(cleaned.loc[0, "Demand"]) == 1200
    assert pd.api.types.is_datetime64_any_dtype(cleaned["Date"])
    workbook = load_workbook(io.BytesIO(result["xlsx"]), data_only=False)
    expected = {
        "START HERE", "EXECUTIVE SUMMARY", "DATA DICTIONARY",
        "QUALITY CHECKS", "CLEANING AUDIT", "CLEAN - Raw Export",
    }
    assert expected <= set(workbook.sheetnames)
    raw_sheets = [name for name in workbook.sheetnames if name.startswith("RAW - ")]
    assert raw_sheets and workbook[raw_sheets[0]].sheet_state == "hidden"
    assert workbook["START HERE"]["A1"].value.startswith("Shoir-IE")
    assert result["bundle"][:2] == b"PK"


def test_excel_studio_normalizes_missing_tokens_but_protects_identifiers():
    table = pd.DataFrame({
        "SKU": ["NA", "A-02"],
        "Description": ["N/A", "NULL"],
        "Qty": ["10", "-"],
    })
    cleaned, audit = __import__("shoir_excel_studio").clean_dataframe(table)
    assert cleaned["SKU"].tolist() == ["NA", "A-02"]
    assert cleaned["Description"].isna().all()
    assert cleaned["Qty"].iloc[0] == 10
    assert pd.isna(cleaned["Qty"].iloc[1])
    assert any("missing-value" in item["Action"] for item in audit)


def test_excel_studio_profile_flags_duplicate_keys_and_outliers():
    table = pd.DataFrame({
        "Asset ID": ["A-1", "A-1", "A-2", "A-3", "A-4", "A-5", "A-6", "A-7", "A-8", "A-9"],
        "Temperature": [10, 10, 10, 10, 10, 10, 10, 10, 10, 100],
    })
    from shoir_excel_studio import profile_dataframe
    profile = profile_dataframe(table)
    assert profile["Duplicate identifier occurrences"] == 1
    assert profile["Potential outliers"] >= 1
    assert profile["Schema fingerprint"]
    assert profile["Readiness"] in {"READY WITH REVIEW", "REVIEW REQUIRED"}


def test_excel_studio_quality_export_contains_governance_layers_and_inert_text():
    table = pd.DataFrame({
        "SKU": ["A-01", "A-02"],
        "Qty": [10, 20],
        "Note": ["=1+1", "Normal"],
    })
    buf = io.BytesIO()
    with pd.ExcelWriter(buf, engine="xlsxwriter") as writer:
        table.to_excel(writer, index=False, sheet_name="Raw")
    result = process_uploaded_workbook(buf.getvalue(), "governance.xlsx")
    workbook = load_workbook(io.BytesIO(result["xlsx"]), data_only=False)
    expected = {
        "START HERE", "EXECUTIVE DASHBOARD", "DATA QUALITY CENTER",
        "FIELD INTELLIGENCE", "VALIDATION & REVIEW", "BEFORE vs AFTER",
        "SOURCE METADATA", "CLEANING AUDIT", "CLEAN - Raw", "RAW - Raw",
    }
    assert expected <= set(workbook.sheetnames)
    clean_ws = workbook["CLEAN - Raw"]
    note_cells = [cell for row in clean_ws.iter_rows() for cell in row if cell.value == "=1+1"]
    assert note_cells and note_cells[0].data_type == "s"
    assert result["source_metadata"][0]["SHA256"] == result["signature"]


def test_excel_studio_archives_source_formulas_and_cross_sheet_map():
    buf = io.BytesIO()
    with pd.ExcelWriter(buf, engine="xlsxwriter") as writer:
        pd.DataFrame({"SKU": ["A-01"], "Qty": [10], "Cost": [2], "Total": ["=B2*C2"]}).to_excel(
            writer, index=False, sheet_name="Orders"
        )
        pd.DataFrame({"SKU": ["A-01"], "Plant": ["Riyadh"]}).to_excel(
            writer, index=False, sheet_name="Master"
        )
    result = process_uploaded_workbook(buf.getvalue(), "formula_map.xlsx")
    assert result["formula_inventory"]
    assert result["formula_inventory"][0]["Formula"] == "=B2*C2"
    assert result["cross_sheet_map"]
    assert any("sku" in row["Potential shared fields"] for row in result["cross_sheet_map"])


def test_excel_studio_supports_semicolon_csv_and_clock_time_without_fake_dates():
    raw = "SKU;Start;Qty\\nA-01;08:30;1,200\\nA-02;09:45;950\\n".encode("utf-8")
    result = process_uploaded_workbook(raw, "schedule.csv")
    frame = result["cleaned_sheets"]["CSV"]
    assert frame["SKU"].tolist() == ["A-01", "A-02"]
    assert frame["Qty"].tolist() == [1200, 950]
    assert "Clock time" in {row["Type"] for row in result["field_intelligence"] if row["Field"] == "Start"} or frame["Start"].dtype == "string"
