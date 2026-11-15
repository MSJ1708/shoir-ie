"""Static execution-route audit for the canonical Shoir-IE T001–T100 registry.

This audit distinguishes a focused canonical Workbench method branch from a
mapped legacy-module launch. It never treats a catalog entry or a test name as
proof that a tool passed runtime acceptance.
"""
from __future__ import annotations

import ast
import csv
import json
import re
from pathlib import Path
from typing import Any

from shoir_tool_registry import TOOL_TARGETS, tool_status_counts


TOOL_ID_PATTERN = re.compile(r"^T\d{3}$")


def _selected_tool_id_subscript(node: ast.AST) -> bool:
    if not isinstance(node, ast.Subscript):
        return False
    if not isinstance(node.value, ast.Name) or node.value.id != "selected_tool":
        return False
    key = node.slice
    return isinstance(key, ast.Constant) and key.value == "tool_id"


def _tool_ids_in_literal(node: ast.AST) -> set[str]:
    values: set[str] = set()
    if isinstance(node, ast.Constant) and isinstance(node.value, str):
        if TOOL_ID_PATTERN.fullmatch(node.value):
            values.add(node.value)
    elif isinstance(node, (ast.Set, ast.Tuple, ast.List)):
        for item in node.elts:
            values.update(_tool_ids_in_literal(item))
    return values


def focused_workbench_dispatch_ids(source: str) -> set[str]:
    """Extract IDs with explicit selected_tool['tool_id'] == / in branches."""
    tree = ast.parse(source)
    found: set[str] = set()
    for node in ast.walk(tree):
        if not isinstance(node, ast.Compare):
            continue
        left = node.left
        for operator, comparator in zip(node.ops, node.comparators):
            if _selected_tool_id_subscript(left):
                if isinstance(operator, ast.Eq):
                    found.update(_tool_ids_in_literal(comparator))
                elif isinstance(operator, ast.In):
                    found.update(_tool_ids_in_literal(comparator))
            left = comparator
    return found


def build_execution_audit(repo_root: Path) -> dict[str, Any]:
    root = Path(repo_root).resolve()
    registry_path = root / "shoir_tool_registry.py"
    workbench_path = root / "pages" / "Industrial_Engineering_Workbench.py"
    matrix_path = root / "docs" / "SHOIR_100_TOOL_IMPLEMENTATION_MATRIX.csv"
    tests_dir = root / "tests"

    from shoir_tool_registry import TOOL_TARGETS as imported_targets

    targets = [dict(row) for row in imported_targets]
    expected = [f"T{i:03d}" for i in range(1, 101)]
    target_ids = [str(row.get("tool_id") or "") for row in targets]
    if target_ids != expected:
        raise ValueError("Canonical registry must contain T001 through T100 exactly once and in order.")

    with matrix_path.open("r", encoding="utf-8-sig", newline="") as handle:
        matrix_rows = list(csv.DictReader(handle))
    matrix_by_id = {str(row.get("tool_id") or ""): row for row in matrix_rows}
    if len(matrix_rows) != 100 or set(matrix_by_id) != set(expected):
        raise ValueError("Implementation matrix must contain exactly one row for each T001–T100 ID.")

    workbench_source = workbench_path.read_text(encoding="utf-8")
    focused_ids = focused_workbench_dispatch_ids(workbench_source)

    test_references: dict[str, int] = {tool_id: 0 for tool_id in expected}
    for test_path in sorted(tests_dir.rglob("test_*.py")):
        try:
            text = test_path.read_text(encoding="utf-8")
        except (OSError, UnicodeError):
            continue
        for match in re.finditer(r"\bT\d{3}\b", text):
            tool_id = match.group(0)
            if tool_id in test_references:
                test_references[tool_id] += 1

    report_rows = []
    for target in targets:
        tool_id = str(target["tool_id"])
        matrix = matrix_by_id[tool_id]
        if str(matrix.get("implementation_status") or "") != str(target.get("implementation_status") or ""):
            raise ValueError(f"{tool_id} registry and matrix readiness statuses disagree.")
        mapped_route = str(target.get("existing_module_or_route") or "").strip()
        if tool_id in focused_ids:
            route_type = "FOCUSED_METHOD_DISPATCH"
        elif mapped_route:
            route_type = "MAPPED_LEGACY_MODULE_LAUNCH"
        else:
            route_type = "NO_DECLARED_EXECUTION_ROUTE"
        report_rows.append({
            "tool_id": tool_id,
            "canonical_name": str(target.get("canonical_name") or ""),
            "minimum_tier": str(target.get("target_minimum_tier") or ""),
            "registry_status": str(target.get("implementation_status") or ""),
            "route_type": route_type,
            "mapped_route": mapped_route,
            "test_source_reference_count": test_references[tool_id],
            "unit_test_reference": str(matrix.get("unit_test") or ""),
            "integration_test_reference": str(matrix.get("integration_test") or ""),
            "browser_test_reference": str(matrix.get("browser_test") or ""),
            "remaining_gap": str(matrix.get("remaining_gap") or ""),
        })

    route_counts: dict[str, int] = {}
    for row in report_rows:
        route = row["route_type"]
        route_counts[route] = route_counts.get(route, 0) + 1

    matrix_status_counts: dict[str, int] = {}
    for row in report_rows:
        status = row["registry_status"]
        matrix_status_counts[status] = matrix_status_counts.get(status, 0) + 1

    return {
        "audit_version": 1,
        "registry_source": str(registry_path.relative_to(root)),
        "workbench_source": str(workbench_path.relative_to(root)),
        "matrix_source": str(matrix_path.relative_to(root)),
        "tool_count": len(report_rows),
        "route_type_counts": route_counts,
        "readiness_status_counts": matrix_status_counts,
        "registry_status_counts": tool_status_counts(),
        "verified_working_count": matrix_status_counts.get("VERIFIED_WORKING", 0),
        "important_limit": (
            "Static source and test-reference inventory only. A route, test reference, "
            "or registry entry is not evidence of a passing calculation, authenticated "
            "browser workflow, persistence, export, or independent engineering review."
        ),
        "tools": report_rows,
    }


def main() -> int:
    repo_root = Path(__file__).resolve().parents[1]
    report = build_execution_audit(repo_root)
    print(json.dumps(report, indent=2, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
