"""Static contract tests for the documented module/tier inventory.

These checks detect catalogue/inventory drift. They deliberately do not mark a
module as browser-verified: authenticated rendering and entitlement enforcement
still require the separate live acceptance matrix.
"""
from __future__ import annotations

import ast
import csv
from pathlib import Path

import pytest


ROOT = Path(__file__).resolve().parents[1]
INVENTORY_PATH = ROOT / "docs" / "MODULE_TIER_INVENTORY.csv"
REQUIRED_COLUMNS = {
    "module_name",
    "minimum_tier",
    "declared_in",
    "catalog_sources",
    "authenticated_browser_status",
}
ALLOWED_TIERS = {
    "Starter",
    "Mid-Tier Pro",
    "Professional",
    "Enterprise",
    "Enterprise Plus",
    "Research Pack",
}
ALLOWED_BROWSER_STATUSES = {
    "UNVERIFIED",
    "IMPLEMENTED / SOURCE-REVIEWED",
    "AUTOMATED",
    "BROWSER VERIFIED",
    "BLOCKED",
}
CATALOG_SOURCES = {
    "app.py MODULE_CATALOG": ROOT / "app.py",
    "industrial_platform.PLATFORM_CATALOG": ROOT / "industrial_platform.py",
}


@pytest.fixture(scope="module")
def inventory_rows() -> list[dict[str, str]]:
    with INVENTORY_PATH.open(encoding="utf-8", newline="") as stream:
        reader = csv.DictReader(stream)
        assert reader.fieldnames is not None
        missing_columns = REQUIRED_COLUMNS.difference(reader.fieldnames)
        assert not missing_columns, (
            f"Module-tier inventory is missing columns: {sorted(missing_columns)}"
        )
        return list(reader)


@pytest.fixture(scope="module")
def source_texts() -> dict[Path, str]:
    paths = {ROOT / "app.py", ROOT / "industrial_platform.py"}
    return {path: path.read_text(encoding="utf-8") for path in paths}


@pytest.fixture(scope="module")
def source_names(source_texts: dict[Path, str]) -> dict[Path, set[str]]:
    names_by_path: dict[Path, set[str]] = {}
    for path, source in source_texts.items():
        tree = ast.parse(source, filename=str(path))
        names: set[str] = set()
        for node in ast.walk(tree):
            if isinstance(node, ast.Name):
                names.add(node.id)
            elif isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef, ast.ClassDef)):
                names.add(node.name)
            elif isinstance(node, ast.arg):
                names.add(node.arg)
        names_by_path[path] = names
    return names_by_path


def test_inventory_has_unique_named_modules_and_valid_tier_labels(
    inventory_rows: list[dict[str, str]],
) -> None:
    assert inventory_rows, "The module-tier inventory must not be empty."

    names = [row["module_name"].strip() for row in inventory_rows]
    assert all(names), "Every inventory row must have a module name."
    duplicates = sorted({name for name in names if names.count(name) > 1})
    assert not duplicates, f"Duplicate module names in inventory: {duplicates}"

    for line_number, row in enumerate(inventory_rows, start=2):
        for field in REQUIRED_COLUMNS:
            assert row.get(field, "").strip(), (
                f"Inventory row {line_number} has an empty {field!r} value."
            )
        assert row["minimum_tier"].strip() in ALLOWED_TIERS, (
            f"Inventory row {line_number} has unknown tier "
            f"{row['minimum_tier']!r}."
        )
        status = row["authenticated_browser_status"].strip().upper()
        assert status in ALLOWED_BROWSER_STATUSES, (
            f"Inventory row {line_number} has unknown browser status {status!r}."
        )


def test_declared_tier_groups_exist_in_the_declared_python_source(
    inventory_rows: list[dict[str, str]],
    source_names: dict[Path, set[str]],
) -> None:
    for line_number, row in enumerate(inventory_rows, start=2):
        declaration = row["declared_in"].strip()
        assert ":" in declaration, (
            f"Inventory row {line_number} must use path:symbol in declared_in; "
            f"got {declaration!r}."
        )
        relative_path, symbol = declaration.rsplit(":", 1)
        path = (ROOT / relative_path).resolve()
        assert path in source_names, (
            f"Inventory row {line_number} points to an untested source file: "
            f"{relative_path!r}."
        )
        assert symbol in source_names[path], (
            f"Inventory row {line_number} declares missing tier group "
            f"{symbol!r} in {relative_path}."
        )


def test_each_module_is_present_in_every_catalogue_it_claims(
    inventory_rows: list[dict[str, str]],
    source_texts: dict[Path, str],
) -> None:
    for line_number, row in enumerate(inventory_rows, start=2):
        module_name = row["module_name"].strip()
        labels = [label.strip() for label in row["catalog_sources"].split(";")]

        assert labels, f"Inventory row {line_number} has no catalogue source."
        for label in labels:
            path = CATALOG_SOURCES.get(label)
            assert path is not None, (
                f"Inventory row {line_number} references unknown catalogue "
                f"source {label!r}."
            )
            assert module_name in source_texts[path], (
                f"Module {module_name!r} is listed in {label!r} but its name "
                f"is absent from {path.relative_to(ROOT)}."
            )
