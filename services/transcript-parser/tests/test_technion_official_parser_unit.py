"""Unit tests for Technion official transcript parser helpers."""

from app.services.technion_official_parser import (
    find_body_start,
    finish_block,
    is_course_start,
    is_header_or_footer,
    parse_block_from_index,
    parse_credits_token,
    parse_exemption_grade,
    parse_numeric_grade,
    parse_semester_from_line,
    parse_technion_official_transcript,
    split_title_and_credits,
)


def test_is_header_or_footer_matches_column_headers_only():
    assert is_header_or_footer("SUBJECT") is True
    assert is_header_or_footer("מקצוע") is True
    assert is_header_or_footer("פטור ללא ניקוד") is False
    assert is_header_or_footer("Page 1 of 3") is True


def test_parse_credits_and_grade_validation_helpers():
    assert parse_credits_token("abc") is None
    assert parse_credits_token("40") is None
    assert parse_credits_token("3.25") is None
    assert parse_numeric_grade("abc") is None
    assert parse_numeric_grade("101") is None


def test_split_title_and_credits_supports_english_title_with_separate_credits():
    title, credits = split_title_and_credits("3.5")
    assert title is None
    assert credits == 3.5


def test_split_title_and_credits_supports_hebrew_title_with_trailing_integer_credits():
    title, credits = split_title_and_credits("'מתמטיקה דיסקרטית ת4")
    assert title is not None
    assert credits == 4.0


def test_split_title_and_credits_does_not_split_english_course_names_with_numbers():
    title, credits = split_title_and_credits("Statistics 1")
    assert title == "Statistics 1"
    assert credits is None


def test_parse_semester_from_line_returns_none_when_year_has_no_term():
    assert parse_semester_from_line("2024-2025 academic year") is None


def test_parse_semester_from_line_supports_english_and_hebrew_terms():
    assert parse_semester_from_line("2021-2022 Spring") == "2021-2"
    assert parse_semester_from_line("2022-2023 Winter") == "2022-1"
    assert parse_semester_from_line("חורף  תשפ\"ג2022-2023") == "2022-1"
    assert parse_semester_from_line("2024-2025 Summer") == "2024-3"
    assert parse_semester_from_line("No semester here") is None


def test_parse_exemption_grade_variants():
    assert parse_exemption_grade("Exemption without points")[0] == 0.0
    assert parse_exemption_grade("Exemption with points")[0] == 55.0
    assert parse_exemption_grade("Pass")[0] == 56.0


def test_finish_block_handles_exemption_grade_line():
    block, index = finish_block(
        course_number="03240033",
        index=0,
        lines=["Exemption with points", "2021-2022 Winter"],
        title="Technical English",
        credits=3.0,
        warnings=[],
        confidence=0.9,
    )
    assert block is not None
    assert block.credits_earned == 3.0
    assert block.grade == 55.0
    assert index == 2


def test_finish_block_returns_none_when_grade_invalid():
    block, index = finish_block(
        course_number="00960401",
        index=0,
        lines=["abc", "2024-2025 Spring"],
        title="Course",
        credits=3.0,
        warnings=[],
        confidence=0.9,
    )
    assert block is None
    assert index == 1


def test_finish_block_returns_none_when_index_out_of_range():
    block, index = finish_block(
        course_number="00960401",
        index=1,
        lines=["3.5"],
        title="Course",
        credits=3.0,
        warnings=[],
        confidence=0.9,
    )
    assert block is None
    assert index == 1


def test_parse_block_from_index_handles_exemption_and_invalid_rows():
    lines = [
        "01030015השלמות מתמטיקה פטור ללא ניקוד",
        "2021-2022 Winter",
        "00960401",
        "Course Title",
        "3.5",
        "2024-2025 Spring",
    ]
    block, _ = parse_block_from_index(lines, 0)
    assert block is not None
    assert block.course_number == "01030015"

    invalid_concat, _ = parse_block_from_index(["00960401BadTitle3.x", "2024-2025 Spring"], 0)
    assert invalid_concat is None

    missing_grade, _ = parse_block_from_index(
        ["00960401", "Title", "3.5", "2024-2025 Spring"],
        0,
    )
    assert missing_grade is None

    blank_line_block, _ = parse_block_from_index(
        ["00960401", "", "3.5", "85", "2024-2025 Spring"],
        0,
    )
    assert blank_line_block is not None

    bad_exemption_semester, _ = parse_block_from_index(
        ["01130013", "Exemption without points", "not-a-semester"],
        0,
    )
    assert bad_exemption_semester is None

    bad_concat_semester, _ = parse_block_from_index(
        ["01030015השלמות מתמטיקה פטור ללא ניקוד", "not-a-semester"],
        0,
    )
    assert bad_concat_semester is None

    interrupted, _ = parse_block_from_index(
        ["00960401", "00960402", "Title", "3.5", "85", "2024-2025 Spring"],
        0,
    )
    assert interrupted is None


def test_parse_block_from_index_rejects_non_course_lines():
    block, next_index = parse_block_from_index(["Not a course"], 0)
    assert block is None
    assert next_index == 1


def test_find_body_start_falls_back_to_first_course():
    assert find_body_start(["00960401", "3.5", "85", "2024-2025 Spring"]) == 0
    courses, warnings = parse_technion_official_transcript("   ")
    assert courses == []
    assert warnings == []


def test_finish_block_returns_none_when_semester_missing_after_grade():
    block, index = finish_block(
        course_number="00960401",
        index=0,
        lines=["85"],
        title="Course",
        credits=3.0,
        warnings=[],
        confidence=0.9,
    )
    assert block is None
    assert index == 2


def test_exemption_concat_invalid_when_marker_missing():
    block, next_index = parse_block_from_index(
        ["01030015Missing exemption marker", "2021-2022 Winter"],
        0,
    )
    assert block is None


def test_parse_technion_official_transcript_warns_when_no_rows():
    _, warnings = parse_technion_official_transcript("Header only\nNo courses")
    assert "No course rows detected" in warnings[0]


def test_is_course_start_detects_concatenated_rows():
    assert is_course_start("00960401Data Science3.5") is True
    assert is_course_start("01030015Intro Exemption with points") is False


def test_infer_term_from_semester_line_returns_none_for_unknown_term():
    from app.services.technion_official_parser import infer_term_from_semester_line

    assert infer_term_from_semester_line("2024-2025") is None


def test_extract_student_id_returns_none_without_digits():
    from app.services.semester_context import extract_student_id

    assert extract_student_id("No id in this transcript") is None


def test_exemption_concat_guard_when_exemption_parser_returns_none(monkeypatch):
    from app.services import technion_official_parser as parser_module

    monkeypatch.setattr(parser_module, "parse_exemption_grade", lambda _line: None)
    block, next_index = parse_block_from_index(
        ["01030015השלמות מתמטיקה פטור ללא ניקוד", "2021-2022 Winter"],
        0,
    )
    assert block is None
    assert next_index == 1

