"""Read-only slice of `completed_courses` access for retrieval.

Ported from `services/agent/app/repositories/completed_course_repository.py`
-- only the read function `mongodb_user_retriever.py` needs. Confirmed this
function needs nothing from `app.services.completed_course_attempts` (that
module only backs the write-side attempt-tracking functions, not this read).
"""

from __future__ import annotations

from typing import Any

from bson import ObjectId
from motor.motor_asyncio import AsyncIOMotorDatabase

from app.config import Settings, get_settings

COMPLETED_COURSES_COLLECTION = "completed_courses"


def parse_object_id(value: str | None) -> ObjectId | None:
    if value is None:
        return None

    try:
        return ObjectId(str(value))
    except Exception:
        return None


async def find_all_completed_courses_by_user_id(
    database: AsyncIOMotorDatabase,
    user_id: str,
    *,
    settings: Settings | None = None,
) -> list[dict[str, Any]]:
    settings = settings or get_settings()
    parsed_user_id = parse_object_id(user_id)
    if parsed_user_id is None:
        return []

    return (
        await database[settings.completed_courses_collection]
        .find({"userId": parsed_user_id})
        .sort("recordedAt", -1)
        .to_list(length=10_000)
    )
