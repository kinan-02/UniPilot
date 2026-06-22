from datetime import datetime, timezone
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


async def ensure_student_profile_indexes(database: AsyncIOMotorDatabase) -> None:
    await database[STUDENT_PROFILES_COLLECTION].create_index(
        [("userId", 1)],
        unique=True,
        name="student_profiles_unique_user",
    )
    await database[STUDENT_PROFILES_COLLECTION].create_index(
        [("degreeId", 1)],
        name="student_profiles_degree_id",
    )


def build_profile_document(user_id: str, profile_data: dict[str, Any]) -> dict[str, Any]:
    parsed_user_id = parse_object_id(user_id)
    if parsed_user_id is None:
        raise ValueError("Invalid user id for student profile")

    now = datetime.now(timezone.utc)
    degree_id = profile_data.get("degreeId")

    return {
        "userId": parsed_user_id,
        "institutionId": profile_data["institutionId"],
        "programType": profile_data["programType"],
        "degreeId": parse_object_id(degree_id) if degree_id else None,
        "catalogYear": profile_data["catalogYear"],
        "currentSemesterCode": profile_data["currentSemesterCode"],
        "academicPath": profile_data.get("academicPath") or {},
        "preferences": profile_data.get("preferences") or {},
        "revision": 1,
        "createdAt": now,
        "updatedAt": now,
    }


async def create_student_profile(
    database: AsyncIOMotorDatabase,
    user_id: str,
    profile_data: dict[str, Any],
) -> dict[str, Any]:
    profile_document = build_profile_document(user_id, profile_data)
    insert_result = await database[STUDENT_PROFILES_COLLECTION].insert_one(profile_document)
    return {
        "_id": insert_result.inserted_id,
        **profile_document,
    }


async def find_student_profile_by_user_id(
    database: AsyncIOMotorDatabase,
    user_id: str,
) -> dict[str, Any] | None:
    parsed_user_id = parse_object_id(user_id)
    if parsed_user_id is None:
        return None

    return await database[STUDENT_PROFILES_COLLECTION].find_one({"userId": parsed_user_id})


async def update_student_profile_by_user_id(
    database: AsyncIOMotorDatabase,
    user_id: str,
    updates: dict[str, Any],
) -> dict[str, Any] | None:
    parsed_user_id = parse_object_id(user_id)
    if parsed_user_id is None:
        return None

    update_document: dict[str, Any] = {
        "updatedAt": datetime.now(timezone.utc),
    }

    if "institutionId" in updates:
        update_document["institutionId"] = updates["institutionId"]
    if "programType" in updates:
        update_document["programType"] = updates["programType"]
    if "degreeId" in updates:
        degree_id = updates["degreeId"]
        update_document["degreeId"] = parse_object_id(degree_id) if degree_id else None
    if "catalogYear" in updates:
        update_document["catalogYear"] = updates["catalogYear"]
    if "currentSemesterCode" in updates:
        update_document["currentSemesterCode"] = updates["currentSemesterCode"]
    if "academicPath" in updates:
        update_document["academicPath"] = updates["academicPath"]
    if "preferences" in updates:
        update_document["preferences"] = updates["preferences"]

    update_result = await database[STUDENT_PROFILES_COLLECTION].find_one_and_update(
        {"userId": parsed_user_id},
        {
            "$set": update_document,
            "$inc": {"revision": 1},
        },
        return_document=True,
    )

    return update_result


async def delete_student_profile_by_user_id(
    database: AsyncIOMotorDatabase,
    user_id: str,
) -> int:
    parsed_user_id = parse_object_id(user_id)
    if parsed_user_id is None:
        return 0

    delete_result = await database[STUDENT_PROFILES_COLLECTION].delete_one(
        {"userId": parsed_user_id}
    )
    return delete_result.deleted_count


def _format_datetime(value: datetime | Any) -> Any:
    if isinstance(value, datetime):
        return value.isoformat().replace("+00:00", "Z")
    return value


def to_public_student_profile(profile_document: dict[str, Any] | None) -> dict[str, Any] | None:
    if not profile_document:
        return None

    degree_id = profile_document.get("degreeId")

    return {
        "id": str(profile_document["_id"]),
        "userId": str(profile_document["userId"]),
        "institutionId": profile_document["institutionId"],
        "programType": profile_document["programType"],
        "degreeId": str(degree_id) if degree_id else None,
        "catalogYear": profile_document["catalogYear"],
        "currentSemesterCode": profile_document["currentSemesterCode"],
        "academicPath": profile_document.get("academicPath") or {},
        "preferences": profile_document.get("preferences") or {},
        "revision": profile_document["revision"],
        "createdAt": _format_datetime(profile_document["createdAt"]),
        "updatedAt": _format_datetime(profile_document["updatedAt"]),
    }
