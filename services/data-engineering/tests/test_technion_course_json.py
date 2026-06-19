"""Tests for Technion course JSON reader/normalizer (Phase 9)."""

from pathlib import Path

from app.sources.technion_course_json import (
    DDS_FACULTY_HEBREW,
    SEMESTER_CODE_LABELS,
    academic_year_from_filename,
    is_dds_faculty,
    read_and_normalize_course_json_files,
    semester_code_from_filename,
)

FIXTURE_201 = Path(__file__).parent / "fixtures" / "courses_2025_201.json"
FIXTURE_202 = Path(__file__).parent / "fixtures" / "courses_2025_202.json"
FIXTURE_200_OTHER = Path(__file__).parent / "fixtures" / "courses_2025_200.json"


def test_semester_and_year_from_filename() -> None:
    path = Path("courses_2025_201.json")
    assert semester_code_from_filename(path) == 201
    assert academic_year_from_filename(path) == 2025
    assert SEMESTER_CODE_LABELS[200] == "winter"
    assert SEMESTER_CODE_LABELS[201] == "spring"
    assert SEMESTER_CODE_LABELS[202] == "summer"


def test_hebrew_field_extraction_and_normalization() -> None:
    result = read_and_normalize_course_json_files([FIXTURE_201])
    course = next(c for c in result.courses if c.courseNumber == "00940345")
    assert course.titleHebrew == "מתמטיקה דיסקרטית ת'"
    assert is_dds_faculty(course.faculty)
    assert course.credits == 4.0
    assert "מספר מקצוע" in course.rawFieldKeys


def test_merge_duplicate_courses_across_semesters() -> None:
    result = read_and_normalize_course_json_files([FIXTURE_201, FIXTURE_202])
    course = next(c for c in result.courses if c.courseNumber == "00940345")
    assert set(course.semestersOffered) == {201, 202}
    assert len(course.sourceFiles) == 2
    assert len(result.offerings) == 3


def test_conflict_warning_on_different_credits() -> None:
    result = read_and_normalize_course_json_files([FIXTURE_201, FIXTURE_202])
    course = next(c for c in result.courses if c.courseNumber == "00940345")
    assert course.credits == 4.0
    assert any("credits conflict" in warning for warning in course.warnings)


def test_dds_only_filter() -> None:
    all_result = read_and_normalize_course_json_files(
        [FIXTURE_201, FIXTURE_200_OTHER],
        dds_only=False,
    )
    dds_result = read_and_normalize_course_json_files(
        [FIXTURE_201, FIXTURE_200_OTHER],
        dds_only=True,
    )
    assert len(all_result.courses) == 3
    assert len(dds_result.courses) == 2
    assert all(is_dds_faculty(course.faculty) for course in dds_result.courses)


def test_invalid_records_do_not_crash_parser() -> None:
    result = read_and_normalize_course_json_files([FIXTURE_202])
    assert len(result.invalid_records) >= 2
    assert result.files_read == 1
