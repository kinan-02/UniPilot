"""Filter semester-matrix rows to executable mandatory curriculum (exclude advisory slots)."""

from __future__ import annotations

import re
from typing import Any

from app.planning.prerequisite_resolver import canonical_course_number

PLACEHOLDER_COURSE_NUMBERS: frozenset[str] = frozenset({"00000004"})

ADVISORY_MATRIX_MARKERS: tuple[str, ...] = (
    "מקצוע מדעי",
    "קורס מתמטי נוסף",
    "חינוך גופני",
    "(see list)",
    "see list",
    "see 4-year",
    "see above",
)

_VALID_COURSE_NUMBER = re.compile(r"^0\d{6,7}$")


def is_executable_matrix_reference(reference: dict[str, Any]) -> bool:
    """True when a matrix row is a concrete required course, not an advisory placeholder."""
    raw_number = reference.get("courseNumber")
    if raw_number is None:
        return False
    number = str(raw_number).strip()
    if not number or number in PLACEHOLDER_COURSE_NUMBERS:
        return False

    canonical = canonical_course_number(number) or number
    if not _VALID_COURSE_NUMBER.match(canonical):
        return False

    title = " ".join(
        str(reference.get("titleHint") or reference.get("title") or "").split()
    )
    notes_text = " ".join(str(note) for note in (reference.get("notes") or []))
    haystack = f"{title} {notes_text} {number}".lower()
    if any(marker.lower() in haystack for marker in ADVISORY_MATRIX_MARKERS):
        return False

    return True


def filter_executable_matrix_documents(
    semester_matrix_documents: list[dict[str, Any]] | None,
) -> list[dict[str, Any]]:
    """Drop advisory / placeholder matrix rows before mandatory curriculum evaluation."""
    filtered: list[dict[str, Any]] = []
    for document in semester_matrix_documents or []:
        references = [
            reference
            for reference in document.get("courseReferences") or []
            if is_executable_matrix_reference(reference)
        ]
        if not references:
            continue
        filtered.append({**document, "courseReferences": references})
    return filtered
