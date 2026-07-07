"""Unit tests for synthesis text promotion policy (Phase 22)."""

from __future__ import annotations

from typing import Any

from app.agent.schemas import AgentResponse, StructuredBlock
from app.agent.synthesis.promotion_policy import evaluate_synthesis_text_promotion
from app.agent.synthesis.schemas import SynthesisOutput
from app.config import Settings

_WORKFLOW = "graduation_progress_workflow"

_BASE = {
    "AGENT_SYNTHESIS_ENABLED": True,
    "AGENT_SYNTHESIS_TEXT_PROMOTION_ENABLED": True,
    "AGENT_SYNTHESIS_TEXT_PROMOTION_MODE": "promote_validated",
}


def _settings(**overrides: Any) -> Settings:
    return Settings(**{**_BASE, **overrides})


def _live(**overrides: Any) -> AgentResponse:
    defaults = dict(
        conversation_id="c1",
        message_id="m1",
        run_id="r1",
        text="Live deterministic answer.",
        blocks=[StructuredBlock(type="GraduationStatusBlock", data={"creditsRemaining": 40.0})],
        warnings=["warn"],
        proposed_actions=[],
        used_sources=["catalog"],
    )
    defaults.update(overrides)
    return AgentResponse(**defaults)


def _synthesis(**overrides: Any) -> SynthesisOutput:
    defaults = dict(
        status="candidate_ready",
        synthesis_id="syn-1",
        decision_summary="ready",
        candidate_answer_text="Synthesis candidate answer with enough detail.",
        safe_to_show=True,
        safe_to_promote=True,
        confidence=0.9,
    )
    defaults.update(overrides)
    return SynthesisOutput(**defaults)


def _metadata(**overrides: Any) -> dict[str, Any]:
    defaults: dict[str, Any] = {
        "monitorDiagnostics": {"status": "passed", "decision": {"action": "continue"}},
        "planRepairDiagnostics": {"modeUsed": "continue"},
        "clarificationDiagnostics": {"questions": []},
        "clarificationState": {"status": "resolved"},
    }
    defaults.update(overrides)
    return defaults


def _evaluate(**overrides: Any):
    defaults: dict[str, Any] = dict(
        workflow_name=_WORKFLOW,
        live_response=_live(),
        synthesis_output=_synthesis(),
        retrieval_metadata=_metadata(),
        settings=_settings(),
        existing_promotion_already_applied=False,
        workflow_promotion_already_applied=False,
        specialist_text_promotion_already_applied=False,
    )
    defaults.update(overrides)
    return evaluate_synthesis_text_promotion(**defaults)


def test_disabled_flag_skips() -> None:
    decision = _evaluate(settings=_settings(AGENT_SYNTHESIS_TEXT_PROMOTION_ENABLED=False))
    assert decision.status == "skipped"


def test_off_mode_skips() -> None:
    decision = _evaluate(settings=_settings(AGENT_SYNTHESIS_TEXT_PROMOTION_MODE="off"))
    assert decision.status == "skipped"


def test_shadow_only_evaluates_but_does_not_promote() -> None:
    decision = _evaluate(settings=_settings(AGENT_SYNTHESIS_TEXT_PROMOTION_MODE="shadow_only"))
    assert decision.promoted is False
    assert decision.diagnostics.get("wouldPromote") is True


def test_promote_validated_promotes_when_all_gates_pass() -> None:
    decision = _evaluate()
    assert decision.status == "promoted"
    assert decision.promoted is True


def test_blocks_when_workflow_not_allowlisted() -> None:
    decision = _evaluate(workflow_name="transcript_import_workflow")
    assert decision.promoted is False


def test_blocks_when_live_response_has_proposed_actions() -> None:
    from app.agent.schemas import ProposedAction

    action = ProposedAction(id="a1", action_type="import_transcript", label="Import", payload={})
    decision = _evaluate(live_response=_live(proposed_actions=[action]))
    assert decision.promoted is False


def test_blocks_when_live_response_has_no_blocks_and_require_blocks_true() -> None:
    decision = _evaluate(live_response=_live(blocks=[]))
    assert decision.promoted is False


def test_blocks_when_synthesis_output_missing() -> None:
    decision = _evaluate(synthesis_output=None)
    assert decision.promoted is False


def test_blocks_when_synthesis_candidate_missing() -> None:
    decision = _evaluate(synthesis_output=_synthesis(candidate_answer_text=None))
    assert decision.promoted is False


def test_blocks_when_synthesis_status_unsafe() -> None:
    decision = _evaluate(synthesis_output=_synthesis(status="unsafe"))
    assert decision.promoted is False


def test_blocks_when_safe_to_show_false() -> None:
    decision = _evaluate(synthesis_output=_synthesis(safe_to_show=False))
    assert decision.promoted is False


def test_blocks_when_confidence_too_low() -> None:
    decision = _evaluate(synthesis_output=_synthesis(confidence=0.5))
    assert decision.promoted is False


def test_blocks_when_candidate_safety_fails() -> None:
    decision = _evaluate(synthesis_output=_synthesis(candidate_answer_text="I saved your profile."))
    assert decision.promoted is False


def test_blocks_on_unresolved_error_conflict() -> None:
    from app.agent.synthesis.schemas import SynthesisConflict

    decision = _evaluate(
        synthesis_output=_synthesis(
            conflicts=[SynthesisConflict(id="c1", severity="error", summary="bad", resolution="unresolved")]
        )
    )
    assert decision.promoted is False


def test_blocks_on_monitor_unsafe_output() -> None:
    decision = _evaluate(
        retrieval_metadata=_metadata(
            monitorDiagnostics={"decision": {"action": "abort_safely"}, "signals": [{"kind": "unsafe_output"}]}
        )
    )
    assert decision.promoted is False


def test_blocks_on_monitor_abort_safely() -> None:
    decision = _evaluate(
        retrieval_metadata=_metadata(monitorDiagnostics={"decision": {"action": "abort_safely"}})
    )
    assert decision.promoted is False


def test_blocks_on_plan_repair_regenerate() -> None:
    decision = _evaluate(retrieval_metadata=_metadata(planRepairDiagnostics={"modeUsed": "regenerate"}))
    assert decision.promoted is False


def test_blocks_on_unresolved_clarification_state() -> None:
    decision = _evaluate(
        retrieval_metadata=_metadata(
            clarificationState={"status": "pending"},
            clarificationDiagnostics={
                "questions": [{"ambiguityType": "preference", "consequence": "high", "optionCount": 2}]
            },
        )
    )
    assert decision.promoted is False


def test_blocks_if_workflow_promotion_already_applied() -> None:
    decision = _evaluate(workflow_promotion_already_applied=True)
    assert decision.promoted is False


def test_blocks_if_specialist_text_promotion_already_applied() -> None:
    decision = _evaluate(specialist_text_promotion_already_applied=True)
    assert decision.promoted is False


def test_never_raises_on_malformed_metadata() -> None:
    decision = _evaluate(retrieval_metadata="bad")  # type: ignore[arg-type]
    assert decision.status in {"blocked", "skipped", "failed", "promoted"}
