"""Unit tests for general Technion elective bucket progress."""

from __future__ import annotations

from bson import ObjectId

from app.services.graduation_progress_calculator import calculate_graduation_progress

PROGRAM = "009216-1-000"


def _general_technion_fixtures(*, pe_course: str = "03940800", enrichment_course: str = "03940580"):
    degree_program = {
        "_id": ObjectId(),
        "programCode": PROGRAM,
        "name": "DNE",
        "totalCredits": 155.0,
        "catalogYear": 2025,
        "catalogVersion": "2025-2026",
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
            "requirementGroupId": f"{PROGRAM}:physical-education",
            "title": "Physical Education",
            "requirementType": "enrichment",
            "minCredits": 2.0,
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
        {
            "requirementGroupId": f"{PROGRAM}:physical-education-pool",
            "linkedCreditBucketId": f"{PROGRAM}:physical-education",
            "ruleExpression": {
                "type": "course_pool",
                "operator": "min_credits",
                "allowedPrefixes": ["039408", "039409"],
            },
            "courseReferences": [],
        },
    ]
    catalog_courses_by_id = {
        str(ObjectId()): {
            "_id": ObjectId(),
            "courseNumber": pe_course,
            "title": "Physical Education",
            "credits": 1.0,
        },
        str(ObjectId()): {
            "_id": ObjectId(),
            "courseNumber": enrichment_course,
            "title": "Enrichment",
            "credits": 3.0,
        },
        str(ObjectId()): {
            "_id": ObjectId(),
            "courseNumber": "00940345",
            "title": "Discrete Math",
            "credits": 4.0,
        },
    }
    course_ids = list(catalog_courses_by_id.keys())
    completed_records = [
        {
            "courseId": ObjectId(course_ids[0]),
            "grade": 90,
            "creditsEarned": 1.0,
            "semesterCode": "2025-1",
        },
        {
            "courseId": ObjectId(course_ids[1]),
            "grade": 88,
            "creditsEarned": 3.0,
            "semesterCode": "2025-1",
        },
        {
            "courseId": ObjectId(course_ids[2]),
            "grade": 85,
            "creditsEarned": 4.0,
            "semesterCode": "2025-1",
        },
    ]
    return degree_program, hard_requirements, pool_documents, catalog_courses_by_id, completed_records


def test_physical_education_strict_pool_counts_only_pe_courses():
    (
        degree_program,
        hard_requirements,
        pool_documents,
        catalog_courses_by_id,
        completed_records,
    ) = _general_technion_fixtures()
    progress = calculate_graduation_progress(
        degree_program=degree_program,
        hard_requirements=hard_requirements,
        pool_documents=pool_documents,
        catalog_courses_by_id=catalog_courses_by_id,
        completed_course_records=completed_records,
    )
    pe = next(
        entry
        for entry in progress["requirementProgress"]
        if entry["requirementGroupId"] == f"{PROGRAM}:physical-education"
    )
    assert pe["eligibilityEnforcement"] == "strict_pool"
    assert pe["creditsCompleted"] == 1.0
    assert len(pe["completedCourses"]) == 1


def test_enrichment_strict_pool_rejects_non_enrichment_course():
    (
        degree_program,
        hard_requirements,
        pool_documents,
        catalog_courses_by_id,
        completed_records,
    ) = _general_technion_fixtures()
    progress = calculate_graduation_progress(
        degree_program=degree_program,
        hard_requirements=hard_requirements,
        pool_documents=pool_documents,
        catalog_courses_by_id=catalog_courses_by_id,
        completed_course_records=completed_records,
    )
    enrichment = next(
        entry
        for entry in progress["requirementProgress"]
        if entry["requirementGroupId"] == f"{PROGRAM}:enrichment"
    )
    assert enrichment["eligibilityEnforcement"] == "strict_pool"
    assert enrichment["creditsCompleted"] == 3.0
    ineligible = [
        item for item in progress["ineligibleCredits"] if item.get("bucketSuffix") == "enrichment"
    ]
    assert any(item.get("courseNumber") == "00940345" for item in ineligible)


def test_free_elective_uses_credit_bucket_only():
    (
        degree_program,
        hard_requirements,
        pool_documents,
        catalog_courses_by_id,
        completed_records,
    ) = _general_technion_fixtures()
    progress = calculate_graduation_progress(
        degree_program=degree_program,
        hard_requirements=hard_requirements,
        pool_documents=pool_documents,
        catalog_courses_by_id=catalog_courses_by_id,
        completed_course_records=completed_records,
    )
    free = next(
        entry
        for entry in progress["requirementProgress"]
        if entry["requirementGroupId"] == f"{PROGRAM}:free-elective"
    )
    assert free["eligibilityEnforcement"] == "credit_bucket_only"
