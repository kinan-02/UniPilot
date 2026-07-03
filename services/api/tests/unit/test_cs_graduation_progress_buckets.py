"""Regression tests for CS faculty bucket assignment (wiki catalog semantics)."""

from __future__ import annotations

from datetime import datetime, timezone
from bson import ObjectId

from app.services.graduation_progress_calculator import calculate_graduation_progress
from app.services.graduation_requirement_links import (
    EXPLORER_POOL_CREDIT_BUCKET_SUFFIX,
    credit_bucket_id_for_pool,
)

PROGRAM = "023044-1-000"


def _program(**overrides):
    base = {
        "_id": ObjectId(),
        "programCode": PROGRAM,
        "name": "CS 3-year",
        "catalogYear": 2025,
        "catalogVersion": "2025-2026",
        "totalCredits": 118.5,
    }
    base.update(overrides)
    return base


def _bucket(suffix: str, min_credits: float, *, mandatory: bool, title: str):
    return {
        "_id": ObjectId(),
        "requirementGroupId": f"{PROGRAM}:{suffix}",
        "title": title,
        "requirementType": "core" if suffix == "required" else "elective",
        "minCredits": min_credits,
        "isMandatory": mandatory,
        "ruleExpression": {"type": "credit_bucket", "operator": "min_credits"},
    }


def _catalog(course_id: str, number: str, credits: float):
    return {
        course_id: {
            "_id": course_id,
            "courseNumber": number,
            "title": number,
            "credits": credits,
        }
    }


def _completion(course_id: str, grade: int, credits: float, *, semester: str = "2024-1"):
    return {
        "courseId": ObjectId(course_id),
        "grade": grade,
        "creditsEarned": credits,
        "semesterCode": semester,
        "recordedAt": datetime(2024, 6, 1, tzinfo=timezone.utc),
    }


def test_cs_spec_pool_maps_to_faculty_electives_bucket():
    pool = {"requirementGroupId": f"{PROGRAM}:cs-spec-group-01"}
    assert credit_bucket_id_for_pool(program_code=PROGRAM, pool_document=pool) == (
        f"{PROGRAM}:faculty-electives"
    )


def test_cs_list_b_pool_maps_to_faculty_electives_bucket():
    pool = {"requirementGroupId": f"{PROGRAM}:cs-additional-faculty-electives"}
    assert EXPLORER_POOL_CREDIT_BUCKET_SUFFIX["cs-additional-faculty-electives"] == (
        "faculty-electives"
    )
    assert credit_bucket_id_for_pool(program_code=PROGRAM, pool_document=pool) == (
        f"{PROGRAM}:faculty-electives"
    )


def test_cs_progress_assigns_required_pe_and_faculty_buckets():
    required_course = str(ObjectId())
    pe_course = str(ObjectId())
    faculty_course = str(ObjectId())
    catalog = {}
    catalog.update(_catalog(required_course, "02340124", 4.0))
    catalog.update(_catalog(pe_course, "03940803", 1.0))
    catalog.update(_catalog(faculty_course, "00440252", 5.0))

    hard_requirements = [
        _bucket("required", 84.0, mandatory=True, title="Required"),
        _bucket("faculty-electives", 24.5, mandatory=True, title="Faculty electives"),
        _bucket("physical-education", 2.0, mandatory=False, title="Physical education"),
        _bucket("enrichment", 6.0, mandatory=False, title="Enrichment"),
        _bucket("free-elective", 2.0, mandatory=False, title="Free electives"),
        _bucket("core", 12.0, mandatory=True, title="Core"),
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
        {
            "requirementGroupId": f"{PROGRAM}:cs-spec-group-01",
            "ruleExpression": {"type": "course_pool", "operator": "choose_n", "chooseCount": 3},
            "courseReferences": [{"courseNumber": "00440252"}],
        },
    ]
    semester_matrix = [
        {
            "courseReferences": [
                {"courseNumber": "02340124"},
            ]
        }
    ]

    progress = calculate_graduation_progress(
        degree_program=_program(),
        hard_requirements=hard_requirements,
        pool_documents=pool_documents,
        catalog_courses_by_id=catalog,
        completed_course_records=[
            _completion(required_course, 80, 4.0),
            _completion(pe_course, 95, 1.0),
            _completion(faculty_course, 84, 5.0),
        ],
        semester_matrix_documents=semester_matrix,
    )

    required = next(
        entry for entry in progress["requirementProgress"] if entry["requirementGroupId"].endswith(":required")
    )
    pe = next(
        entry
        for entry in progress["requirementProgress"]
        if entry["requirementGroupId"].endswith(":physical-education")
    )
    faculty = next(
        entry
        for entry in progress["requirementProgress"]
        if entry["requirementGroupId"].endswith(":faculty-electives")
    )

    assert required["creditsCompleted"] == 84.0
    assert required["status"] == "satisfied"
    assert any(course["courseNumber"] == "02340124" for course in required["completedCourses"])
    assert pe["creditsCompleted"] == 1.0
    assert any(course["courseNumber"] == "03940803" for course in pe["completedCourses"])
    assert faculty["creditsCompleted"] == 5.0
    assert any(course["courseNumber"] == "00440252" for course in faculty["completedCourses"])
    assert not any(
        entry["requirementGroupId"].endswith(":core")
        for entry in progress["requirementProgress"]
    )
    assert progress["ineligibleCredits"] == []
