from app.planning.prerequisite_resolver import extract_course_numbers_from_text
from app.planning.semester_planner import (
    generate_deterministic_semester_plan,
    prerequisites_met,
)
from tests.fixtures.semester_planner_fixtures import (
    ALGORITHMS,
    DATA_STRUCTURES,
    DISCRETE_MATH,
    FOUNDATIONS,
    MACHINE_LEARNING,
    build_catalog_course,
    build_completed_record,
    build_seed_like_context,
)


def test_extract_course_numbers_from_prerequisites_text():
    numbers = extract_course_numbers_from_text("00940345 and 00940411 required")
    assert numbers == ["00940345", "00940411"]


def test_prerequisites_met_requires_all_prerequisite_courses():
    course = build_catalog_course(
        DATA_STRUCTURES,
        number="02340201",
        title="Data Structures",
        prerequisites=[FOUNDATIONS],
    )
    assert prerequisites_met(course, {FOUNDATIONS}) is True
    assert prerequisites_met(course, set()) is False


def test_recommends_mandatory_courses_without_prerequisites_on_empty_transcript():
    context = build_seed_like_context()
    plan = generate_deterministic_semester_plan(
        profile=context["profile"],
        degree=context["degree"],
        catalog_courses=context["catalogCourses"],
        graduation_progress=context["graduationProgress"],
        completed_course_records=context["completedCourseRecords"],
        hard_requirements=context["hardRequirements"],
        semester_matrix_documents=context["semesterMatrixDocuments"],
        semester_code="2025-2",
        max_credits=6,
    )

    recommended_ids = [course["courseId"] for course in plan["semesters"][0]["plannedCourses"]]
    assert FOUNDATIONS in recommended_ids
    assert DISCRETE_MATH in recommended_ids
    assert ALGORITHMS not in recommended_ids
    assert plan["explanation"]["emptyPlan"] is False


def test_does_not_recommend_completed_mandatory_courses():
    context = build_seed_like_context(
        completed_course_records=[build_completed_record(FOUNDATIONS)],
    )
    plan = generate_deterministic_semester_plan(
        profile=context["profile"],
        degree=context["degree"],
        catalog_courses=context["catalogCourses"],
        graduation_progress=context["graduationProgress"],
        completed_course_records=context["completedCourseRecords"],
        hard_requirements=context["hardRequirements"],
        semester_matrix_documents=context["semesterMatrixDocuments"],
        semester_code="2025-2",
        max_credits=12,
    )

    recommended_ids = [course["courseId"] for course in plan["semesters"][0]["plannedCourses"]]
    assert FOUNDATIONS not in recommended_ids


def test_blocks_courses_with_unsatisfied_prerequisites():
    context = build_seed_like_context()
    plan = generate_deterministic_semester_plan(
        profile=context["profile"],
        degree=context["degree"],
        catalog_courses=context["catalogCourses"],
        graduation_progress=context["graduationProgress"],
        completed_course_records=context["completedCourseRecords"],
        hard_requirements=context["hardRequirements"],
        semester_matrix_documents=context["semesterMatrixDocuments"],
        semester_code="2025-2",
        max_credits=3,
    )

    recommended_ids = [course["courseId"] for course in plan["semesters"][0]["plannedCourses"]]
    assert recommended_ids == [FOUNDATIONS]

    blocked_entry = next(
        entry
        for entry in plan["explanation"]["blockedByPrerequisites"]
        if entry["courseId"] == ALGORITHMS
    )
    assert blocked_entry is not None
    assert any(
        missing["courseId"] == DATA_STRUCTURES
        for missing in blocked_entry["missingPrerequisites"]
    )


def test_scheduled_courses_satisfy_prerequisites_for_later_recommendations():
    context = build_seed_like_context(
        completed_course_records=[build_completed_record(FOUNDATIONS)],
    )
    plan = generate_deterministic_semester_plan(
        profile=context["profile"],
        degree=context["degree"],
        catalog_courses=context["catalogCourses"],
        graduation_progress=context["graduationProgress"],
        completed_course_records=context["completedCourseRecords"],
        hard_requirements=context["hardRequirements"],
        semester_matrix_documents=context["semesterMatrixDocuments"],
        semester_code="2025-2",
        max_credits=12,
    )

    recommended_ids = [course["courseId"] for course in plan["semesters"][0]["plannedCourses"]]
    assert DATA_STRUCTURES in recommended_ids


def test_includes_electives_when_mandatory_capacity_allows():
    context = build_seed_like_context(
        completed_course_records=[
            build_completed_record(FOUNDATIONS),
            build_completed_record(DISCRETE_MATH),
            build_completed_record(DATA_STRUCTURES),
            build_completed_record(ALGORITHMS),
        ],
    )
    context["graduationProgress"]["remainingMandatoryCourses"] = []
    context["graduationProgress"]["remainingElectiveCredits"] = 6.0
    context["graduationProgress"]["requirementProgress"] = [
        {
            "requirementType": "elective",
            "status": "not_started",
            "remainingCourses": [
                {
                    "courseId": MACHINE_LEARNING,
                    "courseNumber": "02360363",
                    "courseTitle": "Machine Learning",
                }
            ],
        }
    ]

    plan = generate_deterministic_semester_plan(
        profile=context["profile"],
        degree=context["degree"],
        catalog_courses=context["catalogCourses"],
        graduation_progress=context["graduationProgress"],
        completed_course_records=context["completedCourseRecords"],
        hard_requirements=context["hardRequirements"],
        semester_matrix_documents=context["semesterMatrixDocuments"],
        semester_code="2025-2",
        max_credits=12,
    )

    recommended_ids = [course["courseId"] for course in plan["semesters"][0]["plannedCourses"]]
    assert MACHINE_LEARNING in recommended_ids


def test_respects_max_credits_workload_limit():
    context = build_seed_like_context()
    plan = generate_deterministic_semester_plan(
        profile=context["profile"],
        degree=context["degree"],
        catalog_courses=context["catalogCourses"],
        graduation_progress=context["graduationProgress"],
        completed_course_records=context["completedCourseRecords"],
        hard_requirements=context["hardRequirements"],
        semester_matrix_documents=context["semesterMatrixDocuments"],
        semester_code="2025-2",
        max_credits=3,
    )

    assert plan["explanation"]["totalRecommendedCredits"] <= 3
    assert len(plan["explanation"]["skippedDueToWorkload"]) >= 1
