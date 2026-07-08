"""Read-only slice of `semester_plans` access for retrieval.

Ported from `services/agent/app/repositories/semester_plan_repository.py`
-- only the read function `mongodb_user_retriever.py` needs.
"""

from __future__ import annotations

import asyncio
from typing import Any

from bson import ObjectId
from motor.motor_asyncio import AsyncIOMotorDatabase

from app.config import Settings, get_settings

SEMESTER_PLANS_COLLECTION = "semester_plans"


def parse_object_id(value: str | None) -> ObjectId | None:
    if value is None:
        return None
    try:
        return ObjectId(str(value))
    except Exception:
        return None


async def _fetch_plans_page(collection, query, skip, limit):
    plans_task = collection.find(query).sort("createdAt", -1).skip(skip).limit(limit).to_list(length=limit)
    total_task = collection.count_documents(query)
    plans, total = await asyncio.gather(plans_task, total_task)
    return plans, total


async def find_semester_plans_by_user_id(
    database: AsyncIOMotorDatabase,
    user_id: str,
    *,
    page: int = 1,
    limit: int = 50,
    settings: Settings | None = None,
) -> dict[str, Any]:
    settings = settings or get_settings()
    parsed_user_id = parse_object_id(user_id)
    if parsed_user_id is None:
        return {"plans": [], "total": 0, "page": page, "limit": limit}

    safe_page = max(page, 1)
    safe_limit = min(max(limit, 1), 100)
    skip = (safe_page - 1) * safe_limit

    collection = database[settings.semester_plans_collection]
    query = {"userId": parsed_user_id}

    plans, total = await _fetch_plans_page(collection, query, skip, safe_limit)
    return {
        "plans": plans,
        "total": total,
        "page": safe_page,
        "limit": safe_limit,
    }
