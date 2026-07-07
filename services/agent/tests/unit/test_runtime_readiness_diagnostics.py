"""Unit tests for runtime readiness diagnostics (Phase 25)."""

from __future__ import annotations

from app.agent.readiness.diagnostics import (
    build_runtime_readiness_diagnostic,
    build_turn_runtime_readiness_metadata,
)
from app.agent.readiness.schemas import RuntimeReadinessGateDecision
from app.config import Settings


def test_build_runtime_readiness_diagnostic_is_compact() -> None:
    decision = RuntimeReadinessGateDecision(
        candidate_id="synthesis_text_promotion.course_question_workflow",
        allowed=False,
        level="ready_for_shadow",
        reasons=["level_below_required"],
        reviewed=True,
        scope_allowed=True,
    )
    diag = build_runtime_readiness_diagnostic(decision, settings=Settings(AGENT_RUNTIME_READINESS_GATE_ENABLED=True))
    assert diag["candidateId"] == "synthesis_text_promotion.course_question_workflow"
    assert "manifest" not in str(diag)


def test_build_turn_runtime_readiness_metadata_aggregates() -> None:
    metadata = build_turn_runtime_readiness_metadata(
        settings=Settings(AGENT_RUNTIME_READINESS_GATE_ENABLED=True),
        promotion_diagnostics=[
            {
                "runtimeReadiness": {
                    "candidateId": "synthesis_text_promotion.course_question_workflow",
                    "allowed": False,
                    "reasons": ["level_below_required"],
                }
            }
        ],
    )
    assert metadata is not None
    assert len(metadata["decisions"]) == 1
