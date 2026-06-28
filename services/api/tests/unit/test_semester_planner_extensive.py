"""Extensive semester planner tests — matrix mandatory source, edge cases, determinism."""

from __future__ import annotations

import time

import pytest
from bson import ObjectId

from app.planning.semester_planner import (
    _mandatory_from_semester_matrix,
    build_candidate_pools,
    generate_deterministic_semester_plan,
)
from app.services.graduation_progress_calculator import round_credits
from tests.fixtures.semester_planner_extended_fixtures import (
    ELECTIVE_E,
    S1_COURSE_A,
    S1_COURSE_B,
    S2_COURSE_C,
    S2_COURSE_D,
    build_matrix_completed_record,
    build_matrix_planner_context,
    build_semester_matrix_documents,
)


def _plan(**kwargs):
    planner_kwargs = {
        key: kwargs[key]
        for key in ("max_credits", "min_credits", "name")
        if key in kwargs
    }
    context_kwargs = {
        key: kwargs[key]
        for key in ("completed_course_records", "include_elective_pool")
        if key in kwargs
    }
    context = build_matrix_planner_context(**context_kwargs)
    return generate_deterministic_semester_plan(
        profile=context["profile"],
        degree=context["degree"],
        catalog_courses=context["catalogCourses"],
        graduation_progress=context["graduationProgress"],
        completed_course_records=context["completedCourseRecords"],
        hard_requirements=context["hardRequirements"],
        pool_documents=context["poolDocuments"],
        semester_matrix_documents=context["semesterMatrixDocuments"],
        semester_code="2025-2",
        **planner_kwargs,
    )


def test_mandatory_candidates_come_from_semester_matrix_in_catalog_order():
    context = build_matrix_planner_context()
    pools = build_candidate_pools(
        catalog_courses=context["catalogCourses"],
        graduation_progress=context["graduationProgress"],
        hard_requirements=context["hardRequirements"],
        pool_documents=context["poolDocuments"],
        semester_matrix_documents=context["semesterMatrixDocuments"],
        program_code="009216-1-000",
        completed_course_ids=set(),
    )

    numbers = [course["number"] for course in pools["mandatoryCandidates"]]
    assert numbers[:2] == ["00940345", "01040031"]
    assert "00940219" in numbers
    assert numbers.index("00940345") < numbers.index("00940219")


def test_assumptions_record_semester_matrix_as_mandatory_source():
    plan = _plan()
    assert plan["assumptions"]["mandatorySource"] == "semester_matrix"
    assert plan["assumptions"]["semesterMatrixRuleCount"] == 2
    assert any("semester matrix" in rule.lower() for rule in plan["explanation"]["rulesApplied"])


def test_empty_transcript_recommends_semester_one_matrix_courses_first():
    plan = _plan(max_credits=7.5)
    planned = plan["semesters"][0]["plannedCourses"]
    assert [course["courseId"] for course in planned[:2]] == [S1_COURSE_A, S1_COURSE_B]
    assert all(course["category"] == "mandatory" for course in planned)
    assert all("semester matrix" in course["reason"].lower() for course in planned)


def test_completed_matrix_courses_are_excluded_from_recommendations():
    plan = _plan(
        completed_course_records=[build_matrix_completed_record(S1_COURSE_A, credits_earned=4.0)],
        max_credits=12,
    )
    recommended_ids = [course["courseId"] for course in plan["semesters"][0]["plannedCourses"]]
    assert S1_COURSE_A not in recommended_ids
    assert S1_COURSE_B in recommended_ids


def test_failed_grade_does_not_exclude_matrix_mandatory_course():
    plan = _plan(
        completed_course_records=[build_matrix_completed_record(S1_COURSE_A, grade=50, credits_earned=0)],
        max_credits=6,
    )
    recommended_ids = [course["courseId"] for course in plan["semesters"][0]["plannedCourses"]]
    assert S1_COURSE_A in recommended_ids


def test_grade_55_boundary_is_passing():
    plan = _plan(
        completed_course_records=[build_matrix_completed_record(S1_COURSE_A, grade=55, credits_earned=4.0)],
        max_credits=6,
    )
    recommended_ids = [course["courseId"] for course in plan["semesters"][0]["plannedCourses"]]
    assert S1_COURSE_A not in recommended_ids


def test_grade_56_counts_as_completed():
    plan = _plan(
        completed_course_records=[build_matrix_completed_record(S1_COURSE_A, grade=56, credits_earned=4.0)],
        max_credits=6,
    )
    recommended_ids = [course["courseId"] for course in plan["semesters"][0]["plannedCourses"]]
    assert S1_COURSE_A not in recommended_ids


def test_prerequisites_from_prerequisites_text_block_later_semester():
    plan = _plan(max_credits=3.5)
    recommended_ids = [course["courseId"] for course in plan["semesters"][0]["plannedCourses"]]
    assert recommended_ids == [S1_COURSE_B]
    blocked = {entry["courseId"]: entry for entry in plan["explanation"]["blockedByPrerequisites"]}
    assert S2_COURSE_D in blocked
    assert blocked[S2_COURSE_D]["missingPrerequisites"][0]["courseNumber"] == "00940345"


def test_prerequisite_chain_scheduled_in_same_plan():
    plan = _plan(
        completed_course_records=[build_matrix_completed_record(S1_COURSE_A, credits_earned=4.0)],
        max_credits=7.5,
    )
    recommended_ids = [course["courseId"] for course in plan["semesters"][0]["plannedCourses"]]
    assert S2_COURSE_C in recommended_ids
    assert recommended_ids.index(S1_COURSE_B) < recommended_ids.index(S2_COURSE_C)


def test_semester_two_not_recommended_before_semester_one_completed():
    plan = _plan(max_credits=18)
    recommended_numbers = [
        course["courseNumber"] for course in plan["semesters"][0]["plannedCourses"]
    ]
    first_semester_two_index = next(
        index for index, number in enumerate(recommended_numbers) if number.startswith("009402")
    )
    last_semester_one_index = max(
        index for index, number in enumerate(recommended_numbers) if number in {"00940345", "01040031"}
    )
    assert first_semester_two_index > last_semester_one_index


def test_electives_only_after_mandatory_capacity_or_min_credits_pressure():
    plan = _plan(
        completed_course_records=[
            build_matrix_completed_record(S1_COURSE_A, credits_earned=4.0),
            build_matrix_completed_record(S1_COURSE_B, credits_earned=3.5),
            build_matrix_completed_record(S2_COURSE_C, credits_earned=3.5),
            build_matrix_completed_record(S2_COURSE_D, credits_earned=3.0),
        ],
        max_credits=12,
    )
    planned = plan["semesters"][0]["plannedCourses"]
    categories = [course["category"] for course in planned]
    if ELECTIVE_E in [course["courseId"] for course in planned]:
        assert "elective" in categories
        mandatory_count = sum(1 for category in categories if category == "mandatory")
        assert mandatory_count == 0


def test_min_credits_triggers_elective_backfill():
    plan = _plan(
        completed_course_records=[
            build_matrix_completed_record(S1_COURSE_A, credits_earned=4.0),
            build_matrix_completed_record(S1_COURSE_B, credits_earned=3.5),
            build_matrix_completed_record(S2_COURSE_C, credits_earned=3.5),
            build_matrix_completed_record(S2_COURSE_D, credits_earned=3.0),
        ],
        max_credits=12,
        min_credits=10,
    )
    assert plan["explanation"]["totalRecommendedCredits"] >= 10 or plan["explanation"]["partialPlan"]


def test_partial_plan_when_max_credits_too_low_for_min_credits():
    plan = _plan(max_credits=4, min_credits=9)
    assert plan["explanation"]["partialPlan"] is True
    assert plan["explanation"]["meetsMinCredits"] is False
    assert plan["explanation"]["totalRecommendedCredits"] < 9


def test_empty_plan_when_all_matrix_courses_blocked_and_no_electives():
    context = build_matrix_planner_context(include_elective_pool=False)
    plan = generate_deterministic_semester_plan(
        profile=context["profile"],
        degree=context["degree"],
        catalog_courses=context["catalogCourses"],
        graduation_progress=context["graduationProgress"],
        completed_course_records=[],
        hard_requirements=context["hardRequirements"],
        pool_documents=[],
        semester_matrix_documents=context["semesterMatrixDocuments"],
        semester_code="2025-2",
        max_credits=0,
    )
    assert plan["explanation"]["emptyPlan"] is True
    assert plan["semesters"][0]["plannedCourses"] == []


def test_unknown_matrix_course_numbers_are_skipped_gracefully():
    matrices = build_semester_matrix_documents()
    matrices[0]["courseReferences"].append({"courseNumber": "99999999"})
    context = build_matrix_planner_context()
    pools = build_candidate_pools(
        catalog_courses=context["catalogCourses"],
        graduation_progress=context["graduationProgress"],
        semester_matrix_documents=matrices,
        program_code="009216-1-000",
        completed_course_ids=set(),
    )
    numbers = [course["number"] for course in pools["mandatoryCandidates"]]
    assert "99999999" not in numbers
    assert "00940345" in numbers


def test_duplicate_matrix_course_references_are_deduped():
    matrices = [
        {
            "requirementGroupId": "009216-1-000:semester-1-matrix",
            "ruleExpression": {"type": "semester_matrix", "semester": 1},
            "courseReferences": [{"courseNumber": "00940345"}, {"courseNumber": "00940345"}],
        },
        {
            "requirementGroupId": "009216-1-000:semester-2-matrix",
            "ruleExpression": {"type": "semester_matrix", "semester": 2},
            "courseReferences": [{"courseNumber": "00940345"}],
        },
    ]
    context = build_matrix_planner_context()
    mandatory = _mandatory_from_semester_matrix(
        matrices,
        {str(course["_id"]): course for course in context["catalogCourses"]},
        {course["courseNumber"]: course for course in context["catalogCourses"]},
        set(),
    )
    assert len(mandatory) == len({course["number"] for course in mandatory})


def test_half_credit_increments_respected_in_workload():
    context = build_matrix_planner_context()
    context["catalogCourses"][0]["credits"] = 3.5
    plan = generate_deterministic_semester_plan(
        profile=context["profile"],
        degree=context["degree"],
        catalog_courses=context["catalogCourses"],
        graduation_progress=context["graduationProgress"],
        completed_course_records=[],
        semester_matrix_documents=context["semesterMatrixDocuments"],
        semester_code="2025-2",
        max_credits=3.5,
    )
    assert plan["explanation"]["totalRecommendedCredits"] == 3.5


def test_profile_default_max_credits_used_when_omitted():
    context = build_matrix_planner_context()
    context["profile"]["preferences"]["maxCreditsPerSemester"] = 7
    plan = generate_deterministic_semester_plan(
        profile=context["profile"],
        degree=context["degree"],
        catalog_courses=context["catalogCourses"],
        graduation_progress=context["graduationProgress"],
        completed_course_records=[],
        semester_matrix_documents=context["semesterMatrixDocuments"],
        semester_code="2025-2",
    )
    assert plan["explanation"]["maxCredits"] == 7
    assert plan["explanation"]["totalRecommendedCredits"] <= 7


def test_plan_is_deterministic_for_identical_inputs():
    kwargs = {"max_credits": 9}
    first = _plan(**kwargs)
    second = _plan(**kwargs)
    assert first["semesters"] == second["semesters"]
    assert first["explanation"]["summary"] == second["explanation"]["summary"]


def test_total_recommended_credits_never_exceeds_max_credits():
    for max_credits in [0, 3, 3.5, 6, 9, 12, 18, 36]:
        plan = _plan(max_credits=max_credits)
        assert plan["explanation"]["totalRecommendedCredits"] <= round_credits(max_credits)


def test_mandatory_remaining_before_plan_matches_uncompleted_matrix_courses():
    plan = _plan(max_credits=18)
    assert plan["explanation"]["mandatoryRemainingBeforePlan"] == 4


def test_planner_performance_under_repeated_generation():
    start = time.perf_counter()
    for _ in range(200):
        _plan(max_credits=12)
    elapsed_ms = (time.perf_counter() - start) * 1000
    assert elapsed_ms < 2000, f"200 plans took {elapsed_ms:.1f}ms"


def test_matrix_semester_sorting_with_missing_semester_field():
    matrices = [
        {
            "requirementGroupId": "x:semester-9-matrix",
            "ruleExpression": {"type": "semester_matrix"},
            "courseReferences": [{"courseNumber": "00940412"}],
        },
        {
            "requirementGroupId": "x:semester-1-matrix",
            "ruleExpression": {"type": "semester_matrix", "semester": 1},
            "courseReferences": [{"courseNumber": "00940345"}],
        },
    ]
    context = build_matrix_planner_context()
    mandatory = _mandatory_from_semester_matrix(
        matrices,
        {str(course["_id"]): course for course in context["catalogCourses"]},
        {course["courseNumber"]: course for course in context["catalogCourses"]},
        set(),
    )
    assert mandatory[0]["number"] == "00940345"


def test_fallback_when_no_semester_matrix_uses_graduation_remaining():
    context = build_matrix_planner_context()
    context["graduationProgress"]["remainingMandatoryCourses"] = [
        {"courseId": S1_COURSE_A, "courseNumber": "00940345", "courseTitle": "Discrete Math"},
    ]
    pools = build_candidate_pools(
        catalog_courses=context["catalogCourses"],
        graduation_progress=context["graduationProgress"],
        semester_matrix_documents=[],
        completed_course_ids=set(),
    )
    assert len(pools["mandatoryCandidates"]) == 1
    assert pools["mandatoryCandidates"][0]["number"] == "00940345"
