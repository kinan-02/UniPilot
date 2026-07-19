"""Seeds the ISE fixture student's CURRENT semester plan, on top of `ise_student`.

`ise_student_fixture` has always defined `CURRENT_PLAN_COURSES` -- six real
courses for spring `2025-2`, with provenance comments -- but it seeds only
`student_profiles` and `completed_courses`. Nothing ever wrote a
`semester_plans` document, so the constant is referenced nowhere and the agent
sees a student with a transcript and NO plan. Every "is my registration
actually valid?" question was therefore unanswerable, which is why the original
11-case eval has none.

This fixture writes that plan, matching a real `semester_plans` document's shape
field for field (`semesters[].plannedCourses[]` with courseId/courseNumber/
courseTitle/credits/category), so the agent reaches it by the same path it would
in production. It layers on `ise_student` rather than changing it: the existing
eval's ten cases are keyed to a student with no plan, and quietly giving them one
would change what they measure.

Ground truth, verified against the dev catalog before any assertion was written:

  plan = 6 courses, 19.0 credits (00940314 3.5, 00950605 2.5, 00960211 3.5,
                                  00960411 3.5, 00970800 3.5, 01140051 2.5)
  eligible now      : 00940314, 00950605, 00960211, 00960411
  NOT eligible      : 00970800 (missing 00940594), 01140051 (missing 01130013)
  completed credits : 62.5 across 2024-1 (19.5), 2024-2 (22.5), 2025-1 (20.5)
"""

from __future__ import annotations

from datetime import datetime, timezone
from typing import Any, AsyncIterator

import pytest
from bson import ObjectId

from app.db.mongo import get_database
from tests.agent_core.ise_student_fixture import (  # noqa: F401 -- fixture injection
    CURRENT_PLAN_COURSES,
    CURRENT_SEMESTER_CODE,
    IseStudent,
    _fresh_mongo_client_per_test,
    ise_student,
)

# Verified: the two plan courses whose prerequisites the student does NOT hold,
# and the course each one is waiting on.
PLAN_BLOCKED: dict[str, str] = {
    "00970800": "00940594",
    "01140051": "01130013",
}
PLAN_CREDITS = 19.0


class IsePlanningStudent(IseStudent):
    """The seeded student, now with a spring plan the agent can actually read."""

    def __init__(self, student: IseStudent, plan_credits: float) -> None:
        super().__init__(student.user_id, student.credits_earned)
        self.plan_credits = plan_credits
        self.plan_courses = list(CURRENT_PLAN_COURSES)


@pytest.fixture
async def ise_planning_student(ise_student: IseStudent) -> AsyncIterator[IsePlanningStudent]:
    database = await get_database()
    user_id = ObjectId(ise_student.user_id)
    now = datetime.now(timezone.utc)

    planned: list[dict[str, Any]] = []
    plan_credits = 0.0
    for number in CURRENT_PLAN_COURSES:
        # The course name is in `title`; `name` is null on every catalog document
        # (the same split that leaves `graph.nodes[code]["name"]` empty for some
        # courses). Reading `name` here seeded a plan with null titles, which no
        # real plan has.
        course = await database["courses"].find_one(
            {"courseNumber": number}, {"_id": 1, "credits": 1, "title": 1}
        )
        # Same contract as the base fixture: a plan seeded into the void is worse
        # than a failing test, because the eval would then grade the agent on
        # data it was never given.
        if course is None:
            raise RuntimeError(f"planned course {number} is not in the dev catalog")
        credits = float(course["credits"])
        plan_credits += credits
        planned.append(
            {
                "courseId": str(course["_id"]),
                "courseNumber": number,
                "courseTitle": course.get("title"),
                "credits": str(credits),  # real plans store this as a string
                "category": "mandatory",
                "reason": "Planned for the current semester",
            }
        )

    plan_document = {
        "userId": user_id,
        "name": f"תוכנית {CURRENT_SEMESTER_CODE}",
        "status": "draft",
        "plannerType": "manual",
        "version": 1,
        "basePlanId": None,
        "assumptions": [],
        "explanation": None,
        "plannerInsights": None,
        "semesters": [
            {
                "semesterCode": CURRENT_SEMESTER_CODE,
                "order": 1,
                "goalCredits": plan_credits,
                "plannedCourses": planned,
                "constraintsSnapshot": None,
                "notes": f"{len(planned)} course(s) planned for {CURRENT_SEMESTER_CODE}",
            }
        ],
        "createdAt": now,
        "updatedAt": now,
    }

    await database["semester_plans"].insert_one(plan_document)
    try:
        yield IsePlanningStudent(ise_student, plan_credits)
    finally:
        await database["semester_plans"].delete_many({"userId": user_id})
