"""Unit tests for Phase 6 (post-Phase-9) live clarification.

Covers `app.agent.planner_first_live.attempt_live_clarification`, which
reuses the exact same `clarification.capability.run_clarification_from_shadow_context`
entry point already wired into the deterministic live path -- this module
adds no new clarification mechanism, only a new caller for Planner-first-
live turns.
"""

from __future__ import annotations

from app.agent.planner_first_live import attempt_live_clarification
from app.config import Settings


def _plan(**overrides) -> dict:
    defaults = dict(plan_id="p1", user_goal="test", subtasks=[])
    defaults.update(overrides)
    return defaults


def test_disabled_by_default_returns_none() -> None:
    # Explicit, not relied-on-default: an operator's real `.env` may have
    # clarification on (as this repo's own root `.env` does, post-Phase-9).
    output, metadata = attempt_live_clarification(
        planner_output=_plan(), monitor_metadata=None, settings=Settings(AGENT_CLARIFICATION_ENABLED=False)
    )
    assert output is None
    assert metadata is None


def test_enabled_with_no_needs_returns_empty_output() -> None:
    settings = Settings(AGENT_CLARIFICATION_ENABLED=True)
    output, metadata = attempt_live_clarification(
        planner_output=_plan(), monitor_metadata=None, settings=settings
    )
    assert output is not None
    assert output.questions == []
    assert metadata is not None
    assert metadata["questionCount"] == 0


def test_monitor_ask_clarification_produces_a_question() -> None:
    settings = Settings(
        **{"AGENT_CLARIFICATION_ENABLED": True, "AGENT_CLARIFICATION_USER_FACING_ENABLED": True}
    )
    monitor_metadata = {"decision": {"action": "ask_clarification", "reason": "preference ambiguity about track"}}
    output, metadata = attempt_live_clarification(
        planner_output=_plan(), monitor_metadata=monitor_metadata, settings=settings
    )
    assert output is not None
    assert output.status == "question_ready"
    assert len(output.questions) == 1
    assert output.questions[0].ambiguity_type == "preference"
    assert metadata is not None
    assert metadata["status"] == "question_ready"
    assert metadata["questionCount"] == 1


def test_planner_missing_context_produces_a_need() -> None:
    settings = Settings(
        **{"AGENT_CLARIFICATION_ENABLED": True, "AGENT_CLARIFICATION_USER_FACING_ENABLED": True}
    )
    plan = _plan(
        missing_context=["student_preference_for_elective_track"],
        subtasks=[{"id": "run_it", "capability_name": "graduation_progress_workflow"}],
    )
    output, metadata = attempt_live_clarification(planner_output=plan, monitor_metadata=None, settings=settings)
    assert output is not None
    assert metadata is not None
    assert metadata["needCount"] >= 1


def test_user_facing_disabled_still_produces_output_but_no_user_facing_questions() -> None:
    """`allow_user_questions=False` still runs the capability (assumed
    answers / diagnostics), it just never marks a question `question_ready`
    for the user-facing offer."""
    settings = Settings(
        **{"AGENT_CLARIFICATION_ENABLED": True, "AGENT_CLARIFICATION_USER_FACING_ENABLED": False}
    )
    monitor_metadata = {"decision": {"action": "ask_clarification", "reason": "preference ambiguity about track"}}
    output, metadata = attempt_live_clarification(
        planner_output=_plan(), monitor_metadata=monitor_metadata, settings=settings
    )
    assert output is not None
    assert output.status != "question_ready"
    assert metadata is not None


def test_never_raises_on_malformed_planner_output() -> None:
    settings = Settings(AGENT_CLARIFICATION_ENABLED=True)
    output, metadata = attempt_live_clarification(
        planner_output={"subtasks": "not-a-list"}, monitor_metadata=None, settings=settings
    )
    assert output is not None
    assert metadata is not None
