from pathlib import Path

from scripts.audit_shoir_100_tool_execution import build_execution_audit


def test_execution_audit_accounts_for_all_100_tools_and_distinguishes_route_types():
    root = Path(__file__).resolve().parents[1]
    report = build_execution_audit(root)

    assert report["tool_count"] == 100
    ids = [row["tool_id"] for row in report["tools"]]
    assert ids == [f"T{i:03d}" for i in range(1, 101)]

    route_counts = report["route_type_counts"]
    assert sum(route_counts.values()) == 100
    assert set(route_counts).issubset({
        "FOCUSED_METHOD_DISPATCH",
        "MAPPED_LEGACY_MODULE_LAUNCH",
        "NO_DECLARED_EXECUTION_ROUTE",
    })
    assert route_counts.get("FOCUSED_METHOD_DISPATCH", 0) == 100
    assert route_counts.get("MAPPED_LEGACY_MODULE_LAUNCH", 0) == 0
    assert route_counts.get("NO_DECLARED_EXECUTION_ROUTE", 0) == 0
    assert report["verified_working_count"] == 0


def test_execution_audit_keeps_source_test_references_separate_from_acceptance():
    root = Path(__file__).resolve().parents[1]
    report = build_execution_audit(root)

    assert "not evidence" in report["important_limit"]
    for row in report["tools"]:
        assert row["registry_status"] in {
            "VERIFIED_WORKING",
            "IMPLEMENTED_NEEDS_VALIDATION",
            "FOUNDATION_ONLY",
            "MISSING",
            "EXTERNAL_CONFIGURATION_REQUIRED",
            "BLOCKED",
        }
        assert isinstance(row["test_source_reference_count"], int)
        assert "remaining_gap" in row
