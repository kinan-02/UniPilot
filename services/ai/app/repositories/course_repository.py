"""Catalog course lookups for agent retrieval.

Completed-course records reference a course by `courseId` (an ObjectId) and, in
production, carry an empty `metadata` block -- the human-readable course NUMBER
lives on the `courses` catalog document. This join is what lets the agent's
per-record prerequisite matching see the actual course numbers rather than
opaque ids.
"""

from __future__ import annotations

from typing import Any

from bson import ObjectId
from motor.motor_asyncio import AsyncIOMotorDatabase

from app.config import Settings, get_settings


async def find_course_numbers_by_ids(
    database: AsyncIOMotorDatabase,
    course_ids: list[ObjectId],
    *,
    settings: Settings | None = None,
) -> dict[str, str]:
    """Return `{str(courseId): courseNumber}` for the given course ObjectIds.

    Ids that don't resolve, or whose course document has no `courseNumber`, are
    simply absent from the map (callers fall back to `None`). Returns an empty
    map for empty input without touching the database."""
    settings = settings or get_settings()
    ids = [course_id for course_id in course_ids if course_id is not None]
    if not ids:
        return {}

    documents: list[dict[str, Any]] = (
        await database[settings.courses_collection]
        .find({"_id": {"$in": ids}}, {"courseNumber": 1})
        .to_list(length=len(ids))
    )
    return {
        str(document.get("_id")): str(document.get("courseNumber"))
        for document in documents
        if document.get("courseNumber") is not None
    }
