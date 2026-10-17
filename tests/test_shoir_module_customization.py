"""Regression tests for universal module personalization."""

import ast
from pathlib import Path

import pandas as pd

from industrial_platform import PLATFORM_CATALOG
from shoir_module_customization import (
    PROFILE_STORE_KEY,
    apply_display_labels,
    default_module_profile,
    evaluate_kpi_target,
    get_module_profile,
    normalize_module_profile,
    save_module_profile,
)
from workspace_persistence import load_user_workspace, save_user_workspace


ROOT = Path(__file__).resolve().parents[1]
APP_PATH = ROOT / "app.py"


def _app_assignments():
    tree = ast.parse(APP_PATH.read_text(encoding="utf-8"), filename=str(APP_PATH))
    result = {}
    for node in tree.body:
        if isinstance(node, ast.Assign):
            for target in node.targets:
                if isinstance(target, ast.Name):
                    result[target.id] = node.value
    return result


def _catalogued_module_names():
    assignments = _app_assignments()
    names = {entry["name"] for entry in ast.literal_eval(assignments["MODULE_CATALOG"])}
    names.update(str(entry["name"]) for entry in PLATFORM_CATALOG)
    for extra in ("_IOS_CATALOG_ENTRY", "_VENTURE_CATALOG_ENTRY"):
        if extra in assignments:
            names.add(ast.literal_eval(assignments[extra])["name"])
    return sorted(names)


def test_all_catalogued_modules_accept_distinct_saved_profiles():
    # Every tier catalogue module should be able to keep its own profile
    # without changing module IDs, access gates or the selected page layout.
    modules = _catalogued_module_names()
    assert len(modules) >= 85

    state = {}
    for index, module in enumerate(modules):
        saved = save_module_profile(
            state,
            module,
            "Alice",
            {
                "display_name": f"Workspace {index + 1}",
                "project_name": f"Project {index + 1}",
                "owner_team": "Operations",
                "preferred_chart": "Line",
                "tags": ["plant", "ops", "plant"],
            },
        )
        loaded = get_module_profile(state, module, "Alice")
        assert loaded["display_name"] == f"Workspace {index + 1}"
        assert loaded["preferred_chart"] == "Line"
        assert loaded["tags"] == ["plant", "ops"]

    assert len(state[PROFILE_STORE_KEY]["alice"]) == len(modules)


def test_profiles_are_isolated_by_user_and_module():
    state = {}
    save_module_profile(state, "Fleet Routing", "Alice", {"display_name": "Alice Route Planner"})
    save_module_profile(state, "Fleet Routing", "Bob", {"display_name": "Bob Route Planner"})
    save_module_profile(state, "Quality Engineering & Reliability", "Alice", {"display_name": "Quality Lab"})

    assert get_module_profile(state, "Fleet Routing", "Alice")["display_name"] == "Alice Route Planner"
    assert get_module_profile(state, "Fleet Routing", "Bob")["display_name"] == "Bob Route Planner"
    assert get_module_profile(state, "Quality Engineering & Reliability", "Alice")["display_name"] == "Quality Lab"
    assert get_module_profile(state, "Quality Engineering & Reliability", "Bob")["display_name"] == "Quality Engineering & Reliability"


def test_profile_normalization_bounds_values_and_drops_invalid_options():
    profile = normalize_module_profile(
        "Industrial Workbook",
        {
            "display_name": "  " + ("A" * 200),
            "target_value": float("inf"),
            "target_tolerance": -10,
            "target_direction": "invented",
            "target_statistic": "mode",
            "preferred_chart": "not-a-chart",
            "decimal_places": 99,
            "tags": "plant, safety;plant, research",
            "field_labels": {"Demand": "Demand (custom)", "RemovedColumn": "Should be dropped"},
            "field_units": {"Demand": "units", "RemovedColumn": "unknown"},
        },
        valid_columns=["Demand"],
    )

    assert len(profile["display_name"]) == 120
    assert profile["target_value"] == 0.0
    assert profile["target_tolerance"] == 0.0
    assert profile["target_direction"] == "At least"
    assert profile["target_statistic"] == "Mean"
    assert profile["preferred_chart"] == "Auto"
    assert profile["decimal_places"] == 6
    assert profile["tags"] == ["plant", "safety", "research"]
    assert profile["field_labels"] == {"Demand": "Demand (custom)"}
    assert profile["field_units"] == {"Demand": "units"}


def test_display_labels_are_presentation_only_and_apply_units():
    source = pd.DataFrame({"Demand": [10, 20], "Cost": [40.0, 35.0]})
    profile = default_module_profile("Inventory Playback")
    profile["field_labels"] = {"Demand": "Daily demand"}
    profile["field_units"] = {"Demand": "units/day", "Cost": "SAR"}

    displayed = apply_display_labels(source, profile)

    assert list(source.columns) == ["Demand", "Cost"]
    assert list(displayed.columns) == ["Daily demand (units/day)", "Cost (SAR)"]
    assert displayed["Daily demand (units/day)"].tolist() == [10, 20]


def test_kpi_target_rules_are_directional_and_ignore_non_numeric_values():
    at_least = evaluate_kpi_target(
        pd.Series([85, 90, "not-a-value"]),
        {
            "target_enabled": True, "target_value": 80, "target_direction": "At least",
            "target_tolerance": 0, "target_statistic": "Mean", "target_unit": "%",
        },
    )
    assert at_least is not None and at_least["passed"] is True
    assert at_least["observations"] == 2
    assert at_least["actual"] == 87.5
    assert at_least["unit"] == "%"

    at_most = evaluate_kpi_target(
        [40, 45, 50],
        {"target_enabled": True, "target_value": 50, "target_direction": "At most", "target_statistic": "Maximum"},
    )
    assert at_most is not None and at_most["passed"] is True
    assert at_most["actual"] == 50.0

    near = evaluate_kpi_target(
        [9.4, 10.0, 10.5],
        {"target_enabled": True, "target_value": 10, "target_direction": "Near target",
         "target_tolerance": 0.5, "target_statistic": "Median"},
    )
    assert near is not None and near["passed"] is True
    assert near["actual"] == 10.0

    assert evaluate_kpi_target(["invalid", None], {"target_enabled": True, "target_value": 10}) is None
    assert evaluate_kpi_target([1, 2, 3], {"target_enabled": False, "target_value": 2}) is None


def test_module_profiles_survive_workspace_round_trip_without_widget_state(tmp_path: Path):
    db = str(tmp_path / "workspace.db")
    state = {"current_user": "Alice", "authenticated": True}
    save_module_profile(
        state, "Advanced Planning & Scheduling", "Alice",
        {"display_name": "Riyadh Plant Schedule", "project_name": "Q4 line plan", "preferred_chart": "Gantt"},
    )
    state["module_profile_widget_123_display_name"] = "transient input widget"
    assert save_user_workspace("Alice", state, db)

    restored = {"authenticated": True, "current_user": "Alice"}
    assert load_user_workspace("Alice", restored, db)
    profile = get_module_profile(restored, "Advanced Planning & Scheduling", "Alice")

    assert profile["display_name"] == "Riyadh Plant Schedule"
    assert profile["project_name"] == "Q4 line plan"
    assert profile["preferred_chart"] == "Gantt"
    assert "module_profile_widget_123_display_name" not in restored


def test_customization_layer_is_connected_to_module_prepare_and_live_charts():
    parity = (ROOT / "shoir_module_parity.py").read_text(encoding="utf-8")
    live_visuals = (ROOT / "shoir_live_visuals.py").read_text(encoding="utf-8")
    preparation = parity[parity.index("def _render_prepare("):parity.index("def _render_results(")]
    results = parity[parity.index("def _render_results("):parity.index("def render_universal_module_parity(")]

    assert "render_module_customization(" in preparation
    assert "evaluate_kpi_target(" in results
    assert "display_field_label(" in results
    assert "apply_display_labels(raw_df, profile)" in live_visuals
    assert 'profile.get("preferred_chart", "Auto")' in live_visuals
    assert "target_summary" in live_visuals
