"""Regression tests for strict authenticated release-gate classification."""

from pathlib import Path
import sys

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "scripts"))

from authenticated_release_gate import summarize_results


def test_all_cases_must_pass_for_release_gate_pass():
    assert summarize_results([{"status": "PASS"}, {"status": "PASS"}]) == ("PASS", 0)


def test_explicit_failure_fails_gate():
    assert summarize_results([{"status": "PASS"}, {"status": "FAIL"}]) == ("FAIL", 1)


def test_skipped_mandatory_case_blocks_gate():
    assert summarize_results([{"status": "PASS"}, {"status": "SKIP"}]) == ("BLOCKED", 2)


def test_missing_or_unknown_case_result_blocks_gate():
    assert summarize_results([]) == ("BLOCKED", 2)
    assert summarize_results([{}]) == ("BLOCKED", 2)
    assert summarize_results([{"status": "NOT_RUN"}]) == ("BLOCKED", 2)
