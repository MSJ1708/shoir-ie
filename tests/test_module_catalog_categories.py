"""Catalog, tier-menu and primary-navigation consistency regression tests.

The application entrypoint is parsed rather than imported so these tests can audit its
real tier lists without initializing Streamlit authentication or writing app databases.
"""
import ast
from pathlib import Path

from industrial_platform import PLATFORM_CATALOG
from shoir_application_shell import (
    MODULE_CATEGORY_GROUPS,
    _module_choices,
    build_module_index,
    module_group,
    _module_target_section,
    _preferred_module,
)


APP_PATH = Path(__file__).resolve().parents[1] / "app.py"


def _app_assignments():
    tree = ast.parse(APP_PATH.read_text(encoding="utf-8"), filename=str(APP_PATH))
    assignments = {}
    for node in tree.body:
        if isinstance(node, ast.Assign):
            for target in node.targets:
                if isinstance(target, ast.Name):
                    assignments[target.id] = node.value
    return assignments


def _resolve_literal(name, assignments, cache=None):
    cache = cache if cache is not None else {}
    if name in cache:
        return cache[name]
    node = assignments[name]
    if isinstance(node, ast.BinOp) and isinstance(node.op, ast.Add):
        left = _resolve_node(node.left, assignments, cache)
        right = _resolve_node(node.right, assignments, cache)
        value = left + right
    else:
        value = _resolve_node(node, assignments, cache)
    cache[name] = value
    return value


def _resolve_node(node, assignments, cache):
    if isinstance(node, ast.Name):
        return _resolve_literal(node.id, assignments, cache)
    if isinstance(node, ast.BinOp) and isinstance(node.op, ast.Add):
        return _resolve_node(node.left, assignments, cache) + _resolve_node(node.right, assignments, cache)
    return ast.literal_eval(node)


def _catalog_snapshot():
    assignments = _app_assignments()
    legacy_catalog = _resolve_literal("MODULE_CATALOG", assignments)
    # app.py preserves its own labels for names already in the legacy catalog,
    # then appends specialist catalog entries that were not already listed.
    catalog = {item["name"]: item for item in PLATFORM_CATALOG}
    catalog.update({item["name"]: item for item in legacy_catalog})
    feature_names = set()
    for name in (
        "tier1_features",
        "tier2_features",
        "professional_features",
        "tier3_features",
        "tier4_features",
        "research_pack_features",
    ):
        feature_names.update(_resolve_literal(name, assignments))
    return assignments, catalog, feature_names


def test_every_subscription_module_is_in_the_explorer_catalog_and_categorized():
    _, catalog, feature_names = _catalog_snapshot()
    missing = sorted(feature_names - set(catalog))
    assert not missing, f"Modules available in tier menus but missing from Explore Modules: {missing}"

    uncategorized = sorted(
        name for name in feature_names
        if not str(catalog[name].get("category", "")).strip()
    )
    assert not uncategorized, f"Modules missing a catalog category: {uncategorized}"

    unmapped_categories = sorted(
        {
            str(item.get("category", "")).strip().casefold()
            for item in catalog.values()
            if str(item.get("category", "")).strip().casefold() not in MODULE_CATEGORY_GROUPS
        }
    )
    assert not unmapped_categories, f"Catalog categories have no shell mapping: {unmapped_categories}"

    module_index = build_module_index(sorted(feature_names), catalog)
    assert len(module_index) == len(feature_names)
    assert not (module_index["Group"] == "Industrial Engineering").any(), (
        "A subscription module is falling into the uncategorized fallback group."
    )


def test_every_subscription_module_is_discoverable_in_a_relevant_primary_section():
    _, catalog, feature_names = _catalog_snapshot()
    metadata = catalog
    sections = (
        "DATA", "ANALYZE", "SIMULATE", "OPTIMIZE", "OPERATIONS",
        "DECISIONS", "RESEARCH", "KNOWLEDGE", "ADMIN",
    )
    missing = []
    names = sorted(feature_names)
    for name in names:
        visible_in = [
            section for section in sections
            if name in _module_choices(names, section, "", metadata)
        ]
        if not visible_in:
            missing.append(name)
    assert not missing, f"Modules are not discoverable from any categorized section: {missing}"


def test_empty_filtered_section_does_not_fall_back_to_an_unrelated_module():
    allowed = ["MILP Solvers"]
    metadata = {"MILP Solvers": {"category": "Core Optimization"}}

    choices = _module_choices(allowed, "RESEARCH", "", metadata)
    assert choices == []
    assert _preferred_module(choices, current_module="MILP Solvers") is None


def test_global_search_routes_modules_to_matching_primary_sections():
    metadata = {
        "Excel Data Cleaning & Import": {"category": "Data Platform"},
        "MILP Solvers": {"category": "Core Optimization"},
        "Statistical Hypothesis Testing": {"category": "Research & Experimentation"},
        "Digital Twin & Discrete-Event Simulation": {"category": "Digital Twin"},
        "Engineering Decision Center": {"category": "Decisions"},
    }
    assert _module_target_section("Excel Data Cleaning & Import", metadata) == "DATA"
    assert _module_target_section("MILP Solvers", metadata) == "OPTIMIZE"
    assert _module_target_section("Statistical Hypothesis Testing", metadata) == "RESEARCH"
    assert _module_target_section("Digital Twin & Discrete-Event Simulation", metadata) == "OPERATIONS"
    assert _module_target_section("Engineering Decision Center", metadata) == "DECISIONS"




def test_explore_modules_can_opt_in_to_target_tools_with_readiness_and_existing_routes():
    source = APP_PATH.read_text(encoding="utf-8")

    assert "from shoir_tool_registry import TOOL_TARGETS as _target_tool_targets" in source
    assert "Include the 100 target engineering tools" in source
    assert 'key="explore_include_target_tools_v1"' in source
    assert "_explore_catalog = list(MODULE_CATALOG)" in source
    assert "_explore_catalog.extend(_target_catalog_rows)" in source
    assert "for _m in _explore_catalog:" in source
    assert '"readiness_status"' in source
    assert '"mapped_route"' in source
    assert "Open this target in Workbench" in source
    assert 'st.session_state["shoir_100_tool_query"] = ""' in source
    assert 'st.session_state["shoir_100_tool_workbench"] = "All workbenches"' in source
    assert 'st.session_state["shoir_100_tool_status"] = "All statuses"' in source
    assert 'st.session_state["shoir_expand_target_directory"] = True' in source
    workbench_source = (APP_PATH.parent / "pages" / "Industrial_Engineering_Workbench.py").read_text(encoding="utf-8")
    assert 'st.session_state.pop("shoir_expand_target_directory", False)' in workbench_source
    assert 'with st.expander("🧭 100-tool directory & readiness", expanded=_expand_target_directory)' in workbench_source
    assert 'st.switch_page("pages/Industrial_Engineering_Workbench.py")' in source


def test_recently_added_resilience_tools_have_meaningful_shell_groups():
    _, catalog, _ = _catalog_snapshot()
    expected = {
        "Autonomous Global Supply Chain & Resilient Logistics Network": "Supply Chain",
        "Zero-Waste Closed-Loop Mega-Factory (Industrial Symbiosis Engine)": "Sustainability",
        "Real-Time Urban Mobility & Smart Infrastructure Grid": "Operations",
        "Fully Automated Emergency Response & Humanitarian Disaster Logistics System": "Supply Chain",
        "Autonomous Kinetic-Digital Twin (AKDT) for Industrial Logistics Resilience": "Maintenance",
        "L-SIMS — Local Capability & Dynamic Industrial Readiness Simulator": "Production",
        "ShadowShift — Micro-Loss & Recovery Intelligence": "Operations",
        "Venture Studio": "Platform & Governance",
    }
    for name, group in expected.items():
        assert name in catalog, f"{name} is missing from the shared catalog"
        assert module_group(name, catalog) == group
