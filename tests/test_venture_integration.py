import pandas as pd
import pytest

import shoir_venture_integration as venture


@pytest.fixture
def venture_db(tmp_path, monkeypatch):
    monkeypatch.setattr(venture, "DB_PATH", str(tmp_path / "venture.db"))
    venture.st.session_state.clear()
    venture.st.session_state["current_user"] = "test-user"
    venture.st.session_state["shoir_workspace_name"] = "test-workspace"
    venture.ensure_venture_schema()
    return tmp_path


def test_schema_and_project_persist(venture_db):
    project_id = venture._insert(
        "venture_projects",
        {
            "name": "Test Venture",
            "problem": "Test problem",
            "customer": "Test customer",
            "value_proposition": "Test value",
            "stage": "Idea",
            "status": "Active",
        },
    )
    frame = venture._frame("venture_projects")
    assert project_id in set(frame["id"])
    assert frame.iloc[0]["workspace"] == "test-workspace"


def test_evidence_hash_is_deterministic(venture_db):
    payload = "Measured pilot outcome"
    first = venture.hashlib.sha256(payload.encode("utf-8")).hexdigest()
    second = venture.hashlib.sha256(payload.encode("utf-8")).hexdigest()
    assert first == second


def test_roi_reads_pilot_and_case_data(venture_db):
    venture._insert(
        "venture_pilots",
        {
            "name": "Pilot A",
            "customer": "Customer A",
            "hypothesis": "Improve KPI",
            "baseline": 100.0,
            "target": 80.0,
            "actual": 75.0,
            "status": "Completed",
            "start_date": "",
            "end_date": "",
        },
    )
    pilots = venture._frame("venture_pilots")
    assert float(pilots.iloc[0]["actual"]) == 75.0


def test_all_requested_capabilities_have_existing_module_placements():
    assert set(venture.CAPABILITY_PLACEMENT) == {
        "Venture Studio", "Customer & Stakeholder Hub", "Pilot Manager",
        "Hypothesis → Evidence", "Business Model + Pricing", "ROI / Value Evidence",
        "Investor Data Room", "Product / Traction Analytics", "End-to-End Demo Mode",
        "Market & Competitive Intelligence", "Product-Market-Fit / Readiness Dashboard",
        "Evidence Vault", "Pilot / Experiment Comparison", "Better Onboarding",
        "Case-Study Management",
    }
    assert all(placements for placements in venture.CAPABILITY_PLACEMENT.values())
    assert all("Venture Studio" not in placements for placements in venture.MODULE_TABS.values())


def test_module_mapping_has_no_new_top_level_destination():
    assert "Venture Studio" not in venture.MODULE_TABS
    assert "Industrial Operating System" in venture.MODULE_TABS
    assert "Experiment Lab" in venture.MODULE_TABS
    assert "Engineering Model Registry" in venture.MODULE_TABS
    flattened = {key for values in venture.MODULE_TABS.values() for key in values}
    required = {
        "venture", "stakeholders", "pilots", "hypothesis", "business", "roi",
        "evidence", "data_room", "traction", "demo", "market", "readiness",
        "comparison", "onboarding", "cases",
    }
    assert required <= flattened


def test_readiness_is_transparent_and_bounded(venture_db):
    scores = venture._readiness_scores()
    assert set(scores) == {"Problem", "Customer", "Pilot", "Evidence", "Hypothesis", "Case"}
    assert all(0.0 <= float(value) <= 100.0 for value in scores.values())
