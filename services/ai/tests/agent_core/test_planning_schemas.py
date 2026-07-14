"""Schema tests for the Phase 0 additions to `PlannerInvocationInput`.

`exhausted_steps` (W3a) and `replan_focus` (W3b) are additive fields with
inert defaults, so every existing caller is unaffected (no behavior change).
They are deliberately separate from `monitor_flags` -- same rationale as
`final_round` -- so they cannot trip the council's adaptive-depth gate.
"""

from __future__ import annotations

from app.agent_core.planning.schemas import PlannerInvocationInput, ReplanFocus


def test_new_fields_default_to_inert_values() -> None:
    pi = PlannerInvocationInput(user_goal="g", original_user_message="m")
    assert pi.exhausted_steps == []
    assert pi.replan_focus is None


def test_replan_focus_carries_failed_protected_and_unmet() -> None:
    focus = ReplanFocus(
        failed_step_ids=["1a"],
        protected_step_ids=["1b", "1c"],
        unmet_criteria=["prereq not confirmed against completed courses"],
    )
    assert focus.failed_step_ids == ["1a"]
    assert focus.protected_step_ids == ["1b", "1c"]
    assert focus.unmet_criteria == ["prereq not confirmed against completed courses"]


def test_replan_focus_fields_default_empty() -> None:
    focus = ReplanFocus()
    assert focus.failed_step_ids == []
    assert focus.protected_step_ids == []
    assert focus.unmet_criteria == []


def test_planner_input_accepts_new_fields() -> None:
    focus = ReplanFocus(failed_step_ids=["1a"], protected_step_ids=["1b"])
    pi = PlannerInvocationInput(
        user_goal="g",
        original_user_message="m",
        exhausted_steps=["resolve algorithms"],
        replan_focus=focus,
    )
    assert pi.exhausted_steps == ["resolve algorithms"]
    assert pi.replan_focus is not None
    assert pi.replan_focus.protected_step_ids == ["1b"]
