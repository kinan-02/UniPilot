"""Unit tests for clarification capability runner (Phase 17)."""

from __future__ import annotations

from pathlib import Path

from app.agent.clarification.capability import run_clarification_capability
from app.agent.clarification.schemas import ClarificationNeed


def _preference_need(**overrides) -> ClarificationNeed:
    base = {
        "id": "need-pref",
        "source": "monitor",
        "ambiguity_type": "preference",
        "consequence": "high",
        "question_topic": "workload vs requirements",
        "reason": "missing_preference_context",
        "options": ["requirements first", "lighter workload"],
    }
    base.update(overrides)
    return ClarificationNeed(**base)


def test_disabled_user_facing_mode_produces_diagnostics_only() -> None:
    output = run_clarification_capability(
        needs=[_preference_need()],
        allow_user_questions=False,
    )
    assert output.status in {"assumed_default", "skipped"}
    assert output.questions == []


def test_user_facing_allowed_produces_question_ready() -> None:
    output = run_clarification_capability(
        needs=[_preference_need()],
        allow_user_questions=True,
    )
    assert output.status == "question_ready"
    assert len(output.questions) == 1


def test_ask_user_false_creates_fallback_when_possible() -> None:
    output = run_clarification_capability(
        needs=[
            _preference_need(
                consequence="low",
                default_assumption="prioritize mandatory requirements first",
            )
        ],
        allow_user_questions=False,
    )
    assert output.status == "assumed_default"
    assert len(output.answers) == 1


def test_multiple_questions_are_batched() -> None:
    needs = [
        _preference_need(id=f"need-{index}", question_topic=f"topic {index}")
        for index in range(4)
    ]
    output = run_clarification_capability(
        needs=needs,
        allow_user_questions=True,
        max_questions=2,
    )
    assert output.status == "question_ready"
    assert len(output.questions) <= 2


def test_epistemic_need_does_not_ask_user() -> None:
    output = run_clarification_capability(
        needs=[
            ClarificationNeed(
                id="need-ep",
                source="planner",
                ambiguity_type="epistemic",
                consequence="medium",
                question_topic="catalog requirement detail",
                reason="missing_context",
                evidence={"retrievableEpistemic": True},
            )
        ],
        allow_user_questions=True,
    )
    assert output.questions == []
    assert output.status == "resolved_epistemically"


def test_malformed_needs_never_raise() -> None:
    output = run_clarification_capability(needs=[], allow_user_questions=True)
    assert output.status == "skipped"


def test_no_writes_or_action_proposals() -> None:
    root = Path(__file__).resolve().parents[2] / "app" / "agent" / "clarification"
    text = "\n".join(path.read_text(encoding="utf-8") for path in root.rglob("*.py") if path.name != "safety.py")
    assert "create_agent_action_proposal(" not in text
    assert ".insert_one(" not in text
