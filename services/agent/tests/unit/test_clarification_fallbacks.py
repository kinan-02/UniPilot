"""Unit tests for clarification fallbacks (Phase 17)."""

from __future__ import annotations

from app.agent.clarification.fallbacks import (
    assumed_confidence_is_lower_than_confirmed,
    build_assumed_answer,
    build_assumption_record,
)
from app.agent.clarification.schemas import ClarificationNeed


def _need(**overrides) -> ClarificationNeed:
    base = {
        "id": "need-1",
        "source": "planner",
        "ambiguity_type": "preference",
        "consequence": "medium",
        "question_topic": "prioritize mandatory requirements first",
        "reason": "missing_preference_context",
        "default_assumption": "prioritize mandatory requirements first",
    }
    base.update(overrides)
    return ClarificationNeed(**base)


def test_default_assumption_becomes_assumed_answer() -> None:
    answer = build_assumed_answer(_need())
    assert answer is not None
    assert "mandatory requirements" in answer.value


def test_provenance_is_assumed() -> None:
    answer = build_assumed_answer(_need())
    assert answer is not None
    assert answer.provenance == "assumed"


def test_confidence_lower_than_confirmed() -> None:
    answer = build_assumed_answer(_need())
    assert answer is not None
    assert assumed_confidence_is_lower_than_confirmed(answer.confidence)


def test_no_default_returns_none() -> None:
    assert build_assumed_answer(_need(default_assumption=None)) is None


def test_assumption_record_compatible_with_plan_assumption_shape() -> None:
    need = _need()
    answer = build_assumed_answer(need)
    assert answer is not None
    record = build_assumption_record(need, answer)
    assert record["kind"] in {"user_preference", "context_availability"}
    assert record["provenance"] == "assumed"
    assert "confidence" in record
    assert record["consequenceIfWrong"] in {"low", "medium", "high"}
