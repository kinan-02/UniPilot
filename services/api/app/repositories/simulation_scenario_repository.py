"""User-owned simulation scenario repository (AGT-3)."""

from __future__ import annotations

from datetime import datetime, timezone
from typing import Any

from bson import ObjectId
from motor.motor_asyncio import AsyncIOMotorDatabase

from app.config import Settings, get_settings
from app.repositories.semester_plan_repository import parse_object_id


def _format_datetime(value: Any) -> str | None:
    if value is None:
        return None
    if isinstance(value, datetime):
        return value.astimezone(timezone.utc).isoformat().replace("+00:00", "Z")
    return str(value)


async def ensure_simulation_scenario_indexes(
    database: AsyncIOMotorDatabase,
    *,
    settings: Settings | None = None,
) -> None:
    settings = settings or get_settings()
    collection = database[settings.simulation_scenarios_collection]
    await collection.create_index(
        [("userId", 1), ("createdAt", -1)],
        name="simulation_scenarios_user_created_at",
    )


def build_simulation_scenario_document(
    user_id: str,
    scenario_data: dict[str, Any],
) -> dict[str, Any]:
    parsed_user_id = parse_object_id(user_id)
    if parsed_user_id is None:
        raise ValueError("Invalid user id for simulation scenario")

    now = datetime.now(timezone.utc)
    return {
        "userId": parsed_user_id,
        "name": scenario_data["name"],
        "description": scenario_data.get("description"),
        "operations": scenario_data["operations"],
        "semesterCode": scenario_data.get("semesterCode"),
        "planId": parse_object_id(scenario_data.get("planId"))
        if scenario_data.get("planId")
        else None,
        "naturalLanguagePrompt": scenario_data.get("naturalLanguagePrompt"),
        "status": scenario_data.get("status", "draft"),
        "createdAt": now,
        "updatedAt": now,
    }


async def create_simulation_scenario(
    database: AsyncIOMotorDatabase,
    user_id: str,
    scenario_data: dict[str, Any],
    *,
    settings: Settings | None = None,
) -> dict[str, Any]:
    settings = settings or get_settings()
    document = build_simulation_scenario_document(user_id, scenario_data)
    insert_result = await database[settings.simulation_scenarios_collection].insert_one(document)
    return {"_id": insert_result.inserted_id, **document}


async def find_simulation_scenarios_by_user_id(
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
        return {"scenarios": [], "total": 0, "page": page, "limit": limit}

    safe_page = max(page, 1)
    safe_limit = min(max(limit, 1), 100)
    skip = (safe_page - 1) * safe_limit
    collection = database[settings.simulation_scenarios_collection]
    query = {"userId": parsed_user_id}

    scenarios = (
        await collection.find(query)
        .sort("createdAt", -1)
        .skip(skip)
        .limit(safe_limit)
        .to_list(length=safe_limit)
    )
    total = await collection.count_documents(query)
    return {
        "scenarios": scenarios,
        "total": total,
        "page": safe_page,
        "limit": safe_limit,
    }


async def find_simulation_scenario_by_id_and_user_id(
    database: AsyncIOMotorDatabase,
    scenario_id: str,
    user_id: str,
    *,
    settings: Settings | None = None,
) -> dict[str, Any] | None:
    settings = settings or get_settings()
    parsed_scenario_id = parse_object_id(scenario_id)
    parsed_user_id = parse_object_id(user_id)
    if parsed_scenario_id is None or parsed_user_id is None:
        return None

    return await database[settings.simulation_scenarios_collection].find_one(
        {"_id": parsed_scenario_id, "userId": parsed_user_id}
    )


def to_public_simulation_scenario(document: dict[str, Any] | None) -> dict[str, Any] | None:
    if not document:
        return None
    return {
        "id": str(document["_id"]),
        "name": document.get("name"),
        "description": document.get("description"),
        "operations": document.get("operations") or [],
        "semesterCode": document.get("semesterCode"),
        "planId": str(document["planId"]) if document.get("planId") is not None else None,
        "naturalLanguagePrompt": document.get("naturalLanguagePrompt"),
        "status": document.get("status"),
        "createdAt": _format_datetime(document.get("createdAt")),
        "updatedAt": _format_datetime(document.get("updatedAt")),
    }
