"""Repair completed-course rows that reference stale catalog course ids."""

from __future__ import annotations

from datetime import datetime, timezone
from typing import Any

from bson import ObjectId

from app.config import get_settings
from app.repositories import catalog_repository


async def repair_stale_completed_course_catalog_links(
    database,
    completed_records: list[dict[str, Any]],
    catalog_courses_by_id: dict[str, dict[str, Any]],
) -> tuple[list[dict[str, Any]], dict[str, dict[str, Any]]]:
    """
    Re-link imported transcript rows when catalog promotion changed Mongo course ids.

    Uses ``metadata.importedCourseNumber`` saved at PDF import time.
    """
    settings = get_settings()
    collection = database[settings.completed_courses_collection]
    repaired_records: list[dict[str, Any]] = []
    now = datetime.now(timezone.utc)

    for record in completed_records:
        course_id = str(record.get("courseId") or "")
        if course_id and course_id in catalog_courses_by_id:
            repaired_records.append(record)
            continue

        metadata = dict(record.get("metadata") or {})
        imported_number = metadata.get("importedCourseNumber")
        if not imported_number:
            repaired_records.append(record)
            continue

        course = await catalog_repository.find_course_by_number(database, str(imported_number))
        if not course:
            repaired_records.append(record)
            continue

        new_id = str(course["_id"])
        catalog_courses_by_id[new_id] = course

        if new_id == course_id:
            repaired_records.append(record)
            continue

        await collection.update_one(
            {"_id": record["_id"]},
            {
                "$set": {
                    "courseId": ObjectId(new_id),
                    "metadata": {
                        **metadata,
                        "repairedCatalogLink": True,
                        "previousCourseId": course_id,
                    },
                    "updatedAt": now,
                }
            },
        )
        repaired_records.append({**record, "courseId": ObjectId(new_id)})

    return repaired_records, catalog_courses_by_id
