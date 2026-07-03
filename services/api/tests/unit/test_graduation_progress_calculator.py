from bson import ObjectId

from app.services.grade_evaluation import is_passing_grade
from app.services.graduation_progress_calculator import (
    _build_status_summary,
    _pool_allowed_prefixes,
    _pool_course_numbers,
    _recorded_at_timestamp,
    build_effective_completions,
    calculate_graduation_progress,
    is_course_eligible_for_pool,
    round_credits,
)


def test_is_passing_grade_numeric():
    assert is_passing_grade({"grade": 82}) is True
    assert is_passing_grade({"grade": 56}) is True
    assert is_passing_grade({"grade": 55}) is True
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
    assert progress["transcriptCreditsTotal"] == 8.5
    assert progress["degreeAppliedCredits"] == 3.5
    assert len(progress["ineligibleCredits"]) == 1


# ---------------------------------------------------------------------------
# Missing coverage: _recorded_at_timestamp, _pool_course_numbers,
# _pool_allowed_prefixes, _build_status_summary, custom suffix ordering
# ---------------------------------------------------------------------------

def test_recorded_at_timestamp_handles_datetime():
    from datetime import datetime, timezone

    dt = datetime(2024, 6, 1, tzinfo=timezone.utc)
    result = _recorded_at_timestamp(dt)
    assert result == dt.timestamp()


def test_recorded_at_timestamp_handles_invalid_string():
    result = _recorded_at_timestamp("not-a-date")
    assert result == 0.0


def test_recorded_at_timestamp_handles_non_string_non_datetime():
    assert _recorded_at_timestamp(12345) == 0.0
    assert _recorded_at_timestamp(None) == 0.0


def test_pool_course_numbers_returns_empty_for_none():
    assert _pool_course_numbers(None) == set()


def test_pool_allowed_prefixes_returns_empty_for_none():
    assert _pool_allowed_prefixes(None) == []


def test_build_status_summary_mandatory_requirements_met():
    missing = [{"isMandatory": False, "status": "in_progress"}]
    result = _build_status_summary(10.0, missing)
    assert result == "mandatory_requirements_met"


def test_build_status_summary_not_started():
    result = _build_status_summary(0.0, [])
    assert result == "not_started"


def test_build_status_summary_complete():
    result = _build_status_summary(100.0, [])
    assert result == "complete"


def test_build_status_summary_in_progress_when_mandatory_matrix_remains():
    result = _build_status_summary(
        120.0,
        [],
        remaining_mandatory_courses=[{"courseNumber": "00940411"}],
    )
    assert result == "in_progress"


def test_build_status_summary_in_progress_with_mandatory():
    missing = [{"isMandatory": True, "status": "in_progress"}]
    result = _build_status_summary(10.0, missing)
    assert result == "in_progress"


def test_calculate_progress_handles_custom_bucket_suffix():
    """A bucket suffix NOT in BUCKET_EVALUATION_ORDER gets appended to ordered_suffixes."""
    program = {
        "_id": ObjectId(),
        "programCode": "009216-1-000",
        "name": "DDS",
        "totalCredits": 10.0,
    }
    hard_requirements = [
        {
            "_id": ObjectId(),
            "requirementGroupId": "009216-1-000:my-custom-bucket",
            "title": "Custom",
            "requirementType": "mandatory",
            "minCredits": 5.0,
            "isMandatory": True,
            "ruleExpression": {"type": "credit_bucket", "operator": "min_credits"},
        }
    ]
    progress = calculate_graduation_progress(
        degree_program=program,
        hard_requirements=hard_requirements,
        pool_documents=[],
        catalog_courses_by_id={},
        completed_course_records=[],
    )
    # custom suffix processed → some requirement_progress entry
    assert len(progress["requirementProgress"]) == 1


def test_is_passing_grade_numeric():
    assert is_passing_grade({"grade": 82}) is True
    assert is_passing_grade({"grade": 56}) is True
    assert is_passing_grade({"grade": 55}) is True
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
    assert progress["transcriptCreditsTotal"] == 8.5
    assert progress["degreeAppliedCredits"] == 3.5
    assert len(progress["ineligibleCredits"]) == 1
