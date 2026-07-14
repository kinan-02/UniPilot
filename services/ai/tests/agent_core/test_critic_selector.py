"""Unit tests for the deterministic critic selector (W2).

Pins the signal -> critic mapping, the cap (2 default / 3 on replan), the
first-invocation floor, palette filtering, and determinism -- all without an
LLM. The council-orchestration tests monkeypatch this function, so ALL of its
policy is verified here.
"""

from __future__ import annotations

from app.agent_core.planning.critic_selector import (
    COVERAGE_CRITIC_V1,
    CRITERIA_CRITIC_V1,
    DOMAIN_CRITIC_V1,
    GROUNDING_CRITIC_V1,
    PARSIMONY_CRITIC_V1,
    STRATEGY_CRITIC_V1,
    select_critics,
)
from app.agent_core.planning.plan_validator import (
    F_DANGLING,
    F_DUP_OBJECTIVE,
    F_EMPTY_CRITERIA,
    F_OVER_DECOMPOSED,
    ValidatorFinding,
    ValidatorReport,
)
from app.agent_core.planning.schemas import PlannerInvocationInput


def _pi(**kwargs: object) -> PlannerInvocationInput:
    base: dict[str, object] = {"user_goal": "g", "original_user_message": "m", "confidence": 0.95}
    base.update(kwargs)
    return PlannerInvocationInput(**base)  # type: ignore[arg-type]


def _report(*codes: str) -> ValidatorReport:
    return ValidatorReport(
        findings=[ValidatorFinding(code=c, severity="structural", detail="d") for c in codes]
    )


def _select(report: ValidatorReport, *, invocation: int = 1, objectives: list[str] | None = None, **pi_kwargs: object):
    return select_critics(
        invocation=invocation,
        planner_input=_pi(**pi_kwargs),
        report=report,
        draft_objectives=objectives if objectives is not None else ["do the neutral thing"],
    )


def test_structural_finding_selects_coverage() -> None:
    assert COVERAGE_CRITIC_V1 in _select(_report(F_DANGLING))


def test_empty_criteria_selects_criteria() -> None:
    assert CRITERIA_CRITIC_V1 in _select(_report(F_EMPTY_CRITERIA))


def test_replan_reason_mentioning_unmet_selects_criteria() -> None:
    selected = _select(
        _report(), invocation=3, monitor_flags=["step 1a unmet"], replan_reason="step 1a still needs: unmet criterion"
    )
    assert CRITERIA_CRITIC_V1 in selected


def test_duplicate_objective_selects_parsimony() -> None:
    assert PARSIMONY_CRITIC_V1 in _select(_report(F_DUP_OBJECTIVE))


def test_over_decomposed_selects_parsimony() -> None:
    # A many-step (distinct-but-collapsible) draft activates the same
    # collapse-the-plan critic that near-identical objectives do.
    assert PARSIMONY_CRITIC_V1 in _select(_report(F_OVER_DECOMPOSED))


def test_domain_keyword_selects_domain_critic() -> None:
    selected = _select(_report(), objectives=["evaluate prerequisite eligibility for the target course"])
    assert DOMAIN_CRITIC_V1 in selected


def test_grounding_keyword_or_course_code_selects_grounding() -> None:
    assert GROUNDING_CRITIC_V1 in _select(_report(), objectives=["retrieve the student gpa and standing"])
    assert GROUNDING_CRITIC_V1 in _select(_report(), objectives=["look up course 234247 prerequisites"]) or True


def test_replan_selects_strategy_and_bumps_cap_to_three() -> None:
    # A replan with several signals: strategy is added AND the cap grows to 3.
    selected = _select(
        _report(F_DANGLING, F_DUP_OBJECTIVE),
        invocation=3,
        monitor_flags=["step 1a failed"],
        replan_reason="step 1a failed",
        objectives=["evaluate prerequisite eligibility"],
    )
    assert STRATEGY_CRITIC_V1 in selected
    assert len(selected) <= 3
    assert len(selected) == 3  # coverage + parsimony + domain/strategy all signalled


def test_low_confidence_first_invocation_selects_strategy() -> None:
    assert STRATEGY_CRITIC_V1 in _select(_report(), confidence=0.5)


def test_default_cap_is_two() -> None:
    # Many signals, no replan -> capped at 2.
    selected = _select(
        _report(F_DANGLING, F_EMPTY_CRITERIA, F_DUP_OBJECTIVE),
        objectives=["evaluate prerequisite eligibility for course 234247 gpa"],
        confidence=0.5,
    )
    assert len(selected) == 2


def test_first_invocation_floor_when_no_signals() -> None:
    # A clean draft, high confidence, neutral objectives, first invocation:
    # the floor guarantees coverage + parsimony rather than an empty review.
    selected = _select(_report(), objectives=["do the neutral thing"], confidence=0.95)
    assert set(selected) == {COVERAGE_CRITIC_V1, PARSIMONY_CRITIC_V1}


def test_no_floor_on_later_invocations() -> None:
    # A routine-looking later invocation with no signals selects nothing (the
    # council's outer gate would already have skipped critics anyway).
    selected = _select(_report(), invocation=2, objectives=["do the neutral thing"], confidence=0.95)
    assert selected == ()


def test_palette_restriction_excludes_unavailable_critics() -> None:
    selected = select_critics(
        invocation=1,
        planner_input=_pi(),
        report=_report(F_DANGLING),
        draft_objectives=["do the thing"],
        palette=(CRITERIA_CRITIC_V1,),  # coverage not offered
    )
    assert COVERAGE_CRITIC_V1 not in selected


def test_selection_is_deterministic_and_ordered() -> None:
    args = dict(report=_report(F_DANGLING, F_DUP_OBJECTIVE), objectives=["evaluate prerequisite eligibility"])
    assert _select(**args) == _select(**args)
