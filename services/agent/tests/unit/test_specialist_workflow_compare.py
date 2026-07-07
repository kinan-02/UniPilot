"""Unit tests for Phase 11 workflow-vs-specialist comparison (`specialists/compare.py`)."""

from __future__ import annotations

from app.agent.schemas import AgentResponse, StructuredBlock
from app.agent.specialists.compare import compare_workflow_and_specialist, specialist_agent_for_workflow
from app.agent.specialists.validation_schemas import WORKFLOW_TO_SPECIALIST_AGENT


def _response(**overrides) -> AgentResponse:
    defaults = dict(
        conversation_id="conv-1",
        message_id="",
        run_id="run-1",
        text="You still need 12 credits.",
        blocks=[
            StructuredBlock(type="RequirementSummaryBlock", data={}),
            StructuredBlock(type="SourceSummaryBlock", data={}),
        ],
        warnings=[],
        used_sources=["mongodb:completed_courses"],
    )
    defaults.update(overrides)
    return AgentResponse(**defaults)


def _summary(**overrides) -> dict:
    defaults = dict(
        agentName="graduation_progress_agent",
        status="completed",
        confidence=0.9,
        warningCount=0,
        sourceCount=1,
        hasProposedActions=False,
        missingContextCount=0,
        resultKeys=["creditsRemaining", "requirementProgress"],
    )
    defaults.update(overrides)
    return defaults


# ---------------------------------------------------------------------------
# 1, 2, 3. Deterministic workflow -> specialist mapping.
# ---------------------------------------------------------------------------


def test_graduation_workflow_maps_to_graduation_specialist() -> None:
    assert specialist_agent_for_workflow("graduation_progress_workflow") == "graduation_progress_agent"


def test_course_question_workflow_maps_to_course_catalog_specialist() -> None:
    assert specialist_agent_for_workflow("course_question_workflow") == "course_catalog_agent"


def test_requirement_explanation_workflow_maps_to_requirement_specialist() -> None:
    assert specialist_agent_for_workflow("requirement_explanation_workflow") == "requirement_explanation_agent"


def test_mapping_excludes_general_academic_and_write_workflows() -> None:
    for name in ("general_academic_workflow", "transcript_import_workflow", "semester_planning_workflow"):
        assert name not in WORKFLOW_TO_SPECIALIST_AGENT
        assert specialist_agent_for_workflow(name) is None


# ---------------------------------------------------------------------------
# 4. Unknown workflow is not comparable.
# ---------------------------------------------------------------------------


def test_unknown_workflow_is_not_comparable() -> None:
    assert specialist_agent_for_workflow("some_unknown_workflow") is None

    comparison = compare_workflow_and_specialist(
        workflow_name="some_unknown_workflow", live_response=_response(), specialist_output_summary=_summary()
    )

    assert comparison.comparable is False
    assert comparison.safe_match is False
    codes = [issue.code for issue in comparison.issues]
    assert "workflow_not_comparable" in codes


def test_none_workflow_is_not_comparable() -> None:
    comparison = compare_workflow_and_specialist(
        workflow_name=None, live_response=_response(), specialist_output_summary=_summary()
    )
    assert comparison.comparable is False


def test_missing_specialist_summary_is_not_comparable() -> None:
    comparison = compare_workflow_and_specialist(
        workflow_name="graduation_progress_workflow", live_response=_response(), specialist_output_summary=None
    )
    assert comparison.comparable is False
    codes = [issue.code for issue in comparison.issues]
    assert "no_comparable_specialist_result" in codes


def test_missing_live_response_is_not_comparable() -> None:
    comparison = compare_workflow_and_specialist(
        workflow_name="graduation_progress_workflow", live_response=None, specialist_output_summary=_summary()
    )
    assert comparison.comparable is False


def test_mismatched_specialist_agent_name_is_not_comparable() -> None:
    comparison = compare_workflow_and_specialist(
        workflow_name="graduation_progress_workflow",
        live_response=_response(),
        specialist_output_summary=_summary(agentName="course_catalog_agent"),
    )
    assert comparison.comparable is False
    codes = [issue.code for issue in comparison.issues]
    assert "specialist_agent_mismatch" in codes


# ---------------------------------------------------------------------------
# 5. Matching structural summary returns safe_match=true.
# ---------------------------------------------------------------------------


def test_matching_structural_summary_returns_safe_match() -> None:
    comparison = compare_workflow_and_specialist(
        workflow_name="graduation_progress_workflow", live_response=_response(), specialist_output_summary=_summary()
    )

    assert comparison.comparable is True
    assert comparison.safe_match is True
    assert comparison.live_block_types == ["RequirementSummaryBlock", "SourceSummaryBlock"]
    assert comparison.specialist_result_keys == ["creditsRemaining", "requirementProgress"]
    assert comparison.issues == []


# ---------------------------------------------------------------------------
# 6. Proposed action presence fails comparison.
# ---------------------------------------------------------------------------


def test_proposed_action_presence_fails_comparison() -> None:
    comparison = compare_workflow_and_specialist(
        workflow_name="graduation_progress_workflow",
        live_response=_response(),
        specialist_output_summary=_summary(hasProposedActions=True),
    )

    assert comparison.safe_match is False
    codes = [issue.code for issue in comparison.issues]
    assert "specialist_proposed_actions_detected" in codes


# ---------------------------------------------------------------------------
# 7. Missing context fails safe_match.
# ---------------------------------------------------------------------------


def test_missing_context_fails_safe_match() -> None:
    comparison = compare_workflow_and_specialist(
        workflow_name="graduation_progress_workflow",
        live_response=_response(),
        specialist_output_summary=_summary(missingContextCount=2),
    )

    assert comparison.safe_match is False
    codes = [issue.code for issue in comparison.issues]
    assert "specialist_missing_context" in codes


# ---------------------------------------------------------------------------
# 8. Low confidence fails safe_match.
# ---------------------------------------------------------------------------


def test_low_confidence_fails_safe_match() -> None:
    comparison = compare_workflow_and_specialist(
        workflow_name="graduation_progress_workflow",
        live_response=_response(),
        specialist_output_summary=_summary(confidence=0.2),
    )

    assert comparison.safe_match is False
    codes = [issue.code for issue in comparison.issues]
    assert "low_specialist_confidence" in codes


def test_empty_specialist_result_fails_safe_match() -> None:
    comparison = compare_workflow_and_specialist(
        workflow_name="graduation_progress_workflow",
        live_response=_response(),
        specialist_output_summary=_summary(resultKeys=[]),
    )

    assert comparison.safe_match is False
    codes = [issue.code for issue in comparison.issues]
    assert "specialist_empty_result" in codes


# ---------------------------------------------------------------------------
# 9 & 10. Comparison does not store raw text/blocks.
# ---------------------------------------------------------------------------


def test_comparison_never_stores_raw_text() -> None:
    long_text = "detailed explanation " * 500
    live = _response(text=long_text)

    comparison = compare_workflow_and_specialist(
        workflow_name="graduation_progress_workflow", live_response=live, specialist_output_summary=_summary()
    )

    comparison_text = str(comparison.model_dump())
    assert long_text not in comparison_text


def test_comparison_never_stores_raw_blocks() -> None:
    live = _response(blocks=[StructuredBlock(type="RequirementSummaryBlock", data={"huge": ["x"] * 500})])

    comparison = compare_workflow_and_specialist(
        workflow_name="graduation_progress_workflow", live_response=live, specialist_output_summary=_summary()
    )

    comparison_text = str(comparison.model_dump())
    assert "huge" not in comparison_text


def test_comparison_never_calls_llm() -> None:
    from pathlib import Path

    module_path = Path(__file__).resolve().parents[2] / "app" / "agent" / "specialists" / "compare.py"
    text = module_path.read_text(encoding="utf-8")
    for forbidden in ("ReasoningBlock", "ChatLLMAdapter", "llm.ainvoke", "ChatOpenAI"):
        assert forbidden not in text
