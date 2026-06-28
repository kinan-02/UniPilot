"""Integration tests for Hebrew and English Technion official transcripts."""

from pathlib import Path

import pytest

from app.services.technion_official_parser import (
    extract_student_id,
    extract_student_name,
    parse_technion_official_transcript,
)
from app.services.pdf_pipeline import parse_technion_transcript_pdf

FIXTURES = Path(__file__).resolve().parent / "fixtures"
REPO_ROOT = Path(__file__).resolve().parents[3]
EXPECTED_COURSE_COUNT = 48
EXPECTED_STUDENT_ID = "211479449"


@pytest.mark.parametrize(
    ("fixture_name", "expected_name"),
    [
        ("technion_transcript_en.txt", "TYMOR IBRAHIM"),
        ("technion_transcript_he.txt", "תימור אבראהים"),
    ],
)
def test_official_transcript_fixture_parses_all_courses(fixture_name, expected_name):
    text = (FIXTURES / fixture_name).read_text(encoding="utf-8")
    courses, warnings = parse_technion_official_transcript(text)

    assert not warnings
    assert len(courses) == EXPECTED_COURSE_COUNT
    assert extract_student_id(text) == EXPECTED_STUDENT_ID
    assert extract_student_name(text) == expected_name

    sample = next(course for course in courses if course.courseNumber == "00940202")
    assert sample.semesterCode == "2021-2"
    assert sample.grade == 79
    assert sample.creditsEarned == 3.5

    english = next(course for course in courses if course.courseNumber == "03240033")
    assert english.grade == 55
    assert english.creditsEarned == 3

    failed_credit_total = sum(
        course.creditsEarned for course in courses if 0 < course.grade < 55
    )
    accumulated = sum(
        course.creditsEarned for course in courses if not (0 < course.grade < 55)
    )
    assert failed_credit_total == 23
    assert accumulated == 116 + english.creditsEarned


@pytest.mark.parametrize(
    "pdf_name",
    ["תדפיס (1).pdf", "תדפיס.pdf"],
)
def test_sample_pdf_files_when_present(pdf_name):
    pdf_path = REPO_ROOT / pdf_name
    if not pdf_path.exists():
        pytest.skip(f"Sample PDF not available: {pdf_name}")

    result = parse_technion_transcript_pdf(pdf_path.read_bytes())
    assert len(result.courses) == EXPECTED_COURSE_COUNT
    assert result.studentId == EXPECTED_STUDENT_ID
    assert result.parseMetadata.pipelineVersion == "0.3.0-official-he-en"
