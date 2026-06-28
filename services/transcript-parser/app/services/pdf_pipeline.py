"""Technion official transcript PDF parsing pipeline."""

from __future__ import annotations

from typing import Any

import fitz

from app.schemas.parse_result import ParseMetadata, ParseTranscriptResult
from app.services.hebrew_rtl import normalize_transcript_text
from app.services.course_number import normalize_course_number
from app.services.pdf_intake import is_pdf_bytes
from app.services.technion_official_parser import (
    extract_student_id,
    extract_student_name,
    parse_technion_official_transcript,
)
from app.services.text_line_parser import parse_courses_from_text

PIPELINE_VERSION = "0.3.0-official-he-en"
EXTRACTOR_NAME = "pymupdf-text"


def extract_pdf_text(content: bytes) -> tuple[str, int]:
    if not is_pdf_bytes(content):
        raise ValueError("Uploaded file is not a valid PDF")

    document = fitz.open(stream=content, filetype="pdf")
    try:
        page_count = document.page_count
        text_parts: list[str] = []
        for page_index in range(page_count):
            page = document.load_page(page_index)
            text_parts.append(page.get_text("text"))
        return "\n".join(text_parts), page_count
    finally:
        document.close()


def parse_technion_transcript_pdf(content: bytes) -> ParseTranscriptResult:
    text, page_count = extract_pdf_text(content)
    courses, warnings = parse_technion_official_transcript(text)

    if not courses and text.strip():
        normalized = normalize_transcript_text(text)
        courses, fallback_warnings = parse_courses_from_text(normalized)
        warnings.extend(fallback_warnings)

    if not text.strip():
        warnings.append("No extractable text found in PDF; OCR fallback may be required.")
    elif not courses:
        warnings.append("No course rows detected in transcript text.")

    metadata = ParseMetadata(
        pageCount=page_count,
        extractor=EXTRACTOR_NAME,
        pipelineVersion=PIPELINE_VERSION,
        textCharCount=len(text),
        ocrUsed=False,
    )

    return ParseTranscriptResult(
        courses=_normalize_parsed_courses(courses, warnings),
        studentId=extract_student_id(text),
        studentName=extract_student_name(text),
        warnings=_unique_warnings(warnings),
        parseMetadata=metadata,
    )


def _normalize_parsed_courses(
    courses: list,
    warnings: list[str],
) -> list:
    normalized: list = []
    for course in courses:
        canonical = normalize_course_number(course.courseNumber)
        if not canonical:
            warnings.append(f"Dropped invalid course number from parse output: {course.courseNumber}")
            continue
        if canonical != course.courseNumber:
            normalized.append(course.model_copy(update={"courseNumber": canonical}))
        else:
            normalized.append(course)
    return normalized


def _unique_warnings(warnings: list[str]) -> list[str]:
    seen: set[str] = set()
    unique: list[str] = []
    for warning in warnings:
        if warning in seen:
            continue
        seen.add(warning)
        unique.append(warning)
    return unique


def parse_technion_transcript_pdf_public(content: bytes) -> dict[str, Any]:
    return parse_technion_transcript_pdf(content).model_dump()
