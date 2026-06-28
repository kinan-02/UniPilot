"""Additional unit tests for text line parser helpers."""

from app.services.text_line_parser import (
    detect_attempt,
    normalize_course_number,
    parse_course_line,
    parse_credits,
    parse_grade,
)


def test_normalize_course_number_left_pads():
    assert normalize_course_number("960401") == "00960401"


def test_parse_grade_and_credits_validation():
    assert parse_grade("101") is None
    assert parse_grade("") is None
    assert parse_credits("3.25") is None
    assert parse_credits("3.0") == 3.0
    assert parse_credits("abc") is None
    assert parse_credits("40") is None


def test_detect_attempt_from_hebrew_marker():
    assert detect_attempt("00960401 Data Science 3.0 85 מועד ב") == 2


def test_parse_course_line_compact_format():
    row = parse_course_line("00960401 3.0 85", semester_code="2024-1")
    assert row is not None
    assert row.course_number == "00960401"
    assert row.grade == 85
    assert row.warnings


def test_parse_course_line_compact_format_accepts_unpadded_number():
    row = parse_course_line("960401 3.0 85", semester_code="2024-1")
    assert row is not None
    assert row.course_number == "00960401"
    assert row.grade == 85


def test_parse_course_line_structured_format_with_title():
    row = parse_course_line(
        "00960401 Introduction to Data Science 3.0 85",
        semester_code="2024-1",
    )
    assert row is not None
    assert row.title == "Introduction to Data Science"
    assert row.confidence == 0.9


def test_parse_course_line_returns_none_without_course_number():
    assert parse_course_line("No course here", semester_code="2024-1") is None


def test_parse_course_line_returns_none_without_semester():
    assert parse_course_line("00960401 3.0 85", semester_code="") is None


def test_parse_course_line_returns_none_for_invalid_structured_values():
    assert parse_course_line("00960401 Data Science 3.0 101", semester_code="2024-1") is None


def test_parse_course_line_returns_none_for_invalid_compact_values():
    assert parse_course_line("00960401 3.0 101", semester_code="2024-1") is None


def test_normalize_parsed_courses_drops_invalid_numbers():
    from app.schemas.parse_result import ParsedCourseEntry

    from app.services import pdf_pipeline

    raw_course = ParsedCourseEntry.model_construct(
        courseNumber="123",
        semesterCode="2024-1",
        grade=85,
        creditsEarned=3.0,
        confidence=0.8,
        warnings=[],
    )
    warnings: list[str] = []
    normalized = pdf_pipeline._normalize_parsed_courses([raw_course], warnings)
    assert normalized == []
    assert warnings


def test_parse_course_line_structured_number_mismatch(monkeypatch):
    from app.services import text_line_parser

    monkeypatch.setattr(
        text_line_parser,
        "_normalized_course_number_from_line",
        lambda _line: "00960401",
    )
    assert parse_course_line("00960402 Title 3.0 85", semester_code="2024-1") is None


def test_parse_course_line_compact_number_mismatch(monkeypatch):
    from app.services import text_line_parser

    monkeypatch.setattr(
        text_line_parser,
        "_normalized_course_number_from_line",
        lambda _line: "00960401",
    )
    assert parse_course_line("00960402 3.0 85", semester_code="2024-1") is None


def test_parse_course_line_relaxed_number_mismatch(monkeypatch):
    from app.services import text_line_parser

    monkeypatch.setattr(
        text_line_parser,
        "_normalized_course_number_from_line",
        lambda _line: "00960401",
    )
    assert parse_course_line("960402 3.0 85", semester_code="2024-1") is None


def test_parse_course_line_relaxed_invalid_grade_returns_none():
    assert parse_course_line("960401 3.0 101", semester_code="2024-1") is None


def test_parse_course_line_returns_none_for_unrecognized_row_shape():
    assert parse_course_line("00960401 Data Science only", semester_code="2024-1") is None
