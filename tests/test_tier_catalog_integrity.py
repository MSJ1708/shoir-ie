"""Regression checks for subscription menus and the public module catalogue."""

import ast
from pathlib import Path

from industrial_platform import PLATFORM_CATALOG
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
    assert [len(tier_lists[label]) for label in TIER_LABELS] == [12, 29, 35, 64, 68, 85]

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
    dispatcher_start = platform_source.index("def render_module(")
    experiment_branch = platform_source.index('elif module=="Experiment Lab":', dispatcher_start)

    # Regression guard for the original defect: no earlier Experiment Lab
    # special case may return before the dedicated renderer branch is reached.
    bypass = platform_source.find(
        'if module == "Experiment Lab":',
        dispatcher_start,
        experiment_branch,
    )
    assert bypass == -1
    renderer = platform_source[experiment_branch:platform_source.index(
        'elif module=="Industrial Control Center":', experiment_branch
    )]
    assert "analyze_experiment_scenarios(" in renderer
    assert "st.plotly_chart(" in renderer
    assert "Analyze & Save Experiment" in renderer
    assert "Saved experiment history" in renderer
