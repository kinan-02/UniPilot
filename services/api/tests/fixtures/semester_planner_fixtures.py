"""Fixtures for semester planner unit tests."""

from __future__ import annotations

from typing import Any

from bson import ObjectId

FOUNDATIONS = "665f2b0f2a3f7b2a1a9a7c01"
DISCRETE_MATH = "665f2b0f2a3f7b2a1a9a7c02"
DATA_STRUCTURES = "665f2b0f2a3f7b2a1a9a7c03"
ALGORITHMS = "665f2b0f2a3f7b2a1a9a7c05"
MACHINE_LEARNING = "665f2b0f2a3f7b2a1a9a7c07"
DEGREE_ID = "665f2b0f2a3f7b2a1a9a7d01"


def build_catalog_course(
    course_id: str,
    *,
    number: str,
    title: str,
    credits: float = 3.0,
    prerequisites: list[str] | None = None,
    prerequisites_text: str | None = None,
) -> dict[str, Any]:
    return {
        "_id": ObjectId(course_id),
        "courseNumber": number,
        "title": title,
        "credits": credits,
        "prerequisites": [ObjectId(value) for value in (prerequisites or [])],
        "prerequisitesText": prerequisites_text,
    }


def build_completed_record(
    course_id: str,
    *,
    grade: float = 80.0,
    credits_earned: float = 3.0,
) -> dict[str, Any]:
    return {
        "courseId": ObjectId(course_id),
        "grade": grade,
        "creditsEarned": credits_earned,
        "semesterCode": "2024-1",
        "recordedAt": "2024-06-01T00:00:00.000Z",
    }


def build_seed_like_context(*, completed_course_records: list[dict[str, Any]] | None = None) -> dict[str, Any]:
    from app.services.graduation_progress_calculator import calculate_graduation_progress

    degree = {
        "_id": ObjectId(DEGREE_ID),
        "programCode": "CS-BSC",
        "name": "BSc CS",
        "catalogYear": 2025,
        "catalogVersion": "2025.1",
    }

    catalog_courses = [
        build_catalog_course(FOUNDATIONS, number="02340101", title="Foundations"),
        build_catalog_course(DISCRETE_MATH, number="02340102", title="Discrete Math"),
        build_catalog_course(
            DATA_STRUCTURES,
            number="02340201",
            title="Data Structures",
            prerequisites=[FOUNDATIONS],
        ),
        build_catalog_course(
            ALGORITHMS,
            number="02340301",
            title="Algorithms 1",
            prerequisites=[DATA_STRUCTURES],
        ),
        build_catalog_course(
            MACHINE_LEARNING,
            number="02360363",
            title="Machine Learning",
            prerequisites=[ALGORITHMS],
        ),
    ]

    hard_requirements = [
        {
            "_id": ObjectId("665f2b0f2a3f7b2a1a9a7e01"),
            "requirementGroupId": "CS-BSC:core",
            "requirementType": "core",
            "title": "Core courses",
            "ruleExpression": {"type": "course_set", "operator": "all_of"},
            "minCredits": 24,
            "courseReferences": [
                {"courseNumber": "02340101"},
                {"courseNumber": "02340102"},
                {"courseNumber": "02340201"},
                {"courseNumber": "02340301"},
            ],
            "isMandatory": True,
        },
        {
            "_id": ObjectId("665f2b0f2a3f7b2a1a9a7e03"),
            "requirementGroupId": "CS-BSC:elective",
            "requirementType": "elective",
            "title": "Electives",
            "ruleExpression": {"type": "credit_pool", "operator": "min_credits_from_set"},
            "minCredits": 6,
            "courseReferences": [{"courseNumber": "02360363"}],
            "isMandatory": False,
        },
    ]

    catalog_courses_by_id = {str(course["_id"]): course for course in catalog_courses}
    graduation_progress = calculate_graduation_progress(
        degree_program=degree,
        hard_requirements=hard_requirements,
        pool_documents=[],
        catalog_courses_by_id=catalog_courses_by_id,
        completed_course_records=completed_course_records or [],
    )

    semester_matrix_documents = [
        {
            "requirementGroupId": "CS-BSC:semester-1-matrix",
            "ruleExpression": {"type": "semester_matrix", "operator": "all_of", "semester": 1},
            "courseReferences": [
                {"courseNumber": "02340101"},
                {"courseNumber": "02340102"},
            ],
        },
        {
            "requirementGroupId": "CS-BSC:semester-2-matrix",
            "ruleExpression": {"type": "semester_matrix", "operator": "all_of", "semester": 2},
            "courseReferences": [
                {"courseNumber": "02340201"},
                {"courseNumber": "02340301"},
            ],
        },
    ]

    return {
        "profile": {"preferences": {"maxCreditsPerSemester": 18}},
        "degree": degree,
        "catalogCourses": catalog_courses,
        "hardRequirements": hard_requirements,
        "poolDocuments": [],
        "semesterMatrixDocuments": semester_matrix_documents,
        "graduationProgress": graduation_progress,
        "completedCourseRecords": completed_course_records or [],
    }
