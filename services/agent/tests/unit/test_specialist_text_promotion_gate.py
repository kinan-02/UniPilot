"""Unit tests for `app.agent.specialists.text_promotion.evaluate_specialist_text_promotion` (Phase 14)."""

from __future__ import annotations

from typing import Any

from app.agent.specialists.text_promotion import eligible_text_promotion_agents, evaluate_specialist_text_promotion
from app.config import Settings

_WORKFLOW = "graduation_progress_workflow"
_AGENT = "graduation_progress_agent"

_ENABLED_KWARGS: dict[str, Any] = {
    "AGENT_SPECIALIST_TEXT_PROMOTION_ENABLED": True,
    "AGENT_SPECIALIST_TEXT_PROMOTION_MODE": "promote_validated",
    # Explicit, not relied-on-default: an operator's real `.env` may have the
    # runtime readiness gate on (as this repo's own root `.env` does,
    # post-Phase-9) with no `specialist_text_promotion.*` manifest entry --
    # this file tests the strict-gate logic itself, not the readiness gate.
    "AGENT_RUNTIME_READINESS_GATE_ENABLED": False,
}


def _settings(**overrides: Any) -> Settings:
    kwargs = {**_ENABLED_KWARGS, **overrides}
    return Settings(**kwargs)


def _live_summary(**overrides: Any) -> dict[str, Any]:
    defaults = dict(blockCount=2, proposedActionCount=0)
    defaults.update(overrides)
    return defaults


def _validation(**overrides: Any) -> dict[str, Any]:
    defaults = dict(status="passed", safeToConsider=True)
    defaults.update(overrides)
    return defaults


def _comparison(**overrides: Any) -> dict[str, Any]:
    defaults = dict(
        workflowName=_WORKFLOW, specialistAgentName=_AGENT, comparable=True, safeMatch=True
    )
    defaults.update(overrides)
    return defaults


def _output_summary(**overrides: Any) -> dict[str, Any]:
    defaults = dict(
        status="completed",
        confidence=0.9,
        missingContextCount=0,
        hasProposedActions=False,
        toolLoopStatus=None,
        rejectedObservationCount=0,
    )
    defaults.update(overrides)
    return defaults


def _evaluate(**overrides: Any):
    defaults: dict[str, Any] = dict(
        workflow_name=_WORKFLOW,
        specialist_agent_name=_AGENT,
        live_response_summary=_live_summary(),
        specialist_validation_metadata=_validation(),
        specialist_comparison_metadata=_comparison(),
        specialist_output_summary=_output_summary(),
        answer_text="You still need 40 more credits to graduate. Focus on your remaining core courses.",
        workflow_promotion_already_promoted=False,
        settings=_settings(),
    )
    defaults.update(overrides)
    return evaluate_specialist_text_promotion(**defaults)


# ---------------------------------------------------------------------------
# 1. Skipped when promotion disabled.
# ---------------------------------------------------------------------------


def test_skipped_when_promotion_disabled() -> None:
    decision = _evaluate(settings=_settings(AGENT_SPECIALIST_TEXT_PROMOTION_ENABLED=False))

    assert decision.status == "skipped"
    assert decision.promoted is False
    assert decision.mode == "off"


# ---------------------------------------------------------------------------
# 2. Skipped in shadow_only mode.
# ---------------------------------------------------------------------------


def test_skipped_in_shadow_only_mode() -> None:
    decision = _evaluate(settings=_settings(AGENT_SPECIALIST_TEXT_PROMOTION_MODE="shadow_only"))

    assert decision.status == "skipped"
    assert decision.promoted is False
    assert decision.mode == "shadow_only"


# ---------------------------------------------------------------------------
# 3. Blocked when workflow promotion already promoted.
# ---------------------------------------------------------------------------


def test_blocked_when_workflow_promotion_already_promoted() -> None:
    decision = _evaluate(workflow_promotion_already_promoted=True)

    assert decision.status == "blocked"
    assert decision.promoted is False
    assert any(r.code == "workflow_promotion_already_selected_response" for r in decision.reasons)


# ---------------------------------------------------------------------------
# 4. Blocked for non-graduation workflow.
# ---------------------------------------------------------------------------


def test_blocked_for_non_graduation_workflow() -> None:
    decision = _evaluate(workflow_name="course_question_workflow")

    assert decision.status == "blocked"
    assert any(r.code == "workflow_not_eligible_for_text_promotion" for r in decision.reasons)


# ---------------------------------------------------------------------------
# 5. Blocked for non-graduation specialist.
# ---------------------------------------------------------------------------


def test_blocked_for_non_graduation_specialist() -> None:
    decision = _evaluate(specialist_agent_name="course_catalog_agent")

    assert decision.status == "blocked"
    assert any(r.code == "specialist_not_eligible_for_text_promotion" for r in decision.reasons)


# ---------------------------------------------------------------------------
# 6. Blocked when specialist validation missing.
# ---------------------------------------------------------------------------


def test_blocked_when_specialist_validation_missing() -> None:
    decision = _evaluate(specialist_validation_metadata=None)

    assert decision.status == "blocked"
    assert any(r.code == "specialist_validation_missing" for r in decision.reasons)


# ---------------------------------------------------------------------------
# 7. Blocked when validation failed.
# ---------------------------------------------------------------------------


def test_blocked_when_validation_failed() -> None:
    decision = _evaluate(specialist_validation_metadata=_validation(status="failed"))

    assert decision.status == "blocked"
    assert any(r.code == "specialist_validation_not_passed" for r in decision.reasons)


# ---------------------------------------------------------------------------
# 8. Blocked when safeToConsider=false.
# ---------------------------------------------------------------------------


def test_blocked_when_safe_to_consider_false() -> None:
    decision = _evaluate(specialist_validation_metadata=_validation(safeToConsider=False))

    assert decision.status == "blocked"
    assert any(r.code == "specialist_validation_not_safe_to_consider" for r in decision.reasons)


# ---------------------------------------------------------------------------
# 9. Blocked when comparison missing.
# ---------------------------------------------------------------------------


def test_blocked_when_comparison_missing() -> None:
    decision = _evaluate(specialist_comparison_metadata=None)

    assert decision.status == "blocked"
    assert any(r.code == "specialist_comparison_missing" for r in decision.reasons)


# ---------------------------------------------------------------------------
# 10. Blocked when comparison safeMatch=false.
# ---------------------------------------------------------------------------


def test_blocked_when_comparison_safe_match_false() -> None:
    decision = _evaluate(specialist_comparison_metadata=_comparison(safeMatch=False))

    assert decision.status == "blocked"
    assert any(r.code == "specialist_comparison_not_safe_match" for r in decision.reasons)


def test_blocked_when_comparison_not_comparable() -> None:
    decision = _evaluate(specialist_comparison_metadata=_comparison(comparable=False))

    assert decision.status == "blocked"
    assert any(r.code == "specialist_comparison_not_comparable" for r in decision.reasons)


# ---------------------------------------------------------------------------
# 11. Blocked when specialist confidence < 0.85.
# ---------------------------------------------------------------------------


def test_blocked_when_confidence_too_low() -> None:
    decision = _evaluate(specialist_output_summary=_output_summary(confidence=0.5))

    assert decision.status == "blocked"
    assert any(r.code == "specialist_confidence_too_low" for r in decision.reasons)


def test_promoted_when_confidence_exactly_at_threshold() -> None:
    decision = _evaluate(specialist_output_summary=_output_summary(confidence=0.85))

    assert decision.status == "promoted"


# ---------------------------------------------------------------------------
# 12. Blocked when specialist has missing context.
# ---------------------------------------------------------------------------


def test_blocked_when_missing_context_present() -> None:
    decision = _evaluate(specialist_output_summary=_output_summary(missingContextCount=2))

    assert decision.status == "blocked"
    assert any(r.code == "specialist_missing_context_present" for r in decision.reasons)


# ---------------------------------------------------------------------------
# 13. Blocked when specialist has proposed actions.
# ---------------------------------------------------------------------------


def test_blocked_when_specialist_has_proposed_actions() -> None:
    decision = _evaluate(specialist_output_summary=_output_summary(hasProposedActions=True))

    assert decision.status == "blocked"
    assert any(r.code == "specialist_has_proposed_actions" for r in decision.reasons)


# ---------------------------------------------------------------------------
# 14. Blocked when tool loop budget exceeded.
# ---------------------------------------------------------------------------


def test_blocked_when_tool_loop_budget_exceeded() -> None:
    decision = _evaluate(specialist_output_summary=_output_summary(toolLoopStatus="budget_exceeded"))

    assert decision.status == "blocked"
    assert any(r.code == "specialist_tool_loop_budget_exceeded" for r in decision.reasons)


def test_blocked_when_specialist_has_rejected_tool_requests() -> None:
    decision = _evaluate(specialist_output_summary=_output_summary(rejectedObservationCount=2))

    assert decision.status == "blocked"
    assert any(r.code == "specialist_has_rejected_tool_requests" for r in decision.reasons)


# ---------------------------------------------------------------------------
# 15. Blocked when answer_text missing.
# ---------------------------------------------------------------------------


def test_blocked_when_answer_text_missing() -> None:
    decision = _evaluate(answer_text=None)

    assert decision.status == "blocked"
    assert any(r.code == "specialist_answer_text_missing_or_invalid" for r in decision.reasons)


def test_blocked_when_answer_text_empty_string() -> None:
    decision = _evaluate(answer_text="   ")

    assert decision.status == "blocked"
    assert any(r.code == "specialist_answer_text_missing_or_invalid" for r in decision.reasons)


# ---------------------------------------------------------------------------
# 16. Blocked when answer_text unsafe.
# ---------------------------------------------------------------------------


def test_blocked_when_answer_text_unsafe() -> None:
    decision = _evaluate(answer_text="I updated your profile and saved the changes.")

    assert decision.status == "blocked"
    assert any(r.code == "specialist_answer_text_write_claim" for r in decision.reasons)


def test_blocked_when_answer_text_too_long() -> None:
    decision = _evaluate(answer_text="x" * 5000, settings=_settings(AGENT_SPECIALIST_TEXT_PROMOTION_MAX_CHARS=4000))

    assert decision.status == "blocked"
    assert any(r.code == "specialist_answer_text_too_long" for r in decision.reasons)


# ---------------------------------------------------------------------------
# 17. Blocked when live response has proposed actions.
# ---------------------------------------------------------------------------


def test_blocked_when_live_response_has_proposed_actions() -> None:
    decision = _evaluate(live_response_summary=_live_summary(proposedActionCount=1))

    assert decision.status == "blocked"
    assert any(r.code == "live_response_has_proposed_actions" for r in decision.reasons)


def test_blocked_when_live_response_has_no_blocks() -> None:
    decision = _evaluate(live_response_summary=_live_summary(blockCount=0))

    assert decision.status == "blocked"
    assert any(r.code == "live_response_has_no_blocks" for r in decision.reasons)


# ---------------------------------------------------------------------------
# 18. Promoted only when every strict gate passes.
# ---------------------------------------------------------------------------


def test_promoted_only_when_every_strict_gate_passes() -> None:
    decision = _evaluate()

    assert decision.status == "promoted"
    assert decision.promoted is True
    assert decision.reasons == []
    assert decision.workflow_name == _WORKFLOW
    assert decision.specialist_agent_name == _AGENT
    assert decision.mode == "promote_validated"


# ---------------------------------------------------------------------------
# 19. Never raises on malformed metadata.
# ---------------------------------------------------------------------------


def test_never_raises_on_malformed_metadata() -> None:
    decision = evaluate_specialist_text_promotion(
        workflow_name=_WORKFLOW,  # type: ignore[arg-type]
        specialist_agent_name=123,  # type: ignore[arg-type]
        live_response_summary="not_a_dict",  # type: ignore[arg-type]
        specialist_validation_metadata="also_not_a_dict",  # type: ignore[arg-type]
        specialist_comparison_metadata=["not", "a", "dict"],  # type: ignore[arg-type]
        specialist_output_summary=object(),  # type: ignore[arg-type]
        answer_text=12345,  # type: ignore[arg-type]
        workflow_promotion_already_promoted=False,
        settings=_settings(),
    )

    assert decision.status in ("blocked", "failed")
    assert decision.promoted is False


def test_never_raises_with_none_settings_like_object() -> None:
    class _BrokenSettings:
        def is_agent_specialist_text_promotion_enabled(self) -> bool:
            raise RuntimeError("boom")

    decision = evaluate_specialist_text_promotion(
        workflow_name=_WORKFLOW,
        specialist_agent_name=_AGENT,
        live_response_summary=_live_summary(),
        specialist_validation_metadata=_validation(),
        specialist_comparison_metadata=_comparison(),
        specialist_output_summary=_output_summary(),
        answer_text="test",
        workflow_promotion_already_promoted=False,
        settings=_BrokenSettings(),  # type: ignore[arg-type]
    )

    assert decision.status == "failed"
    assert decision.promoted is False


# ---------------------------------------------------------------------------
# 20. Hardcoded eligibility ceiling ignores misconfigured extra agents.
# ---------------------------------------------------------------------------


def test_hardcoded_eligibility_ceiling_ignores_misconfigured_extra_agents() -> None:
    settings = _settings(
        AGENT_SPECIALIST_TEXT_PROMOTION_AGENTS="graduation_progress_agent,course_catalog_agent,requirement_explanation_agent"
    )

    eligible = eligible_text_promotion_agents(settings)

    assert eligible == {_AGENT}


def test_hardcoded_eligibility_ceiling_empty_when_misconfigured_to_only_other_agents() -> None:
    settings = _settings(AGENT_SPECIALIST_TEXT_PROMOTION_AGENTS="course_catalog_agent")

    eligible = eligible_text_promotion_agents(settings)

    assert eligible == set()

    decision = _evaluate(settings=settings)
    assert decision.status == "blocked"
    assert any(r.code == "specialist_not_eligible_for_text_promotion" for r in decision.reasons)


# ---------------------------------------------------------------------------
# Additional: no chain-of-thought fields on the decision model.
# ---------------------------------------------------------------------------


def test_decision_never_exposes_chain_of_thought_fields() -> None:
    decision = _evaluate()
    dumped_text = str(decision.model_dump())
    for forbidden in ("chain_of_thought", "hidden_reasoning", "private_reasoning", "scratchpad", "thoughts"):
        assert forbidden not in dumped_text
