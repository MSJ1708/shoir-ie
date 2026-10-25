"""Deterministic tests for the guided-study, help and practice target engines."""
import math

import pytest

from shoir_100_tool_learning_engines import (
    build_guided_study_plan,
    check_practice_answer,
    get_practice_question,
    guided_study_problem_types,
    guided_study_required_inputs,
    search_contextual_help,
)


def test_guided_study_requires_valid_type_and_surfaces_missing_prerequisites():
    result = build_guided_study_plan(
        problem_type="Production capacity / bottleneck",
        objective="Find the constraint",
        data_state="No validated dataset",
        available_fields=["demand and period"],
    )
    assert result["status"] == "PLAN_GENERATED"
    assert result["steps"][0]["recommended_tool_id"] == "T011"
    assert "approved source dataset or documented manual observations" in result["missing_inputs"]
    assert "net available time and unit" in result["missing_inputs"]
    assert result["metrics"]["ready_to_analyze"] is False
    assert any("No plant result" in item for item in result["warnings"])


def test_guided_study_complete_checklist_is_deterministic_and_not_a_result():
    problem = "Facility layout / material flow"
    result = build_guided_study_plan(
        problem_type=problem,
        objective="Compare two layout alternatives",
        data_state="Validated dataset",
        available_fields=guided_study_required_inputs(problem),
        key_constraints="Keep egress routes clear",
    )
    assert result["missing_inputs"] == []
    assert result["metrics"]["ready_to_analyze"] is True
    assert result["recommended_tool_ids"] == ["T011", "T013", "T065", "T073", "T095"]
    assert [step["step"] for step in result["steps"]] == list(range(1, 6))
    assert result["status"] != "CALCULATED"


def test_guided_study_rejects_unknown_type_and_oversized_context():
    assert len(guided_study_problem_types()) >= 5
    with pytest.raises(ValueError, match="Problem type"):
        build_guided_study_plan(problem_type="invent a result")
    with pytest.raises(ValueError, match="1000"):
        build_guided_study_plan(problem_type="Quality / defects", objective="x" * 1001)


def test_contextual_help_search_is_curated_and_tool_specific():
    result = search_contextual_help(query="capacity")
    assert result["status"] == "HELP_RESULTS"
    assert result["metrics"]["result_count"] >= 1
    assert any("T025" in item["related_tools"] for item in result["articles"])
    by_tool = search_contextual_help(tool_id="T065")
    assert by_tool["metrics"]["matched_tool_id"] is True
    assert any(item["topic"] == "Facility layout and flow" for item in by_tool["articles"])
    with pytest.raises(ValueError, match="canonical target ID"):
        search_contextual_help(tool_id="T999")
    with pytest.raises(ValueError, match="Enter a help topic"):
        search_contextual_help()


@pytest.mark.parametrize(
    ("topic", "answer", "expected", "correct"),
    [
        ("Takt time", 1.2, 1.2, True),
        ("OEE", 83.8, 83.79, True),
        ("Standard time", 0.70, 0.69575, True),
        ("Takt time", 12, 1.2, False),
    ],
)
def test_practice_examples_match_hand_calculated_answers(topic, answer, expected, correct):
    question = get_practice_question(topic=topic)
    result = check_practice_answer(topic=topic, answer=answer)
    assert question["question_id"] == result["question_id"]
    assert result["correct_answer"] == pytest.approx(expected)
    assert result["is_correct"] is correct
    assert result["worked_formula"]
    assert result["solution_steps"]
    assert result["metrics"]["absolute_error"] == pytest.approx(abs(answer-expected))


def test_practice_rejects_nonfinite_answers_and_unknown_topics():
    for value in (math.nan, math.inf, -math.inf):
        with pytest.raises(ValueError, match="finite"):
            check_practice_answer(topic="Takt time", answer=value)
    with pytest.raises(ValueError, match="Topic"):
        get_practice_question(topic="unknown")
