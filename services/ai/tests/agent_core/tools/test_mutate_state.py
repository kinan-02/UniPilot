"""Unit tests for `mutate_state` (docs/agent/AGENT_VISION.md §5, primitive 7).

`base_state` shape and `change["type"]` vocabulary are defined in
docs/agent/SIMULATION_STATE_CONTRACT.md -- these tests exercise every
documented change type plus its failure paths, and confirm `base_state` is
never mutated in place (this repo's immutability rule).
"""

from __future__ import annotations

import copy

from app.agent_core.tools.primitives.mutate_state import MutateStateInput, run_mutate_state


async def test_missing_change_type_fails_closed():
    result = await run_mutate_state(MutateStateInput(base_state={}, change={}))
    assert result.ok is False
    assert "change_type_required" in result.error


async def test_unknown_change_type_fails_closed():
    result = await run_mutate_state(MutateStateInput(base_state={}, change={"type": "teleport"}))
    assert result.ok is False
    assert "unknown_change_type: teleport" in result.error


# -- fail_course --------------------------------------------------------


async def test_fail_course_adds_new_entry_when_not_already_completed():
    result = await run_mutate_state(
        MutateStateInput(
            base_state={"completedCourses": []},
            change={"type": "fail_course", "courseNumber": "00440105", "semester": "2025-2"},
        )
    )
    assert result.ok is True
    assert result.data["state"]["completedCourses"] == [
        {"courseNumber": "00440105", "semester": "2025-2", "status": "failed"}
    ]
    assert result.certainty.basis == "hypothetical_simulation"
    assert result.certainty.confidence == 1.0


async def test_fail_course_updates_existing_entry():
    base_state = {
        "completedCourses": [{"courseNumber": "00440105", "semester": "2025-2", "status": "completed", "grade": 90}]
    }
    result = await run_mutate_state(
        MutateStateInput(
            base_state=base_state,
            change={"type": "fail_course", "courseNumber": "00440105", "semester": "2025-2"},
        )
    )
    assert result.ok is True
    entry = result.data["state"]["completedCourses"][0]
    assert entry["status"] == "failed"
    assert entry["grade"] == 90  # other fields on the entry are preserved


async def test_fail_course_leaves_other_entries_untouched():
    base_state = {
        "completedCourses": [
            {"courseNumber": "00440105", "semester": "2025-2", "status": "completed"},
            {"courseNumber": "00440140", "semester": "2025-2", "status": "completed"},
        ]
    }
    result = await run_mutate_state(
        MutateStateInput(
            base_state=base_state,
            change={"type": "fail_course", "courseNumber": "00440105", "semester": "2025-2"},
        )
    )
    assert result.ok is True
    completed = {entry["courseNumber"]: entry["status"] for entry in result.data["state"]["completedCourses"]}
    assert completed == {"00440105": "failed", "00440140": "completed"}


async def test_fail_course_missing_required_fields_fails_closed():
    result = await run_mutate_state(
        MutateStateInput(base_state={}, change={"type": "fail_course", "courseNumber": "00440105"})
    )
    assert result.ok is False
    assert "fail_course_requires_courseNumber_and_semester" in result.error


# -- drop_course ----------------------------------------------------------


async def test_drop_course_removes_from_planned_semester():
    base_state = {"plannedSemesters": {"2025-2": ["00440148", "00440105"]}}
    result = await run_mutate_state(
        MutateStateInput(
            base_state=base_state,
            change={"type": "drop_course", "courseNumber": "00440148", "semester": "2025-2"},
        )
    )
    assert result.ok is True
    assert result.data["state"]["plannedSemesters"]["2025-2"] == ["00440105"]


async def test_drop_course_from_semester_with_no_such_course_is_a_no_op():
    base_state = {"plannedSemesters": {"2025-2": ["00440105"]}}
    result = await run_mutate_state(
        MutateStateInput(
            base_state=base_state,
            change={"type": "drop_course", "courseNumber": "00440148", "semester": "2025-2"},
        )
    )
    assert result.ok is True
    assert result.data["state"]["plannedSemesters"]["2025-2"] == ["00440105"]


async def test_drop_course_from_unplanned_semester_is_a_no_op():
    result = await run_mutate_state(
        MutateStateInput(
            base_state={"plannedSemesters": {}},
            change={"type": "drop_course", "courseNumber": "00440148", "semester": "2025-2"},
        )
    )
    assert result.ok is True
    assert result.data["state"]["plannedSemesters"]["2025-2"] == []


async def test_drop_course_missing_required_fields_fails_closed():
    result = await run_mutate_state(
        MutateStateInput(base_state={}, change={"type": "drop_course", "semester": "2025-2"})
    )
    assert result.ok is False
    assert "drop_course_requires_courseNumber_and_semester" in result.error


# -- retake_course ----------------------------------------------------------


async def test_retake_course_adds_to_target_semester():
    result = await run_mutate_state(
        MutateStateInput(
            base_state={"plannedSemesters": {}},
            change={"type": "retake_course", "courseNumber": "00440105", "targetSemester": "2026-1"},
        )
    )
    assert result.ok is True
    assert result.data["state"]["plannedSemesters"]["2026-1"] == ["00440105"]


async def test_retake_course_deduplicates():
    base_state = {"plannedSemesters": {"2026-1": ["00440105"]}}
    result = await run_mutate_state(
        MutateStateInput(
            base_state=base_state,
            change={"type": "retake_course", "courseNumber": "00440105", "targetSemester": "2026-1"},
        )
    )
    assert result.ok is True
    assert result.data["state"]["plannedSemesters"]["2026-1"] == ["00440105"]


async def test_retake_course_missing_required_fields_fails_closed():
    result = await run_mutate_state(
        MutateStateInput(base_state={}, change={"type": "retake_course", "courseNumber": "00440105"})
    )
    assert result.ok is False
    assert "retake_course_requires_courseNumber_and_targetSemester" in result.error


# -- delay_semester ----------------------------------------------------------


async def test_delay_semester_advances_within_same_year():
    result = await run_mutate_state(
        MutateStateInput(
            base_state={"currentSemesterCode": "2025-2"},
            change={"type": "delay_semester", "count": 1},
        )
    )
    assert result.ok is True
    assert result.data["state"]["currentSemesterCode"] == "2025-3"


async def test_delay_semester_wraps_year():
    result = await run_mutate_state(
        MutateStateInput(
            base_state={"currentSemesterCode": "2025-3"},
            change={"type": "delay_semester", "count": 1},
        )
    )
    assert result.ok is True
    assert result.data["state"]["currentSemesterCode"] == "2026-1"


async def test_delay_semester_multi_slot_wrap():
    result = await run_mutate_state(
        MutateStateInput(
            base_state={"currentSemesterCode": "2025-2"},
            change={"type": "delay_semester", "count": 4},
        )
    )
    assert result.ok is True
    assert result.data["state"]["currentSemesterCode"] == "2026-3"


async def test_delay_semester_zero_count_is_a_no_op():
    result = await run_mutate_state(
        MutateStateInput(
            base_state={"currentSemesterCode": "2025-2"},
            change={"type": "delay_semester", "count": 0},
        )
    )
    assert result.ok is True
    assert result.data["state"]["currentSemesterCode"] == "2025-2"


async def test_delay_semester_missing_count_fails_closed():
    result = await run_mutate_state(
        MutateStateInput(base_state={"currentSemesterCode": "2025-2"}, change={"type": "delay_semester"})
    )
    assert result.ok is False
    assert "delay_semester_requires_nonnegative_integer_count" in result.error


async def test_delay_semester_negative_count_fails_closed():
    result = await run_mutate_state(
        MutateStateInput(
            base_state={"currentSemesterCode": "2025-2"},
            change={"type": "delay_semester", "count": -1},
        )
    )
    assert result.ok is False
    assert "delay_semester_requires_nonnegative_integer_count" in result.error


async def test_delay_semester_boolean_count_fails_closed():
    """`isinstance(True, int)` is `True` in Python -- must be rejected
    explicitly, not silently treated as `count=1`."""
    result = await run_mutate_state(
        MutateStateInput(
            base_state={"currentSemesterCode": "2025-2"},
            change={"type": "delay_semester", "count": True},
        )
    )
    assert result.ok is False
    assert "delay_semester_requires_nonnegative_integer_count" in result.error


async def test_delay_semester_missing_current_semester_code_fails_closed():
    result = await run_mutate_state(
        MutateStateInput(base_state={}, change={"type": "delay_semester", "count": 1})
    )
    assert result.ok is False
    assert "delay_semester_requires_currentSemesterCode_in_base_state" in result.error


async def test_delay_semester_unparseable_code_fails_closed():
    result = await run_mutate_state(
        MutateStateInput(
            base_state={"currentSemesterCode": "not-a-code"},
            change={"type": "delay_semester", "count": 1},
        )
    )
    assert result.ok is False
    assert "unparseable_semester_code: not-a-code" in result.error


# -- change_track ----------------------------------------------------------


async def test_change_track_replaces_track_slug():
    result = await run_mutate_state(
        MutateStateInput(
            base_state={"trackSlug": "track-old"},
            change={"type": "change_track", "trackSlug": "track-new"},
        )
    )
    assert result.ok is True
    assert result.data["state"]["trackSlug"] == "track-new"


async def test_change_track_missing_track_slug_fails_closed():
    result = await run_mutate_state(MutateStateInput(base_state={}, change={"type": "change_track"}))
    assert result.ok is False
    assert "change_track_requires_trackSlug" in result.error


# -- immutability + envelope shape ----------------------------------------


async def test_base_state_is_never_mutated_in_place():
    base_state = {"completedCourses": [{"courseNumber": "00440105", "semester": "2025-2", "status": "completed"}]}
    original = copy.deepcopy(base_state)

    result = await run_mutate_state(
        MutateStateInput(
            base_state=base_state,
            change={"type": "fail_course", "courseNumber": "00440105", "semester": "2025-2"},
        )
    )

    assert result.ok is True
    assert base_state == original
    assert result.data["state"] is not base_state


async def test_applied_change_echoed_back_in_data():
    change = {"type": "change_track", "trackSlug": "track-new"}
    result = await run_mutate_state(MutateStateInput(base_state={}, change=change))
    assert result.ok is True
    assert result.data["appliedChange"] == change
