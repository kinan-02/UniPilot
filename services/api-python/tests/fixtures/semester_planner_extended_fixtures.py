"""Extended fixtures for semester planner matrix-based mandatory courses."""

from __future__ import annotations

from typing import Any

from bson import ObjectId

PROGRAM_CODE = "009216-1-000"

# Semester 1
S1_COURSE_A = "665f2b0f2a3f7b2a1a9a7c11"
S1_COURSE_B = "665f2b0f2a3f7b2a1a9a7c12"
# Semester 2 — B requires A
S2_COURSE_C = "665f2b0f2a3f7b2a1a9a7c13"
S2_COURSE_D = "665f2b0f2a3f7b2a1a9a7c14"
# Elective pool
ELECTIVE_E = "665f2b0f2a3f7b2a1a9a7c15"
DEGREE_ID = "665f2b0f2a3f7b2a1a9a7d01"


def build_matrix_catalog_course(
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


def build_matrix_completed_record(
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


def build_semester_matrix_documents() -> list[dict[str, Any]]:
    return [
        {
            "requirementGroupId": f"{PROGRAM_CODE}:semester-1-matrix",
            "programCode": PROGRAM_CODE,
            "ruleExpression": {"type": "semester_matrix", "operator": "all_of", "semester": 1},
            "courseReferences": [
                {"courseNumber": "00940345"},
                {"courseNumber": "01040031"},
            ],
        },
        {
            "requirementGroupId": f"{PROGRAM_CODE}:semester-2-matrix",
            "programCode": PROGRAM_CODE,
            "ruleExpression": {"type": "semester_matrix", "operator": "all_of", "semester": 2},
            "courseReferences": [
                {"courseNumber": "00940219"},
                {"courseNumber": "00940412"},
            ],
        },
    ]


def build_matrix_planner_context(
    *,
    completed_course_records: list[dict[str, Any]] | None = None,
    include_elective_pool: bool = True,
) -> dict[str, Any]:
    from app.services.graduation_progress_calculator import calculate_graduation_progress

    degree = {
        "_id": ObjectId(DEGREE_ID),
        "programCode": PROGRAM_CODE,
        "name": "Data Science and Engineering",
        "catalogYear": 2025,
        "catalogVersion": "2025-2026",
    }

    catalog_courses = [
        build_matrix_catalog_course(S1_COURSE_A, number="00940345", title="Discrete Math", credits=4.0),
        build_matrix_catalog_course(S1_COURSE_B, number="01040031", title="Intro CS", credits=3.5),
        build_matrix_catalog_course(
            S2_COURSE_C,
            number="00940219",
            title="Data Structures",
            credits=3.5,
            prerequisites=[S1_COURSE_A],
        ),
        build_matrix_catalog_course(
            S2_COURSE_D,
            number="00940412",
            title="Probability",
            credits=3.0,
            prerequisites_text="00940345",
        ),
        build_matrix_catalog_course(ELECTIVE_E, number="00940411", title="DS Intro", credits=3.5),
    ]

    hard_requirements = [
        {
            "requirementGroupId": f"{PROGRAM_CODE}:core-mandatory",
            "requirementType": "core",
            "minCredits": 108.0,
            "courseReferences": [],
            "ruleExpression": {"type": "credit_bucket", "operator": "min_credits"},
            "isMandatory": True,
        },
        {
            "requirementGroupId": f"{PROGRAM_CODE}:elective-ds",
            "requirementType": "elective",
            "minCredits": 24.5,
            "courseReferences": [],
            "ruleExpression": {"type": "credit_bucket", "operator": "min_credits"},
            "isMandatory": True,
        },
    ]

    pool_documents = []
    if include_elective_pool:
        pool_documents = [
            {
                "requirementGroupId": f"{PROGRAM_CODE}:elective-ds-pool",
                "programCode": PROGRAM_CODE,
                "ruleExpression": {"type": "course_pool", "operator": "choose_credits"},
                "courseReferences": [{"courseNumber": "00940411"}],
                "linkedCreditBucketId": f"{PROGRAM_CODE}:elective-ds",
            }
        ]

    semester_matrix_documents = build_semester_matrix_documents()
    catalog_courses_by_id = {str(course["_id"]): course for course in catalog_courses}

    graduation_progress = calculate_graduation_progress(
        degree_program=degree,
        hard_requirements=hard_requirements,
        pool_documents=pool_documents,
        catalog_courses_by_id=catalog_courses_by_id,
        completed_course_records=completed_course_records or [],
    )

    return {
        "profile": {"preferences": {"maxCreditsPerSemester": 18}},
        "degree": degree,
        "catalogCourses": catalog_courses,
        "hardRequirements": hard_requirements,
        "poolDocuments": pool_documents,
        "semesterMatrixDocuments": semester_matrix_documents,
        "graduationProgress": graduation_progress,
        "completedCourseRecords": completed_course_records or [],
    }
