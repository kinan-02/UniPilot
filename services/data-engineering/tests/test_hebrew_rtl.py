from app.utils.hebrew_rtl import (
    normalize_hebrew_punctuation,
    normalize_whitespace,
    process_hebrew_text,
    reverse_rtl_line_fragment,
)


def test_normalize_whitespace_collapses_spaces_and_blank_lines():
    raw = "  hello   world \n\n\n\ntest  "
    assert normalize_whitespace(raw) == "hello world\ntest"


def test_reverse_rtl_line_fragment_fixes_broken_hebrew_line():
  broken = "םינותנה יעדמ"
  fixed = reverse_rtl_line_fragment(broken)
  assert fixed == "מדעי הנתונים"


def test_reverse_rtl_line_fragment_preserves_program_code():
    line = "009216-1-000 תוכנית"
    processed = reverse_rtl_line_fragment(line)
    assert "009216-1-000" in processed


def test_reverse_rtl_line_fragment_preserves_course_number():
    line = "00960401 יעדמ"
    processed = reverse_rtl_line_fragment(line)
    assert "00960401" in processed


def test_process_hebrew_text_preserves_raw_text():
    raw = "  םינותנה יעדמ  "
    original, processed = process_hebrew_text(raw)
    assert original == raw
    assert "מדעי הנתונים" in processed


def test_normalize_hebrew_punctuation_replaces_dashes():
    assert normalize_hebrew_punctuation("א–ב") == "א-ב"
