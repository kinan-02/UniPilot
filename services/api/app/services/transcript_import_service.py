"""Persist imported transcript rows after catalog resolution."""

from __future__ import annotations

from typing import Any

from pymongo.errors import DuplicateKeyError

from app.repositories import catalog_repository
from app.planning.prerequisite_resolver import canonical_course_number
from app.repositories.completed_course_repository import (
    create_completed_course,
    ensure_completed_course_indexes,
    find_all_completed_courses_by_user_id,
    to_public_completed_course,
)
from app.services.transcript_import_normalization import (
    resolve_import_credits,
    resolve_import_grade_points,
)
from app.schemas.transcript_import import CommitTranscriptImportRequest


async def commit_transcript_import(
    database,
    user_id: str,
    payload: CommitTranscriptImportRequest,
) -> dict[str, Any]:
    await ensure_completed_course_indexes(database)

    existing_records = await find_all_completed_courses_by_user_id(database, user_id)
    existing_keys = {
        (str(record.get("courseId")), int(record.get("attempt") or 1))
        for record in existing_records
    }

    created: list[dict[str, Any]] = []
    skipped_duplicates: list[str] = []
    unresolved: list[dict[str, str]] = []

    for row in payload.courses:
        normalized_number = canonical_course_number(row.courseNumber)
        if not normalized_number:
            unresolved.append(
                {
                    "courseNumber": row.courseNumber,
                    "semesterCode": row.semesterCode,
                    "reason": "Invalid course number",
                }
            )
            continue

        course = await catalog_repository.find_course_by_number(database, normalized_number)
        if not course:
            unresolved.append(
                {
                    "courseNumber": normalized_number,
                    "semesterCode": row.semesterCode,
                    "reason": "Course not found in catalog",
                }
            )
            continue

        course_id = str(course["_id"])
        attempt = row.attempt or 1
        duplicate_key = (course_id, attempt)
        if payload.skipDuplicates and duplicate_key in existing_keys:
            skipped_duplicates.append(row.courseNumber)
            continue

        metadata: dict[str, Any] = {"importSource": "transcript-pdf"}
        if row.title:
            metadata["importedTitle"] = row.title

        credits_earned = resolve_import_credits(row, course)
        grade_points = resolve_import_grade_points(row)

        record_data = {
            "courseId": course_id,
            "semesterCode": row.semesterCode,
            "grade": row.grade,
            "gradePoints": grade_points,
            "creditsEarned": credits_earned,
            "attempt": attempt,
            "source": "imported",
            "metadata": metadata,
        }

        try:
            record = await create_completed_course(database, user_id, record_data)
        except DuplicateKeyError:
            skipped_duplicates.append(row.courseNumber)
            continue

        existing_keys.add(duplicate_key)
        course_summary = catalog_repository.course_summary_from_document(course)
        public_record = to_public_completed_course(record, course_summary)
        if public_record:
            created.append(public_record)

    return {
        "created": created,
        "skippedDuplicates": skipped_duplicates,
        "unresolved": unresolved,
        "createdCount": len(created),
        "skippedCount": len(skipped_duplicates),
        "unresolvedCount": len(unresolved),
    }
