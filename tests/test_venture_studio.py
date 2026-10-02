import io
import zipfile

import numpy as np
import pandas as pd

import shoir_venture_studio as vs


def test_value_calculation_uses_customer_baseline_and_post_values():
    row = {
        "baseline_value": 8,
        "post_value": 3,
        "frequency_per_year": 50,
        "unit_value": 50,
        "direction": "lower_is_better",
        "implementation_cost": 2000,
    }
    result = vs.value_calculation(row)
    assert np.isclose(result["delta"], 5)
    assert np.isclose(result["annualized_effect"], 250)
    assert np.isclose(result["economic_value"], 12500)
    assert np.isclose(result["implementation_cost"], 2000)


def test_value_summary_calculates_roi_and_payback_from_measured_values():
    values = pd.DataFrame(
        [
            {
                "baseline_value": 8,
                "post_value": 3,
                "frequency_per_year": 50,
                "unit_value": 50,
                "direction": "lower_is_better",
                "implementation_cost": 2000,
            },
        ]
    )
    result = vs.value_summary(values)
    assert np.isclose(result["annualized_benefit"], 12500)
    assert np.isclose(result["net_value"], 10500)
    assert np.isclose(result["roi_percent"], 525)
    assert np.isclose(result["payback_months"], 1.92)


def test_demo_mode_is_deterministic_and_includes_real_quality_findings():
    a = vs._demo_data()
    b = vs._demo_data()
    pd.testing.assert_frame_equal(a["raw"], b["raw"])
    pd.testing.assert_frame_equal(a["clean"], b["clean"])
    pd.testing.assert_frame_equal(a["flow"], b["flow"])
    pd.testing.assert_frame_equal(a["scenarios"], b["scenarios"])
    assert a["quality"]["missing_cells"] >= 1
    assert a["quality"]["duplicate_rows"] >= 1
    assert "synthetic" not in a["raw"].columns


def test_venture_schema_and_artifact_versioning_are_durable(tmp_path, monkeypatch):
    db = tmp_path / "venture.db"
    monkeypatch.setattr(vs, "DB_PATH", str(db))
    monkeypatch.setattr(vs, "ensure_experience_db", lambda *args, **kwargs: None)

    vs.ensure_venture_db()
    first = vs.save_artifact(
        "alice",
        "Product",
        "MVP Overview",
        "v1 product scope",
        "https://example.com/source",
        "2026-10-01",
        "Medium",
    )
    second = vs.save_artifact(
        "alice",
        "Product",
        "MVP Overview",
        "v2 product scope",
        "https://example.com/source2",
        "2026-10-02",
        "High",
    )

    assert first == second
    frame = vs._query(
        "SELECT version,content,confidence FROM venture_artifacts WHERE owner=? AND artifact_id=?",
        ("alice", first),
    )
    assert int(frame.iloc[0]["version"]) == 2
    assert frame.iloc[0]["content"] == "v2 product scope"
    versions = vs._query("SELECT version,content,confidence FROM venture_artifact_versions WHERE artifact_id=?", (first,))
    assert len(versions) == 1
    assert int(versions.iloc[0]["version"]) == 1
    assert versions.iloc[0]["content"] == "v1 product scope"

    with zipfile.ZipFile(io.BytesIO(vs._room_export("alice"))) as z:
        names = set(z.namelist())
    assert "manifest.json" in names
    assert "artifacts.csv" in names
    assert "customers.csv" in names

def test_value_inputs_start_unmeasured_and_incomplete_rows_cannot_create_value():
    table = vs._default_value_table()
    assert table["Baseline"].isna().all()
    assert table["Post"].isna().all()
    invalid = vs.value_calculation({"Baseline": 8, "Post": np.nan, "Unit value": 50, "Frequency / year": 50})
    assert invalid["valid"] == 0.0
    assert invalid["economic_value"] == 0.0


def test_value_summary_does_not_treat_unpriced_measurements_as_economic_value():
    values = pd.DataFrame([
        {"baseline_value": 8, "post_value": 3, "frequency_per_year": 50, "unit_value": np.nan, "implementation_cost": 2000, "direction": "lower_is_better"},
    ])
    result = vs.value_summary(values)
    assert result["measured_rows"] == 1
    assert result["priced_rows"] == 0
    assert result["annualized_benefit"] == 0
    assert result["roi_percent"] == 0
