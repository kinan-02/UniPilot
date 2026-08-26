"""Unit tests for the pure term-plan orchestration (`app.planning.term_plan`).

This is the engine behind the agent's `plan_term` tool. It reuses the audited
schedule/exam primitives but adds the policy the shared selector is MISSING
(verified 2026-07-21): `select_conflict_aware_courses` seats a course even when its
only lesson option hard-overlaps an occupied slot. So the headline test here is
`test_a_conflicting_course_is_dropped_not_seated` -- two courses that can only meet
at the same hour must yield ONE placed course and ONE unscheduled, never an
overlapping timetable.

The functions are PURE (pre-loaded catalog/offerings/completed passed in), so no DB
and no Mongo -- the DB wiring lives in the service layer (Phase 2).
"""

from __future__ import annotations

from app.planning.term_plan import Candidate, TermInput, plan_terms
from app.services.catalog_overlap_groups import build_catalog_overlap_groups


# --- fixtures -----------------------------------------------------------------

def _course(
    course_id: str,
    number: str,
    *,
    credits: float = 3.0,
    title: str = "",
    prerequisites: list[str] | None = None,
    corequisites_text: str | None = None,
    no_credit_text: str | None = None,
) -> dict:
    course: dict = {
        "_id": course_id,
        "courseNumber": number,
        "title": title or f"Course {number}",
        "credits": credits,
        "prerequisites": prerequisites or [],
    }
    if corequisites_text is not None:
        course["corequisitesText"] = corequisites_text
    if no_credit_text is not None:
        course["noAdditionalCreditText"] = no_credit_text
    return course


def _offering(
    number: str,
    *,
    day: str = "Sunday",
    time: str = "10:00-12:00",
    exam: str | None = "2026-02-01",
) -> dict:
    offering: dict = {
        "courseNumber": number,
        "academicYear": 2025,
        "semesterCode": 200,
        "scheduleGroups": [{"day": day, "time": time, "type": "lecture"}],
    }
    if exam is not None:
        offering["examDates"] = {"moedA": exam}
    return offering


def _term(semester_code: str, offerings: dict[str, dict]) -> TermInput:
    return TermInput(
        semester_code=semester_code,
        academic_year=2025,
        technion_semester_code=200,
        offerings_by_number=offerings,
    )


def _courses_by_number(*courses: dict) -> dict[str, dict]:
    return {str(course["courseNumber"]): course for course in courses}


def _placed_numbers(result: dict) -> list[str]:
    return [c["courseNumber"] for term in result["terms"] for c in term["placedCourses"]]


def _unscheduled_numbers(result: dict) -> set[str]:
    return {row["courseNumber"] for row in result["unscheduled"]}


# --- eligibility + credit cap -------------------------------------------------

def test_places_eligible_offered_candidates_up_to_the_credit_cap():
    a = _course("a", "00110001", credits=3.0)
    b = _course("b", "00110002", credits=3.0)
    c = _course("c", "00110003", credits=3.0)
    offerings = {
        "00110001": _offering("00110001", day="Sunday", time="09:00-11:00", exam="2026-02-01"),
        "00110002": _offering("00110002", day="Monday", time="09:00-11:00", exam="2026-02-05"),
        "00110003": _offering("00110003", day="Tuesday", time="09:00-11:00", exam="2026-02-09"),
    }

    result = plan_terms(
        candidates=[Candidate(a, "mandatory"), Candidate(b, "elective"), Candidate(c, "elective")],
        terms=[_term("2025-winter", offerings)],
        completed_course_ids=set(),
        completed_course_numbers=set(),
        courses_by_number=_courses_by_number(a, b, c),
        overlap_groups=[],
        max_credits_limit=6.0,  # only two of the three 3-credit courses fit
    )

    placed = _placed_numbers(result)
    assert len(placed) == 2
    assert result["terms"][0]["credits"] == 6.0
    # mandatory is seated first (priority order), the third course overflows.
    assert "00110001" in placed


def test_the_built_weekly_schedule_is_conflict_free():
    a = _course("a", "00110001")
    offerings = {"00110001": _offering("00110001", day="Sunday", time="09:00-11:00")}

    result = plan_terms(
        candidates=[Candidate(a, "mandatory")],
        terms=[_term("2025-winter", offerings)],
        completed_course_ids=set(),
        completed_course_numbers=set(),
        courses_by_number=_courses_by_number(a),
        overlap_groups=[],
        max_credits_limit=20.0,
    )

    weekly = result["terms"][0]["weeklySchedule"]
    assert weekly["status"] == "valid"
    assert weekly["conflicts"] == []


# --- THE audit fix: conflict-free is ENFORCED, not assumed --------------------

def test_a_conflicting_course_is_dropped_not_seated():
    # A and B can ONLY meet Sunday 10-12. The shared selector would seat both
    # (proven). term_plan must place one and mark the other unscheduled, and the
    # built schedule must be conflict-free.
    a = _course("a", "00110001", credits=3.0)
    b = _course("b", "00110002", credits=3.0)
    offerings = {
        "00110001": _offering("00110001", day="Sunday", time="10:00-12:00", exam="2026-02-01"),
        "00110002": _offering("00110002", day="Sunday", time="10:00-12:00", exam="2026-02-05"),
    }

    result = plan_terms(
        candidates=[Candidate(a, "mandatory"), Candidate(b, "elective")],
        terms=[_term("2025-winter", offerings)],
        completed_course_ids=set(),
        completed_course_numbers=set(),
        courses_by_number=_courses_by_number(a, b),
        overlap_groups=[],
        max_credits_limit=20.0,
    )

    assert _placed_numbers(result) == ["00110001"]  # mandatory kept
    assert "00110002" in _unscheduled_numbers(result)
    reason = next(r["reason"] for r in result["unscheduled"] if r["courseNumber"] == "00110002")
    assert "conflict" in reason.lower()
    assert result["terms"][0]["weeklySchedule"]["status"] == "valid"


def test_an_exam_date_collision_is_skipped():
    a = _course("a", "00110001")
    b = _course("b", "00110002")
    # Different days (no schedule clash) but the SAME exam date.
    offerings = {
        "00110001": _offering("00110001", day="Sunday", time="09:00-11:00", exam="2026-02-01"),
        "00110002": _offering("00110002", day="Monday", time="09:00-11:00", exam="2026-02-01"),
    }

    result = plan_terms(
        candidates=[Candidate(a, "mandatory"), Candidate(b, "elective")],
        terms=[_term("2025-winter", offerings)],
        completed_course_ids=set(),
        completed_course_numbers=set(),
        courses_by_number=_courses_by_number(a, b),
        overlap_groups=[],
        max_credits_limit=20.0,
    )

    assert _placed_numbers(result) == ["00110001"]
    reason = next(r["reason"] for r in result["unscheduled"] if r["courseNumber"] == "00110002")
    assert "exam" in reason.lower()


# --- no-credit overlap + dedup ------------------------------------------------

def test_a_no_additional_credit_overlap_with_a_completed_course_is_excluded():
    # B grants no additional credit against A, which the student already completed.
    b = _course("b", "00110002", no_credit_text="00110001")
    offerings = {"00110002": _offering("00110002")}

    result = plan_terms(
        candidates=[Candidate(b, "elective")],
        terms=[_term("2025-winter", offerings)],
        completed_course_ids={"a"},
        completed_course_numbers={"00110001"},
        courses_by_number=_courses_by_number(b),
        # Built the production way (course_number_keys on both sides), from b's
        # "no additional credit" text referencing the completed course 00110001.
        overlap_groups=build_catalog_overlap_groups([b]),
        max_credits_limit=20.0,
    )

    assert _placed_numbers(result) == []
    reason = next(r["reason"] for r in result["unscheduled"] if r["courseNumber"] == "00110002")
    assert "credit" in reason.lower()


def test_an_already_completed_course_is_not_replanned():
    a = _course("a", "00110001")
    offerings = {"00110001": _offering("00110001")}

    result = plan_terms(
        candidates=[Candidate(a, "mandatory")],
        terms=[_term("2025-winter", offerings)],
        completed_course_ids={"a"},
        completed_course_numbers={"00110001"},
        courses_by_number=_courses_by_number(a),
        overlap_groups=[],
        max_credits_limit=20.0,
    )

    assert _placed_numbers(result) == []


# --- multi-term ---------------------------------------------------------------

def test_multi_term_dedups_and_carries_satisfied_forward():
    # One course, two terms: it is placed in winter and must NOT reappear in spring.
    a = _course("a", "00110001")
    winter = _term("2025-winter", {"00110001": _offering("00110001", day="Sunday", time="09:00-11:00")})
    spring = _term("2025-spring", {"00110001": _offering("00110001", day="Sunday", time="09:00-11:00")})

    result = plan_terms(
        candidates=[Candidate(a, "mandatory")],
        terms=[winter, spring],
        completed_course_ids=set(),
        completed_course_numbers=set(),
        courses_by_number=_courses_by_number(a),
        overlap_groups=[],
        max_credits_limit=20.0,
    )

    assert _placed_numbers(result) == ["00110001"]  # exactly once, in the first term
    assert result["terms"][0]["semesterCode"] == "2025-winter"
    assert result["terms"][1]["placedCourses"] == []


# --- conservative prereq/coreq: FLAG, never silently drop ---------------------

def test_an_unmet_prerequisite_is_flagged_not_dropped():
    # B requires A; A is not completed. Conservative policy: place B, flag it.
    b = _course("b", "00110002", prerequisites=["a"])
    offerings = {"00110002": _offering("00110002")}

    result = plan_terms(
        candidates=[Candidate(b, "mandatory")],
        terms=[_term("2025-winter", offerings)],
        completed_course_ids=set(),
        completed_course_numbers=set(),
        courses_by_number=_courses_by_number(b),
        overlap_groups=[],
        max_credits_limit=20.0,
    )

    assert _placed_numbers(result) == ["00110002"]  # placed, not dropped
    placed = result["terms"][0]["placedCourses"][0]
    assert placed["prereqStatus"] != "satisfied"


def test_a_met_prerequisite_reads_satisfied():
    b = _course("b", "00110002", prerequisites=["a"])
    offerings = {"00110002": _offering("00110002")}

    result = plan_terms(
        candidates=[Candidate(b, "mandatory")],
        terms=[_term("2025-winter", offerings)],
        completed_course_ids={"a"},
        completed_course_numbers={"00110001"},
        courses_by_number=_courses_by_number(b),
        overlap_groups=[],
        max_credits_limit=20.0,
    )

    placed = result["terms"][0]["placedCourses"][0]
    assert placed["prereqStatus"] == "satisfied"
