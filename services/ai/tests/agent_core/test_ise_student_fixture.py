"""Validates the ISE fixture itself, before any eval asserts against it.

A seeded student whose transcript silently resolves to nothing produces an eval
that tests the wrong thing while looking green -- exactly what happened with the
older EE fixture (random `courseId`s -> zero resolved completions). These tests
exist so that failure is loud and immediate rather than mistaken for an agent
bug. See `docs/agent/ISE_EVAL_FIXTURE.md`.
"""

from __future__ import annotations

import pytest
from bson import ObjectId

from app.db.mongo import get_database
from tests.agent_core.ise_student_fixture import (  # noqa: F401 -- fixtures used via pytest injection
    COMPLETED_BY_TERM,
    CURRENT_SEMESTER_CODE,
    PROGRAM_SLUG,
    TOTAL_PROGRAM_CREDITS,
    IseStudent,
    _fresh_mongo_client_per_test,
    ise_student,
)

pytestmark = pytest.mark.live

EXPECTED_COMPLETED_COUNT = 17
# What is actually SEEDED and therefore visible to the agent: the 17 catalog
# courses. Physical Education (1.0cr) has no course code and cannot be seeded,
# so it is not part of ground truth -- counting it would demand an answer no
# correct agent could produce. Confirmed live: the agent's own retrieval of the
# transcript sums these to 62.5.
EXPECTED_CREDITS_EARNED = 62.5
EXPECTED_CREDITS_REMAINING = 92.5


async def test_seeds_seventeen_completions_with_expected_credits(ise_student: IseStudent) -> None:
    assert len(ise_student.completed_course_numbers) == EXPECTED_COMPLETED_COUNT
    assert ise_student.credits_earned == pytest.approx(EXPECTED_CREDITS_EARNED)
    assert ise_student.credits_remaining == pytest.approx(EXPECTED_CREDITS_REMAINING)
    assert TOTAL_PROGRAM_CREDITS == pytest.approx(155.0)


async def test_profile_is_seeded_as_a_4th_semester_ise_student(ise_student: IseStudent) -> None:
    database = await get_database()

    profile = await database["student_profiles"].find_one({"userId": ObjectId(ise_student.user_id)})

    assert profile is not None
    assert profile["programSlug"] == PROGRAM_SLUG
    assert profile["currentSemesterCode"] == CURRENT_SEMESTER_CODE
    assert profile["catalogYear"] == 2025


async def test_profile_is_FULLY_declared(ise_student: IseStudent) -> None:
    """A half-declared profile makes the agent ask which program applies rather
    than answering -- correct behaviour, but it silently invalidates every
    downstream assertion.

    Caught live (2026-07-15): with `degreeId=None` / `academicPath={}` the agent
    returned a clarification ("your degree program is not fully declared") and
    `credits_remaining` never reached an answer. The fixture was at fault, not
    the agent.
    """
    database = await get_database()

    profile = await database["student_profiles"].find_one({"userId": ObjectId(ise_student.user_id)})
    assert profile is not None

    assert profile["degreeId"] is not None, "a null degreeId leaves the program undeclared"
    assert profile["facultyId"] == "faculty-dds"
    assert profile["programType"] == "BSc"
    assert profile["academicPath"]["trackSlug"] == PROGRAM_SLUG, (
        "real registered students declare the track under academicPath.trackSlug"
    )

    # The degreeId must resolve to the real ISE program (155 credits) -- most
    # degreeIds on real ISE profiles are orphaned, so this cannot be assumed.
    degree = await database["degree_programs"].find_one({"_id": profile["degreeId"]})
    assert degree is not None, "degreeId must resolve to a real degree_programs doc"
    assert degree["totalCredits"] == pytest.approx(TOTAL_PROGRAM_CREDITS)


async def test_every_seeded_courseId_resolves_to_a_real_catalog_course(ise_student: IseStudent) -> None:
    """The regression that matters: `student_user_context_service` resolves a
    transcript ONLY via `courseId` -> `courses._id`. An unresolvable id is
    dropped silently, leaving the agent with an empty transcript."""
    database = await get_database()

    records = await database["completed_courses"].find({"userId": ObjectId(ise_student.user_id)}).to_list(length=100)
    assert len(records) == EXPECTED_COMPLETED_COUNT

    course_ids = [record["courseId"] for record in records]
    resolved = await database["courses"].find({"_id": {"$in": course_ids}}).to_list(length=100)

    assert len(resolved) == EXPECTED_COMPLETED_COUNT, (
        "Every seeded courseId must resolve to a real catalog course, or the student's "
        "transcript is invisible to the API and the eval asserts against a ghost."
    )


async def test_completions_are_spread_across_the_three_completed_terms(ise_student: IseStudent) -> None:
    database = await get_database()

    records = await database["completed_courses"].find({"userId": ObjectId(ise_student.user_id)}).to_list(length=100)
    by_term: dict[str, int] = {}
    for record in records:
        by_term[record["semesterCode"]] = by_term.get(record["semesterCode"], 0) + 1

    assert by_term == {term: len(courses) for term, courses in COMPLETED_BY_TERM.items()}
    assert CURRENT_SEMESTER_CODE not in by_term, "The current semester must not appear as completed work."
