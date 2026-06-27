"""Read-only catalog repository — production MongoDB collections only."""

from __future__ import annotations

import re
from typing import Any

from motor.motor_asyncio import AsyncIOMotorDatabase

from app.config import Settings, get_settings
from app.catalog.excluded_courses import (
    PRODUCTION_EXCLUDED_COURSE_NUMBERS,
    is_production_excluded_course_number,
)

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

PUBLISHED_STATUS_FILTER = {"status": "published"}

PUBLISHED_COURSE_FILTER = {
    **PUBLISHED_STATUS_FILTER,
    "courseNumber": {"$exists": True, "$type": "string", "$regex": r"^0[0-9]{7}$"},
}

# Backward-compatible alias for course/offering queries
PUBLISHED_FILTER = PUBLISHED_COURSE_FILTER


def _published_course_filter() -> dict[str, Any]:
    return {
        "$and": [
            PUBLISHED_COURSE_FILTER,
            {"courseNumber": {"$nin": sorted(PRODUCTION_EXCLUDED_COURSE_NUMBERS)}},
        ]
    }


def _strip_internal_fields(document: dict[str, Any]) -> dict[str, Any]:
    return {key: value for key, value in document.items() if key not in INTERNAL_FIELDS}


def _advisory_record_rank(document: dict[str, Any]) -> tuple[int, int]:
    record_type = document.get("recordType", "catalog_rule")
    type_rank = 2 if record_type == "advisory_requirement_group" else 1 if record_type == "catalog_rule" else 0
    ref_count = len(document.get("courseReferences") or [])
    return type_rank, ref_count


def _dedupe_catalog_rules_by_group_id(documents: list[dict[str, Any]]) -> list[dict[str, Any]]:
    """Keep one rule per requirementGroupId, preferring vault advisory_requirement_group rows."""
    best_by_group: dict[str, dict[str, Any]] = {}
    for document in documents:
        group_id = str(document.get("requirementGroupId") or "")
        if not group_id:
            continue
        existing = best_by_group.get(group_id)
        if existing is None or _advisory_record_rank(document) > _advisory_record_rank(existing):
            best_by_group[group_id] = document
    return [best_by_group[group_id] for group_id in sorted(best_by_group)]


def _sanitize_metadata(metadata: dict[str, Any] | None) -> dict[str, Any]:
    if not metadata:
        return {"degreeRequirementsInferred": False}
    cleaned = dict(metadata)
    cleaned["degreeRequirementsInferred"] = False
    return cleaned


def to_public_course(document: dict[str, Any]) -> dict[str, Any]:
    public = _strip_internal_fields(document)
    public["metadata"] = _sanitize_metadata(public.get("metadata"))
    if "_id" in document:
        public["id"] = str(document["_id"])
    return public


def to_public_offering(document: dict[str, Any]) -> dict[str, Any]:
    return _strip_internal_fields(document)


def to_public_degree_program(document: dict[str, Any]) -> dict[str, Any]:
    public = _strip_internal_fields(document)
    if "_id" in document:
        public["id"] = str(document["_id"])
    metadata = public.get("metadata")
    if isinstance(metadata, dict):
        public["metadata"] = dict(metadata)
        if metadata.get("nameHe") and not public.get("nameHebrew"):
            public["nameHebrew"] = metadata.get("nameHe")
    return public


def to_public_catalog_faculty(document: dict[str, Any]) -> dict[str, Any]:
    public = _strip_internal_fields(document)
    if "_id" in document:
        public["id"] = str(document["_id"])
    return public


def to_public_path_option(document: dict[str, Any]) -> dict[str, Any]:
    public = _strip_internal_fields(document)
    if "_id" in document:
        public["id"] = str(document["_id"])
    return public


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
    course_numbers: list[str] | None = None,
    min_credits: float | None = None,
    max_credits: float | None = None,
) -> dict[str, Any]:
    filters: list[dict[str, Any]] = [_published_course_filter()]
    if course_number:
        filters.append({"courseNumber": course_number})
    if course_numbers is not None:
        filters.append({"courseNumber": {"$in": course_numbers}})
    if faculty:
        filters.append({"faculty": {"$regex": re.escape(faculty), "$options": "i"}})
    if min_credits is not None:
        filters.append({"credits": {"$gte": min_credits}})
    if max_credits is not None:
        filters.append({"credits": {"$lte": max_credits}})
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


async def list_course_numbers_with_semester_offerings(
    database: AsyncIOMotorDatabase,
    *,
    academic_year: int,
    semester_code: int,
    settings: Settings | None = None,
) -> set[str]:
    """Course numbers with offerings for a term; exact academic year first, then same term."""
    settings = settings or get_settings()
    collection = database[settings.course_offerings_collection]
    exact_query = {
        **PUBLISHED_FILTER,
        "academicYear": academic_year,
        "semesterCode": semester_code,
    }
    exact = await collection.distinct("courseNumber", exact_query)
    if exact:
        return set(exact)

    fallback_query = {**PUBLISHED_FILTER, "semesterCode": semester_code}
    fallback = await collection.distinct("courseNumber", fallback_query)
    return set(fallback)


async def list_offerings_for_courses_in_semester(
    database: AsyncIOMotorDatabase,
    course_numbers: list[str],
    *,
    academic_year: int,
    semester_code: int,
    settings: Settings | None = None,
) -> dict[str, dict[str, Any]]:
    """Map courseNumber -> best matching offering for planner search summaries."""
    from app.planning.semester_codes import pick_best_offering

    if not course_numbers:
        return {}

    settings = settings or get_settings()
    collection = database[settings.course_offerings_collection]
    cursor = collection.find(
        {
            **PUBLISHED_FILTER,
            "courseNumber": {"$in": course_numbers},
            "semesterCode": semester_code,
        }
    )
    grouped: dict[str, list[dict[str, Any]]] = {}
    async for document in cursor:
        number = str(document.get("courseNumber") or "")
        grouped.setdefault(number, []).append(document)

    summaries: dict[str, dict[str, Any]] = {}
    for number, offerings in grouped.items():
        best = pick_best_offering(
            offerings,
            preferred_academic_year=academic_year,
            semester_code=semester_code,
        )
        if not best:
            continue
        from app.planning.weekly_schedule import summarize_slot_types

        summaries[number] = {
            "academicYear": int(best.get("academicYear") or academic_year),
            "semesterCode": int(best.get("semesterCode") or semester_code),
            "slotTypes": summarize_slot_types(best.get("scheduleGroups") or []),
            "instructors": best.get("instructors"),
        }
    return summaries


async def list_planner_semester_codes_from_offerings(
    database: AsyncIOMotorDatabase,
    settings: Settings | None = None,
) -> list[str]:
    """Distinct plan semester codes (YYYY-1/2/3) from published course offerings."""
    from app.planning.semester_codes import offering_keys_to_plan_semester_code

    settings = settings or get_settings()
    collection = database[settings.course_offerings_collection]
    pipeline = [
        {"$match": PUBLISHED_STATUS_FILTER},
        {
            "$group": {
                "_id": {
                    "academicYear": "$academicYear",
                    "semesterCode": "$semesterCode",
                }
            }
        },
    ]
    codes: list[str] = []
    async for row in collection.aggregate(pipeline):
        keys = row.get("_id") or {}
        academic_year = int(keys.get("academicYear") or 0)
        semester_code = int(keys.get("semesterCode") or 0)
        plan_code = offering_keys_to_plan_semester_code(academic_year, semester_code)
        if plan_code:
            codes.append(plan_code)
    return codes


async def list_courses(
    database: AsyncIOMotorDatabase,
    *,
    q: str | None = None,
    faculty: str | None = None,
    course_number: str | None = None,
    academic_year: int | None = None,
    semester_code: int | None = None,
    min_credits: float | None = None,
    max_credits: float | None = None,
    limit: int = 50,
    offset: int = 0,
    settings: Settings | None = None,
) -> tuple[list[dict[str, Any]], int]:
    settings = settings or get_settings()
    collection = database[settings.courses_collection]

    semester_course_numbers: list[str] | None = None
    offering_summaries: dict[str, dict[str, Any]] = {}
    if academic_year is not None and semester_code is not None:
        semester_numbers = await list_course_numbers_with_semester_offerings(
            database,
            academic_year=academic_year,
            semester_code=semester_code,
            settings=settings,
        )
        if not semester_numbers:
            return [], 0
        semester_course_numbers = sorted(semester_numbers)

    query = _build_course_search_filter(
        q=q,
        faculty=faculty,
        course_number=course_number,
        course_numbers=semester_course_numbers,
        min_credits=min_credits,
        max_credits=max_credits,
    )
    total = await collection.count_documents(query)
    cursor = (
        collection.find(query)
        .sort("courseNumber", 1)
        .skip(offset)
        .limit(limit)
    )
    items = [to_public_course(doc) async for doc in cursor]

    if academic_year is not None and semester_code is not None and items:
        numbers = [item["courseNumber"] for item in items if item.get("courseNumber")]
        offering_summaries = await list_offerings_for_courses_in_semester(
            database,
            numbers,
            academic_year=academic_year,
            semester_code=semester_code,
            settings=settings,
        )
        for item in items:
            summary = offering_summaries.get(str(item.get("courseNumber") or ""))
            if summary:
                item["semesterOfferingSummary"] = summary

    return items, total


async def find_course_by_number(
    database: AsyncIOMotorDatabase,
    course_number: str,
    *,
    settings: Settings | None = None,
) -> dict[str, Any] | None:
    """Return raw published course document (includes _id)."""
    if is_production_excluded_course_number(course_number):
        return None
    settings = settings or get_settings()
    return await database[settings.courses_collection].find_one(
        {**PUBLISHED_FILTER, "courseNumber": course_number}
    )


async def get_course_by_number(
    database: AsyncIOMotorDatabase,
    course_number: str,
    *,
    settings: Settings | None = None,
) -> dict[str, Any] | None:
    if is_production_excluded_course_number(course_number):
        return None
    settings = settings or get_settings()
    document = await database[settings.courses_collection].find_one(
        {**PUBLISHED_FILTER, "courseNumber": course_number}
    )
    if not document:
        return None
    return to_public_course(document)


async def find_course_by_id(
    database: AsyncIOMotorDatabase,
    course_id: str,
    *,
    settings: Settings | None = None,
) -> dict[str, Any] | None:
    """Return raw published course document for FK validation (includes _id)."""
    from bson import ObjectId

    settings = settings or get_settings()
    try:
        parsed_id = ObjectId(str(course_id))
    except Exception:
        return None

    return await database[settings.courses_collection].find_one(
        {"_id": parsed_id, **PUBLISHED_FILTER}
    )


def course_summary_from_document(course_document: dict[str, Any] | None) -> dict[str, str] | None:
    if not course_document:
        return None
    number = course_document.get("courseNumber") or course_document.get("number")
    title = course_document.get("title") or course_document.get("titleHebrew")
    if number is None and title is None:
        return None
    return {
        "number": str(number) if number is not None else None,
        "title": str(title) if title is not None else None,
    }


async def list_offerings_for_course(
    database: AsyncIOMotorDatabase,
    course_number: str,
    *,
    academic_year: int | None = None,
    semester_code: int | None = None,
    settings: Settings | None = None,
) -> list[dict[str, Any]]:
    grouped = await list_offerings_grouped_for_courses(
        database,
        [course_number],
        academic_year=academic_year,
        semester_code=semester_code,
        settings=settings,
    )
    return grouped.get(course_number, [])


async def list_offerings_grouped_for_courses(
    database: AsyncIOMotorDatabase,
    course_numbers: list[str],
    *,
    academic_year: int | None = None,
    semester_code: int | None = None,
    settings: Settings | None = None,
) -> dict[str, list[dict[str, Any]]]:
    """Batch-fetch offerings grouped by courseNumber."""
    unique_numbers = sorted({str(number) for number in course_numbers if number})
    if not unique_numbers:
        return {}

    settings = settings or get_settings()
    query: dict[str, Any] = {
        **PUBLISHED_FILTER,
        "courseNumber": {"$in": unique_numbers},
    }
    if academic_year is not None:
        query["academicYear"] = academic_year
    if semester_code is not None:
        query["semesterCode"] = semester_code

    grouped: dict[str, list[dict[str, Any]]] = {number: [] for number in unique_numbers}
    cursor = database[settings.course_offerings_collection].find(query).sort(
        [("academicYear", 1), ("semesterCode", 1)]
    )
    async for document in cursor:
        number = str(document.get("courseNumber") or "")
        if number in grouped:
            grouped[number].append(to_public_offering(document))
    return grouped


async def list_best_offerings_for_courses(
    database: AsyncIOMotorDatabase,
    course_numbers: list[str],
    *,
    academic_year: int,
    semester_code: int,
    settings: Settings | None = None,
) -> dict[str, dict[str, Any]]:
    """Return best offering per courseNumber for a plan term (exact year, then term fallback)."""
    from app.planning.semester_codes import pick_best_offering

    unique_numbers = sorted({str(number) for number in course_numbers if number})
    if not unique_numbers:
        return {}

    exact_grouped = await list_offerings_grouped_for_courses(
        database,
        unique_numbers,
        academic_year=academic_year,
        semester_code=semester_code,
        settings=settings,
    )
    fallback_grouped = await list_offerings_grouped_for_courses(
        database,
        unique_numbers,
        academic_year=None,
        semester_code=semester_code,
        settings=settings,
    )

    best_by_number: dict[str, dict[str, Any]] = {}
    for number in unique_numbers:
        exact = pick_best_offering(
            exact_grouped.get(number, []),
            preferred_academic_year=academic_year,
            semester_code=semester_code,
        )
        if exact:
            best_by_number[number] = exact
            continue
        fallback = pick_best_offering(
            fallback_grouped.get(number, []),
            preferred_academic_year=academic_year,
            semester_code=semester_code,
        )
        if fallback:
            best_by_number[number] = fallback
    return best_by_number


async def find_courses_by_numbers(
    database: AsyncIOMotorDatabase,
    course_numbers: list[str],
    *,
    settings: Settings | None = None,
) -> list[dict[str, Any]]:
    unique_numbers = sorted({str(number) for number in course_numbers if number})
    if not unique_numbers:
        return []

    settings = settings or get_settings()
    cursor = database[settings.courses_collection].find(
        {**PUBLISHED_FILTER, "courseNumber": {"$in": unique_numbers}}
    )
    return [doc async for doc in cursor]


async def list_degree_programs(
    database: AsyncIOMotorDatabase,
    *,
    faculty_id: str | None = None,
    study_level: str | None = None,
    settings: Settings | None = None,
) -> list[dict[str, Any]]:
    settings = settings or get_settings()
    query: dict[str, Any] = dict(PUBLISHED_STATUS_FILTER)
    if faculty_id:
        query["$or"] = [
            {"metadata.facultyId": faculty_id},
            {"metadata.faculty": faculty_id.removeprefix("faculty-")},
        ]
    cursor = database[settings.degree_programs_collection].find(query).sort("programCode", 1)
    programs = [to_public_degree_program(doc) async for doc in cursor]
    if study_level:
        programs = [
            program
            for program in programs
            if _program_matches_study_level(program, study_level)
        ]
    return programs


def _program_matches_study_level(program: dict[str, Any], study_level: str) -> bool:
    metadata = program.get("metadata") or {}
    kind = metadata.get("programKind")
    if study_level == "MD":
        if kind == "graduate_program":
            return False
        wiki_page = metadata.get("wikiPage")
        if wiki_page == "track-medicine-md":
            return True
        study_levels = program.get("studyLevels") or metadata.get("studyLevels") or []
        return "MD" in study_levels
    if kind == "graduate_program":
        return study_level in {"MSc", "PhD", "MBA"}
    if kind == "md_program" or metadata.get("wikiPage") == "track-medicine-md":
        return study_level == "MD"
    return study_level == "BSc"


async def get_degree_program_by_code(
    database: AsyncIOMotorDatabase,
    program_code: str,
    *,
    settings: Settings | None = None,
) -> dict[str, Any] | None:
    settings = settings or get_settings()
    document = await database[settings.degree_programs_collection].find_one(
        {**PUBLISHED_STATUS_FILTER, "programCode": program_code}
    )
    if not document:
        return None
    return to_public_degree_program(document)


async def find_degree_program_by_id(
    database: AsyncIOMotorDatabase,
    degree_id: str,
    *,
    settings: Settings | None = None,
) -> dict[str, Any] | None:
    """Return raw published degree program document (includes _id)."""
    from bson import ObjectId

    settings = settings or get_settings()
    try:
        object_id = ObjectId(degree_id)
    except Exception:
        return None
    return await database[settings.degree_programs_collection].find_one(
        {**PUBLISHED_STATUS_FILTER, "_id": object_id}
    )


async def find_path_option_by_id(
    database: AsyncIOMotorDatabase,
    option_id: str,
    *,
    settings: Settings | None = None,
) -> dict[str, Any] | None:
    from bson import ObjectId

    settings = settings or get_settings()
    try:
        object_id = ObjectId(option_id)
    except Exception:
        return None
    return await database[settings.catalog_path_options_collection].find_one(
        {**PUBLISHED_STATUS_FILTER, "_id": object_id}
    )


async def find_primary_path_option_for_track(
    database: AsyncIOMotorDatabase,
    *,
    track_slug: str,
    program_code: str | None = None,
    settings: Settings | None = None,
) -> dict[str, Any] | None:
    settings = settings or get_settings()
    query: dict[str, Any] = {
        **PUBLISHED_STATUS_FILTER,
        "wikiSlug": track_slug,
        "selectableAsPrimary": True,
    }
    if program_code:
        query["linkedProgramCode"] = program_code
    return await database[settings.catalog_path_options_collection].find_one(query)


async def _faculty_ids_with_path_options(
    database: AsyncIOMotorDatabase,
    *,
    study_level: str | None = None,
    settings: Settings | None = None,
) -> list[str]:
    settings = settings or get_settings()
    match_query: dict[str, Any] = dict(PUBLISHED_STATUS_FILTER)
    if study_level:
        match_query["studyLevels"] = study_level
    pipeline: list[dict[str, Any]] = [
        {"$match": match_query},
        {"$group": {"_id": "$facultyId"}},
        {"$sort": {"_id": 1}},
    ]
    faculty_ids: list[str] = []
    async for row in database[settings.catalog_path_options_collection].aggregate(pipeline):
        faculty_id = row.get("_id")
        if faculty_id:
            faculty_ids.append(str(faculty_id))
    return faculty_ids


async def list_catalog_faculties(
    database: AsyncIOMotorDatabase,
    *,
    institution_id: str | None = None,
    study_level: str | None = None,
    with_path_options_only: bool = False,
    settings: Settings | None = None,
) -> list[dict[str, Any]]:
    settings = settings or get_settings()
    query: dict[str, Any] = dict(PUBLISHED_STATUS_FILTER)
    if institution_id:
        query["institutionId"] = institution_id
    if with_path_options_only or study_level:
        faculty_ids = await _faculty_ids_with_path_options(
            database,
            study_level=study_level,
            settings=settings,
        )
        if not faculty_ids:
            return []
        query["facultyId"] = {"$in": faculty_ids}
    cursor = database[settings.catalog_faculties_collection].find(query).sort("facultyId", 1)
    return [to_public_catalog_faculty(doc) async for doc in cursor]


async def list_path_options(
    database: AsyncIOMotorDatabase,
    *,
    faculty_id: str | None = None,
    study_level: str | None = None,
    kind: str | None = None,
    primary_only: bool | None = None,
    settings: Settings | None = None,
) -> list[dict[str, Any]]:
    settings = settings or get_settings()
    query: dict[str, Any] = dict(PUBLISHED_STATUS_FILTER)
    if faculty_id:
        query["facultyId"] = faculty_id
    if kind:
        query["kind"] = kind
    if primary_only is True:
        query["selectableAsPrimary"] = True
    elif primary_only is False:
        query["selectableAsPrimary"] = False

    cursor = database[settings.catalog_path_options_collection].find(query).sort("name", 1)
    options = [to_public_path_option(doc) async for doc in cursor]

    if study_level:
        options = [
            option
            for option in options
            if study_level in (option.get("studyLevels") or [])
        ]

    linked_codes = {
        option["linkedProgramCode"]
        for option in options
        if option.get("linkedProgramCode")
    }
    programs_by_code: dict[str, list[dict[str, Any]]] = {}
    if linked_codes:
        program_cursor = database[settings.degree_programs_collection].find(
            {**PUBLISHED_STATUS_FILTER, "programCode": {"$in": list(linked_codes)}},
            {"programCode": 1, "metadata": 1},
        )
        async for program in program_cursor:
            code = str(program["programCode"])
            programs_by_code.setdefault(code, []).append(program)

    for option in options:
        linked_code = option.get("linkedProgramCode")
        if not linked_code:
            continue
        candidates = programs_by_code.get(linked_code, [])
        if not candidates:
            continue
        curriculum_slug = option.get("curriculumWikiSlug") or option.get("wikiSlug")
        matched = next(
            (
                program
                for program in candidates
                if (program.get("metadata") or {}).get("wikiPage") == curriculum_slug
            ),
            None,
        )
        if matched is None and len(candidates) == 1:
            matched = candidates[0]
        if matched is not None:
            option["linkedDegreeProgramId"] = str(matched["_id"])

    return options


async def list_course_pools_for_program(
    database: AsyncIOMotorDatabase,
    program_code: str,
    *,
    settings: Settings | None = None,
) -> list[dict[str, Any]]:
    """Return course_pool documents from catalog_rules for eligibility enforcement."""
    settings = settings or get_settings()
    query = {
        **PUBLISHED_STATUS_FILTER,
        "programCode": program_code,
        "ruleExpression.type": "course_pool",
    }
    cursor = database[settings.catalog_rules_collection].find(query).sort("requirementGroupId", 1)
    return [doc async for doc in cursor]


async def list_semester_matrix_rules_for_program(
    database: AsyncIOMotorDatabase,
    program_code: str,
    *,
    settings: Settings | None = None,
) -> list[dict[str, Any]]:
    """Return semester_matrix catalog rules — mandatory course source for planning."""
    settings = settings or get_settings()
    query = {
        **PUBLISHED_STATUS_FILTER,
        "programCode": program_code,
        "ruleExpression.type": "semester_matrix",
    }
    cursor = database[settings.catalog_rules_collection].find(query).sort("requirementGroupId", 1)
    documents = [doc async for doc in cursor]
    return _dedupe_catalog_rules_by_group_id(documents)


async def list_courses_by_number_prefixes(
    database: AsyncIOMotorDatabase,
    prefixes: list[str],
    *,
    limit: int = 200,
    settings: Settings | None = None,
) -> list[dict[str, Any]]:
    if not prefixes:
        return []

    settings = settings or get_settings()
    prefix_filters = [
        {"courseNumber": {"$regex": f"^{re.escape(str(prefix))}"}} for prefix in prefixes
    ]
    query: dict[str, Any] = {"$and": [PUBLISHED_FILTER, {"$or": prefix_filters}]}
    cursor = (
        database[settings.courses_collection]
        .find(query)
        .sort("courseNumber", 1)
        .limit(limit)
    )
    return [doc async for doc in cursor]


async def find_courses_by_ids(
    database: AsyncIOMotorDatabase,
    course_ids: list[str],
    *,
    settings: Settings | None = None,
) -> list[dict[str, Any]]:
    from bson import ObjectId

    settings = settings or get_settings()
    object_ids = []
    for course_id in course_ids:
        try:
            object_ids.append(ObjectId(str(course_id)))
        except Exception:
            continue

    if not object_ids:
        return []

    cursor = database[settings.courses_collection].find(
        {"_id": {"$in": object_ids}, **PUBLISHED_FILTER}
    )
    return [doc async for doc in cursor]


async def list_hard_requirements_for_program(
    database: AsyncIOMotorDatabase,
    program_code: str,
    *,
    settings: Settings | None = None,
    include_internal: bool = False,
) -> list[dict[str, Any]]:
    settings = settings or get_settings()
    query = {
        **PUBLISHED_STATUS_FILTER,
        "programCode": program_code,
        "ruleIsExecutable": True,
        "advisoryOnly": {"$ne": True},
    }
    cursor = database[settings.degree_requirements_collection].find(query).sort(
        "requirementGroupId", 1
    )
    documents = [doc async for doc in cursor]
    if include_internal:
        return documents
    return [to_public_hard_requirement(doc) for doc in documents]


async def list_advisory_rules_for_program(
    database: AsyncIOMotorDatabase,
    program_code: str,
    *,
    settings: Settings | None = None,
) -> list[dict[str, Any]]:
    settings = settings or get_settings()
    query = {
        **PUBLISHED_STATUS_FILTER,
        "programCode": program_code,
        "advisoryOnly": True,
        "enforceInGraduationProgress": False,
    }
    cursor = database[settings.catalog_rules_collection].find(query).sort(
        "requirementGroupId", 1
    )
    documents = [doc async for doc in cursor]
    deduped = _dedupe_catalog_rules_by_group_id(documents)
    return [to_public_advisory_rule(doc) for doc in deduped]


async def list_faculties(
    database: AsyncIOMotorDatabase,
    *,
    settings: Settings | None = None,
) -> list[str]:
    settings = settings or get_settings()
    collection = database[settings.courses_collection]
    values = await collection.distinct(
        "faculty",
        {**PUBLISHED_STATUS_FILTER, "faculty": {"$exists": True, "$nin": [None, ""]}},
    )
    return sorted(str(value).strip() for value in values if str(value).strip())
