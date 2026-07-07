"""Provenance helpers for clarification answers (Phase 17)."""

from __future__ import annotations

from typing import Any

from app.agent.clarification.schemas import ClarificationAnswer, ClarificationNeed, ClarificationProvenance


def provenance_for_answer(answer: ClarificationAnswer) -> ClarificationProvenance:
    return answer.provenance


def build_assumption_provenance_record(
    *,
    need: ClarificationNeed,
    answer: ClarificationAnswer,
) -> dict[str, Any]:
    """Compact assumption record compatible with Phase 16 `PlanAssumption` shape."""
    kind = "user_preference" if need.ambiguity_type in {"preference", "mixed"} else "context_availability"
    statement = f"Assumed {need.question_topic}: {answer.value}"
    if need.ambiguity_type == "preference":
        statement = f"Assumed preference: {answer.value}"

    return {
        "kind": kind,
        "statement": statement[:240],
        "provenance": answer.provenance,
        "confidence": answer.confidence,
        "consequenceIfWrong": need.consequence,
        "needId": need.id,
    }
