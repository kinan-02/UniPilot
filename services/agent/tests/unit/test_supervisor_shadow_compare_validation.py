"""Unit tests for the Phase 8 run-level shadow comparison (`shadow_compare.build_comparison_summary`).

Complements `test_supervisor_shadow_compare.py` (Phase 7's single-capability
`compare_live_and_shadow_result`) — this file covers the run-level
`ShadowComparisonSummary` builder used by `supervisor.post_context_runner`.
"""

from __future__ import annotations

from pathlib import Path

from app.agent.capabilities.registry import CapabilityRegistry
from app.agent.capabilities.schemas import CapabilityDescriptor, CapabilityExecutionMetadata
from app.agent.schemas import AgentResponse, ProposedAction, StructuredBlock
from app.agent.supervisor.compare_diagnostics import build_supervisor_validation_metadata
from app.agent.supervisor.schemas import SubtaskExecutionRecord, SupervisorRunOutput
from app.agent.supervisor.shadow_compare import build_comparison_summary
from app.agent.supervisor.validation import validate_shadow_run


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


def _record(**overrides) -> SubtaskExecutionRecord:
    defaults = dict(
        subtask_id="check_progress",
        capability_name="graduation_progress_workflow",
        status="completed",
        result_summary={
            "shadowExecuted": True,
            "blockTypes": ["RequirementSummaryBlock", "SourceSummaryBlock"],
            "blockCount": 2,
            "warningCount": 0,
            "proposedActionCount": 0,
            "sourceCount": 1,
        },
    )
    defaults.update(overrides)
    return SubtaskExecutionRecord(**defaults)


def _shadow_output(*records: SubtaskExecutionRecord, **overrides) -> SupervisorRunOutput:
    defaults = dict(
        status="completed",
        plan_id="plan-1",
        execution_mode="single_capability",
        subtask_records=list(records),
        completed_subtasks=[r.subtask_id for r in records if r.status == "completed"],
        failed_subtasks=[r.subtask_id for r in records if r.status == "failed"],
        skipped_subtasks=[r.subtask_id for r in records if r.status == "skipped"],
    )
    defaults.update(overrides)
    return SupervisorRunOutput(**defaults)


# ---------------------------------------------------------------------------
# 1 & 2. Extracts live/shadow block types compactly.
# ---------------------------------------------------------------------------


def test_extracts_live_and_shadow_block_types_compactly() -> None:
    live = _response()
    shadow_output = _shadow_output(_record())

    comparison = build_comparison_summary(
        live_workflow_name="graduation_progress_workflow", live_response=live, shadow_run_output=shadow_output
    )

    assert comparison.live_block_types == ["RequirementSummaryBlock", "SourceSummaryBlock"]
    assert comparison.shadow_block_types == ["RequirementSummaryBlock", "SourceSummaryBlock"]
    assert comparison.live_block_count == 2
    assert comparison.shadow_block_count == 2
    assert comparison.safe_match is True


# ---------------------------------------------------------------------------
# 3 & 4. Never stores raw live/shadow text.
# ---------------------------------------------------------------------------


def test_does_not_store_raw_live_or_shadow_text() -> None:
    long_text = "detailed explanation " * 500
    live = _response(text=long_text)
    shadow_output = _shadow_output(
        _record(result_summary={"shadowExecuted": True, "textPreview": "irrelevant", "blockTypes": []})
    )

    comparison = build_comparison_summary(
        live_workflow_name="graduation_progress_workflow", live_response=live, shadow_run_output=shadow_output
    )

    comparison_text = str(comparison.model_dump())
    assert long_text not in comparison_text


# ---------------------------------------------------------------------------
# 5. Does not store raw blocks.
# ---------------------------------------------------------------------------


def test_does_not_store_raw_blocks() -> None:
    live = _response(blocks=[StructuredBlock(type="RequirementSummaryBlock", data={"huge": ["x"] * 500})])
    shadow_output = _shadow_output(_record())

    comparison = build_comparison_summary(
        live_workflow_name="graduation_progress_workflow", live_response=live, shadow_run_output=shadow_output
    )

    comparison_text = str(comparison.model_dump())
    assert "huge" not in comparison_text


# ---------------------------------------------------------------------------
# 6. Detects proposed-action mismatch.
# ---------------------------------------------------------------------------


def test_detects_proposed_action_mismatch() -> None:
    live = _response(
        proposed_actions=[ProposedAction(id="a1", action_type="save_semester_plan", label="Save", title="Save")]
    )
    shadow_output = _shadow_output(_record())

    comparison = build_comparison_summary(
        live_workflow_name="graduation_progress_workflow", live_response=live, shadow_run_output=shadow_output
    )

    assert comparison.live_proposed_action_count == 1
    assert comparison.shadow_proposed_action_count == 0

    result = validate_shadow_run(comparison=comparison)
    assert result.status == "failed"


def test_detects_shadow_proposed_actions_as_unsafe() -> None:
    live = _response()
    shadow_output = _shadow_output(
        _record(
            result_summary={
                "shadowExecuted": True,
                "blockTypes": ["RequirementSummaryBlock", "SourceSummaryBlock"],
                "blockCount": 2,
                "warningCount": 0,
                "proposedActionCount": 1,
                "sourceCount": 0,
                "hasProposedActions": True,
            }
        )
    )

    comparison = build_comparison_summary(
        live_workflow_name="graduation_progress_workflow", live_response=live, shadow_run_output=shadow_output
    )

    assert comparison.shadow_proposed_action_count == 1
    assert comparison.unsafe_capabilities_attempted == ["graduation_progress_workflow"]
    assert comparison.safe_match is False


# ---------------------------------------------------------------------------
# 7. Handles missing shadow result safely.
# ---------------------------------------------------------------------------


def test_handles_missing_shadow_result_safely() -> None:
    live = _response()

    comparison = build_comparison_summary(
        live_workflow_name="graduation_progress_workflow", live_response=live, shadow_run_output=None
    )

    assert comparison.shadow_block_types == []
    assert comparison.shadow_block_count == 0
    assert comparison.shadow_status is None
    assert comparison.live_block_count == 2


def test_handles_missing_live_response_safely() -> None:
    shadow_output = _shadow_output(_record())

    comparison = build_comparison_summary(
        live_workflow_name="graduation_progress_workflow", live_response=None, shadow_run_output=shadow_output
    )

    assert comparison.live_block_types == []
    assert comparison.live_block_count == 0
    assert comparison.shadow_block_count == 2


# ---------------------------------------------------------------------------
# 8. Handles a skipped unsafe capability safely (not flagged as unsafe).
# ---------------------------------------------------------------------------


def test_skipped_unsafe_capability_is_not_flagged_as_an_unsafe_attempt() -> None:
    live = _response()
    skipped_record = _record(
        capability_name="semester_planning_workflow",
        status="skipped",
        result_summary={
            "shadowExecuted": False,
            "reason": "Capability may create proposed actions; real shadow execution deferred.",
        },
    )
    shadow_output = _shadow_output(skipped_record, status="completed_with_warnings")

    comparison = build_comparison_summary(
        live_workflow_name="semester_planning_workflow", live_response=live, shadow_run_output=shadow_output
    )

    assert comparison.unsafe_capabilities_attempted == []
    assert comparison.shadow_skipped_subtasks == ["check_progress"]


# ---------------------------------------------------------------------------
# Uses `capability_registry.side_effect_level` as an additional unsafe signal.
# ---------------------------------------------------------------------------


def test_uses_capability_registry_side_effect_level_as_unsafe_signal() -> None:
    live = _response()
    registry = CapabilityRegistry()
    registry.register(
        CapabilityDescriptor(
            name="risky_capability",
            type="workflow",
            description="test",
            execution=CapabilityExecutionMetadata(side_effect_level="write"),
        )
    )
    shadow_output = _shadow_output(
        _record(
            capability_name="risky_capability",
            result_summary={
                "shadowExecuted": True,
                "blockTypes": [],
                "blockCount": 0,
                "warningCount": 0,
                "proposedActionCount": 0,
                "sourceCount": 0,
            },
        )
    )

    comparison = build_comparison_summary(
        live_workflow_name="risky_capability",
        live_response=live,
        shadow_run_output=shadow_output,
        capability_registry=registry,
    )

    assert comparison.unsafe_capabilities_attempted == ["risky_capability"]

    result = validate_shadow_run(comparison=comparison)
    assert result.status == "failed"
    assert any(issue.code == "unsafe_capability_shadow_execution_detected" for issue in result.issues)


# ---------------------------------------------------------------------------
# End-to-end: comparison -> validation -> compact metadata dict.
# ---------------------------------------------------------------------------


def test_end_to_end_comparison_validation_and_metadata_never_include_raw_payloads() -> None:
    long_text = "sensitive details " * 200
    live = _response(text=long_text)
    shadow_output = _shadow_output(_record())

    comparison = build_comparison_summary(
        live_workflow_name="graduation_progress_workflow", live_response=live, shadow_run_output=shadow_output
    )
    result = validate_shadow_run(comparison=comparison, validation_enabled=True)
    metadata = build_supervisor_validation_metadata(result)

    assert metadata["status"] == "passed"
    assert metadata["safeToPromote"] is True
    assert metadata["liveWorkflowName"] == "graduation_progress_workflow"
    assert metadata["shadowStatus"] == "completed"

    metadata_text = str(metadata)
    assert long_text not in metadata_text
    for forbidden in ("raw_context", "chain_of_thought", "scratchpad", "proposed_action_payload"):
        assert forbidden not in metadata_text


def test_shadow_compare_module_still_makes_no_llm_calls() -> None:
    module_path = (
        Path(__file__).resolve().parents[2] / "app" / "agent" / "supervisor" / "shadow_compare.py"
    )
    text = module_path.read_text(encoding="utf-8")
    for forbidden in ("ReasoningBlock", "ChatLLMAdapter", "llm.ainvoke", "ChatOpenAI"):
        assert forbidden not in text
