"""Unit tests for `compare_plans` (docs/agent/HIGHER_LEVEL_TOOLS.md).

Pure deterministic diff, no real-data dependency -- every case is
constructed directly, no engine fixtures needed.
"""

from __future__ import annotations

from app.agent_core.tools.composites.compare_plans import ComparePlansInput, run_compare_plans


def _plan(semesters_used: int, unscheduled: list[str]) -> dict:
    return {"semestersUsed": semesters_used, "unscheduledCourses": unscheduled}


async def test_malformed_plan_a_fails_closed():
    result = await run_compare_plans(
        ComparePlansInput(plan_a={"unscheduledCourses": []}, plan_b=_plan(1, []))
    )
    assert result.ok is False
    assert "malformed_plan_a" in result.error
    assert "semestersUsed" in result.error


async def test_malformed_plan_b_fails_closed():
    result = await run_compare_plans(
        ComparePlansInput(plan_a=_plan(1, []), plan_b={"semestersUsed": 1})
    )
    assert result.ok is False
    assert "malformed_plan_b" in result.error
    assert "unscheduledCourses" in result.error


async def test_computes_deltas_with_focus_course():
    result = await run_compare_plans(
        ComparePlansInput(
            plan_a=_plan(1, ["A"]),
            plan_b=_plan(3, ["A", "B"]),
            focus_course_id="B",
        )
    )
    assert result.ok is True
    assert result.data == {
        "additionalSemestersUsed": 2,
        "newlyUnscheduledCourses": ["B"],
        "newlyScheduledCourses": [],
        "focusCourseId": "B",
        "focusCourseStillUnscheduled": True,
    }
    assert result.certainty.basis == "official_record"
    assert result.certainty.confidence == 1.0


async def test_no_change_between_plans():
    result = await run_compare_plans(ComparePlansInput(plan_a=_plan(2, []), plan_b=_plan(2, [])))
    assert result.ok is True
    assert result.data == {
        "additionalSemestersUsed": 0,
        "newlyUnscheduledCourses": [],
        "newlyScheduledCourses": [],
        "focusCourseId": None,
        "focusCourseStillUnscheduled": None,
    }


async def test_newly_scheduled_courses_detected():
    """plan_b resolving a course that was unscheduled in plan_a (e.g.
    comparing two different constraint sets, not just a disruption
    before/after) is a real, useful case this generic tool should surface,
    not something `simulate_course_disruption` itself ever produces."""
    result = await run_compare_plans(
        ComparePlansInput(plan_a=_plan(3, ["A", "B"]), plan_b=_plan(2, ["A"]))
    )
    assert result.ok is True
    assert result.data["newlyUnscheduledCourses"] == []
    assert result.data["newlyScheduledCourses"] == ["B"]
    assert result.data["additionalSemestersUsed"] == -1


async def test_focus_course_resolved_in_plan_b():
    result = await run_compare_plans(
        ComparePlansInput(plan_a=_plan(3, ["A"]), plan_b=_plan(2, []), focus_course_id="A")
    )
    assert result.ok is True
    assert result.data["focusCourseStillUnscheduled"] is False
