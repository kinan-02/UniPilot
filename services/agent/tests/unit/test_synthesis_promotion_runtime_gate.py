"""Unit tests for synthesis promotion runtime readiness gate (Phase 25)."""

from __future__ import annotations

from pathlib import Path
from typing import Any

from app.agent.schemas import AgentResponse, ProposedAction, StructuredBlock
from app.agent.synthesis.promotion_policy import evaluate_synthesis_text_promotion
from app.agent.synthesis.schemas import SynthesisOutput
from app.config import Settings

_WORKFLOW = "course_question_workflow"
_MANIFEST = Path(__file__).resolve().parents[1] / "fixtures" / "promotion_readiness_manifest.test.json"

_BASE = {
    "AGENT_SYNTHESIS_ENABLED": True,
    "AGENT_SYNTHESIS_TEXT_PROMOTION_ENABLED": True,
    "AGENT_SYNTHESIS_TEXT_PROMOTION_MODE": "promote_validated",
    "AGENT_SYNTHESIS_TEXT_PROMOTION_WORKFLOWS": _WORKFLOW,
}


def _settings(**overrides: Any) -> Settings:
    return Settings(**{**_BASE, **overrides})


def _live() -> AgentResponse:
    return AgentResponse(
        conversation_id="c1",
        message_id="m1",
        run_id="r1",
        text="Live answer.",
        blocks=[StructuredBlock(type="CourseInfoBlock", data={"course": "B"})],
        warnings=[],
        proposed_actions=[],
        used_sources=["catalog"],
    )


def _synthesis() -> SynthesisOutput:
    return SynthesisOutput(
        status="candidate_ready",
        synthesis_id="syn-1",
        decision_summary="ready",
        candidate_answer_text="Synthesized course answer with enough detail.",
        safe_to_show=True,
        safe_to_promote=True,
        confidence=0.92,
    )


def _metadata() -> dict[str, Any]:
    return {
        "monitorDiagnostics": {"status": "passed", "decision": {"action": "continue"}},
        "planRepairDiagnostics": {"modeUsed": "continue"},
        "clarificationDiagnostics": {"questions": []},
        "clarificationState": {"status": "resolved"},
    }


def test_gate_disabled_preserves_phase_22_behavior() -> None:
    decision = evaluate_synthesis_text_promotion(
        workflow_name=_WORKFLOW,
        live_response=_live(),
        synthesis_output=_synthesis(),
        retrieval_metadata=_metadata(),
        settings=_settings(AGENT_RUNTIME_READINESS_GATE_ENABLED=False),
    )
    assert decision.promoted is True


def test_gate_enabled_missing_manifest_blocks() -> None:
    decision = evaluate_synthesis_text_promotion(
        workflow_name=_WORKFLOW,
        live_response=_live(),
        synthesis_output=_synthesis(),
        retrieval_metadata=_metadata(),
        settings=_settings(
            AGENT_RUNTIME_READINESS_GATE_ENABLED=True,
            AGENT_RUNTIME_READINESS_MANIFEST_PATH="",
            AGENT_RUNTIME_READINESS_FAIL_CLOSED=True,
        ),
    )
    assert decision.promoted is False
    assert any(reason.code == "runtime_readiness_gate_blocked" for reason in decision.reasons)


def test_gate_enabled_with_approval_allows_when_other_gates_pass() -> None:
    decision = evaluate_synthesis_text_promotion(
        workflow_name=_WORKFLOW,
        live_response=_live(),
        synthesis_output=_synthesis(),
        retrieval_metadata=_metadata(),
        settings=_settings(
            AGENT_RUNTIME_READINESS_GATE_ENABLED=True,
            AGENT_RUNTIME_READINESS_MANIFEST_PATH=str(_MANIFEST),
        ),
    )
    assert decision.promoted is True
    assert decision.diagnostics.get("runtimeReadiness", {}).get("allowed") is True


def test_gate_enabled_low_level_blocks(tmp_path: Path) -> None:
    manifest = tmp_path / "low_level.json"
    manifest.write_text(
        """
{
  "schemaVersion": "1",
  "reviewedAt": "2026-07-06T00:00:00Z",
  "reviewedBy": "human",
  "candidates": [
    {
      "candidateId": "synthesis_text_promotion.course_question_workflow",
      "level": "ready_for_shadow",
      "approved": true,
      "scope": ["course_question_workflow"]
    }
  ]
}
""".strip(),
        encoding="utf-8",
    )
    decision = evaluate_synthesis_text_promotion(
        workflow_name=_WORKFLOW,
        live_response=_live(),
        synthesis_output=_synthesis(),
        retrieval_metadata=_metadata(),
        settings=_settings(
            AGENT_RUNTIME_READINESS_GATE_ENABLED=True,
            AGENT_RUNTIME_READINESS_MANIFEST_PATH=str(manifest),
        ),
    )
    assert decision.promoted is False


def test_gate_enabled_scope_mismatch_blocks(tmp_path: Path) -> None:
    manifest = tmp_path / "scope.json"
    manifest.write_text(
        """
{
  "schemaVersion": "1",
  "reviewedAt": "2026-07-06T00:00:00Z",
  "reviewedBy": "human",
  "candidates": [
    {
      "candidateId": "synthesis_text_promotion.course_question_workflow",
      "level": "ready_for_limited_promotion",
      "approved": true,
      "scope": ["graduation_progress_workflow"]
    }
  ]
}
""".strip(),
        encoding="utf-8",
    )
    decision = evaluate_synthesis_text_promotion(
        workflow_name=_WORKFLOW,
        live_response=_live(),
        synthesis_output=_synthesis(),
        retrieval_metadata=_metadata(),
        settings=_settings(
            AGENT_RUNTIME_READINESS_GATE_ENABLED=True,
            AGENT_RUNTIME_READINESS_MANIFEST_PATH=str(manifest),
        ),
    )
    assert decision.promoted is False


def test_runtime_gate_reason_in_diagnostics() -> None:
    decision = evaluate_synthesis_text_promotion(
        workflow_name=_WORKFLOW,
        live_response=_live(),
        synthesis_output=_synthesis(),
        retrieval_metadata=_metadata(),
        settings=_settings(
            AGENT_RUNTIME_READINESS_GATE_ENABLED=True,
            AGENT_RUNTIME_READINESS_MANIFEST_PATH="",
        ),
    )
    from app.agent.synthesis.promotion_diagnostics import build_synthesis_promotion_metadata

    metadata = build_synthesis_promotion_metadata(decision)
    assert "runtimeReadiness" in metadata


def test_existing_phase_22_gates_still_block_even_when_readiness_allows() -> None:
    decision = evaluate_synthesis_text_promotion(
        workflow_name=_WORKFLOW,
        live_response=_live().model_copy(
            update={"proposed_actions": [ProposedAction(id="a1", label="Save", action_type="save_plan")]}
        ),
        synthesis_output=_synthesis(),
        retrieval_metadata=_metadata(),
        settings=_settings(
            AGENT_RUNTIME_READINESS_GATE_ENABLED=True,
            AGENT_RUNTIME_READINESS_MANIFEST_PATH=str(_MANIFEST),
        ),
    )
    assert decision.promoted is False
    assert any(reason.code == "live_response_has_proposed_actions" for reason in decision.reasons)
