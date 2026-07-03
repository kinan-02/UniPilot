"""Regression tests against the sample Technion gradesheet PDF in the repo root."""

from pathlib import Path

from app.services.pdf_pipeline import parse_technion_transcript_pdf

GRADESHEET_PDF = Path(__file__).resolve().parents[3] / "gradesheet.pdf"


def test_gradesheet_pdf_parses_full_credit_total():
    if not GRADESHEET_PDF.is_file():
        return

    result = parse_technion_transcript_pdf(GRADESHEET_PDF.read_bytes())
    assert len(result.courses) == 24
    assert round(sum(course.creditsEarned for course in result.courses), 1) == 70.5

    numeric_weighted = 0.0
    numeric_credits = 0.0
    for course in result.courses:
        if course.creditsEarned <= 0:
            continue
        if course.grade <= 0:
            continue
        if any("pass grade" in warning.lower() for warning in course.warnings):
            continue
        numeric_weighted += course.grade * course.creditsEarned
        numeric_credits += course.creditsEarned

    assert round(numeric_weighted / numeric_credits, 1) == 83.7


def test_gradesheet_pdf_metadata_marks_summary_transcript():
    if not GRADESHEET_PDF.is_file():
        return

    result = parse_technion_transcript_pdf(GRADESHEET_PDF.read_bytes())
    assert result.parseMetadata.transcriptFormat == "technion_official_summary"
    assert result.parseMetadata.showsAllAttempts is False
