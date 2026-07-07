"""Fallback / assumed answers for clarification needs (Phase 17)."""

from __future__ import annotations

from typing import Any

from app.agent.clarification.provenance import build_assumption_provenance_record
from app.agent.clarification.schemas import ClarificationAnswer, ClarificationNeed

_CONFIRMED_BASELINE_CONFIDENCE = 0.85
_ASSUMED_BASELINE_CONFIDENCE = 0.45


def build_assumed_answer(need: ClarificationNeed) -> ClarificationAnswer | None:
    """Build an assumed answer from `default_assumption` when available."""
    default = (need.default_assumption or "").strip()
    if not default:
        return None

    confidence = _assumed_confidence(need)
    return ClarificationAnswer(
        need_id=need.id,
        value=default,
        provenance="assumed",
        source="fallback" if need.source != "monitor" else "system_default",
        confidence=confidence,
    )


def build_assumption_record(need: ClarificationNeed, answer: ClarificationAnswer) -> dict[str, Any]:
    """Return a compact assumption record for monitor/planner diagnostics."""
    return build_assumption_provenance_record(need=need, answer=answer)


def assumed_confidence_is_lower_than_confirmed(assumed: float) -> bool:
    return assumed < _CONFIRMED_BASELINE_CONFIDENCE


def _assumed_confidence(need: ClarificationNeed) -> float:
    base = _ASSUMED_BASELINE_CONFIDENCE
    if need.consequence == "low":
        return min(base + 0.05, 0.55)
    if need.consequence == "high":
        return max(base - 0.1, 0.3)
    return base
