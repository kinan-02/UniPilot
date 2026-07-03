"""Unit tests for MAS user data quality helpers."""

from __future__ import annotations

from app.services.user_data_quality import (
    build_profile_quality_warnings,
    build_transcript_quality_warnings,
    merge_data_quality,
    normalize_completed_course_numbers,
)


def test_normalize_completed_course_numbers_zero_pads_and_deduplicates() -> None:
    assert normalize_completed_course_numbers(["940139", "00940139", ""]) == ["00940139"]


def test_build_transcript_quality_warnings_flags_unresolved() -> None:
    warnings = build_transcript_quality_warnings(
        completed_record_count=3,
        resolved_completed_count=0,
        unresolved_course_count=2,
        truncated=False,
    )
    assert "transcript_unresolved" in warnings


def test_build_profile_quality_warnings_requires_degree_and_track() -> None:
    warnings = build_profile_quality_warnings(
        {"degreeId": "abc", "academicPath": {}},
        track_slug=None,
    )
    assert warnings == ["track_not_set"]


def test_merge_data_quality_deduplicates() -> None:
    merged = merge_data_quality(["degree_not_selected"], ["track_not_set", "degree_not_selected"])
    assert merged["ok"] is False
    assert merged["warnings"] == ["degree_not_selected", "track_not_set"]
