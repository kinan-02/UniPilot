"""Unit tests for the Phase 7 `shadow_compare` utility.

Standalone utility in Phase 7 (not yet wired into the orchestrator — see
`docs/agent/CURRENT_STATE.md`), but fully implemented and tested here.
"""

from __future__ import annotations

from pathlib import Path

from app.agent.schemas import AgentResponse, ProposedAction, StructuredBlock
from app.agent.supervisor.output_summarizer import summarize_agent_response
from app.agent.supervisor.shadow_compare import compare_live_and_shadow_result


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


# ---------------------------------------------------------------------------
# 1. Compares live and shadow block types.
# ---------------------------------------------------------------------------


def test_compares_block_types_match() -> None:
    live = _response()
    shadow_summary = summarize_agent_response(live, workflow_name="graduation_progress_workflow")

    comparison = compare_live_and_shadow_result(
        live_workflow_name="graduation_progress_workflow",
        live_response=live,
        shadow_capability_name="graduation_progress_workflow",
        shadow_output_summary=shadow_summary,
    )

    assert comparison["liveBlockTypes"] == ["RequirementSummaryBlock", "SourceSummaryBlock"]
    assert comparison["shadowBlockTypes"] == ["RequirementSummaryBlock", "SourceSummaryBlock"]
    assert comparison["safeMatch"] is True
    assert comparison["issues"] == []


def test_flags_block_type_mismatch() -> None:
    live = _response()
    shadow_summary = {"blockTypes": ["SomeOtherBlock"], "warningCount": 0, "proposedActionCount": 0}

    comparison = compare_live_and_shadow_result(
        live_workflow_name="graduation_progress_workflow",
        live_response=live,
        shadow_capability_name="graduation_progress_workflow",
        shadow_output_summary=shadow_summary,
    )

    assert comparison["safeMatch"] is False
    assert "block_types_mismatch" in comparison["issues"]


# ---------------------------------------------------------------------------
# 2. Compares warning/action counts.
# ---------------------------------------------------------------------------


def test_compares_warning_and_action_counts() -> None:
    live = _response(warnings=["a", "b"])
    shadow_summary = {
        "blockTypes": ["RequirementSummaryBlock", "SourceSummaryBlock"],
        "warningCount": 1,
        "proposedActionCount": 0,
    }

    comparison = compare_live_and_shadow_result(
        live_workflow_name="graduation_progress_workflow",
        live_response=live,
        shadow_capability_name="graduation_progress_workflow",
        shadow_output_summary=shadow_summary,
    )

    assert comparison["liveWarningCount"] == 2
    assert comparison["shadowWarningCount"] == 1


# ---------------------------------------------------------------------------
# 3. Flags proposed-action mismatch / any shadow proposed actions at all.
# ---------------------------------------------------------------------------


def test_flags_proposed_action_count_mismatch() -> None:
    live = _response()
    shadow_summary = {
        "blockTypes": ["RequirementSummaryBlock", "SourceSummaryBlock"],
        "warningCount": 0,
        "proposedActionCount": 1,
    }

    comparison = compare_live_and_shadow_result(
        live_workflow_name="graduation_progress_workflow",
        live_response=live,
        shadow_capability_name="graduation_progress_workflow",
        shadow_output_summary=shadow_summary,
    )

    assert comparison["safeMatch"] is False
    assert "proposed_action_count_mismatch" in comparison["issues"]
    assert "shadow_produced_proposed_actions" in comparison["issues"]


def test_live_proposed_actions_counted_correctly() -> None:
    live = _response(
        proposed_actions=[
            ProposedAction(id="a1", action_type="save_semester_plan", label="Save", title="Save")
        ]
    )
    shadow_summary = {
        "blockTypes": ["RequirementSummaryBlock", "SourceSummaryBlock"],
        "warningCount": 0,
        "proposedActionCount": 1,
    }

    comparison = compare_live_and_shadow_result(
        live_workflow_name="graduation_progress_workflow",
        live_response=live,
        shadow_capability_name="graduation_progress_workflow",
        shadow_output_summary=shadow_summary,
    )

    assert comparison["liveProposedActionCount"] == 1
    # Counts match (1 == 1) but a shadow-executed capability producing any
    # proposed action at all is still flagged as unsafe.
    assert "proposed_action_count_mismatch" not in comparison["issues"]
    assert "shadow_produced_proposed_actions" in comparison["issues"]
    assert comparison["safeMatch"] is False


# ---------------------------------------------------------------------------
# 4. Does not store raw full text.
# ---------------------------------------------------------------------------


def test_comparison_never_includes_raw_full_text_or_blocks() -> None:
    long_text = "detailed explanation " * 500
    live = _response(text=long_text, blocks=[StructuredBlock(type="RequirementSummaryBlock", data={"huge": ["x"] * 500})])
    shadow_summary = summarize_agent_response(live, workflow_name="graduation_progress_workflow")

    comparison = compare_live_and_shadow_result(
        live_workflow_name="graduation_progress_workflow",
        live_response=live,
        shadow_capability_name="graduation_progress_workflow",
        shadow_output_summary=shadow_summary,
    )

    comparison_text = str(comparison)
    assert long_text not in comparison_text
    assert "huge" not in comparison_text


# ---------------------------------------------------------------------------
# 5. Does not call LLM (static scan + module inspection).
# ---------------------------------------------------------------------------


def test_shadow_compare_module_makes_no_llm_calls() -> None:
    module_path = (
        Path(__file__).resolve().parents[2] / "app" / "agent" / "supervisor" / "shadow_compare.py"
    )
    text = module_path.read_text(encoding="utf-8")
    for forbidden in ("ReasoningBlock", "ChatLLMAdapter", "llm.ainvoke", "ChatOpenAI"):
        assert forbidden not in text
