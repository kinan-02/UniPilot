"""Unit tests for clarification policy (Phase 17)."""

from __future__ import annotations

from app.agent.clarification.policy import decide_clarification_action
from app.agent.clarification.schemas import ClarificationNeed


def _need(**overrides) -> ClarificationNeed:
    base = {
        "id": "need-1",
        "source": "planner",
        "ambiguity_type": "preference",
        "consequence": "high",
        "question_topic": "planning preference",
        "reason": "test",
    }
    base.update(overrides)
    return ClarificationNeed(**base)


def test_high_consequence_preference_asks_user() -> None:
    decision = decide_clarification_action(_need(consequence="high"))
    assert decision.action == "ask_user"


def test_medium_preference_asks_user_when_no_strong_default() -> None:
    decision = decide_clarification_action(_need(consequence="medium"))
    assert decision.action == "ask_user"


def test_low_preference_assumes_default() -> None:
    decision = decide_clarification_action(
        _need(
            consequence="low",
            default_assumption="keep semester workload lighter",
        )
    )
    assert decision.action == "assume_default"


def test_epistemic_ambiguity_resolves_epistemically_or_skips() -> None:
    resolved = decide_clarification_action(
        _need(
            ambiguity_type="epistemic",
            consequence="medium",
            evidence={"retrievableEpistemic": True},
        )
    )
    assert resolved.action == "resolve_epistemically"

    skipped = decide_clarification_action(
        _need(
            ambiguity_type="epistemic",
            consequence="low",
            evidence={"retrievableEpistemic": False},
        )
    )
    assert skipped.action == "skip"


def test_unknown_ambiguity_skips() -> None:
    decision = decide_clarification_action(_need(ambiguity_type="unknown"))
    assert decision.action == "skip"


def test_policy_never_raises() -> None:
    broken = ClarificationNeed.model_construct(
        id="x",
        source="manual",
        ambiguity_type="preference",
        consequence="high",
        question_topic="t",
        reason="r",
    )
    decision = decide_clarification_action(broken)
    assert decision.action in {"ask_user", "assume_default", "resolve_epistemically", "skip"}
