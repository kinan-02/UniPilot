"""Read-only slice of `student_profiles` access for retrieval.

Ported from `services/agent/app/repositories/student_profile_repository.py`
-- only the read function `mongodb_user_retriever.py` needs. The write-side
functions (create/update/delete) stay in `services/agent`/`services/api`;
this service never writes to shared student-state collections.
"""

from __future__ import annotations

from typing import Any

from bson import ObjectId
from motor.motor_asyncio import AsyncIOMotorDatabase

STUDENT_PROFILES_COLLECTION = "student_profiles"


def parse_object_id(value: str | None) -> ObjectId | None:
    if value is None:
        return None

    try:
        return ObjectId(str(value))
    except Exception:
        return None


async def find_student_profile_by_user_id(
    database: AsyncIOMotorDatabase,
    user_id: str,
) -> dict[str, Any] | None:
    parsed_user_id = parse_object_id(user_id)
    if parsed_user_id is None:
        return None

    return await database[STUDENT_PROFILES_COLLECTION].find_one({"userId": parsed_user_id})
