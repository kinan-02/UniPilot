"""Parse individual transcript rows from normalized text lines."""

from __future__ import annotations

import re
from dataclasses import dataclass

from app.schemas.parse_result import ParsedCourseEntry
from app.services.course_number import normalize_course_number
from app.services.semester_context import parse_semester_code

COURSE_NUMBER_PATTERN = re.compile(r"\b(0\d{7}|\d{6,8})\b")
STRUCTURED_LINE_PATTERN = re.compile(
    r"^(?P<number>0\d{7})\s+(?P<middle>.+?)\s+(?P<credits>\d+(?:\.\d)?)\s+(?P<grade>\d+(?:\.\d)?)\s*$"
)
COMPACT_LINE_PATTERN = re.compile(
    r"^(?P<number>0\d{7})\s+(?P<credits>\d+(?:\.\d)?)\s+(?P<grade>\d+(?:\.\d)?)\s*$"
)
ATTEMPT_B_PATTERN = re.compile(r"מועד\s*ב|attempt\s*2|2nd\s*attempt", re.IGNORECASE)


@dataclass(frozen=True)
class RawCourseRow:
    course_number: str
    semester_code: str
    grade: float
    credits_earned: float
    attempt: int
    title: str | None
    confidence: float
    warnings: tuple[str, ...]


def normalize_course_number(value: str) -> str | None:
    """Public alias used by tests and fallback parsing."""
    from app.services.course_number import normalize_course_number as _normalize

    return _normalize(value)


def _normalized_course_number_from_line(line: str) -> str | None:
    match = COURSE_NUMBER_PATTERN.search(line)
    if not match:
        return None
    return normalize_course_number(match.group(1))


def is_half_credit_increment(value: float) -> bool:
    return abs(value * 2 - round(value * 2)) < 1e-9


def parse_grade(value: str) -> float | None:
    try:
        numeric = float(value)
    except ValueError:
        return None
    if numeric < 0 or numeric > 100:
        return None
    return numeric


def parse_credits(value: str) -> float | None:
    try:
        numeric = float(value)
    except ValueError:
        return None
    if numeric < 0 or numeric > 36:
        return None
    if not is_half_credit_increment(numeric):
        return None
    return numeric


def detect_attempt(line: str) -> int:
    return 2 if ATTEMPT_B_PATTERN.search(line) else 1


def parse_course_line(line: str, *, semester_code: str) -> RawCourseRow | None:
    if not semester_code:
        return None
    course_number = _normalized_course_number_from_line(line)
    if not course_number:
        return None

    structured = STRUCTURED_LINE_PATTERN.match(line.strip())
    if structured:
        structured_number = normalize_course_number(structured.group("number"))
        if structured_number != course_number:
            return None
        grade = parse_grade(structured.group("grade"))
        credits = parse_credits(structured.group("credits"))
        if grade is None or credits is None:
            return None
        middle = structured.group("middle").strip()
        title = middle if middle and not middle.isdigit() else None
        return RawCourseRow(
            course_number=course_number,
            semester_code=semester_code,
            grade=grade,
            credits_earned=credits,
            attempt=detect_attempt(line),
            title=title,
            confidence=0.9 if title else 0.82,
            warnings=(),
        )

    compact = COMPACT_LINE_PATTERN.match(line.strip())
    if compact:
        compact_number = normalize_course_number(compact.group("number"))
        if compact_number != course_number:
            return None
        grade = parse_grade(compact.group("grade"))
        credits = parse_credits(compact.group("credits"))
        if grade is None or credits is None:
            return None
        return RawCourseRow(
            course_number=course_number,
            semester_code=semester_code,
            grade=grade,
            credits_earned=credits,
            attempt=detect_attempt(line),
            title=None,
            confidence=0.75,
            warnings=("Course title not detected on row",),
        )

    relaxed = re.match(
        r"^(?P<number>\d{6,9})\s+(?P<credits>\d+(?:\.\d)?)\s+(?P<grade>\d+(?:\.\d)?)\s*$",
        line.strip(),
    )
    if relaxed:
        if normalize_course_number(relaxed.group("number")) != course_number:
            return None
        grade = parse_grade(relaxed.group("grade"))
        credits = parse_credits(relaxed.group("credits"))
        if grade is None or credits is None:
            return None
        return RawCourseRow(
            course_number=course_number,
            semester_code=semester_code,
            grade=grade,
            credits_earned=credits,
            attempt=detect_attempt(line),
            title=None,
            confidence=0.72,
            warnings=("Course title not detected on row",),
        )

    return None


def parse_courses_from_text(text: str) -> tuple[list[ParsedCourseEntry], list[str]]:
    current_semester: str | None = None
    warnings: list[str] = []
    raw_rows: list[RawCourseRow] = []

    for line in text.splitlines():
        semester_code = parse_semester_code(line)
        if semester_code:
            current_semester = semester_code
            continue

        if current_semester is None:
            continue

        parsed = parse_course_line(line, semester_code=current_semester)
        if parsed:
            raw_rows.append(parsed)

    if not raw_rows and text.strip():
        warnings.append("No course rows detected in transcript text.")

    deduped: dict[tuple[str, str, int], RawCourseRow] = {}
    for row in raw_rows:
        key = (row.course_number, row.semester_code, row.attempt)
        existing = deduped.get(key)
        if existing is None or row.confidence >= existing.confidence:
            deduped[key] = row

    courses = [
        ParsedCourseEntry(
            courseNumber=row.course_number,
            semesterCode=row.semester_code,
            grade=row.grade,
            creditsEarned=row.credits_earned,
            attempt=row.attempt,
            title=row.title,
            confidence=row.confidence,
            warnings=list(row.warnings),
        )
        for row in deduped.values()
    ]
    courses.sort(key=lambda item: (item.semesterCode, item.courseNumber))
    return courses, warnings
