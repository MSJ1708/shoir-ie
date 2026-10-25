"""Structured methods report tests for Research Pack target T090."""
import hashlib
import pytest
from shoir_100_tool_research_report import build_research_methods_report


def test_report_contains_methods_equations_limitations_refs_and_hash():
    result=build_research_methods_report(
        title="Cycle-time study",authors_or_team="IE Team",purpose="Compare two process settings.",
        method_name="Two-sample t test",method_version="1.0",dataset_description="Synthetic fixture, 30 samples",
        dataset_fingerprint="a"*64,formula_or_equations="t = difference / standard error",
        parameters="alpha=0.05; two-sided",assumptions=["Independent observations"],results_summary="Estimated mean difference is 1.2 min.",
        uncertainty_or_diagnostics="95% CI: 0.3 to 2.1 min",limitations=["Synthetic data only"],
        source_references=["Internal run ID RUN-123"],random_seed="42",environment_note="Python 3.x",
        created_at="2026-10-24T10:00:00+00:00")
    report=result["report_markdown"]
    assert result["status"]=="REPORT_GENERATED"
    for phrase in ["Cycle-time study","Formulae and equations","Assumptions","Limitations","RUN-123","authenticate source documents"]:
        assert phrase in report
    assert hashlib.sha256(report.encode()).hexdigest()==result["sha256"]
    assert result["raw_dataset_included"] is False


def test_report_rejects_bad_fingerprint_and_unapproved_review_claim():
    args=dict(title="Study",purpose="Question",method_name="Method",method_version="1",dataset_description="Fixture",results_summary="Result")
    with pytest.raises(ValueError,match="64-character"):
        build_research_methods_report(**args,dataset_fingerprint="not-a-hash")
    with pytest.raises(ValueError,match="Review status"):
        build_research_methods_report(**args,review_status="INDEPENDENTLY VERIFIED BY SHOIR-IE")


def test_report_rejects_oversized_fields_and_naive_timestamp():
    args=dict(title="Study",purpose="Question",method_name="Method",method_version="1",dataset_description="Fixture",results_summary="Result")
    with pytest.raises(ValueError,match="timezone"):
        build_research_methods_report(**args,created_at="2026-10-24T10:00:00")
    with pytest.raises(ValueError,match="character limit"):
        build_research_methods_report(**args,parameters="x"*9000)
