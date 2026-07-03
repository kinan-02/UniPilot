"""ISE elective-faculty bucket assignment regression (vault catalog semantics)."""

from __future__ import annotations

from datetime import datetime, timezone
from bson import ObjectId

from app.services.graduation_progress_calculator import calculate_graduation_progress

PROGRAM = "009118-1-000"


def _program(**overrides):
    base = {
        "_id": ObjectId(),
        "programCode": PROGRAM,
        "name": "Information Systems Engineering",
        "totalCredits": 155.0,
        "catalogYear": 2025,
        "catalogVersion": "2025-2026",
    }
    base.update(overrides)
    return base


def _bucket(suffix: str, min_credits: float, *, mandatory: bool = True):
    return {
        "_id": ObjectId(),
        "requirementGroupId": f"{PROGRAM}:{suffix}",
        "title": suffix,
        "requirementType": "core" if suffix == "core-mandatory" else "elective",
        "minCredits": min_credits,
        "isMandatory": mandatory,
        "ruleExpression": {"type": "credit_bucket", "operator": "min_credits"},
    }


def _catalog(course_id: str, number: str, credits: float):
    return {
        course_id: {
            "_id": ObjectId(course_id),
            "courseNumber": number,
            "title": number,
            "credits": credits,
        }
    }


def _completion(course_id: str, grade: int, credits: float):
    return {
        "courseId": ObjectId(course_id),
        "grade": grade,
        "creditsEarned": credits,
        "semesterCode": "2024-1",
        "recordedAt": datetime(2024, 6, 1, tzinfo=timezone.utc),
    }


def _ise_pools():
    return [
        {
            "requirementGroupId": f"{PROGRAM}:is-additional-faculty-electives",
            "linkedCreditBucketId": f"{PROGRAM}:elective-faculty",
            "ruleExpression": {
                "type": "course_pool",
                "operator": "min_credits",
                "allowedPrefixes": ["0094", "0095", "0096", "0097"],
            },
            "courseReferences": [],
        },
        {
            "requirementGroupId": f"{PROGRAM}:is-focus-chain-ml",
            "linkedCreditBucketId": f"{PROGRAM}:elective-faculty",
            "ruleExpression": {
                "type": "course_pool",
                "operator": "choose_chain",
                "chooseCount": 3,
            },
            "courseReferences": [
                {"courseNumber": "00970215"},
                {"courseNumber": "00970209"},
                {"courseNumber": "00970247"},
            ],
        },
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


def test_ise_faculty_electives_assign_by_pool_specificity_not_broad_prefix():
    mandatory_id = str(ObjectId())
    ml_id = str(ObjectId())
    additional_id = str(ObjectId())
    catalog = {}
    catalog.update(_catalog(mandatory_id, "00940312", 4.0))
    catalog.update(_catalog(ml_id, "00970215", 3.0))
    catalog.update(_catalog(additional_id, "00960266", 3.5))

    progress = calculate_graduation_progress(
        degree_program=_program(),
        hard_requirements=[
            _bucket("core-mandatory", 107.5),
            _bucket("elective-faculty", 35.5),
            _bucket("enrichment", 6.0, mandatory=False),
            _bucket("physical-education", 2.0, mandatory=False),
        ],
        pool_documents=_ise_pools(),
        catalog_courses_by_id=catalog,
        completed_course_records=[
            _completion(mandatory_id, 80, 4.0),
            _completion(ml_id, 84, 3.0),
            _completion(additional_id, 82, 3.5),
        ],
        semester_matrix_documents=[
            {"courseReferences": [{"courseNumber": "00940312"}]},
        ],
    )
    faculty = next(
        entry
        for entry in progress["requirementProgress"]
        if entry["requirementGroupId"].endswith(":elective-faculty")
    )
    assert faculty["creditsCompleted"] == 6.5
    numbers = {course["courseNumber"] for course in faculty["completedCourses"]}
    assert numbers == {"00970215", "00960266"}
    assert all(course.get("assignedPoolGroupId") for course in faculty["completedCourses"])
    core = next(
        entry
        for entry in progress["requirementProgress"]
        if entry["requirementGroupId"].endswith(":core-mandatory")
    )
    assert any(course["courseNumber"] == "00940312" for course in core["completedCourses"])


def test_ise_enrichment_and_pe_use_prefix_pools():
    enrichment_id = str(ObjectId())
    pe_id = str(ObjectId())
    catalog = {}
    catalog.update(_catalog(enrichment_id, "03940501", 3.0))
    catalog.update(_catalog(pe_id, "03940806", 1.0))

    progress = calculate_graduation_progress(
        degree_program=_program(),
        hard_requirements=[
            _bucket("enrichment", 6.0, mandatory=False),
            _bucket("physical-education", 2.0, mandatory=False),
        ],
        pool_documents=_ise_pools(),
        catalog_courses_by_id=catalog,
        completed_course_records=[
            _completion(enrichment_id, 90, 3.0),
            _completion(pe_id, 95, 1.0),
        ],
        semester_matrix_documents=[],
    )
    enrichment = next(
        entry
        for entry in progress["requirementProgress"]
        if entry["requirementGroupId"].endswith(":enrichment")
    )
    pe = next(
        entry
        for entry in progress["requirementProgress"]
        if entry["requirementGroupId"].endswith(":physical-education")
    )
    assert enrichment["creditsCompleted"] == 3.0
    assert pe["creditsCompleted"] == 1.0
