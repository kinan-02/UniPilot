"""Tests for `tools/composites/student_state.py`.

The specification is the 2026-07-16 ise_correctness audit of the
simulation_planning role: of its five composites, only `check_eligibility` could
name a student. The other four could only be TOLD what was in the record, so the
model hand-copied it -- measured at 1775 argument chars and a 41.9s call for
`simulate_course_disruption`, against 96 chars and 3.1s for `check_eligibility`
in the same run.
"""

from __future__ import annotations

from bson import ObjectId

from app.agent_core.tools.composites.simulate_course_disruption import (
    SimulateCourseDisruptionInput,
    run_simulate_course_disruption,
)
from app.agent_core.tools.composites.student_state import (
    completed_entries,
    resolve_completed_entries,
    resolve_student_state,
)
from app.db.mongo import set_test_database

_RECORD = [
    {"courseNumber": "00940224", "semesterCode": "2025-1", "grade": 85.0, "creditsEarned": 4.0},
    {"courseNumber": "00940345", "semesterCode": "2024-1", "grade": 88.0, "creditsEarned": 4.0},
]


def test_completed_entries_reads_either_spelling_of_the_key():
    """The relay snake_cased `completedCourses` in transit, live, so the
    camelCase lookup found nothing and a student who had passed 00940224 was told
    they were ineligible for a course requiring it. `state` is still
    model-authored on the what-if path, so the tolerance stays.
    """
    assert completed_entries({"completedCourses": _RECORD}) == _RECORD
    assert completed_entries({"completed_courses": _RECORD}) == _RECORD
    assert completed_entries({}) == []
    assert completed_entries({"completedCourses": []}) == []


def test_non_dict_entries_are_discarded_rather_than_crashing():
    assert completed_entries({"completedCourses": [{"courseNumber": "1"}, "junk", None]}) == [
        {"courseNumber": "1"}
    ]


async def test_a_supplied_state_wins_and_no_record_is_read(monkeypatch):
    """The what-if path. A caller who deliberately altered the record (e.g.
    `mutate_state` failing a course) must not have it silently re-read from
    source -- a fresh read would defeat the entire simulation.
    """
    import app.agent_core.tools.composites.student_state as module

    async def _must_not_fetch(*_args, **_kwargs):
        raise AssertionError("a supplied state must never trigger a record read")

    monkeypatch.setattr(module, "run_get_entity", _must_not_fetch)

    state = {"completedCourses": _RECORD, "currentSemesterCode": "2025-2"}
    resolved, error = await resolve_student_state(state, "some-student-id")

    assert error is None
    assert resolved == state


async def test_the_students_record_is_read_when_only_an_id_is_given(
    use_real_academic_engine, fake_database_factory
):
    """The whole point: one id in, record read at source. No completed-course
    list crosses a model, so no amount of transcription can reshape it."""
    user_id = str(ObjectId())
    set_test_database(
        fake_database_factory(
            {
                "completed_courses": [
                    {"_id": ObjectId(), "userId": ObjectId(user_id), "courseNumber": "00940224", "grade": 85},
                ]
            }
        )
    )

    entries, error = await resolve_completed_entries({}, user_id)

    assert error is None
    assert [entry["courseNumber"] for entry in entries] == ["00940224"]


async def test_resolving_a_state_never_mutates_the_callers_dict(
    use_real_academic_engine, fake_database_factory
):
    """A what-if state is the caller's own object. A composite that quietly
    rewrote it would corrupt the baseline half of its own before/after diff."""
    user_id = str(ObjectId())
    set_test_database(
        fake_database_factory(
            {
                "completed_courses": [
                    {"_id": ObjectId(), "userId": ObjectId(user_id), "courseNumber": "00940224", "grade": 85},
                ]
            }
        )
    )

    original = {"currentSemesterCode": "2025-2"}
    resolved, error = await resolve_student_state(original, user_id)

    assert error is None
    assert original == {"currentSemesterCode": "2025-2"}, "the caller's dict must be untouched"
    assert resolved["currentSemesterCode"] == "2025-2"
    assert [entry["courseNumber"] for entry in resolved["completedCourses"]] == ["00940224"]


async def test_no_student_id_and_no_state_is_not_an_error_here():
    """Each caller decides whether an empty record is fatal for what it was asked
    to do; this resolver does not decide for them."""
    entries, error = await resolve_completed_entries({}, None)

    assert entries == []
    assert error is None


async def test_an_unreadable_record_surfaces_as_an_error(monkeypatch):
    import app.agent_core.tools.composites.student_state as module
    from app.agent_core.tools.envelope import ToolOutputEnvelope

    async def _fail(*_args, **_kwargs):
        return ToolOutputEnvelope(ok=False, data=None, error="entity_not_found: completed_courses:x")

    monkeypatch.setattr(module, "run_get_entity", _fail)

    entries, error = await resolve_completed_entries({}, "x")

    assert entries == []
    assert "completed_courses_unavailable" in error


async def test_simulate_course_disruption_needs_only_an_id_now(
    use_real_academic_engine, fake_database_factory
):
    """The flagship composite, and the one that paid the most for `state`.

    It applies the disruption ITSELF via `mutate_state`, so a caller never had a
    reason to pre-mutate anything -- it was hand-copying the real record in only
    to have our own code read it back. Live, that was 1775 argument chars, a
    41.9s call, and three siblings dead on the 45s subagent ceiling.
    """
    user_id = str(ObjectId())
    set_test_database(
        fake_database_factory(
            {
                "completed_courses": [
                    {"_id": ObjectId(), "userId": ObjectId(user_id), "courseNumber": "00940224", "grade": 85},
                ]
            }
        )
    )

    result = await run_simulate_course_disruption(
        SimulateCourseDisruptionInput(
            course_id="00940224",
            disruption_type="fail",
            student_id=user_id,
            semester="2025-2",
        )
    )

    assert result.ok is True, result.error
