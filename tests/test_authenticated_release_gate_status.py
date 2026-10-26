"""Regression tests for strict authenticated release-gate classification."""

from pathlib import Path
import sys

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "scripts"))

from authenticated_release_gate import summarize_results


REQUIRED = {("login", "active"), ("logout", "active")}


def case(name, status):
    return {"case": name, "account_class": "active", "status": status}


def test_all_required_cases_must_pass_for_release_gate_pass():
    assert summarize_results([case("login", "PASS"), case("logout", "PASS")], REQUIRED) == ("PASS", 0)


def test_explicit_failure_fails_gate():
    assert summarize_results([case("login", "PASS"), case("logout", "FAIL")], REQUIRED) == ("FAIL", 1)


def test_skipped_mandatory_case_blocks_gate():
    assert summarize_results([case("login", "PASS"), case("logout", "SKIP")], REQUIRED) == ("BLOCKED", 2)


def test_missing_mandatory_case_blocks_gate_even_if_remaining_cases_pass():
    assert summarize_results([case("login", "PASS")], REQUIRED) == ("BLOCKED", 2)


def test_empty_missing_or_unknown_results_block_gate():
    assert summarize_results([], REQUIRED) == ("BLOCKED", 2)
    assert summarize_results([{"status": "PASS", "case": "login", "account_class": "active"}], REQUIRED) == ("BLOCKED", 2)
    assert summarize_results([case("logout", "NOT_RUN"), case("login", "PASS")], REQUIRED) == ("BLOCKED", 2)
    assert summarize_results([case("logout", "mystery"), case("login", "PASS")], REQUIRED) == ("BLOCKED", 2)


def test_default_contract_requires_named_gate_cases():
    # Even a list consisting only of PASS records cannot pass without the
    # authenticated gate's required cases being present.
    assert summarize_results([case("unrelated", "PASS")]) == ("BLOCKED", 2)
