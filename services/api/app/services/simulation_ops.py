"""Apply validated simulation operations to hypothetical transcript rows."""

from __future__ import annotations

import copy
from typing import Any

from motor.motor_asyncio import AsyncIOMotorDatabase

from app.repositories import catalog_repository
from app.services.graduation_progress_calculator import is_passing_grade


async def resolve_course_id_by_number(
    database: AsyncIOMotorDatabase,
    course_number: str,
) -> tuple[str | None, dict[str, Any] | None]:
    course = await catalog_repository.find_course_by_number(database, course_number)
    if not course:
        return None, None
    return str(course["_id"]), course


async def apply_transcript_operations(
    database: AsyncIOMotorDatabase,
    completed_records: list[dict[str, Any]],
    operations: list[dict[str, Any]],
    *,
    default_semester_code: str | None = None,
) -> tuple[list[dict[str, Any]], list[str]]:
    """
    Return a new completed-course record list with transcript-affecting ops applied.
    """
    records = copy.deepcopy(completed_records)
    warnings: list[str] = []

    for operation in operations:
        op_type = operation.get("type")
        if op_type == "drop_course":
            records, warning = await _apply_drop_course(database, records, operation)
        elif op_type == "add_course":
            records, warning = await _apply_add_course(
                database,
                records,
                operation,
                default_semester_code=default_semester_code,
            )
        elif op_type in {"add_planned_course", "change_track"}:
            warning = None
        else:
            warning = f"Unsupported operation type: {op_type}"

        if warning:
            warnings.append(warning)

    return records, warnings


async def _apply_drop_course(
    database: AsyncIOMotorDatabase,
    records: list[dict[str, Any]],
    operation: dict[str, Any],
) -> tuple[list[dict[str, Any]], str | None]:
    course_number = str(operation["courseNumber"])
    course_id, _course = await resolve_course_id_by_number(database, course_number)
    if not course_id:
        return records, f"Course {course_number} was not found in the catalog"

    before_count = len(records)
    records = [
        record
        for record in records
        if str(record.get("courseId")) != course_id or not is_passing_grade(record)
    ]
    if len(records) == before_count:
        return records, f"No passing completion found for course {course_number}"
    return records, None


async def _apply_add_course(
    database: AsyncIOMotorDatabase,
    records: list[dict[str, Any]],
    operation: dict[str, Any],
    *,
    default_semester_code: str | None,
) -> tuple[list[dict[str, Any]], str | None]:
    course_number = str(operation["courseNumber"])
    course_id, course = await resolve_course_id_by_number(database, course_number)
    if not course_id or not course:
        return records, f"Course {course_number} was not found in the catalog"

    for record in records:
        if str(record.get("courseId")) == course_id and is_passing_grade(record):
            return records, f"Course {course_number} is already completed in the scenario baseline"

    grade = float(operation.get("grade") or 90)
    semester_code = operation.get("semesterCode") or default_semester_code or "2025-1"
    credits = float(course.get("credits") or 0)
    records.append(
        {
            "courseId": course["_id"],
            "semesterCode": semester_code,
            "grade": grade,
            "gradePoints": grade,
            "creditsEarned": credits,
            "attempt": 1,
            "source": "simulation",
        }
    )
    return records, None


def collect_planned_course_numbers(operations: list[dict[str, Any]]) -> list[str]:
    numbers: list[str] = []
    for operation in operations:
        if operation.get("type") == "add_planned_course":
            numbers.append(str(operation["courseNumber"]))
    return numbers


def collect_track_change(operations: list[dict[str, Any]]) -> str | None:
    for operation in operations:
        if operation.get("type") == "change_track":
            return str(operation.get("trackSlug") or "").strip() or None
    return None
