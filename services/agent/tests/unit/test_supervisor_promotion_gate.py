"""Unit tests for the Phase 9 promotion gate (`supervisor/promotion.evaluate_promotion_decision`).

Uses only compact summaries/settings for gates 1–15 (matching the promotion
gate's own docstring: most gates never need a raw `AgentResponse`), and a
real `AgentResponse` candidate only for the "promoted" happy path and the
deep candidate-safety gate.
"""

from __future__ import annotations

from app.agent.schemas import AgentResponse, ProposedAction, StructuredBlock
from app.agent.supervisor.promotion import evaluate_promotion_decision
from app.config import Settings

_DISABLED = Settings(AGENT_SUPERVISOR_PROMOTION_ENABLED=False, AGENT_SUPERVISOR_PROMOTION_MODE="off")
_SHADOW_ONLY = Settings(AGENT_SUPERVISOR_PROMOTION_ENABLED=True, AGENT_SUPERVISOR_PROMOTION_MODE="shadow_only")
_PROMOTE_VALIDATED = Settings(AGENT_SUPERVISOR_PROMOTION_ENABLED=True, AGENT_SUPERVISOR_PROMOTION_MODE="promote_validated")
_ENABLED_BUT_MODE_OFF = Settings(AGENT_SUPERVISOR_PROMOTION_ENABLED=True, AGENT_SUPERVISOR_PROMOTION_MODE="off")


def _live_summary(**overrides) -> dict:
    defaults = dict(proposedActionCount=0, blockTypes=["RequirementSummaryBlock"], blockCount=1, warningCount=0)
    defaults.update(overrides)
    return defaults


def _candidate_summary(**overrides) -> dict:
    defaults = dict(proposedActionCount=0, blockTypes=["RequirementSummaryBlock"], blockCount=1, warningCount=0)
    defaults.update(overrides)
    return defaults


def _validation(**overrides) -> dict:
    defaults = dict(status="passed", safeToPromote=True, issues=[])
    defaults.update(overrides)
    return defaults


def _supervisor_output(**overrides) -> dict:
    defaults = dict(status="completed", capabilities=["graduation_progress_workflow"], failedSubtasks=[], skippedSubtasks=[])
    defaults.update(overrides)
    return defaults


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


def _evaluate(*, settings: Settings, workflow_name="graduation_progress_workflow", **overrides):
    kwargs = dict(
        workflow_name=workflow_name,
        live_response_summary=_live_summary(),
        candidate_response_summary=_candidate_summary(),
        supervisor_validation=_validation(),
        supervisor_output_summary=_supervisor_output(),
        settings=settings,
        live_response=_response(),
        candidate_response=_response(),
    )
    kwargs.update(overrides)
    return evaluate_promotion_decision(**kwargs)


# ---------------------------------------------------------------------------
# 1. Skipped when promotion disabled.
# ---------------------------------------------------------------------------


def test_skipped_when_promotion_disabled() -> None:
    decision = _evaluate(settings=_DISABLED)
    assert decision.status == "skipped"
    assert decision.promoted is False


def test_skipped_when_enabled_but_mode_off() -> None:
    decision = _evaluate(settings=_ENABLED_BUT_MODE_OFF)
    assert decision.status == "skipped"
    assert decision.promoted is False


# ---------------------------------------------------------------------------
# 2. Skipped in shadow_only mode.
# ---------------------------------------------------------------------------


def test_skipped_in_shadow_only_mode() -> None:
    decision = _evaluate(settings=_SHADOW_ONLY)
    assert decision.status == "skipped"
    assert decision.promoted is False


# ---------------------------------------------------------------------------
# 3. Blocked for general_academic_workflow; course_question_workflow and
# requirement_explanation_workflow are eligible (widened this cycle
# alongside graduation_progress_workflow -- see
# `supervisor.promotion._HARD_ALLOWED_PROMOTION_WORKFLOWS`).
# general_academic_workflow stays excluded: its shadow execution is always
# the dry-run stand-in by default (operationally expensive), so it could
# never produce a real, promotable candidate.
# ---------------------------------------------------------------------------


def test_blocked_for_general_academic_workflow() -> None:
    decision = _evaluate(settings=_PROMOTE_VALIDATED, workflow_name="general_academic_workflow")
    assert decision.status == "blocked"
    assert decision.promoted is False
    assert any(r.code == "workflow_not_eligible_for_promotion" for r in decision.reasons)


def test_not_blocked_for_eligibility_for_newly_widened_read_only_workflows() -> None:
    for name in ("course_question_workflow", "requirement_explanation_workflow"):
        decision = _evaluate(
            settings=_PROMOTE_VALIDATED,
            workflow_name=name,
            supervisor_output_summary=_supervisor_output(capabilities=[name]),
        )
        assert decision.status == "promoted", name
        assert decision.promoted is True
        assert not any(r.code == "workflow_not_eligible_for_promotion" for r in decision.reasons)


def test_blocked_for_transcript_import_workflow() -> None:
    decision = _evaluate(settings=_PROMOTE_VALIDATED, workflow_name="transcript_import_workflow")
    assert decision.status == "blocked"
    assert any(r.code == "workflow_not_eligible_for_promotion" for r in decision.reasons)


def test_blocked_for_semester_planning_workflow() -> None:
    decision = _evaluate(settings=_PROMOTE_VALIDATED, workflow_name="semester_planning_workflow")
    assert decision.status == "blocked"
    assert any(r.code == "workflow_not_eligible_for_promotion" for r in decision.reasons)


# ---------------------------------------------------------------------------
# 4. Blocked when validation missing.
# ---------------------------------------------------------------------------


def test_blocked_when_validation_missing() -> None:
    decision = _evaluate(settings=_PROMOTE_VALIDATED, supervisor_validation=None)
    assert decision.status == "blocked"
    assert any(r.code == "validation_missing" for r in decision.reasons)


# ---------------------------------------------------------------------------
# 5. Blocked when validation failed.
# ---------------------------------------------------------------------------


def test_blocked_when_validation_failed() -> None:
    decision = _evaluate(settings=_PROMOTE_VALIDATED, supervisor_validation=_validation(status="failed", safeToPromote=False))
    assert decision.status == "blocked"
    codes = [r.code for r in decision.reasons]
    assert "validation_not_passed" in codes
    assert "validation_not_safe_to_promote" in codes


# ---------------------------------------------------------------------------
# 6. Blocked when validation passed_with_warnings.
# ---------------------------------------------------------------------------


def test_blocked_when_validation_passed_with_warnings() -> None:
    decision = _evaluate(
        settings=_PROMOTE_VALIDATED, supervisor_validation=_validation(status="passed_with_warnings", safeToPromote=False)
    )
    assert decision.status == "blocked"
    assert any(r.code == "validation_not_passed" for r in decision.reasons)


# ---------------------------------------------------------------------------
# 7. Blocked when live proposed actions exist.
# ---------------------------------------------------------------------------


def test_blocked_when_live_proposed_actions_exist() -> None:
    decision = _evaluate(settings=_PROMOTE_VALIDATED, live_response_summary=_live_summary(proposedActionCount=1))
    assert decision.status == "blocked"
    assert any(r.code == "live_response_has_proposed_actions" for r in decision.reasons)


# ---------------------------------------------------------------------------
# 8. Blocked when candidate proposed actions exist.
# ---------------------------------------------------------------------------


def test_blocked_when_candidate_proposed_actions_exist() -> None:
    candidate = _response(
        proposed_actions=[ProposedAction(id="a1", action_type="save_semester_plan", label="Save", title="Save")]
    )
    decision = _evaluate(
        settings=_PROMOTE_VALIDATED,
        candidate_response_summary=_candidate_summary(proposedActionCount=1),
        candidate_response=candidate,
    )
    assert decision.status == "blocked"
    codes = [r.code for r in decision.reasons]
    assert "candidate_response_has_proposed_actions" in codes
    assert "candidate_has_proposed_actions" in codes


# ---------------------------------------------------------------------------
# 9. Blocked when block types differ.
# ---------------------------------------------------------------------------


def test_blocked_when_block_types_differ() -> None:
    decision = _evaluate(settings=_PROMOTE_VALIDATED, candidate_response_summary=_candidate_summary(blockTypes=["Other"]))
    assert decision.status == "blocked"
    assert any(r.code == "block_types_mismatch" for r in decision.reasons)


# ---------------------------------------------------------------------------
# 10. Blocked when block counts differ.
# ---------------------------------------------------------------------------


def test_blocked_when_block_counts_differ() -> None:
    decision = _evaluate(settings=_PROMOTE_VALIDATED, candidate_response_summary=_candidate_summary(blockCount=3))
    assert decision.status == "blocked"
    assert any(r.code == "block_count_mismatch" for r in decision.reasons)


# ---------------------------------------------------------------------------
# 11. Blocked when unsafe capabilities attempted.
# ---------------------------------------------------------------------------


def test_blocked_when_unsafe_capabilities_attempted() -> None:
    validation = _validation(
        issues=[{"code": "unsafe_capability_shadow_execution_detected", "severity": "error"}], status="failed", safeToPromote=False
    )
    decision = _evaluate(settings=_PROMOTE_VALIDATED, supervisor_validation=validation)
    assert decision.status == "blocked"
    assert any(r.code == "unsafe_capability_attempted" for r in decision.reasons)


def test_blocked_when_write_or_proposal_capability_in_execution_path() -> None:
    decision = _evaluate(
        settings=_PROMOTE_VALIDATED,
        supervisor_output_summary=_supervisor_output(
            capabilities=["graduation_progress_workflow", "semester_planning_workflow"]
        ),
    )
    assert decision.status == "blocked"
    assert any(r.code == "write_or_proposal_capability_in_path" for r in decision.reasons)


def test_blocked_when_supervisor_subtask_failed() -> None:
    decision = _evaluate(settings=_PROMOTE_VALIDATED, supervisor_output_summary=_supervisor_output(failedSubtasks=["s1"]))
    assert decision.status == "blocked"
    assert any(r.code == "supervisor_subtask_failed" for r in decision.reasons)


def test_blocked_when_supervisor_output_missing() -> None:
    decision = _evaluate(settings=_PROMOTE_VALIDATED, supervisor_output_summary=None)
    assert decision.status == "blocked"
    assert any(r.code == "supervisor_output_missing" for r in decision.reasons)


def test_blocked_when_candidate_summary_missing() -> None:
    decision = _evaluate(settings=_PROMOTE_VALIDATED, candidate_response_summary=None)
    assert decision.status == "blocked"
    assert any(r.code == "candidate_response_summary_missing" for r in decision.reasons)


def test_blocked_when_forbidden_diagnostic_key_present() -> None:
    decision = _evaluate(settings=_PROMOTE_VALIDATED, live_response_summary=_live_summary(raw_context={"x": 1}))
    assert decision.status == "blocked"
    assert any(r.code == "forbidden_diagnostic_payload_detected" for r in decision.reasons)


# ---------------------------------------------------------------------------
# 12. Promoted only when every strict condition passes.
# ---------------------------------------------------------------------------


def test_promoted_only_when_every_strict_condition_passes() -> None:
    decision = _evaluate(settings=_PROMOTE_VALIDATED)
    assert decision.status == "promoted"
    assert decision.promoted is True
    assert decision.reasons == []
    assert decision.workflow_name == "graduation_progress_workflow"
    assert decision.mode == "promote_validated"


def test_not_promoted_if_a_single_gate_fails() -> None:
    decision = _evaluate(settings=_PROMOTE_VALIDATED, live_response_summary=_live_summary(proposedActionCount=1))
    assert decision.status == "blocked"
    assert decision.promoted is False


# ---------------------------------------------------------------------------
# 13. Never raises on malformed inputs.
# ---------------------------------------------------------------------------


def test_never_raises_on_malformed_inputs() -> None:
    decision = evaluate_promotion_decision(
        workflow_name="graduation_progress_workflow",
        live_response_summary=None,  # type: ignore[arg-type]
        candidate_response_summary="not-a-dict",  # type: ignore[arg-type]
        supervisor_validation=12345,  # type: ignore[arg-type]
        supervisor_output_summary=object(),  # type: ignore[arg-type]
        settings=_PROMOTE_VALIDATED,
    )
    assert decision.status in ("blocked", "failed")
    assert decision.promoted is False


def test_never_raises_with_completely_wrong_settings_type() -> None:
    class _NotSettings:
        pass

    decision = evaluate_promotion_decision(
        workflow_name="graduation_progress_workflow",
        live_response_summary=_live_summary(),
        candidate_response_summary=_candidate_summary(),
        supervisor_validation=_validation(),
        supervisor_output_summary=_supervisor_output(),
        settings=_NotSettings(),  # type: ignore[arg-type]
    )
    assert decision.status == "failed"
    assert decision.promoted is False


# ---------------------------------------------------------------------------
# 14 & 15. Diagnostics are compact and contain no raw text/blocks/context/
# action payloads.
# ---------------------------------------------------------------------------


def test_decision_diagnostics_are_compact() -> None:
    decision = _evaluate(settings=_PROMOTE_VALIDATED, candidate_response_summary=_candidate_summary(blockTypes=["Other"]))
    dumped = decision.model_dump()
    assert set(dumped) == {"status", "promoted", "workflow_name", "mode", "reasons", "diagnostics"}
    for reason in dumped["reasons"]:
        assert set(reason) == {"code", "message", "severity", "details"}


def test_decision_never_contains_raw_payloads() -> None:
    long_text = "sensitive text " * 300
    live = _response(text=long_text)
    decision = _evaluate(settings=_PROMOTE_VALIDATED, live_response=live, candidate_response=live)

    decision_text = str(decision.model_dump())
    assert long_text not in decision_text
    for forbidden in ("chain_of_thought", "scratchpad", "raw_context", "proposed_action_payload"):
        assert forbidden not in decision_text
