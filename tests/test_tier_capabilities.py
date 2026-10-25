import ast
import csv
from pathlib import Path

from shoir_tier_capabilities import (MODULE_REQUIREMENTS, TIER_ORDER, audit_module_entitlement_coverage, available_modules, copilot_gate, module_required_tier, normalize_tier, tier_allows)
from industrial_platform import PLATFORM_CATALOG, TIER_FEATURES, tier_allows as platform_tier_allows


def test_tier_order_and_research_are_distinct():
    assert normalize_tier("Starter Tier") == "Starter"
    assert normalize_tier("Enterprise Plus Tier") == "Enterprise Plus"
    assert normalize_tier("Research Pack ($30 add-on)") == "Research Pack"
    assert tier_allows("Starter", "Starter")
    assert tier_allows("Research Pack", "Enterprise")
    assert tier_allows("Research Pack", "Research Pack")
    assert not tier_allows("Research Pack", "Enterprise Plus")
    assert not tier_allows("Enterprise Plus", "Research Pack")


def test_platform_tier_gate_matches_shared_research_add_on_policy():
    # Research Pack inherits the Enterprise base but not Enterprise Plus.
    assert platform_tier_allows("Research Pack ($30 add-on)", "Enterprise")
    assert platform_tier_allows("Research Pack ($30 add-on)", "Research Pack")
    assert not platform_tier_allows("Research Pack ($30 add-on)", "Enterprise Plus")
    assert platform_tier_allows("Enterprise Plus Tier ($399)", "Enterprise Plus")
    assert not platform_tier_allows("Enterprise Plus Tier ($399)", "Research Pack")


def test_copilot_and_research_module_requirements():
    assert module_required_tier("AI Copilot") == "Starter"
    assert module_required_tier("Research AI") == "Research Pack"
    assert tier_allows("Starter", "Starter")
    assert not tier_allows("Starter", "Research Pack")
    assert not tier_allows("Enterprise", "Research Pack")




def test_research_pack_cannot_access_enterprise_plus_modules_or_copilot_actions():
    candidates = [
        "Research AI",
        "Advanced Engineering Copilot",
        "Live Industrial Digital Twin",
        "Enterprise Security & Governance",
        "Predictive Maintenance Digital Twin",
    ]
    assert available_modules("Research Pack ($30 add-on)", candidates) == ["Research AI"]
    assert available_modules("Enterprise Plus Tier ($399)", candidates) == [
        "Advanced Engineering Copilot",
        "Live Industrial Digital Twin",
        "Enterprise Security & Governance",
        "Predictive Maintenance Digital Twin",
    ]

    for phrase in (
        "open Advanced Engineering Copilot",
        "open Live Industrial Digital Twin",
        "open Enterprise Security & Governance",
        "open Predictive Maintenance Digital Twin",
    ):
        gate = copilot_gate(phrase, "Research Pack")
        assert gate is not None and gate["required_tier"] == "Enterprise Plus"


def test_copilot_blocks_package_gated_actions():
    gate = copilot_gate("run Monte Carlo simulation", "Starter Tier")
    assert gate is not None and gate["required_tier"] == "Enterprise"
    research_gate = copilot_gate("run hypothesis testing", "Enterprise Tier")
    assert research_gate is not None and research_gate["required_tier"] == "Research Pack"
    assert copilot_gate("run Monte Carlo simulation", "Research Pack") is None
    assert copilot_gate("what is ANOVA?", "Starter Tier") is None



def test_module_entitlement_audit_reports_unmapped_catalog_items():
    report = audit_module_entitlement_coverage([
        "AI Copilot",
        "Research AI",
        "Module with no explicit policy",
        "AI Copilot",
        "",
    ])

    assert report["status"] == "INCOMPLETE"
    assert report["total_modules"] == 3
    assert report["explicit_policy_count"] == 2
    assert report["unmapped_count"] == 1
    assert report["unmapped_modules"] == ["Module with no explicit policy"]
    assert report["invalid_policy_count"] == 0
    assert report["coverage_percent"] == 66.67
    assert report["policy_source"] == "MODULE_REQUIREMENTS"


def test_module_entitlement_audit_reports_empty_catalog_without_claiming_coverage():
    report = audit_module_entitlement_coverage([])

    assert report["status"] == "EMPTY"
    assert report["total_modules"] == 0
    assert report["coverage_percent"] == 0.0


def test_module_entitlement_audit_exposes_invalid_policy_tier(monkeypatch):
    monkeypatch.setitem(MODULE_REQUIREMENTS, "Audit-only invalid mapping", "Unrecognized tier")

    report = audit_module_entitlement_coverage(["Audit-only invalid mapping"])

    assert report["status"] == "INCOMPLETE"
    assert report["explicit_policy_count"] == 0
    assert report["invalid_policy_count"] == 1
    assert report["invalid_policy_modules"] == [
        {"module": "Audit-only invalid mapping", "required_tier": "Unrecognized tier"}
    ]



def test_unmapped_and_invalid_module_policies_fail_closed():
    from shoir_tier_capabilities import module_access_decision

    unknown = "Unregistered Protected Capability"
    assert module_access_decision("Enterprise Plus", unknown) == {
        "allowed": False,
        "module": unknown,
        "required_tier": None,
        "current_tier": "Enterprise Plus",
        "reason": "unmapped_capability",
    }
    assert unknown not in available_modules("Enterprise Plus", [unknown, "AI Copilot"])

    MODULE_REQUIREMENTS["Test-only invalid policy"] = "Unknown Tier"
    try:
        invalid = module_access_decision("Enterprise Plus", "Test-only invalid policy")
        assert invalid["allowed"] is False
        assert invalid["reason"] == "invalid_tier_policy"
        assert "Test-only invalid policy" not in available_modules(
            "Enterprise Plus", ["Test-only invalid policy"]
        )
    finally:
        MODULE_REQUIREMENTS.pop("Test-only invalid policy", None)


def test_declared_module_entitlement_tiers_are_known_tiers():
    assert set(MODULE_REQUIREMENTS.values()).issubset(set(TIER_ORDER))



def test_every_platform_catalog_entry_has_an_explicit_matching_shared_tier_policy():
    names = [str(item["name"]) for item in PLATFORM_CATALOG]
    report = audit_module_entitlement_coverage(names)

    assert report["status"] == "COMPLETE"
    assert report["total_modules"] == len(names)
    assert report["total_modules"] == len(set(names))
    assert report["unmapped_modules"] == []
    assert report["invalid_policy_modules"] == []
    assert all(
        module_required_tier(str(item["name"])) == normalize_tier(str(item["tier"]))
        for item in PLATFORM_CATALOG
    )



def test_every_tier_feature_has_explicit_matching_shared_tier_policy():
    tier_order = ["Starter", "Mid-Tier Pro", "Professional", "Enterprise", "Enterprise Plus"]
    minimum_tiers = {}
    for tier in tier_order:
        for module in TIER_FEATURES.get(tier, []):
            minimum_tiers.setdefault(str(module), tier)

    report = audit_module_entitlement_coverage(minimum_tiers.keys())

    assert report["status"] == "COMPLETE"
    assert report["total_modules"] == len(minimum_tiers)
    assert report["unmapped_modules"] == []
    assert all(
        module_required_tier(module) == tier
        for module, tier in minimum_tiers.items()
    )



def _app_source_tree():
    app_path = Path(__file__).resolve().parents[1] / "app.py"
    return ast.parse(app_path.read_text(encoding="utf-8"), filename=str(app_path))


def _literal_dict_name(node):
    if not isinstance(node, ast.Dict):
        return None
    for key, value in zip(node.keys, node.values):
        if isinstance(key, ast.Constant) and key.value == "name":
            if isinstance(value, ast.Constant) and isinstance(value.value, str):
                return value.value
    return None


def _app_subscription_feature_lists():
    required_names = {
        "tier1_features", "tier2_features", "professional_features",
        "tier3_features", "tier4_features", "research_pack_features",
    }
    expressions = {}
    for node in _app_source_tree().body:
        if not isinstance(node, ast.Assign):
            continue
        targets = [target.id for target in node.targets if isinstance(target, ast.Name)]
        for target in targets:
            if target in required_names:
                expressions[target] = node.value

    values = {}
    for name in (
        "tier1_features", "tier2_features", "professional_features",
        "tier3_features", "tier4_features", "research_pack_features",
    ):
        expr = expressions.get(name)
        if expr is None:
            raise AssertionError(f"app.py is missing the {name} assignment")
        if isinstance(expr, ast.List):
            values[name] = ast.literal_eval(expr)
        elif isinstance(expr, ast.BinOp) and isinstance(expr.op, ast.Add) and isinstance(expr.left, ast.Name):
            parent = expr.left.id
            if parent not in values:
                raise AssertionError(f"app.py tier list {name} references unevaluated list {parent}")
            values[name] = values[parent] + ast.literal_eval(expr.right)
        else:
            raise AssertionError(f"Unsupported app.py tier-list expression for {name}")
    return values


def _app_minimum_tier_by_module():
    lists = _app_subscription_feature_lists()
    minimum = {}
    for list_name, required_tier in (
        ("tier1_features", "Starter"),
        ("tier2_features", "Mid-Tier Pro"),
        ("professional_features", "Professional"),
        ("tier3_features", "Enterprise"),
        ("tier4_features", "Enterprise Plus"),
        ("research_pack_features", "Research Pack"),
    ):
        for module in lists[list_name]:
            minimum.setdefault(str(module), required_tier)
    return minimum


def _app_runtime_catalog_names():
    tree = _app_source_tree()
    assignments = {}
    for node in tree.body:
        if not isinstance(node, ast.Assign):
            continue
        targets = [target.id for target in node.targets if isinstance(target, ast.Name)]
        for target in targets:
            if target in {"MODULE_CATALOG", "_IOS_CATALOG_ENTRY", "_VENTURE_CATALOG_ENTRY"}:
                assignments[target] = node.value

    catalog_expr = assignments.get("MODULE_CATALOG")
    if not isinstance(catalog_expr, ast.List):
        raise AssertionError("app.py MODULE_CATALOG must remain a literal list for source inventory verification")

    names = set()
    for item in catalog_expr.elts:
        name = _literal_dict_name(item)
        if name:
            names.add(name)
    for item in PLATFORM_CATALOG:
        name = str(item.get("name") or "").strip()
        if name:
            names.add(name)
    for constant in ("_IOS_CATALOG_ENTRY", "_VENTURE_CATALOG_ENTRY"):
        expr = assignments.get(constant)
        name = _literal_dict_name(expr) if expr is not None else None
        if name:
            names.add(name)
    return names


def test_all_app_subscription_features_have_explicit_matching_shared_policies():
    minimum = _app_minimum_tier_by_module()
    report = audit_module_entitlement_coverage(minimum.keys())

    assert len(minimum) == 96
    assert report["status"] == "COMPLETE"
    assert report["total_modules"] == 96
    assert report["unmapped_modules"] == []
    assert report["invalid_policy_modules"] == []
    assert all(
        module_required_tier(module) == required
        for module, required in minimum.items()
    )


def test_runtime_module_catalog_matches_the_tiered_module_inventory():
    catalog_names = _app_runtime_catalog_names()
    minimum = _app_minimum_tier_by_module()

    assert len(catalog_names) == 96
    assert catalog_names == set(minimum)



def test_checked_in_module_tier_inventory_matches_live_source_declarations():
    root = Path(__file__).resolve().parents[1]
    inventory_path = root / "docs" / "MODULE_TIER_INVENTORY.csv"
    with inventory_path.open(encoding="utf-8", newline="") as handle:
        rows = list(csv.DictReader(handle))

    minimum = _app_minimum_tier_by_module()
    assert len(rows) == 96
    assert len({row["module_name"] for row in rows}) == 96
    assert {row["module_name"] for row in rows} == set(minimum)
    assert {
        row["module_name"]: row["minimum_tier"] for row in rows
    } == minimum
    assert all(row["declared_in"].startswith("app.py:") for row in rows)
    assert all(row["authenticated_browser_status"] == "UNVERIFIED" for row in rows)
    assert all(
        module_required_tier(row["module_name"]) == row["minimum_tier"]
        for row in rows
    )



def test_every_app_module_follows_the_shared_allow_deny_matrix_for_all_tiers():
    minimum = _app_minimum_tier_by_module()
    catalog = list(minimum)
    tiers = ["Starter", "Mid-Tier Pro", "Professional", "Enterprise", "Enterprise Plus", "Research Pack"]

    assert len(catalog) == 96
    for current_tier in tiers:
        actual = set(available_modules(current_tier, catalog))
        expected = {
            module for module, required_tier in minimum.items()
            if tier_allows(current_tier, required_tier)
        }
        assert actual == expected, f"Tier policy mismatch for {current_tier}"
