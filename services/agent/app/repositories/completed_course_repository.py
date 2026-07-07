"""User-owned completed courses repository."""

from __future__ import annotations

from datetime import datetime, timezone
from typing import Any, Literal

from bson import ObjectId
from motor.motor_asyncio import AsyncIOMotorDatabase

from app.config import Settings, get_settings
from app.services.completed_course_attempts import MAX_COURSE_ATTEMPTS, resolve_available_attempt

UpdateStatus = Literal["updated", "not_found", "not_editable"]
DeleteStatus = Literal["deleted", "not_found", "not_editable"]


def parse_object_id(value: str | None) -> ObjectId | None:
    if value is None:
        return None
    try:
        return ObjectId(str(value))
    except Exception:
        return None


async def ensure_completed_course_indexes(
    database: AsyncIOMotorDatabase,
    *,
    settings: Settings | None = None,
) -> None:
    settings = settings or get_settings()
    collection = database[settings.completed_courses_collection]
    await collection.create_index(
        [("userId", 1), ("courseId", 1), ("attempt", 1)],
        unique=True,
        name="completed_courses_unique_user_course_attempt",
    )
    await collection.create_index(
        [("userId", 1), ("semesterCode", 1)],
        name="completed_courses_user_semester",
    )
    await collection.create_index(
        [("userId", 1), ("recordedAt", -1)],
        name="completed_courses_user_recorded_at",
    )


def build_completed_course_document(user_id: str, record_data: dict[str, Any]) -> dict[str, Any]:
    parsed_user_id = parse_object_id(user_id)
    if parsed_user_id is None:
        raise ValueError("Invalid user id for completed course")

    parsed_course_id = parse_object_id(record_data["courseId"])
    if parsed_course_id is None:
        raise ValueError("Invalid course id for completed course")

    now = datetime.now(timezone.utc)

    return {
        "userId": parsed_user_id,
        "courseId": parsed_course_id,
        "courseOfferingId": None,
        "semesterCode": record_data["semesterCode"],
        "grade": record_data["grade"],
        "gradePoints": record_data.get("gradePoints"),
        "creditsEarned": record_data["creditsEarned"],
        "attempt": record_data.get("attempt", 1),
        "source": record_data.get("source", "manual"),
        "metadata": record_data.get("metadata") or {},
        "recordedAt": now,
        "createdAt": now,
        "updatedAt": now,
    }


async def find_used_attempts_for_course(
    database: AsyncIOMotorDatabase,
    user_id: str,
    course_id: str,
    *,
    settings: Settings | None = None,
) -> set[int]:
    settings = settings or get_settings()
    parsed_user_id = parse_object_id(user_id)
    parsed_course_id = parse_object_id(course_id)
    if parsed_user_id is None or parsed_course_id is None:
        return set()

    records = await database[settings.completed_courses_collection].find(
        {"userId": parsed_user_id, "courseId": parsed_course_id},
        {"attempt": 1},
    ).to_list(length=MAX_COURSE_ATTEMPTS)

    return {int(record.get("attempt") or 1) for record in records}


async def create_completed_course(
    database: AsyncIOMotorDatabase,
    user_id: str,
    record_data: dict[str, Any],
    *,
    settings: Settings | None = None,
) -> dict[str, Any]:
    settings = settings or get_settings()
    course_id = str(record_data["courseId"])
    used_attempts = await find_used_attempts_for_course(
        database,
        user_id,
        course_id,
        settings=settings,
    )
    resolved_attempt = resolve_available_attempt(
        used_attempts,
        record_data.get("attempt", 1),
    )
    resolved_record_data = {**record_data, "attempt": resolved_attempt}
    document = build_completed_course_document(user_id, resolved_record_data)
    insert_result = await database[settings.completed_courses_collection].insert_one(document)
    return {
        "_id": insert_result.inserted_id,
        **document,
    }


async def find_completed_courses_by_user_id(
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
        return {"records": [], "total": 0, "page": page, "limit": limit}

    safe_page = max(page, 1)
    safe_limit = min(max(limit, 1), 100)
    skip = (safe_page - 1) * safe_limit

    collection = database[settings.completed_courses_collection]
    query = {"userId": parsed_user_id}

    records = (
        await collection.find(query)
        .sort("recordedAt", -1)
        .skip(skip)
        .limit(safe_limit)
        .to_list(length=safe_limit)
    )
    total = await collection.count_documents(query)

    return {
        "records": records,
        "total": total,
        "page": safe_page,
        "limit": safe_limit,
    }


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


async def find_completed_course_by_id_and_user_id(
    database: AsyncIOMotorDatabase,
    record_id: str,
    user_id: str,
    *,
    settings: Settings | None = None,
) -> dict[str, Any] | None:
    settings = settings or get_settings()
    parsed_record_id = parse_object_id(record_id)
    parsed_user_id = parse_object_id(user_id)
    if parsed_record_id is None or parsed_user_id is None:
        return None

    return await database[settings.completed_courses_collection].find_one(
        {"_id": parsed_record_id, "userId": parsed_user_id}
    )


async def update_completed_course_by_id_and_user_id(
    database: AsyncIOMotorDatabase,
    record_id: str,
    user_id: str,
    updates: dict[str, Any],
    *,
    settings: Settings | None = None,
) -> dict[str, Any]:
    settings = settings or get_settings()
    existing_record = await find_completed_course_by_id_and_user_id(
        database,
        record_id,
        user_id,
        settings=settings,
    )
    if not existing_record:
        return {"status": "not_found"}

    if existing_record.get("source") != "manual":
        return {"status": "not_editable", "record": existing_record}

    update_document: dict[str, Any] = {"updatedAt": datetime.now(timezone.utc)}

    if "semesterCode" in updates:
        update_document["semesterCode"] = updates["semesterCode"]
    if "grade" in updates:
        update_document["grade"] = updates["grade"]
    if "gradePoints" in updates:
        update_document["gradePoints"] = updates["gradePoints"]
    if "creditsEarned" in updates:
        update_document["creditsEarned"] = updates["creditsEarned"]
    if "metadata" in updates:
        update_document["metadata"] = updates["metadata"]

    update_result = await database[settings.completed_courses_collection].find_one_and_update(
        {
            "_id": existing_record["_id"],
            "userId": existing_record["userId"],
            "source": "manual",
        },
        {"$set": update_document},
        return_document=True,
    )

    if not update_result:
        return {"status": "not_found"}

    return {"status": "updated", "record": update_result}


async def delete_imported_completed_courses_by_user_id(
    database: AsyncIOMotorDatabase,
    user_id: str,
    *,
    settings: Settings | None = None,
) -> int:
    """Remove all PDF-imported transcript rows for a user (manual rows are kept)."""
    settings = settings or get_settings()
    parsed_user_id = parse_object_id(user_id)
    if parsed_user_id is None:
        return 0

    result = await database[settings.completed_courses_collection].delete_many(
        {"userId": parsed_user_id, "source": "imported"},
    )
    return int(result.deleted_count)


async def delete_completed_course_by_id_and_user_id(
    database: AsyncIOMotorDatabase,
    record_id: str,
    user_id: str,
    *,
    settings: Settings | None = None,
) -> dict[str, Any]:
    settings = settings or get_settings()
    existing_record = await find_completed_course_by_id_and_user_id(
        database,
        record_id,
        user_id,
        settings=settings,
    )
    if not existing_record:
        return {"status": "not_found"}

    if existing_record.get("source") != "manual":
        return {"status": "not_editable", "record": existing_record}

    delete_result = await database[settings.completed_courses_collection].delete_one(
        {
            "_id": existing_record["_id"],
            "userId": existing_record["userId"],
            "source": "manual",
        }
    )

    if not delete_result.deleted_count:
        return {"status": "not_found"}

    return {"status": "deleted"}


def _format_datetime(value: datetime | Any) -> Any:
    if isinstance(value, datetime):
        return value.isoformat().replace("+00:00", "Z")
    return value


def to_public_completed_course(
    record_document: dict[str, Any] | None,
    course_summary: dict[str, str] | None = None,
) -> dict[str, Any] | None:
    if not record_document:
        return None

    return {
        "id": str(record_document["_id"]),
        "courseId": str(record_document["courseId"]),
        "courseNumber": course_summary.get("number") if course_summary else None,
        "courseTitle": course_summary.get("title") if course_summary else None,
        "semesterCode": record_document["semesterCode"],
        "grade": record_document["grade"],
        "gradePoints": record_document.get("gradePoints"),
        "creditsEarned": record_document["creditsEarned"],
        "attempt": record_document["attempt"],
        "source": record_document["source"],
        "metadata": record_document.get("metadata") or {},
        "recordedAt": _format_datetime(record_document["recordedAt"]),
        "createdAt": _format_datetime(record_document["createdAt"]),
        "updatedAt": _format_datetime(record_document["updatedAt"]),
    }
