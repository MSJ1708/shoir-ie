"""Regression coverage for the universal 60-capability experience layer."""
from pathlib import Path
import pandas as pd

from industrial_experience import FEATURES_60, feature_catalog, generic_result, verification_snapshot, _starter_data


def test_exactly_60_capabilities_are_tracked():
    assert len(FEATURES_60) == 60
    ids = [item[0] for item in FEATURES_60]
    assert ids == [f"{i:02d}" for i in range(1, 61)]
    assert all(item[1] and item[2] and item[3] for item in FEATURES_60)


def test_universal_studio_produces_safe_results_for_multiple_module_families():
    for module in ["Industrial Simulation Lab", "Advanced Planning & Scheduling", "Industrial Sustainability & LCA", "AI Copilot"]:
        df = _starter_data(module)
        result = generic_result(df)
        verification = verification_snapshot(df)
        assert result["rows"] > 0
        assert 0 <= result["quality"] <= 100
        assert verification["score"] == 100.0


def test_capability_catalog_is_user_facing_and_numbered():
    catalog = feature_catalog()
    assert list(catalog.columns) == ["ID", "Feature", "Description", "Status"]
    assert catalog.iloc[0]["ID"] == "01"
    assert catalog.iloc[-1]["ID"] == "60"


def test_visual_shell_has_reduced_motion_and_action_surfaces():
    source = Path("industrial_experience.py").read_text(encoding="utf-8")
    for marker in ["@keyframes sxShimmer", "prefers-reduced-motion", "Save Study", "Create Run", "Decision Card", "Copilot Plan", "Evidence Pack", "plotly_chart"]:
        assert marker in source, f"Missing visual/action regression marker: {marker}"


def test_blank_module_studio_has_result_first_sections():
    source = Path("industrial_experience.py").read_text(encoding="utf-8")
    for marker in ["Overview", "Analysis", "Verification", "Decision", "Export", "Download Module Evidence Bundle"]:
        assert marker in source
