"""Tests for cross-track course code equivalence."""

from __future__ import annotations

from app.curriculum.cross_track_equivalence import (
    KNOWN_CROSS_TRACK_EQUIVALENCE_GROUPS,
    cross_track_equivalence_sets,
)
from app.services.course_reference_keys import (
    build_mandatory_equivalence_groups,
    merge_with_cross_track_equivalence_groups,
)


def test_known_cross_track_group_links_ecommerce_codes():
    merged = merge_with_cross_track_equivalence_groups([])
    assert len(merged) == 1
    group = merged[0]
    assert "00960211" in group
    assert "00960221" in group


def test_cross_track_sets_include_both_codes():
    sets = cross_track_equivalence_sets()
    assert len(sets) == 1
    assert "00960211" in sets[0]
    assert "00960221" in sets[0]


def test_mandatory_groups_include_cross_track_equivalence():
    groups = build_mandatory_equivalence_groups(
        [
            {
                "courseReferences": [
                    {"courseNumber": "00960221", "titleHint": "E-commerce models"},
                ]
            }
        ]
    )
    ecommerce_group = next(group for group in groups if "00960221" in group)
    assert "00960211" in ecommerce_group


def test_cross_track_pairs_are_documented():
    assert ("00960211", "00960221") in KNOWN_CROSS_TRACK_EQUIVALENCE_GROUPS


def test_empty_matrix_yields_cross_track_only_without_matrix_rows():
    from app.services.course_reference_keys import build_matrix_mandatory_equivalence_groups

    assert build_matrix_mandatory_equivalence_groups(None) == []
    cross_track_only = build_mandatory_equivalence_groups(None)
    assert len(cross_track_only) == 1
    assert "00960211" in cross_track_only[0]
