"""Read-only catalog repository — production MongoDB collections only."""

from __future__ import annotations

import re
from typing import Any

from motor.motor_asyncio import AsyncIOMotorDatabase

from app.config import Settings, get_settings

INTERNAL_FIELDS = frozenset(
    {
        "_id",
        "productionKey",
        "promotionRunId",
        "promotedAt",
        "isStaging",
        "productionEligible",
        "sourceMetadata",
        "sourceName",
        "sourceType",
        "sourceVersion",
        "sourceRefs",
        "sourceFiles",
        "updatedAt",
    }
)

PUBLISHED_FILTER = {"status": "published"}


def _strip_internal_fields(document: dict[str, Any]) -> dict[str, Any]:
    return {key: value for key, value in document.items() if key not in INTERNAL_FIELDS}


def _sanitize_metadata(metadata: dict[str, Any] | None) -> dict[str, Any]:
    if not metadata:
        return {"degreeRequirementsInferred": False}
    cleaned = dict(metadata)
    cleaned["degreeRequirementsInferred"] = False
    return cleaned


def to_public_course(document: dict[str, Any]) -> dict[str, Any]:
    public = _strip_internal_fields(document)
    public["metadata"] = _sanitize_metadata(public.get("metadata"))
    return public


def to_public_offering(document: dict[str, Any]) -> dict[str, Any]:
    return _strip_internal_fields(document)


def to_public_degree_program(document: dict[str, Any]) -> dict[str, Any]:
    return _strip_internal_fields(document)


def to_public_hard_requirement(document: dict[str, Any]) -> dict[str, Any]:
    public = _strip_internal_fields(document)
    public["requirementEnforcement"] = "hard"
    public["advisoryOnly"] = False
    public["enforceInGraduationProgress"] = True
    return public


def to_public_advisory_rule(document: dict[str, Any]) -> dict[str, Any]:
    public = _strip_internal_fields(document)
    public["advisoryOnly"] = True
    public["enforceInGraduationProgress"] = False
    public["notHardRequirement"] = True
    public["isMandatory"] = False
    public["ruleIsExecutable"] = False
    return public


def _build_course_search_filter(
    *,
    q: str | None,
    faculty: str | None,
    course_number: str | None,
) -> dict[str, Any]:
    filters: list[dict[str, Any]] = [PUBLISHED_FILTER.copy()]
    if course_number:
        filters.append({"courseNumber": course_number})
    if faculty:
        filters.append({"faculty": {"$regex": re.escape(faculty), "$options": "i"}})
    if q:
        pattern = re.escape(q)
        filters.append(
            {
                "$or": [
                    {"courseNumber": {"$regex": pattern, "$options": "i"}},
                    {"titleHebrew": {"$regex": pattern, "$options": "i"}},
                    {"title": {"$regex": pattern, "$options": "i"}},
                    {"faculty": {"$regex": pattern, "$options": "i"}},
                ]
            }
        )
    if len(filters) == 1:
        return filters[0]
    return {"$and": filters}


async def list_courses(
    database: AsyncIOMotorDatabase,
    *,
    q: str | None = None,
    faculty: str | None = None,
    course_number: str | None = None,
    limit: int = 50,
    offset: int = 0,
    settings: Settings | None = None,
) -> tuple[list[dict[str, Any]], int]:
    settings = settings or get_settings()
    collection = database[settings.courses_collection]
    query = _build_course_search_filter(q=q, faculty=faculty, course_number=course_number)
    total = await collection.count_documents(query)
    cursor = (
        collection.find(query)
        .sort("courseNumber", 1)
        .skip(offset)
        .limit(limit)
    )
    items = [to_public_course(doc) async for doc in cursor]
    return items, total


async def get_course_by_number(
    database: AsyncIOMotorDatabase,
    course_number: str,
    *,
    settings: Settings | None = None,
) -> dict[str, Any] | None:
    settings = settings or get_settings()
    document = await database[settings.courses_collection].find_one(
        {**PUBLISHED_FILTER, "courseNumber": course_number}
    )
    if not document:
        return None
    return to_public_course(document)


async def list_offerings_for_course(
    database: AsyncIOMotorDatabase,
    course_number: str,
    *,
    academic_year: int | None = None,
    semester_code: int | None = None,
    settings: Settings | None = None,
) -> list[dict[str, Any]]:
    settings = settings or get_settings()
    query: dict[str, Any] = {**PUBLISHED_FILTER, "courseNumber": course_number}
    if academic_year is not None:
        query["academicYear"] = academic_year
    if semester_code is not None:
        query["semesterCode"] = semester_code
    cursor = database[settings.course_offerings_collection].find(query).sort(
        [("academicYear", 1), ("semesterCode", 1)]
    )
    return [to_public_offering(doc) async for doc in cursor]


async def list_degree_programs(
    database: AsyncIOMotorDatabase,
    *,
    settings: Settings | None = None,
) -> list[dict[str, Any]]:
    settings = settings or get_settings()
    cursor = database[settings.degree_programs_collection].find(PUBLISHED_FILTER).sort(
        "programCode", 1
    )
    return [to_public_degree_program(doc) async for doc in cursor]


async def get_degree_program_by_code(
    database: AsyncIOMotorDatabase,
    program_code: str,
    *,
    settings: Settings | None = None,
) -> dict[str, Any] | None:
    settings = settings or get_settings()
    document = await database[settings.degree_programs_collection].find_one(
        {**PUBLISHED_FILTER, "programCode": program_code}
    )
    if not document:
        return None
    return to_public_degree_program(document)


async def list_hard_requirements_for_program(
    database: AsyncIOMotorDatabase,
    program_code: str,
    *,
    settings: Settings | None = None,
) -> list[dict[str, Any]]:
    settings = settings or get_settings()
    query = {
        **PUBLISHED_FILTER,
        "programCode": program_code,
        "ruleIsExecutable": True,
        "advisoryOnly": {"$ne": True},
    }
    cursor = database[settings.degree_requirements_collection].find(query).sort(
        "requirementGroupId", 1
    )
    return [to_public_hard_requirement(doc) async for doc in cursor]


async def list_advisory_rules_for_program(
    database: AsyncIOMotorDatabase,
    program_code: str,
    *,
    settings: Settings | None = None,
) -> list[dict[str, Any]]:
    settings = settings or get_settings()
    query = {
        **PUBLISHED_FILTER,
        "programCode": program_code,
        "advisoryOnly": True,
        "enforceInGraduationProgress": False,
    }
    cursor = database[settings.catalog_rules_collection].find(query).sort(
        "requirementGroupId", 1
    )
    return [to_public_advisory_rule(doc) async for doc in cursor]
