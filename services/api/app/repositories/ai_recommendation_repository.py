"""MongoDB repository for proactive AI recommendations (AGT-8)."""

from __future__ import annotations

from datetime import datetime, timezone
from typing import Any

from motor.motor_asyncio import AsyncIOMotorDatabase

from app.config import Settings, get_settings
from app.repositories.semester_plan_repository import parse_object_id


def _format_datetime(value: Any) -> str | None:
    if value is None:
        return None
    if isinstance(value, datetime):
        return value.astimezone(timezone.utc).isoformat().replace("+00:00", "Z")
    return str(value)


async def ensure_ai_recommendation_indexes(
    database: AsyncIOMotorDatabase,
    *,
    settings: Settings | None = None,
) -> None:
    settings = settings or get_settings()
    collection = database[settings.ai_recommendations_collection]
    await collection.create_index(
        [("userId", 1), ("createdAt", -1)],
        name="ai_recommendations_user_created_at",
    )
    await collection.create_index(
        [("userId", 1), ("status", 1), ("createdAt", -1)],
        name="ai_recommendations_user_status_created_at",
    )
    await collection.create_index(
        [("userId", 1), ("dedupeKey", 1)],
        unique=True,
        name="ai_recommendations_user_dedupe_key",
    )


def build_ai_recommendation_document(
    user_id: str,
    recommendation: dict[str, Any],
) -> dict[str, Any]:
    parsed_user_id = parse_object_id(user_id)
    if parsed_user_id is None:
        raise ValueError("Invalid user id for AI recommendation")

    now = datetime.now(timezone.utc)
    plan_id = recommendation.get("planId")
    risk_analysis_id = recommendation.get("riskAnalysisId")

    return {
        "userId": parsed_user_id,
        "type": recommendation.get("type") or "watchdog_nudge",
        "nudgeType": recommendation.get("nudgeType"),
        "trigger": recommendation.get("trigger"),
        "severity": recommendation.get("severity") or "medium",
        "title": recommendation.get("title") or "",
        "body": recommendation.get("body") or "",
        "evidence": recommendation.get("evidence") or {},
        "planId": parse_object_id(plan_id) if plan_id else None,
        "riskAnalysisId": parse_object_id(risk_analysis_id) if risk_analysis_id else None,
        "dedupeKey": recommendation.get("dedupeKey"),
        "status": recommendation.get("status") or "active",
        "createdAt": now,
        "updatedAt": now,
    }


async def upsert_ai_recommendation(
    database: AsyncIOMotorDatabase,
    user_id: str,
    recommendation: dict[str, Any],
    *,
    settings: Settings | None = None,
) -> dict[str, Any]:
    """Insert or refresh an active recommendation keyed by userId + dedupeKey."""
    settings = settings or get_settings()
    dedupe_key = recommendation.get("dedupeKey")
    if not dedupe_key:
        raise ValueError("dedupeKey is required for AI recommendations")

    parsed_user_id = parse_object_id(user_id)
    if parsed_user_id is None:
        raise ValueError("Invalid user id for AI recommendation")

    collection = database[settings.ai_recommendations_collection]
    now = datetime.now(timezone.utc)
    plan_id = recommendation.get("planId")
    risk_analysis_id = recommendation.get("riskAnalysisId")

    update_fields = {
        "type": recommendation.get("type") or "watchdog_nudge",
        "nudgeType": recommendation.get("nudgeType"),
        "trigger": recommendation.get("trigger"),
        "severity": recommendation.get("severity") or "medium",
        "title": recommendation.get("title") or "",
        "body": recommendation.get("body") or "",
        "evidence": recommendation.get("evidence") or {},
        "planId": parse_object_id(plan_id) if plan_id else None,
        "riskAnalysisId": parse_object_id(risk_analysis_id) if risk_analysis_id else None,
        "status": "active",
        "updatedAt": now,
    }

    result = await collection.find_one_and_update(
        {"userId": parsed_user_id, "dedupeKey": dedupe_key},
        {
            "$set": update_fields,
            "$setOnInsert": {
                "userId": parsed_user_id,
                "dedupeKey": dedupe_key,
                "createdAt": now,
            },
        },
        upsert=True,
        return_document=True,
    )
    if result is None:
        raise RuntimeError("Failed to upsert AI recommendation")
    return result


async def list_ai_recommendations_for_user(
    database: AsyncIOMotorDatabase,
    user_id: str,
    *,
    status: str | None = "active",
    page: int = 1,
    limit: int = 20,
    settings: Settings | None = None,
) -> dict[str, Any]:
    settings = settings or get_settings()
    parsed_user_id = parse_object_id(user_id)
    if parsed_user_id is None:
        return {"recommendations": [], "total": 0, "page": 1, "limit": limit}

    safe_page = max(page, 1)
    safe_limit = min(max(limit, 1), 50)
    skip = (safe_page - 1) * safe_limit

    query: dict[str, Any] = {"userId": parsed_user_id}
    if status:
        query["status"] = status

    collection = database[settings.ai_recommendations_collection]
    cursor = collection.find(query).sort("createdAt", -1).skip(skip).limit(safe_limit)
    recommendations = [document async for document in cursor]
    total = await collection.count_documents(query)

    return {
        "recommendations": recommendations,
        "total": total,
        "page": safe_page,
        "limit": safe_limit,
    }


async def dismiss_ai_recommendation_for_user(
    database: AsyncIOMotorDatabase,
    user_id: str,
    recommendation_id: str,
    *,
    settings: Settings | None = None,
) -> dict[str, Any] | None:
    settings = settings or get_settings()
    parsed_user_id = parse_object_id(user_id)
    parsed_recommendation_id = parse_object_id(recommendation_id)
    if parsed_user_id is None or parsed_recommendation_id is None:
        return None

    return await database[settings.ai_recommendations_collection].find_one_and_update(
        {"_id": parsed_recommendation_id, "userId": parsed_user_id},
        {
            "$set": {
                "status": "dismissed",
                "updatedAt": datetime.now(timezone.utc),
            }
        },
        return_document=True,
    )


def to_public_ai_recommendation(document: dict[str, Any] | None) -> dict[str, Any] | None:
    if not document:
        return None

    return {
        "id": str(document["_id"]),
        "type": document.get("type") or "watchdog_nudge",
        "nudgeType": document.get("nudgeType"),
        "trigger": document.get("trigger"),
        "severity": document.get("severity"),
        "title": document.get("title"),
        "body": document.get("body"),
        "evidence": document.get("evidence") or {},
        "planId": str(document["planId"]) if document.get("planId") is not None else None,
        "riskAnalysisId": (
            str(document["riskAnalysisId"])
            if document.get("riskAnalysisId") is not None
            else None
        ),
        "dedupeKey": document.get("dedupeKey"),
        "status": document.get("status"),
        "createdAt": _format_datetime(document.get("createdAt")),
        "updatedAt": _format_datetime(document.get("updatedAt")),
    }
