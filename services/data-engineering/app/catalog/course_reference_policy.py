"""Shared course-reference policy for vault export, staging quality, and promotion."""

from __future__ import annotations

from difflib import SequenceMatcher
from typing import Any, Literal

from app.sources.technion_course_json import is_dds_faculty
from app.sources.technion_course_json_index import CourseOfferingRecord

KNOWN_OCR_CORRECTIONS: dict[str, str | None] = {
    "00906292": "00960292",
    "02300401": None,
}

DDS_COURSE_NUMBER_PREFIXES = frozenset(
    {
        "0090",
        "0091",
        "0094",
        "0095",
        "0096",
        "0097",
        "0098",
    }
)

CROSS_FACULTY_COURSE_PREFIXES = frozenset(
    {
        "0014",
        "0040",
        "0044",
        "0104",
        "0114",
        "0216",
        "0234",
        "0324",
    }
)

MissingReferenceClassification = Literal[
    "ingestible",
    "production_excluded",
    "cross_faculty",
    "ocr_suspect",
    "missing",
]


def is_dds_scoped_course_number(course_number: str) -> bool:
    return len(course_number) >= 4 and course_number[:4] in DDS_COURSE_NUMBER_PREFIXES


def is_cross_faculty_course_reference(course_number: str) -> bool:
    if not course_number or len(course_number) < 4:
        return False
    if is_dds_scoped_course_number(course_number):
        return False
    return course_number[:4] in CROSS_FACULTY_COURSE_PREFIXES


def build_dds_promotion_course_number_set(
    course_index: dict[str, CourseOfferingRecord],
) -> set[str]:
    """Course numbers eligible for DDS production course ingestion."""
    return {
        course_number
        for course_number, record in course_index.items()
        if is_dds_faculty(record.faculty)
    }


def collect_catalog_course_numbers(document: dict[str, Any]) -> set[str]:
    numbers: set[str] = set()
    for program in document.get("programs", []):
        for group in program.get("requirementGroups", []):
            for ref in group.get("courseReferences", []):
                number = ref.get("courseNumber")
                if number:
                    numbers.add(str(number))
    return numbers


def derive_production_excluded_course_numbers(
    catalog_numbers: set[str],
    *,
    ingestible_course_numbers: set[str],
) -> list[str]:
    """Catalog refs that remain reference-only and must not become production courses."""
    return sorted(number for number in catalog_numbers if number not in ingestible_course_numbers)


def derive_production_excluded_from_refs(
    catalog_refs: set[str],
    ingestible_course_numbers: set[str],
) -> set[str]:
    return catalog_refs - ingestible_course_numbers


def _similarity(left: str, right: str) -> float:
    return SequenceMatcher(None, left, right).ratio()


def find_dds_ocr_neighbor_matches(
    missing_number: str,
    ingestible_course_numbers: set[str],
    *,
    min_similarity: float = 0.75,
) -> list[str]:
    """Likely DDS OCR typos: similar course numbers within the DDS ingest scope."""
    if not is_dds_scoped_course_number(missing_number):
        return []

    neighbors: list[str] = []
    scored: list[tuple[float, str]] = []
    for candidate in ingestible_course_numbers:
        if candidate == missing_number:
            continue
        if not is_dds_scoped_course_number(candidate):
            continue
        ratio = _similarity(missing_number, candidate)
        if ratio >= min_similarity or (
            missing_number[:5] == candidate[:5] and abs(len(missing_number) - len(candidate)) <= 1
        ):
            scored.append((ratio, candidate))
    scored.sort(reverse=True)
    for _ratio, candidate in scored[:3]:
        if candidate not in neighbors:
            neighbors.append(candidate)
    return neighbors


def classify_missing_course_reference(
    course_number: str,
    *,
    ingestible_course_numbers: set[str],
    production_excluded_course_numbers: set[str],
    neighbor_matches: list[str] | None = None,
) -> MissingReferenceClassification:
    if course_number in KNOWN_OCR_CORRECTIONS:
        return "ocr_suspect"
    if course_number in ingestible_course_numbers:
        return "ingestible"
    if course_number in production_excluded_course_numbers:
        return "production_excluded"
    if is_cross_faculty_course_reference(course_number):
        return "cross_faculty"
    neighbors = neighbor_matches or find_dds_ocr_neighbor_matches(
        course_number,
        ingestible_course_numbers,
    )
    if neighbors:
        return "ocr_suspect"
    if is_dds_scoped_course_number(course_number):
        return "missing"
    return "cross_faculty"
