import io
import zipfile

import pandas as pd

from shoir_module_parity import (
    _build_export_zip,
    parity_keys,
    summarize_module_dataframe,
    validate_module_dataframe,
)


def test_parity_keys_are_stable_and_module_specific():
    first = parity_keys("Quality Engineering & Reliability")
    again = parity_keys("Quality Engineering & Reliability")
    other = parity_keys("Advanced Planning & Scheduling")
    assert first == again
    assert first["data"] != other["data"]
    assert first["validation"] != other["validation"]


def test_validation_detects_duplicates_and_missing_values():
    df = pd.DataFrame([[1, None], [1, 2]], columns=["Metric", "Value"])
    report = validate_module_dataframe(df)
    assert report["rows"] == 2
    assert report["columns"] == 2
    assert report["duplicate_rows"] == 0
    assert report["missing_cells"] == 1
    assert report["score"] < 100
    assert report["status"] == "REVIEW"


def test_summary_contains_numeric_statistics():
    df = pd.DataFrame({"Line": ["A", "B", "C"], "Throughput": [10, 20, 30], "Cost": [5, 7, 9]})
    summary = summarize_module_dataframe(df)
    assert summary["Rows"] == 3
    assert summary["Numeric Measures"] == 2
    numeric = summary["numeric_summary"]
    assert set(["Measure", "mean", "median", "min", "max"]).issubset(numeric.columns)
    assert float(numeric.loc[numeric["Measure"] == "Throughput", "mean"].iloc[0]) == 20.0


def test_evidence_bundle_contains_data_validation_results_and_manifest():
    df = pd.DataFrame({"Category": ["A", "B"], "Value": [10, 20]})
    validation = validate_module_dataframe(df)
    results = summarize_module_dataframe(df)
    bundle = _build_export_zip("Test Module", df, validation, results, b"xlsx-placeholder", None)

    with zipfile.ZipFile(io.BytesIO(bundle), "r") as zf:
        names = set(zf.namelist())
        assert "test_module_data.csv" in names
        assert "test_module_validation.json" in names
        assert "test_module_results.json" in names
        assert "test_module_universal_parity.xlsx" in names
        assert "manifest.json" in names
