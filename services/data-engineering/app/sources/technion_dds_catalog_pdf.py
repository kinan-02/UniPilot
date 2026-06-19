"""Technion DDS faculty catalog PDF extraction (local artifacts only)."""

from __future__ import annotations

import json
import re
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from pypdf import PdfReader

from app.models.extraction_report import ExtractionReport
from app.utils.hebrew_rtl import (
    COURSE_NUMBER_PATTERN,
    PROGRAM_CODE_PATTERN,
    process_hebrew_text,
)

EXTRACTOR_NAME = "pypdf"
SOURCE_TYPE = "technion_dds_catalog_pdf"
LOW_TEXT_THRESHOLD = 50

KNOWN_PROGRAM_CODES: dict[str, dict[str, str]] = {
    "009216-1-000": {
        "sectionType": "program_data_science_engineering",
        "title": "Data Science and Engineering",
        "titleHe": "הנדסה ומדעי הנתונים",
    },
    "009009-1-000": {
        "sectionType": "program_management_operations",
        "title": "Management and Operations Engineering",
        "titleHe": "הנדסה וניהול שיטות",
    },
    "009118-1-000": {
        "sectionType": "program_information_systems",
        "title": "Information Systems Engineering",
        "titleHe": "הנדסת מערכות מידע",
    },
}

SECTION_PATTERNS: list[dict[str, Any]] = [
  {
    "sectionType": "mandatory_courses",
    "keywords": ["חובה", "יסרוק הבוח", "mandatory"],
  },
  {
    "sectionType": "elective_courses",
    "keywords": ["הריחב", "בחירה חופשית", "elective"],
  },
  {
    "sectionType": "credit_requirements",
    "keywords": ["נקודות", "נקודות זכות", "נ\"ז", "'קנ", "credits"],
  },
  {
    "sectionType": "semester_tables",
    "keywords": ["רטסמס", "סמסטר", "semester"],
  },
  {
    "sectionType": "footnotes",
    "keywords": ["הערת שוליים", "footnote", "***", "**", "##"],
  },
  {
    "sectionType": "course_lists",
    "keywords": ["רשימת קורסים", "course list"],
  },
  {
    "sectionType": "requirement_explanations",
    "keywords": ["דרישות", "השלמה", "requirements"],
  },
]


@dataclass(frozen=True)
class ExtractedPage:
    page_number: int
    raw_text: str
    processed_text: str
    character_count: int


@dataclass(frozen=True)
class ExtractionArtifacts:
    pages: list[ExtractedPage]
    report: ExtractionReport
    candidate_sections: dict[str, Any]
    output_directory: Path


def service_root() -> Path:
    return Path(__file__).resolve().parents[2]


def default_output_directory() -> Path:
    return service_root() / "data" / "generated" / "technion" / "dds_catalog"


def resolve_pdf_path(pdf_path: str | None, env_path: str | None = None) -> Path:
    candidate = pdf_path or env_path
    if not candidate:
        raise FileNotFoundError(
            "DDS catalog PDF path is required. Pass --pdf-path or set DDS_CATALOG_PDF_PATH."
        )

    resolved = Path(candidate)
    if not resolved.is_absolute():
        resolved = (Path.cwd() / resolved).resolve()

    if not resolved.exists():
        raise FileNotFoundError(f"DDS catalog PDF not found: {resolved}")
    if not resolved.is_file():
        raise FileNotFoundError(f"DDS catalog PDF path is not a file: {resolved}")
    return resolved


def normalize_course_number(raw_number: str) -> str:
    digits = re.sub(r"\D", "", raw_number)
    if not digits:
        raise ValueError("course number must contain digits")
    return digits.zfill(8)[-8:]


def detect_program_codes(text: str) -> list[dict[str, Any]]:
    hits: list[dict[str, Any]] = []
    seen: set[str] = set()
    for match in PROGRAM_CODE_PATTERN.finditer(text):
        code = match.group(0)
        if code in seen:
            continue
        seen.add(code)
        known = KNOWN_PROGRAM_CODES.get(code, {})
        hits.append(
            {
                "programCode": code,
                "sectionType": known.get("sectionType", "program_unknown"),
                "title": known.get("title", "Unknown program"),
                "titleHe": known.get("titleHe"),
                "manualReviewRequired": True,
                "confidence": "high" if code in KNOWN_PROGRAM_CODES else "low",
            }
        )
    return hits


def detect_course_numbers(text: str, *, page_number: int) -> list[dict[str, Any]]:
    hits: list[dict[str, Any]] = []
    seen_on_page: set[str] = set()
    for match in COURSE_NUMBER_PATTERN.finditer(text):
        normalized = normalize_course_number(match.group(0))
        if normalized in seen_on_page:
            continue
        seen_on_page.add(normalized)
        start = max(0, match.start() - 40)
        end = min(len(text), match.end() + 40)
        hits.append(
            {
                "courseNumber": normalized,
                "pageNumber": page_number,
                "contextSnippet": text[start:end].strip(),
                "manualReviewRequired": True,
                "confidence": "low",
            }
        )
    return hits


def detect_candidate_sections(pages: list[ExtractedPage]) -> dict[str, Any]:
    sections: list[dict[str, Any]] = []
    program_codes: list[dict[str, Any]] = []
    course_hits: list[dict[str, Any]] = []

    for page in pages:
        searchable = f"{page.raw_text}\n{page.processed_text}"
        page_program_codes = detect_program_codes(searchable)
        for program in page_program_codes:
            program_entry = {
                **program,
                "pageNumbers": [page.page_number],
                "snippet": page.processed_text[:240].strip(),
            }
            existing = next(
                (item for item in program_codes if item["programCode"] == program["programCode"]),
                None,
            )
            if existing:
                if page.page_number not in existing["pageNumbers"]:
                    existing["pageNumbers"].append(page.page_number)
            else:
                program_codes.append(program_entry)
                sections.append(program_entry)

        for pattern in SECTION_PATTERNS:
            if any(keyword in searchable for keyword in pattern["keywords"]):
                sections.append(
                    {
                        "sectionType": pattern["sectionType"],
                        "pageNumbers": [page.page_number],
                        "snippet": page.processed_text[:240].strip(),
                        "manualReviewRequired": True,
                        "confidence": "medium",
                    }
                )

        course_hits.extend(
            detect_course_numbers(page.processed_text, page_number=page.page_number)
        )

    if course_hits:
        sections.append(
            {
                "sectionType": "course_lists",
                "pageNumbers": sorted({hit["pageNumber"] for hit in course_hits}),
                "detectedCourseCount": len(course_hits),
                "manualReviewRequired": True,
                "confidence": "medium",
            }
        )

    return {
        "sections": sections,
        "programCodes": program_codes,
        "courseNumberHits": course_hits,
        "manualReviewRequired": True,
        "notes": [
            "Candidate sections are heuristic matches only.",
            "Manual curation is required before staging import.",
        ],
    }


def extract_pdf_pages(pdf_path: Path) -> tuple[list[ExtractedPage], list[str]]:
    warnings: list[str] = []
    reader = PdfReader(str(pdf_path))
    pages: list[ExtractedPage] = []

    for index, page in enumerate(reader.pages, start=1):
        raw_text = page.extract_text() or ""
        if not raw_text.strip():
            warnings.append(f"page {index}: no extractable text")
        _, processed_text = process_hebrew_text(raw_text)
        pages.append(
            ExtractedPage(
                page_number=index,
                raw_text=raw_text,
                processed_text=processed_text,
                character_count=len(processed_text),
            )
        )

    if not pages:
        warnings.append("pdf contains zero pages")

    return pages, warnings


def build_extraction_report(
    *,
    pdf_path: Path,
    pages: list[ExtractedPage],
    warnings: list[str],
    output_directory: Path,
) -> ExtractionReport:
    total_characters = sum(page.character_count for page in pages)
    low_text_pages = [
        page.page_number for page in pages if page.character_count < LOW_TEXT_THRESHOLD
    ]
    extracted_count = sum(1 for page in pages if page.character_count > 0)
    average = total_characters / len(pages) if pages else 0.0

    return ExtractionReport(
        sourceFile=str(pdf_path),
        sourceType=SOURCE_TYPE,
        pageCount=len(pages),
        extractedPageCount=extracted_count,
        totalCharacters=total_characters,
        averageCharactersPerPage=round(average, 2),
        lowTextPages=low_text_pages,
        extractionWarnings=warnings,
        extractorName=EXTRACTOR_NAME,
        createdAt=datetime.now(timezone.utc),
        outputDirectory=str(output_directory),
    )


def write_extraction_artifacts(
    *,
    pages: list[ExtractedPage],
    report: ExtractionReport,
    candidate_sections: dict[str, Any],
    output_directory: Path,
) -> None:
    output_directory.mkdir(parents=True, exist_ok=True)

    pages_payload = [
        {
            "pageNumber": page.page_number,
            "rawText": page.raw_text,
            "processedText": page.processed_text,
            "characterCount": page.character_count,
        }
        for page in pages
    ]

    (output_directory / "extracted_pages.json").write_text(
        json.dumps(pages_payload, ensure_ascii=False, indent=2),
        encoding="utf-8",
    )

    txt_lines = []
    for page in pages:
        txt_lines.append(f"===== PAGE {page.page_number} =====")
        txt_lines.append("--- raw ---")
        txt_lines.append(page.raw_text)
        txt_lines.append("--- processed ---")
        txt_lines.append(page.processed_text)
        txt_lines.append("")
    (output_directory / "extracted_pages.txt").write_text(
        "\n".join(txt_lines),
        encoding="utf-8",
    )

    (output_directory / "extraction_report.json").write_text(
        report.model_dump_json(indent=2),
        encoding="utf-8",
    )

    (output_directory / "candidate_sections.json").write_text(
        json.dumps(candidate_sections, ensure_ascii=False, indent=2),
        encoding="utf-8",
    )


def extract_dds_catalog(
    pdf_path: str | None,
    *,
    env_path: str | None = None,
    output_directory: str | Path | None = None,
) -> ExtractionArtifacts:
    resolved_pdf = resolve_pdf_path(pdf_path, env_path)
    output_dir = Path(output_directory) if output_directory else default_output_directory()
    if not output_dir.is_absolute():
        output_dir = (service_root() / output_dir).resolve()

    pages, warnings = extract_pdf_pages(resolved_pdf)
    candidate_sections = detect_candidate_sections(pages)
    report = build_extraction_report(
        pdf_path=resolved_pdf,
        pages=pages,
        warnings=warnings,
        output_directory=output_dir,
    )
    write_extraction_artifacts(
        pages=pages,
        report=report,
        candidate_sections=candidate_sections,
        output_directory=output_dir,
    )
    return ExtractionArtifacts(
        pages=pages,
        report=report,
        candidate_sections=candidate_sections,
        output_directory=output_dir,
    )


def inspect_dds_catalog(
    pdf_path: str | None,
    *,
    env_path: str | None = None,
) -> dict[str, Any]:
    resolved_pdf = resolve_pdf_path(pdf_path, env_path)
    pages, warnings = extract_pdf_pages(resolved_pdf)
    candidate_sections = detect_candidate_sections(pages)
    report = build_extraction_report(
        pdf_path=resolved_pdf,
        pages=pages,
        warnings=warnings,
        output_directory=default_output_directory(),
    )

    return {
        "sourceFile": report.sourceFile,
        "pageCount": report.pageCount,
        "totalCharacters": report.totalCharacters,
        "averageCharactersPerPage": report.averageCharactersPerPage,
        "lowTextPages": report.lowTextPages,
        "detectedProgramCodes": [
            item["programCode"] for item in candidate_sections["programCodes"]
        ],
        "detectedCourseNumbersCount": len(candidate_sections["courseNumberHits"]),
        "candidateSectionsCount": len(candidate_sections["sections"]),
        "extractionWarnings": report.extractionWarnings,
        "extractorName": report.extractorName,
        "note": "Inspect only — no artifacts written. Manual review required before staging import.",
    }
