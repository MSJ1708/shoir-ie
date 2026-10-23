"""Regression checks for subscription menus and the public module catalogue."""

import ast
import re
from pathlib import Path

import pandas as pd

from industrial_platform import PLATFORM_CATALOG
from industrial_experience import FALLBACK_MODULE_BLUEPRINTS
from shoir_tier_capabilities import unique_modules


APP_PATH = Path(__file__).resolve().parents[1] / "app.py"
TIER_NAMES = (
    "tier1_features",
    "tier2_features",
    "professional_features",
    "tier3_features",
    "tier4_features",
    "research_pack_features",
)
TIER_LABELS = (
    "Starter",
    "Mid-Tier Pro",
    "Professional",
    "Enterprise",
    "Enterprise Plus",
    "Research Pack",
)


def _top_level_assignments(tree):
    assignments = {}
    for node in tree.body:
        if isinstance(node, ast.Assign):
            for target in node.targets:
                if isinstance(target, ast.Name):
                    assignments[target.id] = node.value
    return assignments


def _resolve_list(node, assignments):
    if isinstance(node, ast.Name):
        return _resolve_list(assignments[node.id], assignments)
    if isinstance(node, ast.BinOp) and isinstance(node.op, ast.Add):
        return _resolve_list(node.left, assignments) + _resolve_list(node.right, assignments)
    if isinstance(node, ast.List):
        return [ast.literal_eval(item) for item in node.elts]
    raise AssertionError(f"Unexpected subscription list expression: {ast.dump(node)}")


def _catalogue_entries(assignments):
    entries = list(ast.literal_eval(assignments["MODULE_CATALOG"]))
    entries.extend(PLATFORM_CATALOG)
    for name in ("_IOS_CATALOG_ENTRY", "_VENTURE_CATALOG_ENTRY"):
        if name in assignments:
            entries.append(ast.literal_eval(assignments[name]))

    # The application merges catalogue entries by their exact display name.
    unique = {}
    for entry in entries:
        unique.setdefault(entry["name"], entry)
    return unique


def test_all_subscription_modules_are_catalogued_with_the_correct_tier():
    tree = ast.parse(APP_PATH.read_text(encoding="utf-8"), filename=str(APP_PATH))
    assignments = _top_level_assignments(tree)
    tier_lists = {
        label: unique_modules(_resolve_list(assignments[name], assignments))
        for name, label in zip(TIER_NAMES, TIER_LABELS)
    }
    catalogue = _catalogue_entries(assignments)

    # Keep the tier progression and its Research Pack add-on boundary explicit.
    assert [len(tier_lists[label]) for label in TIER_LABELS] == [12, 30, 36, 70, 75, 91]

    access_names = set().union(*(set(names) for names in tier_lists.values()))
    catalogue_names = set(catalogue)
    assert access_names == catalogue_names, {
        "missing_from_catalogue": sorted(access_names - catalogue_names),
        "not_in_any_tier": sorted(catalogue_names - access_names),
    }

    first_tier = {}
    for label in TIER_LABELS[:-1]:
        for name in tier_lists[label]:
            first_tier.setdefault(name, label)
    # Research-only tools are an add-on and do not imply Enterprise Plus access.
    for name in tier_lists["Research Pack"]:
        first_tier.setdefault(name, "Research Pack")

    mismatches = {
        name: {"catalogue": catalogue[name]["tier"], "access": first_tier[name]}
        for name in catalogue_names
        if catalogue[name].get("tier") != first_tier[name]
    }
    assert not mismatches, mismatches


def test_every_module_has_one_shared_live_visualization_surface():
    app_source = APP_PATH.read_text(encoding="utf-8")
    parity_source = (APP_PATH.parent / "shoir_module_parity.py").read_text(encoding="utf-8")
    dispatcher_start = app_source.index(
        'elif mod in {x["name"] for x in PLATFORM_CATALOG}:'
    )
    dispatcher_end = app_source.index(
        "# CARBON ACCOUNTING & NET-ZERO STUDIO",
        dispatcher_start,
    )
    platform_dispatcher = app_source[dispatcher_start:dispatcher_end]
    results_start = parity_source.index("def _render_results(")
    results_end = parity_source.index("def render_universal_module_parity(", results_start)
    shared_results = parity_source[results_start:results_end]

    assert "render_industrial_module(" in platform_dispatcher
    # Native module charts remain first; the shared studio is rendered once
    # by the common results contract rather than duplicated by the dispatcher.
    assert "render_live_visualization_studio" not in platform_dispatcher
    assert "render_live_visualization_studio(module, expanded=True" in shared_results



def test_experiment_lab_renderer_is_reachable_and_charted():
    platform_source = (APP_PATH.parent / "industrial_platform.py").read_text(encoding="utf-8")
    experience_source = (APP_PATH.parent / "industrial_experience.py").read_text(encoding="utf-8")
    live_visuals_source = (APP_PATH.parent / "shoir_live_visuals.py").read_text(encoding="utf-8")
    dispatcher_start = platform_source.index("def render_module(")
    experiment_route = platform_source.index('if module == "Experiment Lab":', dispatcher_start)
    generic_import = platform_source.index("render_module_data_exchange(module, st, tier, username)", dispatcher_start)

    # Experiment Lab must route to the persistent research workspace before
    # generic module import/activation. The old duplicate scenario branch must
    # stay removed so there is one canonical Scenario Lab implementation.
    assert experiment_route < generic_import
    assert "render_research_workspace(module, tier, username)" in platform_source[experiment_route:generic_import]
    assert "return" in platform_source[experiment_route:generic_import]
    assert 'elif module=="Experiment Lab":' not in platform_source[dispatcher_start:]

    workspace_start = experience_source.index('with tabs[6]:', experience_source.index("def render_research_workspace"))
    workspace_end = experience_source.index("def _safe_key", workspace_start)
    scenario_lab = experience_source[workspace_start:workspace_end]
    assert "analyze_experiment_scenarios(" in scenario_lab
    assert "st.plotly_chart(" in scenario_lab
    assert "Analyze & Save" in scenario_lab
    assert "Saved scenario experiments" in scenario_lab


def test_legacy_module_stop_hook_keeps_shared_results_and_autosave():
    app_source = APP_PATH.read_text(encoding="utf-8")
    start = app_source.index("def _shoir_module_stop():")
    end = app_source.index("from shoir_venture_studio import", start)
    stop_hook = app_source[start:end]

    assert 'and not globals().get("_shell_surface")' in stop_hook
    assert 'active_module in set(map(str, allowed))' in stop_hook
    assert 'render_universal_module_parity(active_module, phase="results")' in stop_hook
    assert 'save_user_workspace(st.session_state["current_user"], st.session_state)' in stop_hook



def test_every_catalogued_module_has_a_specialist_route_or_named_fallback_blueprint():
    app_source = APP_PATH.read_text(encoding="utf-8")
    platform_source = (APP_PATH.parent / "industrial_platform.py").read_text(encoding="utf-8")
    tree = ast.parse(app_source, filename=str(APP_PATH))
    catalogue = _catalogue_entries(_top_level_assignments(tree))

    app_renderer_names = set(re.findall(
        r"""(?:if|elif)\s+mod\s*==\s*['"]([^'"]+)['"]""",
        app_source,
    ))
    platform_renderer_names = set(re.findall(
        r"""(?:if|elif)\s+module\s*==\s*['"]([^'"]+)['"]""",
        platform_source,
    ))
    specialist_names = app_renderer_names | platform_renderer_names
    named_fallback_names = set(FALLBACK_MODULE_BLUEPRINTS)
    catalogue_names = set(catalogue)

    # This exact count includes the additive Engineering Tool Library route.
    # Keep the assertion strict so missing or duplicate routes cannot slip through.
    assert len(catalogue_names) == 97
    uncovered = catalogue_names - specialist_names - named_fallback_names
    assert not uncovered, {
        "modules_without_specialist_route_or_named_fallback": sorted(uncovered)
    }



def test_experiment_lab_routes_to_full_research_workspace_with_scenario_lab():
    app_source = APP_PATH.read_text(encoding="utf-8")
    platform_source = (APP_PATH.parent / "industrial_platform.py").read_text(encoding="utf-8")
    experience_source = (APP_PATH.parent / "industrial_experience.py").read_text(encoding="utf-8")
    live_visuals_source = (APP_PATH.parent / "shoir_live_visuals.py").read_text(encoding="utf-8")

    render_start = platform_source.index("def render_module(")
    experiment_route = platform_source.index('if module == "Experiment Lab":', render_start)
    generic_import = platform_source.index("render_module_data_exchange(module, st, tier, username)", render_start)
    control_route = platform_source.index('elif module=="Industrial Control Center":', experiment_route)
    assert experiment_route < generic_import
    assert "render_research_workspace(module, tier, username)" in platform_source[experiment_route:generic_import]
    assert "return" in platform_source[experiment_route:generic_import]
    assert control_route > experiment_route
    assert 'tabs = st.tabs(["📚 Studies & Recovery","📋 Protocol","🧪 Experiment Engine","🧪 Runs & Results","📝 Decisions","📦 Evidence & Export","📊 Scenario Lab"])' in experience_source
    assert '"Experiment Lab":["research_scenario_lab_matrix"' in platform_source
    assert '"Experiment Lab": ["research_scenario_lab_matrix", "research_scenario_lab_saved_results"' in live_visuals_source

    workspace_start = experience_source.index('with tabs[6]:', experience_source.index("def render_research_workspace"))
    workspace_end = experience_source.index("def _safe_key", workspace_start)
    scenario_lab = experience_source[workspace_start:workspace_end]
    for required_piece in (
        "analyze_experiment_scenarios(",
        "save_experiment(",
        "render_export_bar(",
        "Saved scenario experiments",
        "Inspect saved experiment",
        "research_scenario_lab_saved_signature",
        "Saved experiment inputs and results",
        "stored_results_payload, dict",
        "stored_results_payload, list",
        "Cost versus service trade-off",
    ):
        assert required_piece in scenario_lab


def test_every_named_fallback_module_has_an_analyzable_starter_dataset():
    from industrial_experience import (
        FALLBACK_MODULE_BLUEPRINTS,
        _starter_data,
        analyze_fallback_module,
    )
    failures = {}
    for module in sorted(FALLBACK_MODULE_BLUEPRINTS):
        starter = _starter_data(module)
        try:
            analysis = analyze_fallback_module(module, starter)
            if not isinstance(analysis.get("result"), pd.DataFrame):
                failures[module] = "analysis did not return a result DataFrame"
            elif analysis["result"].empty:
                failures[module] = "analysis returned an empty result"
            elif not isinstance(analysis.get("metrics"), dict):
                failures[module] = "analysis did not return a KPI dictionary"
        except Exception as exc:
            failures[module] = f"{type(exc).__name__}: {exc}"
    assert not failures, failures


def test_module_run_history_persists_snapshots_and_is_owner_scoped(tmp_path):
    from industrial_experience import (
        load_module_analysis_run,
        list_module_analysis_runs,
        save_module_analysis_run,
    )
    from shoir_module_customization import default_module_profile

    db = str(tmp_path / "module-runs.db")
    profile = default_module_profile("Quality Control, Six Sigma & Reliability")
    profile.update({"display_name": "Plant Quality Review", "project_name": "Line 2 capability"})
    inputs = pd.DataFrame({"Part": ["A", "B", "C"], "Measurement": [10.0, 10.2, 9.9]})
    results = inputs.assign(Deviation=[0.0, 0.2, -0.1])
    saved = save_module_analysis_run(
        "Quality Control, Six Sigma & Reliability", "quality-user", profile, inputs,
        {
            "result": results,
            "metrics": {"Rows reviewed": 3, "Mean deviation": 0.0333333333},
            "method": "Regression test",
            "guardrail": "Illustrative test result only.",
        },
        duration_ms=12.5, db_path=db,
    )
    history = list_module_analysis_runs(
        "Quality Control, Six Sigma & Reliability", "quality-user", db_path=db
    )
    loaded = load_module_analysis_run(saved["run_id"], "quality-user", db_path=db)

    assert saved["run_id"].startswith("MRUN-")
    assert saved["snapshot_status"] == "Complete"
    assert len(history) == 1
    assert loaded is not None
    assert loaded["input_df"]["Part"].tolist() == ["A", "B", "C"]
    assert loaded["result_df"]["Deviation"].tolist() == [0.0, 0.2, -0.1]
    assert loaded["profile"]["display_name"] == "Plant Quality Review"
    assert loaded["metrics"]["Rows reviewed"] == 3
    assert load_module_analysis_run(saved["run_id"], "different-user", db_path=db) is None
    assert list_module_analysis_runs(
        "Quality Control, Six Sigma & Reliability", "different-user", db_path=db
    ).empty


def test_module_customization_targets_and_display_names_are_independent():
    from shoir_module_customization import (
        apply_display_labels,
        default_module_profile,
        evaluate_kpi_target,
        get_module_profile,
        save_module_profile,
    )

    state = {}
    profile = default_module_profile("Advanced Planning & Scheduling")
    profile.update({
        "display_name": "Riyadh Plant Finite Schedule",
        "project_name": "Expansion Program",
        "primary_kpi": "Late Minutes",
        "target_enabled": True,
        "target_value": 30,
        "target_direction": "At most",
        "target_tolerance": 5,
        "target_statistic": "Latest",
        "target_unit": "min",
        "field_labels": {"Late Minutes": "Order lateness"},
        "field_units": {"Late Minutes": "min"},
        "preferred_chart": "SPC",
    })
    saved = save_module_profile(
        state, "Advanced Planning & Scheduling", "planner-1", profile,
        valid_columns=["Order", "Late Minutes"],
    )
    frame = pd.DataFrame({"Order": ["WO-1", "WO-2"], "Late Minutes": [20, 38]})
    displayed = apply_display_labels(frame, saved)
    check = evaluate_kpi_target(frame["Late Minutes"], saved)

    assert saved["display_name"] == "Riyadh Plant Finite Schedule"
    assert displayed.columns.tolist() == ["Order", "Order lateness (min)"]
    assert check is not None and check["passed"] is False
    assert get_module_profile(state, "Advanced Planning & Scheduling", "planner-1")["display_name"] == "Riyadh Plant Finite Schedule"
    assert get_module_profile(state, "Advanced Planning & Scheduling", "planner-2")["display_name"] == "Advanced Planning & Scheduling"


def test_profiled_chart_builder_honors_compatible_preferred_charts():
    import pandas as pd
    from industrial_experience import build_profiled_module_figure
    from shoir_module_customization import default_module_profile

    frame = pd.DataFrame({
        "Period": ["P1", "P2", "P3", "P4"],
        "Output": [100.0, 105.0, 98.0, 112.0],
        "Defects": [4.0, 3.0, 5.0, 2.0],
    })
    profile = default_module_profile("Production Planning & Control (PPC)")
    profile["preferred_chart"] = "Line"
    fig, actual, notice = build_profiled_module_figure(
        frame, "Period", "Output", profile, "Production trend"
    )
    assert fig is not None
    assert actual == "Line"
    assert notice is None

    profile["preferred_chart"] = "Correlation Heatmap"
    fig, actual, notice = build_profiled_module_figure(
        frame, "Period", "Output", profile, "Correlation diagnostics"
    )
    assert fig is not None
    assert actual == "Correlation Heatmap"
