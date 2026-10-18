from types import SimpleNamespace

import pandas as pd
import pytest

import shoir_excel_studio
import shoir_enterprise_integration
import shoir_facility_layout


def _csv_upload():
    return SimpleNamespace(
        name="departments.csv",
        getvalue=lambda: b"ID,Name\nD1,Receiving\n",
    )


@pytest.mark.parametrize(
    "importer",
    [
        shoir_enterprise_integration._import_dataset,
        shoir_facility_layout._file_to_frames,
    ],
    ids=["enterprise-shared-data", "facility-layout"],
)
def test_cleaning_engine_processing_error_is_not_hidden_by_raw_csv_fallback(
    monkeypatch, importer
):
    def broken_processor(_raw, _name):
        raise RuntimeError("cleaning engine regression")

    monkeypatch.setattr(
        shoir_excel_studio, "process_uploaded_workbook", broken_processor
    )

    with pytest.raises(RuntimeError, match="cleaning engine regression"):
        importer(_csv_upload())


@pytest.mark.parametrize(
    "importer",
    [
        shoir_enterprise_integration._import_dataset,
        shoir_facility_layout._file_to_frames,
    ],
    ids=["enterprise-shared-data", "facility-layout"],
)
def test_cleaning_engine_empty_result_is_an_actionable_import_failure(
    monkeypatch, importer
):
    monkeypatch.setattr(
        shoir_excel_studio,
        "process_uploaded_workbook",
        lambda _raw, _name: {"cleaned_sheets": {}, "raw_sheets": {}},
    )

    with pytest.raises(ValueError, match="no non-empty worksheets"):
        importer(_csv_upload())


def test_cleaned_sheet_is_returned_by_both_import_surfaces(monkeypatch):
    cleaned = pd.DataFrame({"ID": ["D1"], "Name": ["Receiving"]})
    monkeypatch.setattr(
        shoir_excel_studio,
        "process_uploaded_workbook",
        lambda _raw, _name: {
            "cleaned_sheets": {"Cleaned": cleaned},
            "raw_sheets": {"Raw": pd.DataFrame({"untrusted": ["raw"]})},
            "signature": "verified-fixture-digest",
        },
    )

    enterprise_frames, digest = shoir_enterprise_integration._import_dataset(
        _csv_upload()
    )
    facility_frames = shoir_facility_layout._file_to_frames(_csv_upload())

    assert digest == "verified-fixture-digest"
    assert list(enterprise_frames) == ["Cleaned"]
    assert list(facility_frames) == ["Cleaned"]
    enterprise_frames["Cleaned"].loc[0, "Name"] = "Changed"
    assert cleaned.loc[0, "Name"] == "Receiving"
