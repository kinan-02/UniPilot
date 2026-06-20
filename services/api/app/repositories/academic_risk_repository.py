"""User-owned academic risk analyses repository (Phase 17)."""

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


async def ensure_academic_risk_indexes(
    database: AsyncIOMotorDatabase,
    *,
    settings: Settings | None = None,
) -> None:
    settings = settings or get_settings()
    collection = database[settings.academic_risks_collection]
    await collection.create_index(
        [("userId", 1), ("createdAt", -1)],
        name="academic_risks_user_created_at",
    )
    await collection.create_index(
        [("userId", 1), ("status", 1), ("summary.highestSeverity", 1)],
        name="academic_risks_user_status_severity",
    )
    await collection.create_index(
        [("userId", 1), ("planId", 1), ("createdAt", -1)],
        name="academic_risks_user_plan_created_at",
    )


def build_academic_risk_document(user_id: str, analysis_data: dict[str, Any]) -> dict[str, Any]:
    parsed_user_id = parse_object_id(user_id)
    if parsed_user_id is None:
        raise ValueError("Invalid user id for academic risk analysis")

    now = datetime.now(timezone.utc)
    return {
        "userId": parsed_user_id,
        "planId": parse_object_id(analysis_data.get("planId"))
        if analysis_data.get("planId")
        else None,
        "semesterCode": analysis_data.get("semesterCode"),
        "analyzerType": analysis_data.get("analyzerType") or "deterministic",
        "analysisSource": analysis_data.get("analysisSource") or "semester_plan",
        "status": analysis_data.get("status") or "open",
        "summary": analysis_data.get("summary")
        or {
            "totalRisks": 0,
            "highestSeverity": None,
            "counts": {"low": 0, "medium": 0, "high": 0},
        },
        "risks": analysis_data.get("risks") or [],
        "contextSnapshot": analysis_data.get("contextSnapshot") or {},
        "createdAt": now,
        "updatedAt": now,
    }


async def create_academic_risk_analysis(
    database: AsyncIOMotorDatabase,
    user_id: str,
    analysis_data: dict[str, Any],
    *,
    settings: Settings | None = None,
) -> dict[str, Any]:
    settings = settings or get_settings()
    document = build_academic_risk_document(user_id, analysis_data)
    insert_result = await database[settings.academic_risks_collection].insert_one(document)
    return {"_id": insert_result.inserted_id, **document}


async def find_academic_risk_analyses_by_user_id(
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
        return {"analyses": [], "total": 0, "page": 1, "limit": limit}

    safe_page = max(page, 1)
    safe_limit = min(max(limit, 1), 100)
    skip = (safe_page - 1) * safe_limit

    collection = database[settings.academic_risks_collection]
    query = {"userId": parsed_user_id}

    cursor = (
        collection.find(query)
        .sort("createdAt", -1)
        .skip(skip)
        .limit(safe_limit)
    )
    analyses = [document async for document in cursor]
    total = await collection.count_documents(query)

    return {
        "analyses": analyses,
        "total": total,
        "page": safe_page,
        "limit": safe_limit,
    }


async def find_academic_risk_analysis_by_id_and_user_id(
    database: AsyncIOMotorDatabase,
    analysis_id: str,
    user_id: str,
    *,
    settings: Settings | None = None,
) -> dict[str, Any] | None:
    settings = settings or get_settings()
    parsed_analysis_id = parse_object_id(analysis_id)
    parsed_user_id = parse_object_id(user_id)
    if parsed_analysis_id is None or parsed_user_id is None:
        return None

    return await database[settings.academic_risks_collection].find_one(
        {"_id": parsed_analysis_id, "userId": parsed_user_id}
    )


def to_public_academic_risk_summary(
    analysis_document: dict[str, Any] | None,
) -> dict[str, Any] | None:
    if not analysis_document:
        return None

    return {
        "id": str(analysis_document["_id"]),
        "planId": (
            str(analysis_document["planId"])
            if analysis_document.get("planId") is not None
            else None
        ),
        "semesterCode": analysis_document.get("semesterCode"),
        "analyzerType": analysis_document.get("analyzerType"),
        "analysisSource": analysis_document.get("analysisSource"),
        "status": analysis_document.get("status"),
        "summary": analysis_document.get("summary"),
        "createdAt": _format_datetime(analysis_document.get("createdAt")),
        "updatedAt": _format_datetime(analysis_document.get("updatedAt")),
    }


def to_public_academic_risk_analysis(
    analysis_document: dict[str, Any] | None,
) -> dict[str, Any] | None:
    if not analysis_document:
        return None

    return {
        "id": str(analysis_document["_id"]),
        "planId": (
            str(analysis_document["planId"])
            if analysis_document.get("planId") is not None
            else None
        ),
        "semesterCode": analysis_document.get("semesterCode"),
        "analyzerType": analysis_document.get("analyzerType"),
        "analysisSource": analysis_document.get("analysisSource"),
        "status": analysis_document.get("status"),
        "summary": analysis_document.get("summary"),
        "risks": analysis_document.get("risks") or [],
        "contextSnapshot": analysis_document.get("contextSnapshot") or {},
        "createdAt": _format_datetime(analysis_document.get("createdAt")),
        "updatedAt": _format_datetime(analysis_document.get("updatedAt")),
    }
