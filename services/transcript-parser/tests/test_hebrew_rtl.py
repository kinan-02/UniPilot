"""Unit tests for Hebrew RTL normalization."""

from app.services.hebrew_rtl import normalize_transcript_text, reverse_rtl_line_fragment, should_reverse_line


def test_normalize_transcript_text_collapses_blank_lines():
    text = "2024-1\n\n\n00960401 Data Science 3.0 85\n"
    normalized = normalize_transcript_text(text)
    assert "2024-1" in normalized
    assert "\n\n\n" not in normalized


def test_should_reverse_line_for_hebrew_dominant_text():
    line = "מבוא למדעי הנתונים"
    assert should_reverse_line(line) is True
    assert reverse_rtl_line_fragment(line) != line


def test_should_reverse_line_for_empty_line():
    assert should_reverse_line("   ") is False


def test_should_reverse_line_for_mixed_hebrew_ratio():
    line = "x אבגדה הזה טקסט בעברית עם הרבה מילים בעברית"
    assert should_reverse_line(line) is True


def test_should_reverse_line_for_hebrew_with_leading_paren():
    line = "(מבוא למדעי הנתונים"
    assert should_reverse_line(line) is True


def test_extract_student_id_from_header():
    from app.services.semester_context import extract_student_id

    text = "Technion transcript\nStudent: 123456789\n2024-1\n"
    assert extract_student_id(text) == "123456789"
