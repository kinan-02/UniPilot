"""Unit tests for semester context helpers."""

from app.services.semester_context import extract_student_id, parse_semester_code


def test_parse_semester_code_accepts_direct_format():
    assert parse_semester_code("2024-1") == "2024-1"
    assert parse_semester_code("2023-2") == "2023-2"


def test_parse_semester_code_accepts_summer_term():
    assert parse_semester_code("2024-3") == "2024-3"


def test_parse_semester_code_from_academic_year_and_hebrew_term():
    assert parse_semester_code("2024-2025 סמסטר א") == "2024-1"
    assert parse_semester_code("2023-2024 Spring semester") == "2023-2"


def test_infer_term_from_english_seasons():
    from app.services.semester_context import infer_term_from_line

    assert infer_term_from_line("Summer term") == 3
    assert infer_term_from_line("Unknown") is None


def test_parse_semester_code_accepts_summer_from_hebrew_heading():
    assert parse_semester_code("2024-2025 סמסטר ג") == "2024-3"


def test_parse_semester_code_returns_none_without_term_hint():
    assert parse_semester_code("2024-2025 academic year") is None
