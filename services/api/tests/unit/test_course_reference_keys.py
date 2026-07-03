"""Tests for course reference alternative expansion."""

from __future__ import annotations

from app.services.course_reference_keys import (
    build_mandatory_course_number_keys,
    build_mandatory_equivalence_groups,
    build_remaining_mandatory_course_entries,
    course_reference_number_keys,
    filter_remaining_mandatory_courses,
    is_mandatory_curriculum_course,
    mandatory_group_for_course,
    merge_overlapping_equivalence_groups,
    resolve_mandatory_bucket_suffix,
    qualifies_for_required_bucket,
    should_skip_redundant_core_bucket,
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


def test_resolve_mandatory_bucket_suffix_prefers_required_over_faculty_and_core():
    buckets = {
        "core": {"isMandatory": True},
        "faculty-electives": {"isMandatory": True},
        "required": {"isMandatory": True},
        "enrichment": {"isMandatory": False},
    }
    assert resolve_mandatory_bucket_suffix(buckets) == "required"


def test_qualifies_for_required_bucket_rejects_pe_overlap_only_group():
    mandatory_groups = [{"02340124"}]
    progress_groups = [
        {"02340124"},
        {"03940800", "03940801", "03940803"},
    ]
    assert qualifies_for_required_bucket(
        "02340124",
        mandatory_equivalence_groups=mandatory_groups,
        progress_equivalence_groups=progress_groups,
    )
    assert not qualifies_for_required_bucket(
        "03940803",
        mandatory_equivalence_groups=mandatory_groups,
        progress_equivalence_groups=progress_groups,
    )


def test_qualifies_for_required_bucket_accepts_overlap_substitute_for_matrix_slot():
    mandatory_groups = [{"02340117"}]
    progress_groups = [{"02340114", "02340117", "02340221"}]
    assert qualifies_for_required_bucket(
        "02340114",
        mandatory_equivalence_groups=mandatory_groups,
        progress_equivalence_groups=progress_groups,
    )


def test_should_skip_redundant_core_bucket_for_cs_style_programs():
    buckets = {
        "required": {"isMandatory": True},
        "enrichment": {"isMandatory": False},
        "physical-education": {"isMandatory": False},
        "core": {"isMandatory": True},
    }
    assert should_skip_redundant_core_bucket("core", buckets) is True
    assert should_skip_redundant_core_bucket("required", buckets) is False


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


def test_filter_remaining_mandatory_ignores_catalog_overlap_groups():
    """Catalog overlap must not satisfy unrelated matrix mandatory slots."""
    matrix_groups = build_mandatory_equivalence_groups(
        [{"courseReferences": [{"courseNumber": "02360343"}]}]
    )
    merged_overlap_group = [{"02360343", "02340292", "02340218"}]
    satisfied = {frozenset(merged_overlap_group[0])}
    remaining = filter_remaining_mandatory_courses(
        [{"courseNumber": "02360343"}],
        [{"courseNumber": "02340292"}],
        satisfied_group_keys=satisfied,
        mandatory_groups=matrix_groups,
    )
    assert len(remaining) == 1
    assert remaining[0]["courseNumber"] == "02360343"

    wrongly_filtered = filter_remaining_mandatory_courses(
        [{"courseNumber": "02360343"}],
        [{"courseNumber": "02340292"}],
        satisfied_group_keys=satisfied,
        mandatory_groups=merged_overlap_group,
    )
    assert wrongly_filtered == []


def test_filter_remaining_mandatory_drops_transcript_completed_even_when_not_assigned():
    remaining = filter_remaining_mandatory_courses(
        [{"courseNumber": "01040031"}, {"courseNumber": "02340123"}],
        [],
        mandatory_groups=[{"01040031"}, {"02340123"}],
        transcript_completed_keys={"01040031"},
    )
    assert len(remaining) == 1
    assert remaining[0]["courseNumber"] == "02340123"


def test_filter_remaining_mandatory_drops_entry_already_in_completed_keys_for_group():
    groups = [{"00940101"}]
    remaining = filter_remaining_mandatory_courses(
        [{"courseNumber": "00940101"}],
        [{"courseNumber": "00940101"}],
        mandatory_groups=groups,
    )
    assert remaining == []


def test_build_mandatory_course_number_keys_collects_all_group_members():
    keys = build_mandatory_course_number_keys(
        [{"courseReferences": [{"courseNumber": "01040031"}]}]
    )
    assert "01040031" in keys


def test_resolve_mandatory_bucket_suffix_falls_back_to_first_mandatory_bucket():
    assert (
        resolve_mandatory_bucket_suffix(
            {"custom-mandatory": {"isMandatory": True}, "elective-ds": {"isMandatory": False}}
        )
        == "custom-mandatory"
    )


def test_build_remaining_mandatory_course_entries_skips_reference_without_keys():
    remaining = build_remaining_mandatory_course_entries(
        [{"courseReferences": [{"notes": ["no numbers here"]}]}],
        set(),
    )
    assert remaining == []


def test_build_remaining_mandatory_course_entries_uses_sorted_key_when_primary_missing():
    remaining = build_remaining_mandatory_course_entries(
        [{"courseReferences": [{"alternatives": ["01040031"], "titleHint": "Alt only"}]}],
        set(),
    )
    assert remaining[0]["courseNumber"] == "01040031"


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
