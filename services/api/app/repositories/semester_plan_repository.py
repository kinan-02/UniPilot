"""User-owned semester plans repository (Phase 16)."""

from __future__ import annotations

from datetime import datetime, timezone
from typing import Any

from bson import ObjectId
from motor.motor_asyncio import AsyncIOMotorDatabase

from app.config import Settings, get_settings


def parse_object_id(value: str | None) -> ObjectId | None:
    if value is None:
        return None
    try:
        return ObjectId(str(value))
    except Exception:
        return None


async def ensure_semester_plan_indexes(
    database: AsyncIOMotorDatabase,
    *,
    settings: Settings | None = None,
) -> None:
    settings = settings or get_settings()
    collection = database[settings.semester_plans_collection]
    await collection.create_index(
        [("userId", 1), ("updatedAt", -1)],
        name="semester_plans_user_updated_at",
    )
    await collection.create_index(
        [("userId", 1), ("status", 1)],
        name="semester_plans_user_status",
    )
    await collection.create_index(
        [("shareToken", 1)],
        name="semester_plans_share_token",
        unique=True,
        sparse=True,
    )


def build_semester_plan_document(user_id: str, plan_data: dict[str, Any]) -> dict[str, Any]:
    parsed_user_id = parse_object_id(user_id)
    if parsed_user_id is None:
        raise ValueError("Invalid user id for semester plan")

    now = datetime.now(timezone.utc)
    return {
        "userId": parsed_user_id,
        "name": plan_data["name"],
        "status": plan_data.get("status", "draft"),
        "version": plan_data.get("version", 1),
        "basePlanId": None,
        "plannerType": plan_data.get("plannerType", "deterministic"),
        "assumptions": plan_data.get("assumptions") or {},
        "explanation": plan_data.get("explanation") or {},
        "semesters": plan_data.get("semesters") or [],
        "createdAt": now,
        "updatedAt": now,
    }


async def create_semester_plan(
    database: AsyncIOMotorDatabase,
    user_id: str,
    plan_data: dict[str, Any],
    *,
    settings: Settings | None = None,
) -> dict[str, Any]:
    settings = settings or get_settings()
    document = build_semester_plan_document(user_id, plan_data)
    insert_result = await database[settings.semester_plans_collection].insert_one(document)
    return {"_id": insert_result.inserted_id, **document}


async def create_semester_plan_version_from_source(
    database: AsyncIOMotorDatabase,
    user_id: str,
    source_plan: dict[str, Any],
    *,
    name: str | None = None,
    settings: Settings | None = None,
) -> dict[str, Any]:
    import copy

    settings = settings or get_settings()
    parsed_user_id = parse_object_id(user_id)
    if parsed_user_id is None:
        raise ValueError("Invalid user id for semester plan version")

    source_version = int(source_plan.get("version") or 1)
    next_version = source_version + 1
    default_name = str(source_plan.get("name") or "Semester plan")
    version_name = name or f"{default_name} v{next_version}"

    now = datetime.now(timezone.utc)
    assumptions = copy.deepcopy(source_plan.get("assumptions") or {})
    assumptions["forkedFromPlanId"] = str(source_plan["_id"])
    assumptions["forkedFromVersion"] = source_version

    document = {
        "userId": parsed_user_id,
        "name": version_name,
        "status": "draft",
        "version": next_version,
        "basePlanId": source_plan["_id"],
        "plannerType": source_plan.get("plannerType", "deterministic"),
        "assumptions": assumptions,
        "explanation": copy.deepcopy(source_plan.get("explanation") or {}),
        "semesters": copy.deepcopy(source_plan.get("semesters") or []),
        "createdAt": now,
        "updatedAt": now,
    }

    insert_result = await database[settings.semester_plans_collection].insert_one(document)
    return {"_id": insert_result.inserted_id, **document}


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


async def _fetch_plans_page(collection, query, skip, limit):
    import asyncio

    plans_task = collection.find(query).sort("createdAt", -1).skip(skip).limit(limit).to_list(length=limit)
    total_task = collection.count_documents(query)
    plans, total = await asyncio.gather(plans_task, total_task)
    return plans, total


async def find_semester_plan_by_share_token(
    database: AsyncIOMotorDatabase,
    share_token: str,
    *,
    settings: Settings | None = None,
) -> dict[str, Any] | None:
    settings = settings or get_settings()
    if not share_token:
        return None
    return await database[settings.semester_plans_collection].find_one(
        {"shareToken": share_token, "shareEnabled": True}
    )


async def find_semester_plan_by_id_and_user_id(
    database: AsyncIOMotorDatabase,
    plan_id: str,
    user_id: str,
    *,
    settings: Settings | None = None,
) -> dict[str, Any] | None:
    settings = settings or get_settings()
    parsed_plan_id = parse_object_id(plan_id)
    parsed_user_id = parse_object_id(user_id)
    if parsed_plan_id is None or parsed_user_id is None:
        return None

    return await database[settings.semester_plans_collection].find_one(
        {"_id": parsed_plan_id, "userId": parsed_user_id}
    )


async def update_semester_plan_by_id_and_user_id(
    database: AsyncIOMotorDatabase,
    plan_id: str,
    user_id: str,
    updates: dict[str, Any],
    *,
    settings: Settings | None = None,
) -> dict[str, Any] | None:
    settings = settings or get_settings()
    parsed_plan_id = parse_object_id(plan_id)
    parsed_user_id = parse_object_id(user_id)
    if parsed_plan_id is None or parsed_user_id is None:
        return None

    update_document = {
        **updates,
        "updatedAt": datetime.now(timezone.utc),
    }
    await database[settings.semester_plans_collection].update_one(
        {"_id": parsed_plan_id, "userId": parsed_user_id},
        {"$set": update_document},
    )
    return await find_semester_plan_by_id_and_user_id(database, plan_id, user_id, settings=settings)


def _serialize_semester(semester: dict[str, Any]) -> dict[str, Any]:
    payload = {
        "semesterCode": semester.get("semesterCode"),
        "goalCredits": semester.get("goalCredits"),
        "order": semester.get("order"),
        "plannedCourses": semester.get("plannedCourses") or [],
        "maybeCourses": semester.get("maybeCourses") or [],
        "notes": semester.get("notes") or "",
        "constraintsSnapshot": semester.get("constraintsSnapshot") or {},
    }
    if semester.get("weeklySchedule") is not None:
        payload["weeklySchedule"] = semester.get("weeklySchedule")
    if semester.get("customEvents") is not None:
        payload["customEvents"] = semester.get("customEvents")
    return payload


def _format_datetime(value: datetime | Any) -> Any:
    if isinstance(value, datetime):
        return value.isoformat().replace("+00:00", "Z")
    return value


def to_public_semester_plan_summary(plan_document: dict[str, Any] | None) -> dict[str, Any] | None:
    if not plan_document:
        return None

    primary_semester = (plan_document.get("semesters") or [None])[0]
    explanation = plan_document.get("explanation") or {}

    return {
        "id": str(plan_document["_id"]),
        "name": plan_document.get("name"),
        "status": plan_document.get("status"),
        "version": plan_document.get("version"),
        "plannerType": plan_document.get("plannerType"),
        "semesterCode": (primary_semester or {}).get("semesterCode"),
        "recommendedCourseCount": len((primary_semester or {}).get("plannedCourses") or []),
        "totalRecommendedCredits": explanation.get("totalRecommendedCredits", 0),
        "summary": explanation.get("summary"),
        "createdAt": _format_datetime(plan_document.get("createdAt")),
        "updatedAt": _format_datetime(plan_document.get("updatedAt")),
    }


def to_public_semester_plan(plan_document: dict[str, Any] | None) -> dict[str, Any] | None:
    if not plan_document:
        return None

    payload = {
        "id": str(plan_document["_id"]),
        "name": plan_document.get("name"),
        "status": plan_document.get("status"),
        "version": plan_document.get("version"),
        "basePlanId": (
            str(plan_document["basePlanId"])
            if plan_document.get("basePlanId") is not None
            else None
        ),
        "plannerType": plan_document.get("plannerType"),
        "assumptions": plan_document.get("assumptions") or {},
        "explanation": plan_document.get("explanation") or {},
        "semesters": [
            _serialize_semester(semester)
            for semester in (plan_document.get("semesters") or [])
        ],
        "createdAt": _format_datetime(plan_document.get("createdAt")),
        "updatedAt": _format_datetime(plan_document.get("updatedAt")),
        "shareEnabled": bool(plan_document.get("shareEnabled")),
    }
    if plan_document.get("shareEnabled") and plan_document.get("shareToken"):
        payload["shareToken"] = str(plan_document["shareToken"])
    return payload


def to_public_shared_semester_plan(plan_document: dict[str, Any] | None) -> dict[str, Any] | None:
    public = to_public_semester_plan(plan_document)
    if public is None:
        return None
    public.pop("shareToken", None)
    public["readOnly"] = True
    public["shareEnabled"] = True
    return public
