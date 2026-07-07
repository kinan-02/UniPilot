"""Unit tests for the Phase 9 candidate response safety checks
(`supervisor/promotion.check_candidate_response_safety`).

Deliberately exercises both real `AgentResponse` instances (proposed
actions, forbidden payload fields, block mismatches) and lightweight
duck-typed stand-ins (`types.SimpleNamespace`) for structurally malformed
fields Pydantic itself would never allow a real `AgentResponse` to hold.
"""

from __future__ import annotations

import types

from app.agent.schemas import AgentResponse, ProposedAction, StructuredBlock
from app.agent.supervisor.promotion import check_candidate_response_safety, eligible_promotion_workflows
from app.config import Settings


def _response(**overrides) -> AgentResponse:
    defaults = dict(
        conversation_id="c",
        message_id="",
        run_id="r",
        text="text",
        blocks=[StructuredBlock(type="RequirementSummaryBlock", data={})],
        warnings=[],
        used_sources=[],
    )
    defaults.update(overrides)
    return AgentResponse(**defaults)


# ---------------------------------------------------------------------------
# 1. Valid AgentResponse candidate passes.
# ---------------------------------------------------------------------------


def test_valid_candidate_passes() -> None:
    candidate = _response()
    reasons = check_candidate_response_safety(candidate, live_response=candidate)
    assert reasons == []


def test_valid_candidate_passes_without_live_response() -> None:
    candidate = _response()
    reasons = check_candidate_response_safety(candidate)
    assert reasons == []


# ---------------------------------------------------------------------------
# 2. Candidate with proposed_actions fails.
# ---------------------------------------------------------------------------


def test_candidate_with_proposed_actions_fails() -> None:
    candidate = _response(
        proposed_actions=[ProposedAction(id="a1", action_type="save_semester_plan", label="Save", title="Save")]
    )
    reasons = check_candidate_response_safety(candidate)
    codes = [r.code for r in reasons]
    assert "candidate_has_proposed_actions" in codes


# ---------------------------------------------------------------------------
# 3. Candidate with raw payload field fails.
# ---------------------------------------------------------------------------


def test_candidate_with_raw_payload_field_fails() -> None:
    candidate = _response(blocks=[StructuredBlock(type="RequirementSummaryBlock", data={"raw_context": {"secret": 1}})])
    reasons = check_candidate_response_safety(candidate)
    codes = [r.code for r in reasons]
    assert "candidate_forbidden_payload_detected" in codes


# ---------------------------------------------------------------------------
# 4. Candidate with mismatched block types fails.
# ---------------------------------------------------------------------------


def test_candidate_with_mismatched_block_types_fails() -> None:
    live = _response(blocks=[StructuredBlock(type="RequirementSummaryBlock", data={})])
    candidate = _response(blocks=[StructuredBlock(type="SomeOtherBlock", data={})])
    reasons = check_candidate_response_safety(candidate, live_response=live)
    codes = [r.code for r in reasons]
    assert "candidate_block_type_mismatch" in codes


# ---------------------------------------------------------------------------
# 5. Candidate with mismatched block count fails.
# ---------------------------------------------------------------------------


def test_candidate_with_mismatched_block_count_fails() -> None:
    live = _response(
        blocks=[
            StructuredBlock(type="RequirementSummaryBlock", data={}),
            StructuredBlock(type="SourceSummaryBlock", data={}),
        ]
    )
    candidate = _response(blocks=[StructuredBlock(type="RequirementSummaryBlock", data={})])
    reasons = check_candidate_response_safety(candidate, live_response=live)
    codes = [r.code for r in reasons]
    assert "candidate_block_count_mismatch" in codes
    # Block type sets happen to still overlap (subset), so type mismatch
    # also legitimately fires -- both are valid, independent signals.


# ---------------------------------------------------------------------------
# 6. Candidate with malformed warnings/sources fails.
# ---------------------------------------------------------------------------


def test_candidate_with_malformed_warnings_fails() -> None:
    candidate = types.SimpleNamespace(
        proposed_actions=[],
        warnings="not-a-list",
        used_sources=[],
        blocks=[types.SimpleNamespace(type="RequirementSummaryBlock")],
    )
    reasons = check_candidate_response_safety(candidate)
    codes = [r.code for r in reasons]
    assert "candidate_warnings_malformed" in codes


def test_candidate_with_malformed_sources_fails() -> None:
    candidate = types.SimpleNamespace(
        proposed_actions=[],
        warnings=[],
        used_sources="not-a-list",
        blocks=[types.SimpleNamespace(type="RequirementSummaryBlock")],
    )
    reasons = check_candidate_response_safety(candidate)
    codes = [r.code for r in reasons]
    assert "candidate_sources_malformed" in codes


def test_candidate_with_malformed_proposed_actions_fails() -> None:
    candidate = types.SimpleNamespace(
        proposed_actions="not-a-list",
        warnings=[],
        used_sources=[],
        blocks=[types.SimpleNamespace(type="RequirementSummaryBlock")],
    )
    reasons = check_candidate_response_safety(candidate)
    codes = [r.code for r in reasons]
    assert "candidate_proposed_actions_malformed" in codes


def test_candidate_with_missing_blocks_fails() -> None:
    candidate = types.SimpleNamespace(proposed_actions=[], warnings=[], used_sources=[], blocks=[])
    reasons = check_candidate_response_safety(candidate)
    codes = [r.code for r in reasons]
    assert "candidate_blocks_missing_or_malformed" in codes


def test_candidate_with_structurally_invalid_block_fails() -> None:
    candidate = types.SimpleNamespace(
        proposed_actions=[], warnings=[], used_sources=[], blocks=[types.SimpleNamespace(type="")]
    )
    reasons = check_candidate_response_safety(candidate)
    codes = [r.code for r in reasons]
    assert "candidate_block_structurally_invalid" in codes


def test_candidate_none_fails() -> None:
    reasons = check_candidate_response_safety(None)
    codes = [r.code for r in reasons]
    assert "candidate_missing" in codes


# ---------------------------------------------------------------------------
# 7. Forbidden chain-of-thought/scratchpad keys fail.
# ---------------------------------------------------------------------------


def test_candidate_with_chain_of_thought_key_fails() -> None:
    candidate = _response(blocks=[StructuredBlock(type="RequirementSummaryBlock", data={"chain_of_thought": "..."})])
    reasons = check_candidate_response_safety(candidate)
    codes = [r.code for r in reasons]
    assert "candidate_forbidden_payload_detected" in codes


def test_candidate_with_scratchpad_key_fails() -> None:
    candidate = _response(blocks=[StructuredBlock(type="RequirementSummaryBlock", data={"scratchpad": "..."})])
    reasons = check_candidate_response_safety(candidate)
    codes = [r.code for r in reasons]
    assert "candidate_forbidden_payload_detected" in codes


# ---------------------------------------------------------------------------
# Eligible-workflow ceiling.
# ---------------------------------------------------------------------------


def test_eligible_promotion_workflows_is_hard_capped_regardless_of_config() -> None:
    settings = Settings(
        AGENT_SUPERVISOR_PROMOTION_WORKFLOWS="graduation_progress_workflow,semester_planning_workflow,course_question_workflow"
    )
    # semester_planning_workflow is a write/proposal workflow and stays hard-excluded
    # even though it's in the configured list; course_question_workflow was widened
    # into the hard ceiling this cycle alongside graduation_progress_workflow.
    assert eligible_promotion_workflows(settings) == {"graduation_progress_workflow", "course_question_workflow"}


def test_eligible_promotion_workflows_empty_when_configured_list_excludes_it() -> None:
    settings = Settings(AGENT_SUPERVISOR_PROMOTION_WORKFLOWS="semester_planning_workflow")
    assert eligible_promotion_workflows(settings) == set()


def test_eligible_promotion_workflows_empty_when_unconfigured() -> None:
    settings = Settings(AGENT_SUPERVISOR_PROMOTION_WORKFLOWS="")
    assert eligible_promotion_workflows(settings) == set()
