"""Stress tests for graduation progress calculator performance."""

from __future__ import annotations

import time

import pytest
from bson import ObjectId

from app.services.graduation_progress_calculator import calculate_graduation_progress

PROGRAM = "009216-1-000"


def _build_large_scenario(course_count: int) -> tuple[dict, list, list, dict, list]:
    program = {
        "_id": ObjectId(),
        "programCode": PROGRAM,
        "name": "DDS",
        "catalogYear": 2025,
        "catalogVersion": "2025-2026",
        "totalCredits": 155.0,
    }
    hard_requirements = [
        {
            "_id": ObjectId(),
            "requirementGroupId": f"{PROGRAM}:elective-ds",
            "title": "elective ds",
            "requirementType": "elective",
            "minCredits": 24.5,
            "isMandatory": True,
            "ruleExpression": {"type": "credit_bucket", "operator": "min_credits"},
        },
        {
            "_id": ObjectId(),
            "requirementGroupId": f"{PROGRAM}:elective-faculty",
            "title": "elective faculty",
            "requirementType": "elective",
            "minCredits": 10.5,
            "isMandatory": True,
            "ruleExpression": {"type": "credit_bucket", "operator": "min_credits"},
        },
        {
            "_id": ObjectId(),
            "requirementGroupId": f"{PROGRAM}:core-mandatory",
            "title": "core",
            "requirementType": "core",
            "minCredits": 108.0,
            "isMandatory": True,
            "ruleExpression": {"type": "credit_bucket", "operator": "min_credits"},
        },
    ]
    pool_documents = [
        {
            "requirementGroupId": f"{PROGRAM}:elective-ds-pool",
            "linkedCreditBucketId": f"{PROGRAM}:elective-ds",
            "ruleExpression": {"type": "course_pool", "operator": "choose_credits"},
            "courseReferences": [{"courseNumber": "00940411"}],
            "enforceInGraduationProgress": True,
        },
        {
            "requirementGroupId": f"{PROGRAM}:elective-faculty-pool",
            "linkedCreditBucketId": f"{PROGRAM}:elective-faculty",
            "ruleExpression": {"type": "course_pool", "allowedPrefixes": ["094"]},
            "courseReferences": [],
            "enforceInGraduationProgress": True,
        },
    ]

    catalog: dict = {}
    completed: list = []
    ds_pool_number = "00940411"

    for index in range(course_count):
        course_id = str(ObjectId())
        if index % 3 == 0:
            number = ds_pool_number
        elif index % 3 == 1:
            number = f"094{index:05d}"[:8]
            if len(number) < 8:
                number = f"094{index:04d}01"
        else:
            number = f"009{index:05d}"[:8]
            if len(number) < 8:
                number = f"009{index:04d}01"

        catalog[course_id] = {
            "_id": course_id,
            "courseNumber": number,
            "title": f"Course {index}",
            "credits": 3.5 if index % 2 == 0 else 3.0,
        }
        completed.append(
            {
                "courseId": ObjectId(course_id),
                "grade": 88,
                "creditsEarned": catalog[course_id]["credits"],
                "semesterCode": "2024-1",
            }
        )

    return program, hard_requirements, pool_documents, catalog, completed


@pytest.mark.parametrize("course_count", [50, 200, 500])
def test_calculator_scales_linearly_with_completed_courses(course_count: int):
    program, requirements, pools, catalog, completed = _build_large_scenario(course_count)

    start = time.perf_counter()
    for _ in range(10):
        progress = calculate_graduation_progress(
            degree_program=program,
            hard_requirements=requirements,
            pool_documents=pools,
            catalog_courses_by_id=catalog,
            completed_course_records=completed,
        )
    elapsed_ms = (time.perf_counter() - start) * 1000 / 10

    assert progress["completedCredits"] > 0
    assert len(progress["requirementProgress"]) == 3
    per_course_budget_ms = 2.0
    assert elapsed_ms < course_count * per_course_budget_ms, (
        f"{course_count} courses took {elapsed_ms:.1f}ms avg (budget {course_count * per_course_budget_ms}ms)"
    )


def test_calculator_empty_inputs_is_fast():
    program = {
        "_id": ObjectId(),
        "programCode": PROGRAM,
        "name": "DDS",
        "totalCredits": 155.0,
    }
    start = time.perf_counter()
    for _ in range(1000):
        calculate_graduation_progress(
            degree_program=program,
            hard_requirements=[],
            pool_documents=[],
            catalog_courses_by_id={},
            completed_course_records=[],
        )
    elapsed_ms = (time.perf_counter() - start) * 1000 / 1000
    assert elapsed_ms < 5.0
