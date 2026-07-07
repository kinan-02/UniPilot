"""Unit tests for the Phase 7 `output_summarizer` module."""

from __future__ import annotations

from app.agent.schemas import AgentResponse, ProposedAction, StructuredBlock
from app.agent.supervisor.output_summarizer import summarize_agent_response, unsafe_output_summary

_FORBIDDEN_FIELD_NAMES = {
    "chain_of_thought",
    "hidden_reasoning",
    "private_reasoning",
    "scratchpad",
    "thoughts",
}


def _response(**overrides) -> AgentResponse:
    defaults = dict(
        conversation_id="conv-1",
        message_id="",
        run_id="run-1",
        text="short text",
        blocks=[],
        warnings=[],
        used_sources=[],
    )
    defaults.update(overrides)
    return AgentResponse(**defaults)


# ---------------------------------------------------------------------------
# 1. Text preview with max length.
# ---------------------------------------------------------------------------


def test_short_text_is_not_truncated() -> None:
    summary = summarize_agent_response(_response(text="short answer"), workflow_name="wf")
    assert summary["textPreview"] == "short answer"


def test_long_text_is_truncated_with_ellipsis() -> None:
    long_text = "a" * 1000
    summary = summarize_agent_response(_response(text=long_text), workflow_name="wf")
    assert len(summary["textPreview"]) < 260
    assert summary["textPreview"].endswith("…")


# ---------------------------------------------------------------------------
# 2/3. Block count + block types.
# ---------------------------------------------------------------------------


def test_counts_blocks_and_extracts_types() -> None:
    response = _response(
        blocks=[
            StructuredBlock(type="RequirementSummaryBlock", data={}),
            StructuredBlock(type="RequirementBucketBlock", data={}),
            StructuredBlock(type="SourceSummaryBlock", data={}),
        ]
    )
    summary = summarize_agent_response(response, workflow_name="wf")
    assert summary["blockCount"] == 3
    assert summary["blockTypes"] == [
        "RequirementSummaryBlock",
        "RequirementBucketBlock",
        "SourceSummaryBlock",
    ]


# ---------------------------------------------------------------------------
# 4. Counts warnings.
# ---------------------------------------------------------------------------


def test_counts_warnings() -> None:
    summary = summarize_agent_response(
        _response(warnings=["missing_profile", "low_confidence"]), workflow_name="wf"
    )
    assert summary["warningCount"] == 2


# ---------------------------------------------------------------------------
# 5. Counts sources.
# ---------------------------------------------------------------------------


def test_counts_sources() -> None:
    summary = summarize_agent_response(
        _response(used_sources=["mongodb:completed_courses", "catalog:degree_requirements"]),
        workflow_name="wf",
    )
    assert summary["sourceCount"] == 2


# ---------------------------------------------------------------------------
# 6/7. Counts proposed actions; omits raw proposed action payloads.
# ---------------------------------------------------------------------------


def test_counts_proposed_actions_without_raw_payload() -> None:
    response = _response(
        proposed_actions=[
            ProposedAction(
                id="a1",
                action_type="save_semester_plan",
                label="Save",
                title="Save plan",
                payload={"plannedCourses": ["234218"] * 50, "secretInternalField": "raw"},
            )
        ]
    )
    summary = summarize_agent_response(response, workflow_name="wf")
    assert summary["proposedActionCount"] == 1
    assert summary["hasProposedActions"] is True
    assert "plannedCourses" not in str(summary)
    assert "secretInternalField" not in str(summary)
    assert "payload" not in summary


# ---------------------------------------------------------------------------
# 8. Omits raw transcript rows (nothing transcript-shaped ever appears).
# ---------------------------------------------------------------------------


def test_summary_never_includes_raw_transcript_or_course_rows() -> None:
    response = _response(
        blocks=[
            StructuredBlock(
                type="TranscriptReviewBlock",
                data={"rows": [{"courseNumber": "234218", "grade": 90}] * 100},
            )
        ]
    )
    summary = summarize_agent_response(response, workflow_name="wf")
    assert "rows" not in summary
    assert "234218" not in str(summary)
    # Only the block's type is surfaced, never its `data` payload.
    assert summary["blockTypes"] == ["TranscriptReviewBlock"]


# ---------------------------------------------------------------------------
# 9. No forbidden chain-of-thought/scratchpad fields.
# ---------------------------------------------------------------------------


def test_no_forbidden_fields_in_summary() -> None:
    summary = summarize_agent_response(_response(), workflow_name="wf")
    assert not (_FORBIDDEN_FIELD_NAMES & set(summary))


def test_unsafe_output_summary_shape_and_no_forbidden_fields() -> None:
    summary = unsafe_output_summary(workflow_name="wf", reason="test_reason")
    assert summary == {
        "shadowExecuted": False,
        "workflowName": "wf",
        "responseType": "AgentResponse",
        "reason": "test_reason",
    }
    assert not (_FORBIDDEN_FIELD_NAMES & set(summary))


def test_summary_confidence_reflects_warnings() -> None:
    clean = summarize_agent_response(_response(warnings=[]), workflow_name="wf")
    warned = summarize_agent_response(_response(warnings=["something_off"]), workflow_name="wf")
    assert clean["confidence"] == 1.0
    assert warned["confidence"] < clean["confidence"]
