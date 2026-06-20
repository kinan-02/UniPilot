from bson import ObjectId

from app.services.grade_evaluation import is_passing_grade
from app.services.graduation_progress_calculator import (
    build_effective_completions,
    calculate_graduation_progress,
    is_course_eligible_for_pool,
    round_credits,
)


def test_is_passing_grade_numeric():
    assert is_passing_grade({"grade": 82}) is True
    assert is_passing_grade({"grade": 56}) is True
    assert is_passing_grade({"grade": 55}) is False
    assert is_passing_grade({"grade": 0}) is False


def test_round_credits_supports_half_increments():
    assert round_credits(3.5) == 3.5
    assert round_credits(1.5 + 2) == 3.5


def test_build_effective_completions_uses_best_passing_attempt():
    course_id = str(ObjectId())
    completions = build_effective_completions(
        [
            {
                "courseId": ObjectId(course_id),
                "grade": 40,
                "creditsEarned": 0,
                "semesterCode": "2024-1",
                "recordedAt": "2024-01-01T00:00:00Z",
            },
            {
                "courseId": ObjectId(course_id),
                "grade": 82,
                "creditsEarned": 3.5,
                "semesterCode": "2024-2",
                "recordedAt": "2024-06-01T00:00:00Z",
            },
        ]
    )
    assert len(completions) == 1
    assert next(iter(completions.values()))["creditsEarned"] == 3.5


def test_is_course_eligible_for_pool_list_and_prefix():
    list_pool = {
        "ruleExpression": {"type": "course_pool", "operator": "choose_credits"},
        "courseReferences": [{"courseNumber": "00940411"}],
    }
    prefix_pool = {
        "ruleExpression": {
            "type": "course_pool",
            "operator": "choose_credits",
            "allowedPrefixes": ["094"],
        },
        "courseReferences": [],
    }
    assert is_course_eligible_for_pool("00940411", list_pool) is True
    assert is_course_eligible_for_pool("01040031", list_pool) is False
    assert is_course_eligible_for_pool("09400101", prefix_pool) is True
    assert is_course_eligible_for_pool("00940411", prefix_pool) is False


def test_calculate_progress_enforces_ds_pool_for_elective_bucket():
    program = {
        "_id": ObjectId(),
        "programCode": "009216-1-000",
        "name": "DDS",
        "catalogYear": 2025,
        "catalogVersion": "2025-2026",
        "totalCredits": 155.0,
    }
    course_in_pool = str(ObjectId())
    course_out_pool = str(ObjectId())
    hard_requirements = [
        {
            "_id": ObjectId(),
            "requirementGroupId": "009216-1-000:elective-ds",
            "title": "elective ds",
            "requirementType": "elective",
            "minCredits": 24.5,
            "isMandatory": True,
            "ruleExpression": {"type": "credit_bucket", "operator": "min_credits"},
        }
    ]
    pool_documents = [
        {
            "requirementGroupId": "009216-1-000:elective-ds-pool",
            "ruleExpression": {"type": "course_pool", "operator": "choose_credits"},
            "courseReferences": [{"courseNumber": "00940411"}],
        }
    ]
    catalog = {
        course_in_pool: {
            "_id": course_in_pool,
            "courseNumber": "00940411",
            "title": "DS elective",
            "credits": 3.5,
        },
        course_out_pool: {
            "_id": course_out_pool,
            "courseNumber": "01040031",
            "title": "Calculus",
            "credits": 5.0,
        },
    }
    completed = [
        {
            "courseId": ObjectId(course_in_pool),
            "grade": 88,
            "creditsEarned": 3.5,
            "semesterCode": "2024-1",
        },
        {
            "courseId": ObjectId(course_out_pool),
            "grade": 90,
            "creditsEarned": 5.0,
            "semesterCode": "2024-1",
        },
    ]

    progress = calculate_graduation_progress(
        degree_program=program,
        hard_requirements=hard_requirements,
        pool_documents=pool_documents,
        catalog_courses_by_id=catalog,
        completed_course_records=completed,
    )

    ds_bucket = next(
        item
        for item in progress["requirementProgress"]
        if item["requirementGroupId"] == "009216-1-000:elective-ds"
    )
    assert ds_bucket["creditsCompleted"] == 3.5
    assert ds_bucket["eligibilityEnforcement"] == "strict_pool"
    assert progress["completedCredits"] == 8.5
