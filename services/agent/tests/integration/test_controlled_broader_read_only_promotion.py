"""Integration tests for controlled broader read-only text promotion (Phase 25)."""

from __future__ import annotations

from pathlib import Path

from app.agent.schemas import AgentResponse, StructuredBlock
from app.agent.synthesis.promotion_policy import evaluate_synthesis_text_promotion
from app.agent.synthesis.response_builder import build_synthesis_text_promoted_response
from app.agent.synthesis.schemas import SynthesisOutput
from app.config import Settings

_MANIFEST = Path(__file__).resolve().parents[1] / "fixtures" / "promotion_readiness_manifest.test.json"


def _settings(workflow: str, **overrides: object) -> Settings:
    base = {
        "AGENT_SYNTHESIS_ENABLED": True,
        "AGENT_SYNTHESIS_TEXT_PROMOTION_ENABLED": True,
        "AGENT_SYNTHESIS_TEXT_PROMOTION_MODE": "promote_validated",
        "AGENT_SYNTHESIS_TEXT_PROMOTION_WORKFLOWS": workflow,
        "AGENT_RUNTIME_READINESS_GATE_ENABLED": True,
        "AGENT_RUNTIME_READINESS_MANIFEST_PATH": str(_MANIFEST),
    }
    base.update(overrides)
    return Settings(**base)


def _live(workflow_block: str) -> AgentResponse:
    return AgentResponse(
        conversation_id="c1",
        message_id="m1",
        run_id="r1",
        text="Live deterministic answer.",
        blocks=[StructuredBlock(type=workflow_block, data={"ok": True})],
        warnings=["keep"],
        proposed_actions=[],
        used_sources=["catalog"],
    )


def _synthesis(text: str) -> SynthesisOutput:
    return SynthesisOutput(
        status="candidate_ready",
        synthesis_id="syn-1",
        decision_summary="ready",
        candidate_answer_text=text,
        safe_to_show=True,
        safe_to_promote=True,
        confidence=0.94,
    )


def _meta() -> dict:
    return {
        "monitorDiagnostics": {"decision": {"action": "continue"}},
        "planRepairDiagnostics": {"modeUsed": "continue"},
        "clarificationDiagnostics": {"questions": []},
        "clarificationState": {"status": "resolved"},
    }


def test_readiness_manifest_approved_allows_synthesis_text_promotion_when_gates_pass() -> None:
    workflow = "course_question_workflow"
    live = _live("CourseInfoBlock")
    synthesis = _synthesis("Approved synthesized course answer with enough detail.")
    decision = evaluate_synthesis_text_promotion(
        workflow_name=workflow,
        live_response=live,
        synthesis_output=synthesis,
        retrieval_metadata=_meta(),
        settings=_settings(workflow),
    )
    assert decision.promoted is True


def test_write_workflow_remains_blocked_even_with_manifest_approval() -> None:
    workflow = "transcript_import_workflow"
    decision = evaluate_synthesis_text_promotion(
        workflow_name=workflow,
        live_response=_live("TranscriptImportBlock"),
        synthesis_output=_synthesis("This should never promote for write workflow."),
        retrieval_metadata=_meta(),
        settings=_settings(
            "graduation_progress_workflow,course_question_workflow,requirement_explanation_workflow,transcript_import_workflow"
        ),
    )
    assert decision.promoted is False


def test_promotion_changes_only_response_text() -> None:
    workflow = "graduation_progress_workflow"
    live = _live("GraduationStatusBlock")
    synthesis = _synthesis("Synthesized graduation summary with enough detail.")
    decision = evaluate_synthesis_text_promotion(
        workflow_name=workflow,
        live_response=live,
        synthesis_output=synthesis,
        retrieval_metadata=_meta(),
        settings=_settings(workflow),
    )
    assert decision.promoted is True
    promoted = build_synthesis_text_promoted_response(live_response=live, candidate_text=synthesis.candidate_answer_text)
    assert promoted.text == synthesis.candidate_answer_text
    assert promoted.blocks == live.blocks
    assert promoted.warnings == live.warnings
    assert promoted.used_sources == live.used_sources
    assert promoted.proposed_actions == live.proposed_actions


def test_stale_manifest_blocks_promotion(tmp_path: Path) -> None:
    manifest = tmp_path / "stale.json"
    manifest.write_text(
        """
{
  "schemaVersion": "1",
  "reviewedAt": "2020-01-01T00:00:00Z",
  "reviewedBy": "human",
  "candidates": [
    {
      "candidateId": "synthesis_text_promotion.course_question_workflow",
      "level": "ready_for_limited_promotion",
      "approved": true,
      "scope": ["course_question_workflow"]
    }
  ]
}
""".strip(),
        encoding="utf-8",
    )
    decision = evaluate_synthesis_text_promotion(
        workflow_name="course_question_workflow",
        live_response=_live("CourseInfoBlock"),
        synthesis_output=_synthesis("Should be blocked by stale manifest."),
        retrieval_metadata=_meta(),
        settings=_settings(
            "course_question_workflow",
            AGENT_RUNTIME_READINESS_MANIFEST_PATH=str(manifest),
            AGENT_RUNTIME_READINESS_MAX_AGE_DAYS=30,
        ),
    )
    assert decision.promoted is False
