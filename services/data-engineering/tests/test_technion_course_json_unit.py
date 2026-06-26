"""Unit tests for app/sources/technion_course_json.py (83% → ~95%)."""

from __future__ import annotations

import json
import tempfile
from pathlib import Path
from unittest.mock import patch

import pytest

from app.sources.technion_course_json import (
    DDS_FACULTY_HEBREW,
    DDS_FACULTY_VARIANTS,
    FILENAME_PATTERN,
    academic_year_from_filename,
    course_staging_key,
    default_course_json_paths,
    is_dds_faculty,
    normalize_faculty_name,
    offering_staging_key,
    read_and_normalize_course_json_files,
    semester_code_from_filename,
    _merge_credits,
    _merge_text_field,
    _parse_credits,
    _schedule_summary,
    _truncate,
)


# ---------------------------------------------------------------------------
# semester_code_from_filename / academic_year_from_filename
# ---------------------------------------------------------------------------

class TestSemesterCodeFromFilename:
    def test_winter_200(self):
        p = Path("courses_2025_200.json")
        assert semester_code_from_filename(p) == 200

    def test_spring_201(self):
        p = Path("courses_2025_201.json")
        assert semester_code_from_filename(p) == 201

    def test_summer_202(self):
        p = Path("courses_2025_202.json")
        assert semester_code_from_filename(p) == 202

    def test_invalid_code_returns_none(self):
        p = Path("courses_2025_999.json")
        assert semester_code_from_filename(p) is None

    def test_no_match_returns_none(self):
        p = Path("some_other_file.json")
        assert semester_code_from_filename(p) is None


class TestAcademicYearFromFilename:
    def test_extracts_year(self):
        p = Path("courses_2025_200.json")
        assert academic_year_from_filename(p) == 2025

    def test_no_match_returns_none(self):
        p = Path("random.json")
        assert academic_year_from_filename(p) is None


# ---------------------------------------------------------------------------
# course_staging_key / offering_staging_key
# ---------------------------------------------------------------------------

class TestStagingKeys:
    def test_course_staging_key(self):
        assert course_staging_key("01234567") == "technion:course:01234567"

    def test_offering_staging_key(self):
        key = offering_staging_key("01234567", 2025, 200)
        assert key == "technion:course-offering:01234567:2025:200"


# ---------------------------------------------------------------------------
# normalize_faculty_name
# ---------------------------------------------------------------------------

class TestNormalizeFacultyName:
    def test_none_returns_none(self):
        assert normalize_faculty_name(None) is None

    def test_empty_string_returns_none(self):
        assert normalize_faculty_name("") is None

    def test_collapses_whitespace(self):
        result = normalize_faculty_name("  פקולטה  למדעים  ")
        assert "  " not in result

    def test_strips_leading_trailing(self):
        assert normalize_faculty_name("  test  ") == "test"

    def test_blank_after_strip_returns_none(self):
        assert normalize_faculty_name("   ") is None


# ---------------------------------------------------------------------------
# is_dds_faculty
# ---------------------------------------------------------------------------

class TestIsDdsFaculty:
    def test_dds_hebrew_exact_match(self):
        assert is_dds_faculty(DDS_FACULTY_HEBREW) is True

    def test_dds_variant_match(self):
        for variant in DDS_FACULTY_VARIANTS:
            assert is_dds_faculty(variant) is True

    def test_other_faculty_false(self):
        assert is_dds_faculty("הפקולטה לכימיה") is False

    def test_none_returns_false(self):
        assert is_dds_faculty(None) is False

    def test_empty_returns_false(self):
        assert is_dds_faculty("") is False

    def test_semester_json_short_faculty_name(self):
        assert is_dds_faculty("מדעי הנתונים וההחלטות") is True


# ---------------------------------------------------------------------------
# _parse_credits
# ---------------------------------------------------------------------------

class TestParseCredits:
    def test_none_returns_none(self):
        assert _parse_credits(None) is None

    def test_empty_string_returns_none(self):
        assert _parse_credits("") is None

    def test_int_converts(self):
        assert _parse_credits(3) == 3.0

    def test_float_string_converts(self):
        assert _parse_credits("3.5") == 3.5

    def test_comma_decimal_converts(self):
        assert _parse_credits("3,5") == 3.5

    def test_invalid_returns_none(self):
        assert _parse_credits("abc") is None


# ---------------------------------------------------------------------------
# _truncate
# ---------------------------------------------------------------------------

class TestTruncate:
    def test_short_text_returned_as_is(self):
        assert _truncate("hello", 100) == "hello"

    def test_none_returns_none(self):
        assert _truncate(None, 50) is None

    def test_empty_returns_none(self):
        assert _truncate("", 50) is None

    def test_whitespace_only_returns_none(self):
        assert _truncate("   ", 50) is None

    def test_long_text_truncated_with_ellipsis(self):
        text = "a" * 200
        result = _truncate(text, 50)
        assert len(result) == 50
        assert result.endswith("...")

    def test_collapses_whitespace(self):
        result = _truncate("hello   world", 50)
        assert result == "hello world"


# ---------------------------------------------------------------------------
# _schedule_summary
# ---------------------------------------------------------------------------

class TestScheduleSummary:
    def test_empty_schedule_returns_none(self):
        assert _schedule_summary([]) is None

    def test_extracts_first_group_summary(self):
        schedule = [{"סוג": "הרצאה", "יום": "ב", "שעה": "10:30"}]
        result = _schedule_summary(schedule)
        assert result is not None
        assert "הרצאה" in result

    def test_missing_keys_still_works(self):
        schedule = [{}]
        result = _schedule_summary(schedule)
        assert result is None or isinstance(result, str)


# ---------------------------------------------------------------------------
# _merge_text_field
# ---------------------------------------------------------------------------

class TestMergeTextField:
    def test_sets_incoming_when_current_none(self):
        result = _merge_text_field(None, "new", field_name="title", source_file="f.json", warnings=[])
        assert result == "new"

    def test_keeps_current_when_incoming_none(self):
        result = _merge_text_field("existing", None, field_name="title", source_file="f.json", warnings=[])
        assert result == "existing"

    def test_keeps_current_on_conflict_and_warns(self):
        warnings: list[str] = []
        result = _merge_text_field("A", "B", field_name="title", source_file="f.json", warnings=warnings)
        assert result == "A"
        assert len(warnings) == 1
        assert "title" in warnings[0]

    def test_returns_incoming_when_same(self):
        result = _merge_text_field("same", "same", field_name="title", source_file="f.json", warnings=[])
        assert result == "same"


# ---------------------------------------------------------------------------
# _merge_credits
# ---------------------------------------------------------------------------

class TestMergeCredits:
    def test_incoming_none_keeps_current(self):
        result = _merge_credits(3.0, None, source_file="f.json", warnings=[])
        assert result == 3.0

    def test_current_none_uses_incoming(self):
        result = _merge_credits(None, 4.0, source_file="f.json", warnings=[])
        assert result == 4.0

    def test_conflict_keeps_current_and_warns(self):
        warnings: list[str] = []
        result = _merge_credits(3.0, 4.0, source_file="f.json", warnings=warnings)
        assert result == 3.0
        assert len(warnings) == 1

    def test_same_value_no_conflict(self):
        result = _merge_credits(3.0, 3.0, source_file="f.json", warnings=[])
        assert result == 3.0


# ---------------------------------------------------------------------------
# read_and_normalize_course_json_files
# ---------------------------------------------------------------------------

def _make_course_entry(
    course_number: str = "01234567",
    title: str = "מבוא לתכנות",
    credits: float = 3.0,
    faculty: str = "הפקולטה למדעי הנתונים וההחלטות",
) -> dict:
    return {
        "general": {
            "מספר מקצוע": course_number,
            "שם מקצוע": title,
            "נקודות": credits,
            "פקולטה": faculty,
            "מסגרת לימודים": "",
            "סילבוס": "",
            "מקצועות קדם": "",
            "מקצועות צמודים": "",
            "מקצועות ללא זיכוי נוסף": "",
            "אחראים": "",
            "הערות": "",
            "מועד א": "",
            "מועד ב": "",
        },
        "schedule": [],
    }


class TestReadAndNormalizeCourseJsonFiles:
    def test_returns_empty_when_no_paths(self):
        result = read_and_normalize_course_json_files([])
        assert result.files_read == 0
        assert result.courses == []

    def test_skips_nonexistent_file(self, tmp_path):
        missing = tmp_path / "courses_2025_200.json"
        result = read_and_normalize_course_json_files([missing])
        assert result.files_read == 0
        assert any("not found" in w for w in result.warnings)

    def test_warns_on_invalid_filename(self, tmp_path):
        bad = tmp_path / "random_name.json"
        bad.write_text("[]")
        result = read_and_normalize_course_json_files([bad])
        assert result.files_read == 0
        assert any("filename" in w.lower() or "semester" in w.lower() for w in result.warnings)

    def test_reads_valid_json_file(self, tmp_path):
        path = tmp_path / "courses_2025_200.json"
        entries = [_make_course_entry("01234567")]
        path.write_text(json.dumps(entries), encoding="utf-8")

        result = read_and_normalize_course_json_files([path])

        assert result.files_read == 1
        assert result.raw_records_read == 1
        assert len(result.courses) == 1
        assert result.courses[0].courseNumber == "01234567"

    def test_skips_non_dict_entries(self, tmp_path):
        path = tmp_path / "courses_2025_200.json"
        path.write_text(json.dumps(["not a dict"]), encoding="utf-8")

        result = read_and_normalize_course_json_files([path])

        assert len(result.invalid_records) == 1
        assert "not a JSON object" in result.invalid_records[0].reason

    def test_skips_missing_general(self, tmp_path):
        path = tmp_path / "courses_2025_200.json"
        path.write_text(json.dumps([{"schedule": []}]), encoding="utf-8")

        result = read_and_normalize_course_json_files([path])

        assert len(result.invalid_records) == 1
        assert "general" in result.invalid_records[0].reason

    def test_skips_invalid_course_number(self, tmp_path):
        path = tmp_path / "courses_2025_200.json"
        entry = _make_course_entry(course_number="INVALID")
        path.write_text(json.dumps([entry]), encoding="utf-8")

        result = read_and_normalize_course_json_files([path])

        assert len(result.invalid_records) == 1

    def test_dds_only_filters_non_dds(self, tmp_path):
        path = tmp_path / "courses_2025_200.json"
        entries = [
            _make_course_entry("01234567", faculty=DDS_FACULTY_HEBREW),
            _make_course_entry("09876543", faculty="פקולטה אחרת"),
        ]
        path.write_text(json.dumps(entries), encoding="utf-8")

        result = read_and_normalize_course_json_files([path], dds_only=True)

        assert all(is_dds_faculty(c.faculty) for c in result.courses)

    def test_merges_same_course_from_two_files(self, tmp_path):
        path1 = tmp_path / "courses_2025_200.json"
        path2 = tmp_path / "courses_2025_201.json"

        entry = _make_course_entry("01234567")
        path1.write_text(json.dumps([entry]), encoding="utf-8")
        path2.write_text(json.dumps([entry]), encoding="utf-8")

        result = read_and_normalize_course_json_files([path1, path2])

        courses = [c for c in result.courses if c.courseNumber == "01234567"]
        assert len(courses) == 1
        assert len(courses[0].semestersOffered) == 2

    def test_warns_on_title_conflict(self, tmp_path):
        path1 = tmp_path / "courses_2025_200.json"
        path2 = tmp_path / "courses_2025_201.json"

        e1 = _make_course_entry("01234567", title="כותרת א")
        e2 = _make_course_entry("01234567", title="כותרת ב")
        path1.write_text(json.dumps([e1]), encoding="utf-8")
        path2.write_text(json.dumps([e2]), encoding="utf-8")

        result = read_and_normalize_course_json_files([path1, path2])

        assert any("titleHebrew" in w or "conflict" in w for w in result.warnings)

    def test_warns_on_credits_conflict(self, tmp_path):
        path1 = tmp_path / "courses_2025_200.json"
        path2 = tmp_path / "courses_2025_201.json"

        e1 = _make_course_entry("01234567", credits=3.0)
        e2 = _make_course_entry("01234567", credits=4.0)
        path1.write_text(json.dumps([e1]), encoding="utf-8")
        path2.write_text(json.dumps([e2]), encoding="utf-8")

        result = read_and_normalize_course_json_files([path1, path2])

        assert any("credits" in w for w in result.warnings)

    def test_warns_when_title_missing(self, tmp_path):
        path = tmp_path / "courses_2025_200.json"
        entry = _make_course_entry("01234567", title="")
        path.write_text(json.dumps([entry]), encoding="utf-8")

        result = read_and_normalize_course_json_files([path])

        assert any("titleHebrew" in w or "missing" in w for w in result.warnings)

    def test_handles_json_decode_error(self, tmp_path):
        path = tmp_path / "courses_2025_200.json"
        path.write_text("{ not valid json }", encoding="utf-8")

        result = read_and_normalize_course_json_files([path])

        assert any("Failed to read" in w for w in result.warnings)

    def test_handles_non_array_json(self, tmp_path):
        path = tmp_path / "courses_2025_200.json"
        path.write_text(json.dumps({"key": "value"}), encoding="utf-8")

        result = read_and_normalize_course_json_files([path])

        assert any("Failed to read" in w for w in result.warnings)

    def test_dds_faculty_count_correct(self, tmp_path):
        path = tmp_path / "courses_2025_200.json"
        entries = [
            _make_course_entry("01234567", faculty=DDS_FACULTY_HEBREW),
            _make_course_entry("02345678", faculty="אחר"),
        ]
        path.write_text(json.dumps(entries), encoding="utf-8")

        result = read_and_normalize_course_json_files([path])

        assert result.dds_faculty_course_count == 1


# ---------------------------------------------------------------------------
# default_course_json_paths
# ---------------------------------------------------------------------------

class TestDefaultCourseJsonPaths:
    def test_returns_list_of_paths(self):
        paths = default_course_json_paths()
        assert isinstance(paths, list)
        for p in paths:
            assert isinstance(p, Path)
