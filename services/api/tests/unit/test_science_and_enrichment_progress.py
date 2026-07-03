"""Regression tests for science supplement and CHE enrichment bucket assignment."""

from __future__ import annotations

from bson import ObjectId

from app.services.graduation_progress_calculator import (
    calculate_graduation_progress,
    is_course_eligible_for_pool,
)

PROGRAM = "009216-1-000"


def _catalog_entry(course_id: str, number: str, credits: float) -> dict:
    return {
        str(course_id): {
            "_id": ObjectId(course_id),
            "courseNumber": number,
            "title": number,
            "credits": credits,
        }
    }


def _completion(course_id: str, grade: int, credits: float) -> dict:
    return {
        "courseId": ObjectId(course_id),
        "grade": grade,
        "creditsEarned": credits,
        "semesterCode": "2024-1",
    }


def test_science_supplement_assigns_to_core_mandatory_when_matrix_bucket_full():
    """Biology must count toward science supplement even when core-mandatory is the matrix bucket."""
    biology_id = str(ObjectId())
    filler_a = str(ObjectId())
    filler_b = str(ObjectId())
    matrix_course_id = str(ObjectId())

    catalog = {
        **_catalog_entry(biology_id, "01340058", 3.0),
        **_catalog_entry(filler_a, "00940345", 3.5),
        **_catalog_entry(filler_b, "00940346", 3.5),
        **_catalog_entry(matrix_course_id, "01040031", 5.0),
    }
    hard_requirements = [
        {
            "_id": ObjectId(),
            "requirementGroupId": f"{PROGRAM}:core-mandatory",
            "title": "Required courses",
            "requirementType": "core",
            "minCredits": 10.0,
            "isMandatory": True,
            "ruleExpression": {"type": "credit_bucket", "operator": "min_credits"},
        },
        {
            "_id": ObjectId(),
            "requirementGroupId": f"{PROGRAM}:free-elective",
            "title": "Free electives",
            "requirementType": "elective",
            "minCredits": 4.0,
            "isMandatory": False,
            "ruleExpression": {"type": "credit_bucket", "operator": "min_credits"},
        },
    ]
    pool_documents = [
        {
            "requirementGroupId": f"{PROGRAM}:science-elective-supplement-pool",
            "linkedCreditBucketId": f"{PROGRAM}:core-mandatory",
            "minCredits": 5.5,
            "ruleExpression": {
                "type": "course_pool",
                "operator": "min_credits",
                "physics1CourseNumber": "01140051",
                "physics1mCourseNumber": "01140071",
                "supplementCreditsIfPhysics1m": 4.5,
            },
            "courseReferences": [
                {"courseNumber": "01340058"},
                {"courseNumber": "01140051"},
            ],
        },
    ]
    semester_matrix_documents = [
        {
            "requirementGroupId": f"{PROGRAM}:semester-1-matrix",
            "courseReferences": [{"courseNumber": "01040031", "titleHint": "Calculus 1"}],
        },
    ]
    progress = calculate_graduation_progress(
        degree_program={
            "_id": ObjectId(),
            "programCode": PROGRAM,
            "totalCredits": 155.0,
        },
        hard_requirements=hard_requirements,
        pool_documents=pool_documents,
        catalog_courses_by_id=catalog,
        completed_course_records=[
            _completion(matrix_course_id, 90, 5.0),
            _completion(filler_a, 88, 3.5),
            _completion(filler_b, 87, 3.5),
            _completion(biology_id, 85, 3.0),
        ],
        semester_matrix_documents=semester_matrix_documents,
    )

    core = next(
        entry
        for entry in progress["requirementProgress"]
        if entry["requirementGroupId"] == f"{PROGRAM}:core-mandatory"
    )
    completed_numbers = {course["courseNumber"] for course in core["completedCourses"]}
    assert "01340058" in completed_numbers
    assert not any(
        item.get("courseNumber") == "01340058"
        for item in progress["ineligibleCredits"]
    )
    assert core.get("poolConstraints") is not None


def test_humanities_che_courses_assign_to_enrichment_not_free_elective():
    humanities_a = str(ObjectId())
    humanities_b = str(ObjectId())
    free_only = str(ObjectId())

    catalog = {
        **_catalog_entry(humanities_a, "03240292", 2.0),
        **_catalog_entry(humanities_b, "03240305", 2.0),
        **_catalog_entry(free_only, "00940345", 4.0),
    }
    hard_requirements = [
        {
            "_id": ObjectId(),
            "requirementGroupId": f"{PROGRAM}:enrichment",
            "title": "University enrichment",
            "requirementType": "enrichment",
            "minCredits": 6.0,
            "isMandatory": False,
            "ruleExpression": {"type": "credit_bucket", "operator": "min_credits"},
        },
        {
            "_id": ObjectId(),
            "requirementGroupId": f"{PROGRAM}:free-elective",
            "title": "Free electives",
            "requirementType": "elective",
            "minCredits": 4.0,
            "isMandatory": False,
            "ruleExpression": {"type": "credit_bucket", "operator": "min_credits"},
        },
    ]
    pool_documents = [
        {
            "requirementGroupId": f"{PROGRAM}:enrichment-pool",
            "linkedCreditBucketId": f"{PROGRAM}:enrichment",
            "ruleExpression": {
                "type": "course_pool",
                "operator": "min_credits",
                "allowedPrefixes": ["039405"],
            },
            "courseReferences": [],
        },
    ]
    progress = calculate_graduation_progress(
        degree_program={
            "_id": ObjectId(),
            "programCode": PROGRAM,
            "totalCredits": 155.0,
        },
        hard_requirements=hard_requirements,
        pool_documents=pool_documents,
        catalog_courses_by_id=catalog,
        completed_course_records=[
            _completion(humanities_a, 90, 2.0),
            _completion(humanities_b, 88, 2.0),
            _completion(free_only, 85, 4.0),
        ],
    )

    enrichment = next(
        entry
        for entry in progress["requirementProgress"]
        if entry["requirementGroupId"] == f"{PROGRAM}:enrichment"
    )
    enrichment_numbers = {course["courseNumber"] for course in enrichment["completedCourses"]}
    assert "03240292" in enrichment_numbers
    assert "03240305" in enrichment_numbers
    free = next(
        entry
        for entry in progress["requirementProgress"]
        if entry["requirementGroupId"] == f"{PROGRAM}:free-elective"
    )
    free_numbers = {course["courseNumber"] for course in free["completedCourses"]}
    assert "00940345" in free_numbers
    assert "03240292" not in free_numbers
    assert "03240305" not in free_numbers


def test_mandatory_english_excluded_from_enrichment_pool():
    pool = {
        "requirementGroupId": f"{PROGRAM}:enrichment-pool",
        "ruleExpression": {
            "type": "course_pool",
            "operator": "min_credits",
            "allowedPrefixes": ["032402", "039405"],
            "excludedCourseNumbers": ["03240033"],
        },
        "courseReferences": [],
    }
    assert is_course_eligible_for_pool("03240292", pool, program_code=PROGRAM) is True
    assert is_course_eligible_for_pool("03240033", pool, program_code=PROGRAM) is False
    assert is_course_eligible_for_pool("03940580", pool, program_code=PROGRAM) is True
