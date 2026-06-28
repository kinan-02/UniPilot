"""Unit tests for PDF pipeline."""

from io import BytesIO

import fitz
import pytest

from app.services.pdf_pipeline import (
    extract_pdf_text,
    parse_technion_transcript_pdf,
    parse_technion_transcript_pdf_public,
)


def test_extract_pdf_text_rejects_non_pdf_bytes():
    with pytest.raises(ValueError, match="not a valid PDF"):
        extract_pdf_text(b"not-a-pdf")


def test_extract_pdf_text_reads_page_content():
    document = fitz.open()
    page = document.new_page()
    page.insert_text((72, 72), "Technion transcript sample")
    buffer = BytesIO()
    document.save(buffer)
    document.close()

    text, page_count = extract_pdf_text(buffer.getvalue())
    assert page_count == 1
    assert "Technion transcript sample" in text


def test_parse_technion_transcript_pdf_public_returns_dict():
    document = fitz.open()
    page = document.new_page()
    page.insert_text((72, 72), "00960401 Data Science 88")
    buffer = BytesIO()
    document.save(buffer)
    document.close()

    payload = parse_technion_transcript_pdf_public(buffer.getvalue())
    assert "courses" in payload
    assert "parseMetadata" in payload


def test_parse_technion_transcript_pdf_returns_metadata():
    document = fitz.open()
    page = document.new_page()
    page.insert_text((72, 72), "00960401 Data Science 88")
    buffer = BytesIO()
    document.save(buffer)
    document.close()

    result = parse_technion_transcript_pdf(buffer.getvalue())
    assert result.parseMetadata.pageCount == 1
    assert result.parseMetadata.textCharCount > 0
    assert result.courses == []


def test_parse_technion_transcript_pdf_normalizes_course_numbers_on_output():
    from app.schemas.parse_result import ParsedCourseEntry

    from app.services import pdf_pipeline

    raw_course = ParsedCourseEntry.model_construct(
        courseNumber="960401",
        semesterCode="2024-1",
        grade=85,
        creditsEarned=3.0,
        confidence=0.8,
        warnings=[],
    )
    warnings: list[str] = []
    normalized = pdf_pipeline._normalize_parsed_courses([raw_course], warnings)
    assert normalized[0].courseNumber == "00960401"
    assert warnings == []
