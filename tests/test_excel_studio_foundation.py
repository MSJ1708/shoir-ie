import io
import zipfile

import pandas as pd
from openpyxl import load_workbook

from shoir_excel_foundation import (
    activation_gate,
    build_contracts,
    build_dataset_registry,
    build_industrial_semantics,
    build_scalable_ingestion_profile,
    classify_field,
    fidelity_report,
    frame_hash,
    schema_hash,
    scalable_text_reader,
)


def _result(frames):
    catalog = []
    for key, frame in frames.items():
        sheet = key.split("::")[0]
        table = key.split("::")[-1]
        catalog.append({
            "Dataset ID": key,
            "Sheet": sheet,
            "Table ID": table,
            "Start row": 1,
            "End row": len(frame) + 1,
            "Header row": 1,
        })
    return {
        "filename": "industrial.xlsx",
        "signature": "abc123",
        "table_datasets": frames,
        "cleaned_sheets": {k.split("::")[0]: v for k, v in frames.items()},
        "table_catalog": catalog,
        "audits": {},
        "lineage_manifest": {},
    }


def test_dataset_first_registry_promotes_every_table_to_first_class_dataset():
    frames = {
        "Ops::T001": pd.DataFrame({"Asset ID": ["A1", "A2"], "Output": [10, 20]}),
        "Quality::T002": pd.DataFrame({"Asset ID": ["A1"], "Defect Rate": [0.02]}),
    }
    result = _result(frames)
    registry = build_dataset_registry(result)
    assert len(registry) == 2
    assert {x["Table ID"] for x in registry} == {"T001", "T002"}
    assert all(x["Dataset ID"].startswith("DS-") for x in registry)
    assert all(x["Schema hash"] for x in registry)
    assert all(x["Content hash"] for x in registry)


def test_industrial_semantics_classifies_keys_measures_time_and_entities():
    df = pd.DataFrame({
        "Asset ID": ["A1", "A2"],
        "Production Qty": [10, 12],
        "Timestamp": pd.to_datetime(["2026-01-01", "2026-01-02"]),
        "Defect Rate": [0.01, 0.02],
    })
    fields = build_industrial_semantics({"cleaned_sheets": {"Ops": df}})
    by = {x["Field"]: x for x in fields}
    assert by["Asset ID"]["Entity"] == "Asset"
    assert by["Asset ID"]["Role"] == "Key"
    assert by["Production Qty"]["Role"] == "Measure"
    assert by["Timestamp"]["Role"] == "Time"
    assert by["Defect Rate"]["Entity"] == "Quality"


def test_contract_blocks_empty_dataset_and_allows_explicit_exception():
    empty = pd.DataFrame(columns=["Asset ID", "Output"])
    result = {
        "dataset_registry": build_dataset_registry(_result({"Ops::T001": empty})),
        "industrial_semantics": build_industrial_semantics({"table_datasets": {"Ops::T001": empty}}),
        "table_datasets": {"Ops::T001": empty},
        "cleaned_sheets": {"Ops": empty},
    }
    contracts = build_contracts(result)
    assert contracts and contracts[0]["Status"] == "BLOCKED"
    result["dataset_contracts"] = contracts
    gate = activation_gate(result, "Ops::T001")
    assert gate["allowed"] is False
    contracts[0]["Approved exception"] = True
    assert activation_gate(result, "Ops::T001")["allowed"] is True


def test_fidelity_report_identifies_workbook_features_without_claiming_preservation():
    buf = io.BytesIO()
    with pd.ExcelWriter(buf, engine="xlsxwriter") as writer:
        pd.DataFrame({"SKU": ["A1"], "Qty": [2]}).to_excel(writer, index=False, sheet_name="Data")
        ws = writer.sheets["Data"]
        ws.write_url("C2", "https://example.com", string="link")
        chart = writer.book.add_chart({"type": "column"})
        chart.add_series({"values": ["Data", 1, 1, 1, 1]})
        ws.insert_chart("E2", chart)
    report = fidelity_report(buf.getvalue(), "features.xlsx")
    assert report["Charts present"] is True
    assert "not guaranteed" in report["Fidelity warning"]


def test_scalable_reader_handles_ragged_delimited_rows_and_tsv_metadata():
    raw = b"SKU\tQty\tNote\nA1\t10\textra\nA2\t20\n"
    result = scalable_text_reader(raw, "example.tsv")
    frame = result["TEXT"]
    assert frame.shape == (3, 3)
    assert frame.iloc[2, 2] == ""
    assert frame.attrs["source_delimiter"] == "\t"


def test_large_file_profile_selects_chunked_ingestion_mode():
    profile = build_scalable_ingestion_profile(b"x" * (8 * 1024 * 1024), "large.csv")
    assert profile["Mode"] == "chunked-delimited"
    assert profile["Chunk rows"] == 100_000


def test_hashes_are_stable_and_schema_changes_are_detectable():
    a = pd.DataFrame({"SKU": ["A1"], "Qty": [10]})
    b = pd.DataFrame({"SKU": ["A1"], "Qty": [11]})
    c = pd.DataFrame({"SKU": ["A1"], "Qty": [10.0]})
    assert frame_hash(a) != frame_hash(b)
    assert schema_hash(a) == schema_hash(b)
    assert schema_hash(a) != schema_hash(c)


def test_evidence_bundle_contains_exact_source_bytes_after_integration():
    from shoir_excel_foundation import augment_evidence_bundle
    source = b"SKU,Qty\nA1,10\n"
    result = {"bundle": zipfile.ZipFile(io.BytesIO(), "w").fp if False else b""}
    base = io.BytesIO()
    with zipfile.ZipFile(base, "w", zipfile.ZIP_DEFLATED) as zf:
        zf.writestr("README.txt", "evidence")
    result["bundle"] = base.getvalue()
    result["dataset_registry"] = [{"Dataset ID": "DS-1"}]
    result["dataset_contracts"] = []
    result["fidelity_report"] = {}
    result["scalable_ingestion"] = {}
    result["dataset_versions_history"] = []
    result["industrial_semantics"] = []
    bundle = augment_evidence_bundle(result, source, "source.csv")
    with zipfile.ZipFile(io.BytesIO(bundle), "r") as zf:
        assert zf.read("SOURCE_ORIGINAL/source.csv") == source
        assert b"DS-1" in zf.read("governance/foundation_manifest.json")
