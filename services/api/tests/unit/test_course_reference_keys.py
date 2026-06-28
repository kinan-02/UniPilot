"""Tests for course reference alternative expansion."""

from __future__ import annotations

from app.services.course_reference_keys import (
    build_mandatory_equivalence_groups,
    build_remaining_mandatory_course_entries,
    course_reference_number_keys,
    filter_remaining_mandatory_courses,
    is_mandatory_curriculum_course,
    mandatory_group_for_course,
    merge_overlapping_equivalence_groups,
    resolve_mandatory_bucket_suffix,
)
from app.services.graduation_progress_calculator import is_course_eligible_for_pool


def test_course_reference_number_keys_includes_explicit_and_text_alternatives():
    keys = course_reference_number_keys(
        {
            "courseNumber": "1040065",
            "alternatives": ["1040016"],
            "notes": ["Alt: 01040031 if needed"],
        }
    )
    assert "1040065" in keys
    assert "01040031" in keys
    assert is_mandatory_curriculum_course("1040016", [{"1040065", "1040016", "01040031"}])


def test_mandatory_equivalence_groups_keep_parallel_options_together():
    groups = build_mandatory_equivalence_groups(
        [
            {
                "courseReferences": [
                    {"courseNumber": "1040065", "alternatives": ["1040016"]},
                    {"courseNumber": "01040031"},
                ]
            }
        ]
    )
    assert len(groups) >= 2
    assert mandatory_group_for_course("1040016", groups) == frozenset(
        next(group for group in groups if "1040065" in group)
    )


def test_merge_overlapping_equivalence_groups_unions_duplicate_matrix_rows():
    merged = merge_overlapping_equivalence_groups(
        [
            {"1040065", "1040016"},
            {"1040065"},
            {"01040031"},
        ]
    )
    assert len(merged) == 2
    algebra_group = next(group for group in merged if "1040065" in group)
    assert algebra_group == {"1040065", "1040016"}


def test_filter_remaining_mandatory_courses_drops_completed_parallel():
    groups = build_mandatory_equivalence_groups(
        [
            {
                "courseReferences": [
                    {"courseNumber": "1040065", "alternatives": ["1040016"]},
                    {"courseNumber": "01040031"},
                ]
            }
        ]
    )
    satisfied = {frozenset(groups[0])}
    remaining = filter_remaining_mandatory_courses(
        [
            {"courseId": "matrix:1040065", "courseNumber": "1040065"},
            {"courseId": "matrix:01040031", "courseNumber": "01040031"},
        ],
        [{"courseId": "abc", "courseNumber": "1040016"}],
        satisfied_group_keys=satisfied,
        mandatory_groups=groups,
    )
    assert len(remaining) == 1
    assert remaining[0]["courseNumber"] == "01040031"


def test_resolve_mandatory_bucket_suffix_prefers_core_then_technion():
    buckets = {
        "track-mandatory-courses": {"isMandatory": True},
        "mandatory-technion-and-faculty-courses": {"isMandatory": True},
    }
    assert resolve_mandatory_bucket_suffix(buckets) == "mandatory-technion-and-faculty-courses"
    assert resolve_mandatory_bucket_suffix(
        {"core-mandatory": {"isMandatory": True}, **buckets}
    ) == "core-mandatory"


def test_build_remaining_mandatory_course_entries_skips_satisfied_groups():
    matrix = [
        {"courseReferences": [{"courseNumber": "00940101"}]},
        {"courseReferences": [{"courseNumber": "00940102", "titleHint": "Still needed"}]},
    ]
    groups = build_mandatory_equivalence_groups(matrix)
    satisfied = {frozenset(groups[0])}
    remaining = build_remaining_mandatory_course_entries(matrix, satisfied)
    assert len(remaining) == 1
    assert remaining[0]["courseNumber"] == "00940102"
    assert remaining[0]["courseTitle"] == "Still needed"


def test_build_remaining_mandatory_course_entries_skips_cross_track_satisfied_group():
    matrix = [
        {"courseReferences": [{"courseNumber": "00960221", "titleHint": "E-commerce models"}]},
    ]
    groups = build_mandatory_equivalence_groups(matrix)
    assert any("00960211" in group and "00960221" in group for group in groups)
    satisfied = {frozenset(group) for group in groups if "00960211" in group}
    remaining = build_remaining_mandatory_course_entries(matrix, satisfied)
    assert remaining == []


def test_pool_eligibility_accepts_alternative_listed_on_pool_reference():
    pool = {
        "ruleExpression": {"type": "course_pool", "operator": "choose_credits"},
        "courseReferences": [
            {
                "courseNumber": "0960324",
                "alternatives": ["0980413"],
            }
        ],
    }
    assert is_course_eligible_for_pool("0980413", pool) is True
    assert is_course_eligible_for_pool("00960324", pool) is True
