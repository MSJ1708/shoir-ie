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

def test_quality_evidence_calculates_error_detection_and_rework_avoided():
    result = vs.quality_evidence_calculation({
        "issues_detected": 8,
        "issues_confirmed": 10,
        "baseline_rework_hours": 14,
        "post_rework_hours": 6,
    })
    assert np.isclose(result["error_detection_rate_percent"], 80.0)
    assert np.isclose(result["rework_avoided_hours"], 8.0)


def test_venture_ui_foundation_helpers_and_demo_story_are_present():
    assert callable(vs._render_overview)
    assert callable(vs._show_fig)
    assert callable(vs._optional_float)
    assert len(vs.DEMO_STORY) == 7


def test_value_calculation_distinguishes_unmeasured_from_zero():
    missing = vs.value_calculation({
        "Baseline": np.nan,
        "Post": 0,
        "Unit value": 50,
        "Frequency / year": 50,
    })
    measured_zero = vs.value_calculation({
        "Baseline": 0,
        "Post": 0,
        "Unit value": 50,
        "Frequency / year": 50,
    })
    assert missing["valid"] == 0.0
    assert missing["economic_value"] == 0.0
    assert measured_zero["valid"] == 1.0
    assert measured_zero["economic_value"] == 0.0


def test_value_summary_blocks_silent_mixed_currency_aggregation():
    values = pd.DataFrame([
        {"baseline_value": 10, "post_value": 5, "frequency_per_year": 10, "unit_value": 2, "currency": "SAR", "implementation_cost": 100},
        {"baseline_value": 20, "post_value": 15, "frequency_per_year": 10, "unit_value": 3, "currency": "USD", "implementation_cost": 100},
    ])
    result = vs.value_summary(values)
    assert result["measured_rows"] == 2
    assert result["priced_rows"] == 2
    assert result["mixed_currency"] == 1.0
    assert result["annualized_benefit"] == 0.0
    assert result["roi_percent"] == 0.0
    assert result["currency"] == "MIXED"


def test_venture_scope_exposes_requested_incubator_workspaces():
    required = [
        "_render_customer",
        "_render_pilots",
        "_render_hypothesis_evidence",
        "_render_evidence_vault",
        "_render_pilot_comparison",
        "_render_value_evidence",
        "_render_data_room",
        "_render_readiness",
        "_render_traction",
        "_render_demo",
        "_render_market",
        "_render_case_study",
        "_render_business_model",
    ]
    assert all(callable(getattr(vs, name, None)) for name in required)


def test_value_summary_blocks_unspecified_currency_when_priced():
    values = pd.DataFrame([
        {"baseline_value": 10, "post_value": 5, "frequency_per_year": 10, "unit_value": 2, "currency": "", "implementation_cost": 100},
    ])
    result = vs.value_summary(values)
    assert result["priced_rows"] == 1
    assert result["mixed_currency"] == 1.0
    assert result["currency_missing"] == 1.0
    assert result["annualized_benefit"] == 0.0



def test_artifact_version_history_is_scoped_to_parent_artifact_owner(tmp_path, monkeypatch):
    db = tmp_path / "venture.db"
    monkeypatch.setattr(vs, "DB_PATH", str(db))
    monkeypatch.setattr(vs, "ensure_experience_db", lambda *args, **kwargs: None)
    vs.ensure_venture_db()

    alice_artifact = vs.save_artifact(
        "alice", "Product", "Plan", "alice version 1", "https://alice.example/1",
        "2026-10-10", "Medium"
    )
    vs.save_artifact(
        "alice", "Product", "Plan", "alice version 2", "https://alice.example/2",
        "2026-10-11", "High"
    )
    bob_artifact = vs.save_artifact(
        "bob", "Product", "Plan", "bob version 1", "https://bob.example/1",
        "2026-10-10", "Medium"
    )
    vs.save_artifact(
        "bob", "Product", "Plan", "bob version 2", "https://bob.example/2",
        "2026-10-12", "High"
    )

    alice_history = vs.artifact_version_history("alice", alice_artifact)
    bob_history = vs.artifact_version_history("bob", alice_artifact)
    bob_own_history = vs.artifact_version_history("bob", bob_artifact)

    assert len(alice_history) == 1
    assert alice_history.iloc[0]["source_url"] == "https://alice.example/1"
    assert bob_history.empty
    assert len(bob_own_history) == 1
    assert bob_own_history.iloc[0]["source_url"] == "https://bob.example/1"


def test_investor_room_export_contains_only_the_requested_owners_artifacts(tmp_path, monkeypatch):
    monkeypatch.setattr(vs, "DB_PATH", str(tmp_path / "venture-export.sqlite"))
    monkeypatch.setattr(vs, "ensure_experience_db", lambda *args, **kwargs: None)
    vs.ensure_venture_db()
    alice_id = vs.save_artifact(
        "alice", "Product", "Alice confidential", "Alice-only content",
        "https://example.com/alice", "2026-10-10", "High",
    )
    vs.save_artifact(
        "bob", "Product", "Bob confidential", "Bob-only content",
        "https://example.com/bob", "2026-10-11", "High",
    )
    vs.save_artifact(
        "alice", "Product", "Alice confidential", "Alice updated content",
        "https://example.com/alice-v2", "2026-10-12", "Audited",
    )

    with zipfile.ZipFile(io.BytesIO(vs._room_export("alice"))) as archive:
        artifacts = pd.read_json(archive.open("artifact_content.json"))
        versions = pd.read_csv(archive.open("artifact_versions.csv"))
        manifest = pd.read_json(archive.open("manifest.json"), typ="series")

    assert alice_id in set(artifacts["artifact_id"])
    assert artifacts["title"].tolist() == ["Alice confidential"]
    assert "Bob-only content" not in artifacts.to_json()
    assert "Bob confidential" not in artifacts.to_json()
    assert set(versions["artifact_id"]) == {alice_id}
    assert manifest["owner"] == "alice"
    assert int(artifacts.iloc[0]["version"]) == 2
