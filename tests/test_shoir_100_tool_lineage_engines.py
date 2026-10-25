"""Tests for dataset fingerprinting, lineage and explicit stale-run comparison."""
import pandas as pd
import pytest

from shoir_100_tool_lineage_engines import build_dataset_lineage_record


def test_lineage_hash_is_repeatable_and_stores_no_raw_dataset_cells():
    frame = pd.DataFrame({"asset_id":["A1","A2"],"units":[10,20]})
    a = build_dataset_lineage_record(frame,dataset_name="Production",source_type="IMPORTED",source_reference="file-a.xlsx")
    b = build_dataset_lineage_record(frame,dataset_name="Production",source_type="IMPORTED",source_reference="file-a.xlsx")
    assert a["dataset_fingerprint"] == b["dataset_fingerprint"]
    assert a["version_id"] == b["version_id"]
    assert a["row_count"] == 2 and a["column_count"] == 2
    assert a["raw_dataset_included"] is False
    assert "A1" not in str(a)


def test_lineage_changes_for_content_transform_or_source_and_marks_previous_version_change():
    original = pd.DataFrame({"units":[10,20]})
    first = build_dataset_lineage_record(original,dataset_name="Output",source_type="USER_ENTERED")
    changed = build_dataset_lineage_record(
        pd.DataFrame({"units":[10,21]}),dataset_name="Output",source_type="USER_ENTERED",
        transformations=[{"step":"clean-1","operation":"replace flagged value","method_version":"1"}],
        prior_versions=[first],
    )
    assert first["dataset_fingerprint"] != changed["dataset_fingerprint"]
    assert changed["version_id"] != first["version_id"]
    assert changed["changed_since_previous_version"] is True
    assert changed["previous_version_id"] == first["version_id"]


def test_lineage_flags_stale_downstream_runs_only_with_known_fingerprints():
    frame = pd.DataFrame({"good_units":[100,90]})
    current = build_dataset_lineage_record(frame,dataset_name="Quality",source_type="IMPORTED")
    result = build_dataset_lineage_record(
        frame,dataset_name="Quality",source_type="IMPORTED",
        downstream_runs=[
            {"run_id":"RUN-CURRENT","dataset_fingerprint":current["dataset_fingerprint"]},
            {"run_id":"RUN-STALE","dataset_fingerprint":"different-hash"},
            {"run_id":"RUN-UNKNOWN","dataset_fingerprint":""},
        ],
    )
    assert [row["run_id"] for row in result["stale_downstream_runs"]] == ["RUN-STALE"]
    assert result["uncheckable_downstream_run_ids"] == ["RUN-UNKNOWN"]


@pytest.mark.parametrize("kwargs,match",[
    ({"dataset_name":"","source_type":"IMPORTED"},"name is required"),
    ({"dataset_name":"A","source_type":"DEMO"},"Source type must be"),
])
def test_lineage_rejects_invalid_metadata(kwargs,match):
    with pytest.raises(ValueError,match=match):
        build_dataset_lineage_record(pd.DataFrame({"x":[1]}),**kwargs)


def test_lineage_rejects_bad_transformation_and_duplicate_run_ids():
    with pytest.raises(ValueError,match="requires step and operation"):
        build_dataset_lineage_record(pd.DataFrame({"x":[1]}),dataset_name="A",source_type="IMPORTED",
                                     transformations=[{"step":"clean"}])
    frame=pd.DataFrame({"x":[1]})
    fingerprint=build_dataset_lineage_record(frame,dataset_name="A",source_type="IMPORTED")["dataset_fingerprint"]
    with pytest.raises(ValueError,match="must be unique"):
        build_dataset_lineage_record(frame,dataset_name="A",source_type="IMPORTED",downstream_runs=[
            {"run_id":"R1","dataset_fingerprint":fingerprint},{"run_id":"R1","dataset_fingerprint":fingerprint}
        ])
