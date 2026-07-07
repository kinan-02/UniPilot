"""Integration tests for runtime readiness gate wiring (Phase 25)."""

from __future__ import annotations

from pathlib import Path

from app.agent.schemas import AgentResponse, StructuredBlock
from app.agent.synthesis.promotion_diagnostics import build_synthesis_promotion_metadata
from app.agent.synthesis.promotion_policy import evaluate_synthesis_text_promotion
from app.agent.synthesis.schemas import SynthesisOutput
from app.config import Settings

_MANIFEST = Path(__file__).resolve().parents[1] / "fixtures" / "promotion_readiness_manifest.test.json"
_WORKFLOW = "course_question_workflow"


def _promote_settings(**overrides: object) -> Settings:
    base = {
        "AGENT_SYNTHESIS_ENABLED": True,
        "AGENT_SYNTHESIS_TEXT_PROMOTION_ENABLED": True,
        "AGENT_SYNTHESIS_TEXT_PROMOTION_MODE": "promote_validated",
        "AGENT_SYNTHESIS_TEXT_PROMOTION_WORKFLOWS": _WORKFLOW,
    }
    base.update(overrides)
    return Settings(**base)


def _live_response() -> AgentResponse:
    return AgentResponse(
        conversation_id="c1",
        message_id="m1",
        run_id="r1",
        text="Live workflow answer.",
        blocks=[StructuredBlock(type="CourseInfoBlock", data={"course": "B"})],
        warnings=["warn"],
        proposed_actions=[],
        used_sources=["catalog"],
    )


def _synthesis_output() -> SynthesisOutput:
    return SynthesisOutput(
        status="candidate_ready",
        synthesis_id="syn-1",
        decision_summary="ready",
        candidate_answer_text="Synthesized read-only course answer with enough detail.",
        safe_to_show=True,
        safe_to_promote=True,
        confidence=0.93,
    )


def test_flags_off_preserves_behavior() -> None:
    decision = evaluate_synthesis_text_promotion(
        workflow_name=_WORKFLOW,
        live_response=_live_response(),
        synthesis_output=_synthesis_output(),
        retrieval_metadata={
            "monitorDiagnostics": {"decision": {"action": "continue"}},
            "planRepairDiagnostics": {"modeUsed": "continue"},
            "clarificationDiagnostics": {"questions": []},
            "clarificationState": {"status": "resolved"},
        },
        settings=_promote_settings(AGENT_RUNTIME_READINESS_GATE_ENABLED=False),
    )
    assert decision.promoted is True
    metadata = build_synthesis_promotion_metadata(decision)
    assert "runtimeReadiness" not in metadata


def test_readiness_gate_enabled_without_manifest_blocks_promotion() -> None:
    decision = evaluate_synthesis_text_promotion(
        workflow_name=_WORKFLOW,
        live_response=_live_response(),
        synthesis_output=_synthesis_output(),
        retrieval_metadata={
            "monitorDiagnostics": {"decision": {"action": "continue"}},
            "planRepairDiagnostics": {"modeUsed": "continue"},
            "clarificationDiagnostics": {"questions": []},
            "clarificationState": {"status": "resolved"},
        },
        settings=_promote_settings(
            AGENT_RUNTIME_READINESS_GATE_ENABLED=True,
            AGENT_RUNTIME_READINESS_MANIFEST_PATH="",
            AGENT_RUNTIME_READINESS_FAIL_CLOSED=True,
        ),
    )
    assert decision.promoted is False
    metadata = build_synthesis_promotion_metadata(decision)
    assert metadata["runtimeReadiness"]["allowed"] is False


def test_manifest_not_approved_blocks_promotion(tmp_path: Path) -> None:
    manifest = tmp_path / "not-approved.json"
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
      "approved": false,
      "scope": ["course_question_workflow"]
    }
  ]
}
""".strip(),
        encoding="utf-8",
    )
    decision = evaluate_synthesis_text_promotion(
        workflow_name=_WORKFLOW,
        live_response=_live_response(),
        synthesis_output=_synthesis_output(),
        retrieval_metadata={
            "monitorDiagnostics": {"decision": {"action": "continue"}},
            "planRepairDiagnostics": {"modeUsed": "continue"},
            "clarificationDiagnostics": {"questions": []},
            "clarificationState": {"status": "resolved"},
        },
        settings=_promote_settings(
            AGENT_RUNTIME_READINESS_GATE_ENABLED=True,
            AGENT_RUNTIME_READINESS_MANIFEST_PATH=str(manifest),
        ),
    )
    assert decision.promoted is False


def test_runtime_readiness_diagnostics_attached_when_gate_enabled() -> None:
    decision = evaluate_synthesis_text_promotion(
        workflow_name=_WORKFLOW,
        live_response=_live_response(),
        synthesis_output=_synthesis_output(),
        retrieval_metadata={
            "monitorDiagnostics": {"decision": {"action": "continue"}},
            "planRepairDiagnostics": {"modeUsed": "continue"},
            "clarificationDiagnostics": {"questions": []},
            "clarificationState": {"status": "resolved"},
        },
        settings=_promote_settings(
            AGENT_RUNTIME_READINESS_GATE_ENABLED=True,
            AGENT_RUNTIME_READINESS_MANIFEST_PATH=str(_MANIFEST),
        ),
    )
    metadata = build_synthesis_promotion_metadata(decision)
    assert "runtimeReadiness" in metadata
    assert metadata["runtimeReadiness"]["candidateId"] == f"synthesis_text_promotion.{_WORKFLOW}"


def test_no_direct_llm_calls(monkeypatch) -> None:
    def _fail(*_args: object, **_kwargs: object) -> None:
        raise AssertionError("real_llm_called")

    monkeypatch.setattr("openai.OpenAI", _fail)
    evaluate_synthesis_text_promotion(
        workflow_name=_WORKFLOW,
        live_response=_live_response(),
        synthesis_output=_synthesis_output(),
        retrieval_metadata={"monitorDiagnostics": {}, "planRepairDiagnostics": {}, "clarificationDiagnostics": {}},
        settings=_promote_settings(AGENT_RUNTIME_READINESS_GATE_ENABLED=False),
    )
