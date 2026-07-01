"""Unit tests for shared course attempt helpers."""

from app.services.course_attempts import detect_attempt_from_text


def test_detect_attempt_from_text_recognizes_hebrew_moed_b():
    assert detect_attempt_from_text("85 מועד ב") == 2


def test_detect_attempt_from_text_defaults_to_first_attempt():
    assert detect_attempt_from_text("00960401 Data Science 3.0 85") == 1
