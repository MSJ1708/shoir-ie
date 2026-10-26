"""Regression tests for safe XLSX handling of untrusted text."""
from io import BytesIO

import pandas as pd
from openpyxl import load_workbook

from shoir_upgrade import build_excel_report


def test_formula_and_url_like_values_remain_inert_text_in_xlsx_report():
    formula = '=HYPERLINK("https://attacker.invalid/collect","Open report")'
    url = "https://attacker.invalid/collect"
    formula_header = '=HYPERLINK("https://attacker.invalid/header","Metric")'
    formula_title = '=HYPERLINK("https://attacker.invalid/title","Report")'

    source = pd.DataFrame({formula_header: [formula, url]})
    payload = build_excel_report(
        formula_title,
        [("Metrics", source)],
        audit=[{"Action": formula, "Source": url}],
        function_reference=False,
    )

    assert payload.startswith(b"PK")
    workbook = load_workbook(BytesIO(payload), data_only=False)
    metrics = workbook["Metrics"]

    # The title, header, and values must remain strings, never spreadsheet formulas.
    for cell_ref, expected in (
        ("A1", formula_title),
        ("A4", formula_header),
        ("A5", formula),
        ("A6", url),
    ):
        cell = metrics[cell_ref]
        assert cell.value == expected
        assert cell.data_type != "f"
        assert cell.hyperlink is None

    audit = workbook["Cleaning Audit"]
    assert audit["A2"].value == formula
    assert audit["B2"].value == url
    assert audit["A2"].data_type != "f"
    assert audit["A2"].hyperlink is None
    assert audit["B2"].hyperlink is None
