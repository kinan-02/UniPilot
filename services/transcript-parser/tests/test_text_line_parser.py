"""Unit tests for text line parser."""

from app.services.text_line_parser import parse_courses_from_text


SAMPLE_TRANSCRIPT = """
Student ID 123456789
2024-1
00960401 Introduction to Data Science 3.0 85
00940313 Linear Algebra 5.0 72
2023-2
00960401 Introduction to Data Science 3.0 88
00940201 Calculus 1 5.0 90
"""


def test_parse_courses_from_text_extracts_multiple_semesters():
    courses, warnings = parse_courses_from_text(SAMPLE_TRANSCRIPT)
    assert not warnings or warnings[0] != "No course rows detected in transcript text."
    assert len(courses) == 4
    numbers = {course.courseNumber for course in courses}
    assert "00960401" in numbers
    assert "00940313" in numbers


def test_parse_courses_from_text_assigns_attempt_numbers_for_cross_semester_retakes():
    text = """
2023-2
00960401 Data Science 3.0 40
2024-1
00960401 Data Science 3.0 85
"""
    courses, _ = parse_courses_from_text(text)
    attempts = sorted((course.semesterCode, course.attempt) for course in courses if course.courseNumber == "00960401")
    assert attempts == [("2023-2", 1), ("2024-1", 2)]


def test_parse_courses_from_text_deduplicates_same_course_attempt():
    text = """
2024-1
00960401 Data Science 3.0 85
00960401 Data Science 3.0 90
"""
    courses, _ = parse_courses_from_text(text)
    assert len(courses) == 1
    assert courses[0].grade == 90


def test_parse_courses_from_text_warns_when_no_rows():
    courses, warnings = parse_courses_from_text("Header only\nNo courses here")
    assert courses == []
    assert any("No course rows detected" in warning for warning in warnings)
