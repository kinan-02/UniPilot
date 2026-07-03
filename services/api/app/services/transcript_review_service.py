"""Build transcript import review rows before user confirmation (spec §30.3)."""

from __future__ import annotations

from typing import Any, Literal

from motor.motor_asyncio import AsyncIOMotorDatabase
from pydantic import BaseModel, Field

from app.planning.prerequisite_resolver import canonical_course_number
from app.repositories import catalog_repository
from app.services.grade_evaluation import parse_numeric_grade

RowStatus = Literal["matched", "duplicate", "uncertain", "unmatched", "ignored"]


class TranscriptReviewRow(BaseModel):
    courseNumber: str
    courseName: str | None = None
    creditsEarned: float
    grade: float
    semesterCode: str
    status: RowStatus = "matched"
    notes: list[str] = Field(default_factory=list)
    confidence: float | None = None
    selected: bool = True
    catalogCourseId: str | None = None
    attempt: int | None = None
    warnings: list[str] = Field(default_factory=list)


class TranscriptReviewResult(BaseModel):
    rows: list[TranscriptReviewRow] = Field(default_factory=list)
    totalExtractedCredits: float = 0.0
    importableCredits: float = 0.0
    matchedCount: int = 0
    duplicateCount: int = 0
    uncertainCount: int = 0
    unmatchedCount: int = 0
    warnings: list[str] = Field(default_factory=list)
    parseMetadata: dict[str, Any] = Field(default_factory=dict)
    studentId: str | None = None
    studentName: str | None = None


def _grade_key(grade: Any) -> str:
    numeric = parse_numeric_grade(grade)
    if numeric is not None and numeric == int(numeric):
        return str(int(numeric))
    if numeric is not None:
        return str(numeric)
    return str(grade)


def _existing_signatures(records: list[dict[str, Any]]) -> set[tuple[str, str, str]]:
    signatures: set[tuple[str, str, str]] = set()
    for record in records:
        course_id = str(record.get("courseId") or "")
        semester = str(record.get("semesterCode") or "")
        if not course_id or not semester:
            continue
        signatures.add((course_id, semester, _grade_key(record.get("grade"))))
    return signatures


async def build_transcript_review(
    database: AsyncIOMotorDatabase,
    *,
    parse_preview: dict[str, Any],
    completed_course_records: list[dict[str, Any]] | None = None,
) -> TranscriptReviewResult:
    """Match parsed transcript rows to catalog and existing completed courses."""
    courses = list(parse_preview.get("courses") or [])
    existing = _existing_signatures(completed_course_records or [])
    rows: list[TranscriptReviewRow] = []
    warnings = [str(item) for item in parse_preview.get("warnings") or []]

    for entry in courses:
        if not isinstance(entry, dict):
            continue
        raw_number = str(entry.get("courseNumber") or "")
        normalized = canonical_course_number(raw_number)
        semester = str(entry.get("semesterCode") or "").strip()
        grade = float(entry.get("grade") or 0)
        credits = float(entry.get("creditsEarned") or 0)
        confidence = entry.get("confidence")
        row_warnings = [str(item) for item in entry.get("warnings") or []]
        notes: list[str] = list(row_warnings)

        if not normalized:
            rows.append(
                TranscriptReviewRow(
                    courseNumber=raw_number,
                    courseName=entry.get("title"),
                    creditsEarned=credits,
                    grade=grade,
                    semesterCode=semester,
                    status="unmatched",
                    notes=[*notes, "Invalid course number format"],
                    confidence=float(confidence) if confidence is not None else None,
                    selected=False,
                    attempt=entry.get("attempt"),
                    warnings=row_warnings,
                )
            )
            continue

        catalog_course = await catalog_repository.find_course_by_number(database, normalized)
        if not catalog_course:
            rows.append(
                TranscriptReviewRow(
                    courseNumber=normalized,
                    courseName=entry.get("title"),
                    creditsEarned=credits,
                    grade=grade,
                    semesterCode=semester,
                    status="unmatched",
                    notes=[*notes, "Course not found in catalog"],
                    confidence=float(confidence) if confidence is not None else None,
                    selected=False,
                    attempt=entry.get("attempt"),
                    warnings=row_warnings,
                )
            )
            continue

        course_id = str(catalog_course.get("_id"))
        catalog_title = str(catalog_course.get("title") or catalog_course.get("titleHebrew") or "")
        parsed_title = str(entry.get("title") or "").strip()
        status: RowStatus = "matched"

        if (course_id, semester, _grade_key(grade)) in existing:
            status = "duplicate"
            notes.append("Already exists in completed courses")
        elif confidence is not None and float(confidence) < 0.8:
            status = "uncertain"
            notes.append("Low parser confidence")
        elif row_warnings:
            status = "uncertain"
            notes.append("Parser reported warnings for this row")
        elif parsed_title and catalog_title and parsed_title not in catalog_title and catalog_title not in parsed_title:
            status = "uncertain"
            notes.append("Course name does not exactly match catalog")

        rows.append(
            TranscriptReviewRow(
                courseNumber=normalized,
                courseName=catalog_title or parsed_title or None,
                creditsEarned=credits,
                grade=grade,
                semesterCode=semester,
                status=status,
                notes=notes,
                confidence=float(confidence) if confidence is not None else None,
                selected=status in {"matched", "uncertain"},
                catalogCourseId=course_id,
                attempt=entry.get("attempt"),
                warnings=row_warnings,
            )
        )

    matched_count = sum(1 for row in rows if row.status == "matched")
    duplicate_count = sum(1 for row in rows if row.status == "duplicate")
    uncertain_count = sum(1 for row in rows if row.status == "uncertain")
    unmatched_count = sum(1 for row in rows if row.status == "unmatched")
    total_credits = sum(row.creditsEarned for row in rows)
    importable_credits = sum(row.creditsEarned for row in rows if row.selected and row.status != "duplicate")

    return TranscriptReviewResult(
        rows=rows,
        totalExtractedCredits=total_credits,
        importableCredits=importable_credits,
        matchedCount=matched_count,
        duplicateCount=duplicate_count,
        uncertainCount=uncertain_count,
        unmatchedCount=unmatched_count,
        warnings=warnings,
        parseMetadata=dict(parse_preview.get("parseMetadata") or {}),
        studentId=parse_preview.get("studentId"),
        studentName=parse_preview.get("studentName"),
    )


def review_rows_for_commit(review: TranscriptReviewResult) -> list[dict[str, Any]]:
    """Return commit-ready course payloads for selected importable rows."""
    commit_rows: list[dict[str, Any]] = []
    for row in review.rows:
        if not row.selected or row.status == "duplicate" or row.status == "unmatched":
            continue
        commit_rows.append(
            {
                "courseNumber": row.courseNumber,
                "semesterCode": row.semesterCode,
                "grade": row.grade,
                "creditsEarned": row.creditsEarned,
                "attempt": row.attempt or 1,
                "title": row.courseName,
                "warnings": row.warnings,
            }
        )
    return commit_rows
