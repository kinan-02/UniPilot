"""Unit tests for catalog overlap groups (מקצועות ללא זיכוי נוסף)."""

from __future__ import annotations

from bson import ObjectId

from app.services.grade_evaluation import resolve_record_numeric_grade
from app.services.catalog_overlap_groups import (
    build_catalog_overlap_groups,
    collect_overlap_partner_numbers,
    exclude_overlap_duplicate_credits,
)
from app.services.course_reference_keys import build_progress_equivalence_groups
from app.services.graduation_progress_calculator import calculate_graduation_progress


def test_build_catalog_overlap_groups_links_intro_cs_variants():
    groups = build_catalog_overlap_groups(
        [
            {
                "courseNumber": "02340114",
                "noAdditionalCreditText": "02340117 02340221",
            },
            {
                "courseNumber": "02340117",
                "noAdditionalCreditText": "02340114 02340221",
            },
        ]
    )
    merged = groups[0]
    assert "02340114" in merged
    assert "02340117" in merged
    assert "02340221" in merged


def test_collect_overlap_partner_numbers():
    partners = collect_overlap_partner_numbers(
        [{"courseNumber": "02340114", "noAdditionalCreditText": "02340117 02340221"}]
    )
    assert partners == {"02340117", "02340221"}


def test_resolve_record_numeric_grade():
    assert resolve_record_numeric_grade({"grade": 70}) == 70.0
    assert resolve_record_numeric_grade({"gradePoints": 88}) == 88.0
    assert resolve_record_numeric_grade({"grade": 70, "gradePoints": 88}) == 70.0


def test_exclude_overlap_duplicate_credits_prefers_latest_completion():
    older_id = str(ObjectId())
    newer_id = str(ObjectId())
    completions = {
        older_id: {
            "creditsEarned": 4.0,
            "recordedAt": "2024-01-01T00:00:00Z",
        },
        newer_id: {
            "creditsEarned": 3.5,
            "recordedAt": "2025-01-01T00:00:00Z",
        },
    }
    catalog = {
        older_id: {"courseNumber": "02340114"},
        newer_id: {"courseNumber": "02340117"},
    }
    excluded = exclude_overlap_duplicate_credits(
        completions,
        catalog,
        [{"02340114", "02340117"}],
        recorded_at_timestamp=lambda value: 0 if value == "2024-01-01T00:00:00Z" else 1,
    )
    assert excluded == {older_id}


def test_exclude_overlap_duplicate_credits_keeps_latest_when_credits_equal():
    older_id = str(ObjectId())
    newer_id = str(ObjectId())
    completions = {
        older_id: {
            "creditsEarned": 4.0,
            "recordedAt": "2024-01-01T00:00:00Z",
        },
        newer_id: {
            "creditsEarned": 4.0,
            "recordedAt": "2025-01-01T00:00:00Z",
        },
    }
    catalog = {
        older_id: {"courseNumber": "02340114"},
        newer_id: {"courseNumber": "02340117"},
    }
    excluded = exclude_overlap_duplicate_credits(
        completions,
        catalog,
        [{"02340114", "02340117"}],
        recorded_at_timestamp=lambda value: 0 if value == "2024-01-01T00:00:00Z" else 1,
    )
    assert excluded == {older_id}


def test_intro_cs_m_satisfies_matrix_chet_requirement():
    program = "009009-1-000"
    completed_id = str(ObjectId())
    catalog = {
        completed_id: {
            "_id": ObjectId(completed_id),
            "courseNumber": "02340114",
            "title": "מבוא למדעי המחשב מ'",
            "credits": 4.0,
            "noAdditionalCreditText": "02340117 02340221",
        },
        "partner": {
            "_id": ObjectId(),
            "courseNumber": "02340117",
            "title": "מבוא למדעי המחשב ח'",
            "credits": 4.0,
            "noAdditionalCreditText": "02340114 02340221",
        },
    }
    progress = calculate_graduation_progress(
        degree_program={
            "_id": ObjectId(),
            "programCode": program,
            "name": "IE",
            "totalCredits": 155.0,
        },
        hard_requirements=[
            {
                "_id": ObjectId(),
                "requirementGroupId": f"{program}:core-mandatory",
                "title": "core",
                "requirementType": "core",
                "minCredits": 108.0,
                "isMandatory": True,
                "ruleExpression": {"type": "credit_bucket", "operator": "min_credits"},
            }
        ],
        pool_documents=[],
        catalog_courses_by_id=catalog,
        completed_course_records=[
            {
                "courseId": ObjectId(completed_id),
                "grade": 88,
                "creditsEarned": 4.0,
                "semesterCode": "2023-1",
            }
        ],
        semester_matrix_documents=[
            {"courseReferences": [{"courseNumber": "02340117", "titleHint": "Intro CS Chet"}]}
        ],
    )
    remaining_numbers = {
        course["courseNumber"] for course in progress["remainingMandatoryCourses"]
    }
    assert "02340117" not in remaining_numbers
    core = next(
        entry
        for entry in progress["requirementProgress"]
        if entry["requirementGroupId"].endswith(":core-mandatory")
    )
    assert any(course["courseNumber"] == "02340114" for course in core["completedCourses"])
    assert progress["completedCredits"] == 4.0


def test_transcript_credits_used_when_catalog_differs():
    program = "009009-1-000"
    completed_id = str(ObjectId())
    catalog = {
        completed_id: {
            "_id": ObjectId(completed_id),
            "courseNumber": "00940345",
            "title": "Sample",
            "credits": 3.5,
        }
    }
    progress = calculate_graduation_progress(
        degree_program={
            "_id": ObjectId(),
            "programCode": program,
            "name": "IE",
            "totalCredits": 155.0,
        },
        hard_requirements=[
            {
                "_id": ObjectId(),
                "requirementGroupId": f"{program}:elective-ds",
                "title": "elective",
                "requirementType": "elective",
                "minCredits": 6.0,
                "isMandatory": False,
                "ruleExpression": {"type": "credit_bucket", "operator": "min_credits"},
            }
        ],
        pool_documents=[],
        catalog_courses_by_id=catalog,
        completed_course_records=[
            {
                "courseId": ObjectId(completed_id),
                "grade": 88,
                "creditsEarned": 4.0,
                "semesterCode": "2020-1",
            }
        ],
    )
    assert progress["completedCredits"] == 4.0
    bucket = progress["requirementProgress"][0]
    entry = bucket["completedCourses"][0]
    assert entry["creditsEarned"] == 4.0
    assert entry["catalogCredits"] == 3.5
    assert entry["creditsFromTranscript"] is True


def test_build_progress_equivalence_groups_merges_matrix_and_catalog_overlap():
    groups = build_progress_equivalence_groups(
        [{"courseReferences": [{"courseNumber": "02340117"}]}],
        [{"courseNumber": "02340114", "noAdditionalCreditText": "02340117"}],
    )
    assert any({"02340114", "02340117"} <= group for group in groups)


def test_dual_overlapping_transcript_courses_count_once_toward_degree():
    older_id = str(ObjectId())
    newer_id = str(ObjectId())
    catalog = {
        older_id: {
            "courseNumber": "02340114",
            "credits": 4.0,
            "noAdditionalCreditText": "02340117",
        },
        newer_id: {
            "courseNumber": "02340117",
            "credits": 3.5,
            "noAdditionalCreditText": "02340114",
        },
    }
    progress = calculate_graduation_progress(
        degree_program={
            "_id": ObjectId(),
            "programCode": "009009-1-000",
            "totalCredits": 155.0,
        },
        hard_requirements=[
            {
                "_id": ObjectId(),
                "requirementGroupId": "009009-1-000:elective-ds",
                "minCredits": 24.5,
                "isMandatory": False,
                "ruleExpression": {"type": "credit_bucket"},
            }
        ],
        pool_documents=[],
        catalog_courses_by_id=catalog,
        completed_course_records=[
            {
                "courseId": ObjectId(older_id),
                "grade": 88,
                "creditsEarned": 4.0,
                "recordedAt": "2024-01-01T00:00:00Z",
            },
            {
                "courseId": ObjectId(newer_id),
                "grade": 90,
                "creditsEarned": 3.5,
                "recordedAt": "2025-01-01T00:00:00Z",
            },
        ],
    )
    assert progress["completedCredits"] == 3.5
    assert progress["transcriptCreditsTotal"] == 3.5
    assert any(
        {"02340114", "02340117"} <= set(group)
        for group in progress["catalogOverlapEquivalenceGroups"]
    )
    overlap_rows = [
        row for row in progress["ineligibleCredits"] if row["reason"] == "overlap_no_additional_credit"
    ]
    assert len(overlap_rows) == 1
    assert overlap_rows[0]["courseNumber"] == "02340114"


def test_matrix_alternatives_without_catalog_overlap_do_not_exclude_transcript_credits():
    older_id = str(ObjectId())
    newer_id = str(ObjectId())
    catalog = {
        older_id: {"courseNumber": "01040031", "credits": 3.5},
        newer_id: {"courseNumber": "01040016", "credits": 3.5},
    }
    progress = calculate_graduation_progress(
        degree_program={
            "_id": ObjectId(),
            "programCode": "009009-1-000",
            "totalCredits": 155.0,
        },
        hard_requirements=[
            {
                "_id": ObjectId(),
                "requirementGroupId": "009009-1-000:core-mandatory",
                "minCredits": 108.0,
                "isMandatory": True,
                "ruleExpression": {"type": "credit_bucket"},
            }
        ],
        pool_documents=[],
        catalog_courses_by_id=catalog,
        completed_course_records=[
            {
                "courseId": ObjectId(older_id),
                "grade": 88,
                "creditsEarned": 3.5,
                "recordedAt": "2024-01-01T00:00:00Z",
            },
            {
                "courseId": ObjectId(newer_id),
                "grade": 90,
                "creditsEarned": 3.5,
                "recordedAt": "2025-01-01T00:00:00Z",
            },
        ],
        semester_matrix_documents=[
            {
                "courseReferences": [
                    {
                        "courseNumber": "01040031",
                        "alternatives": ["01040016"],
                    }
                ]
            }
        ],
    )
    assert progress["transcriptCreditsTotal"] == 7.0
    overlap_rows = [
        row for row in progress["ineligibleCredits"] if row["reason"] == "overlap_no_additional_credit"
    ]
    assert overlap_rows == []
