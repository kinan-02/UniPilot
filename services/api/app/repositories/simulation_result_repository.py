"""Immutable simulation result repository (AGT-3)."""

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


async def ensure_simulation_result_indexes(
    database: AsyncIOMotorDatabase,
    *,
    settings: Settings | None = None,
) -> None:
    settings = settings or get_settings()
    collection = database[settings.simulation_results_collection]
    await collection.create_index(
        [("scenarioId", 1), ("generatedAt", -1)],
        name="simulation_results_scenario_generated_at",
    )
    await collection.create_index(
        [("userId", 1), ("generatedAt", -1)],
        name="simulation_results_user_generated_at",
    )


def build_simulation_result_document(
    user_id: str,
    result_data: dict[str, Any],
) -> dict[str, Any]:
    parsed_user_id = parse_object_id(user_id)
    parsed_scenario_id = parse_object_id(result_data.get("scenarioId"))
    if parsed_user_id is None or parsed_scenario_id is None:
        raise ValueError("Invalid user or scenario id for simulation result")

    now = datetime.now(timezone.utc)
    return {
        "userId": parsed_user_id,
        "scenarioId": parsed_scenario_id,
        "status": result_data.get("status", "completed"),
        "beforeSnapshot": result_data["beforeSnapshot"],
        "afterSnapshot": result_data["afterSnapshot"],
        "deltas": result_data["deltas"],
        "summary": result_data["summary"],
        "narrative": result_data.get("narrative"),
        "warnings": result_data.get("warnings") or [],
        "jobId": parse_object_id(result_data.get("jobId")) if result_data.get("jobId") else None,
        "generatedAt": now,
        "createdAt": now,
    }


async def create_simulation_result(
    database: AsyncIOMotorDatabase,
    user_id: str,
    result_data: dict[str, Any],
    *,
    settings: Settings | None = None,
) -> dict[str, Any]:
    settings = settings or get_settings()
    document = build_simulation_result_document(user_id, result_data)
    insert_result = await database[settings.simulation_results_collection].insert_one(document)
    return {"_id": insert_result.inserted_id, **document}


async def find_simulation_result_by_id_and_user_id(
    database: AsyncIOMotorDatabase,
    result_id: str,
    user_id: str,
    *,
    settings: Settings | None = None,
) -> dict[str, Any] | None:
    settings = settings or get_settings()
    parsed_result_id = parse_object_id(result_id)
    parsed_user_id = parse_object_id(user_id)
    if parsed_result_id is None or parsed_user_id is None:
        return None

    return await database[settings.simulation_results_collection].find_one(
        {"_id": parsed_result_id, "userId": parsed_user_id}
    )


async def find_simulation_results_by_scenario_id(
    database: AsyncIOMotorDatabase,
    user_id: str,
    scenario_id: str,
    *,
    page: int = 1,
    limit: int = 20,
    settings: Settings | None = None,
) -> dict[str, Any]:
    settings = settings or get_settings()
    parsed_user_id = parse_object_id(user_id)
    parsed_scenario_id = parse_object_id(scenario_id)
    if parsed_user_id is None or parsed_scenario_id is None:
        return {"results": [], "total": 0, "page": page, "limit": limit}

    safe_page = max(page, 1)
    safe_limit = min(max(limit, 1), 50)
    skip = (safe_page - 1) * safe_limit
    collection = database[settings.simulation_results_collection]
    query = {"userId": parsed_user_id, "scenarioId": parsed_scenario_id}

    results = (
        await collection.find(query)
        .sort("generatedAt", -1)
        .skip(skip)
        .limit(safe_limit)
        .to_list(length=safe_limit)
    )
    total = await collection.count_documents(query)
    return {
        "results": results,
        "total": total,
        "page": safe_page,
        "limit": safe_limit,
    }


def to_public_simulation_result(document: dict[str, Any] | None) -> dict[str, Any] | None:
    if not document:
        return None
    return {
        "id": str(document["_id"]),
        "scenarioId": str(document["scenarioId"]),
        "status": document.get("status"),
        "beforeSnapshot": document.get("beforeSnapshot") or {},
        "afterSnapshot": document.get("afterSnapshot") or {},
        "deltas": document.get("deltas") or {},
        "summary": document.get("summary"),
        "narrative": document.get("narrative"),
        "warnings": document.get("warnings") or [],
        "jobId": str(document["jobId"]) if document.get("jobId") is not None else None,
        "generatedAt": _format_datetime(document.get("generatedAt")),
        "createdAt": _format_datetime(document.get("createdAt")),
    }
