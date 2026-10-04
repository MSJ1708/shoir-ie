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
        assert "too large" in str(exc).lower()
    else:
        raise AssertionError("Large uploads must be rejected before workbook parsing.")
