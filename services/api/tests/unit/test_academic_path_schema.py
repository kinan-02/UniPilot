"""Unit tests for academic path schemas."""

from __future__ import annotations

from app.schemas.academic_path import AcademicPathSelection, StudentAcademicPath


def test_academic_path_selection_strips_optional_fields():
    selection = AcademicPathSelection(
        kind="bsc_track",
        trackSlug="  track-data-information-engineering  ",
        programCode=" 009216-1-000 ",
        label="  IE track ",
    )
    assert selection.trackSlug == "track-data-information-engineering"
    assert selection.programCode == "009216-1-000"
    assert selection.label == "IE track"


def test_academic_path_selection_blank_strings_become_none():
    selection = AcademicPathSelection(kind="minor", trackSlug="   ")
    assert selection.trackSlug is None


def test_student_academic_path_strips_track_slug():
    path = StudentAcademicPath(trackSlug="  track-data-information-engineering ")
    assert path.trackSlug == "track-data-information-engineering"


def test_student_academic_path_blank_track_slug_becomes_none():
    path = StudentAcademicPath(trackSlug="   ")
    assert path.trackSlug is None


def test_student_academic_path_none_track_slug():
    path = StudentAcademicPath(trackSlug=None)
    assert path.trackSlug is None


def test_academic_path_selection_none_optional_fields():
    selection = AcademicPathSelection(kind="minor", trackSlug=None)
    assert selection.trackSlug is None
