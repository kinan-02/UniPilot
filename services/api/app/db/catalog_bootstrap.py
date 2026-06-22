"""Seed a minimal published catalog when production collections are empty (development only)."""

from __future__ import annotations

import logging
from typing import Any

from motor.motor_asyncio import AsyncIOMotorDatabase

from app.config import Settings, get_settings

logger = logging.getLogger(__name__)

EXCLUDED_COURSE = "00960226"
KNOWN_COURSE = "00940345"
KNOWN_PROGRAM = "009216-1-000"
HARD_REQUIREMENT_ID = "009216-1-000:core-mandatory"
ADVISORY_RULE_ID = "009216-1-000:semester-1-matrix"

ALL_PROGRAMS = (
    "009216-1-000",
    "009009-1-000",
    "009118-1-000",
)

TOTAL_HARD_REQUIREMENTS = 16
TOTAL_ADVISORY_RULES = 37

ADVISORY_COUNTS_BY_PROGRAM: dict[str, int] = {
    "009216-1-000": 11,
    "009009-1-000": 14,
    "009118-1-000": 12,
}

HARD_REQUIREMENT_SLUGS_BY_PROGRAM: dict[str, list[tuple[str, str, float]]] = {
    "009216-1-000": [
        ("core-mandatory", "Required courses", 108.0),
        ("elective-ds", "DNE electives", 24.5),
        ("elective-faculty", "Faculty electives", 10.5),
        ("enrichment", "University enrichment", 6.0),
        ("free-elective", "Free electives", 4.0),
        ("physical-education", "Physical Education", 2.0),
    ],
    "009009-1-000": [
        ("core-mandatory", "Required courses", 103.0),
        ("elective-faculty", "Faculty electives", 40.0),
        ("enrichment", "University enrichment", 6.0),
        ("free-elective", "Free electives", 4.0),
        ("physical-education", "Physical Education", 2.0),
    ],
    "009118-1-000": [
        ("core-mandatory", "Required courses", 107.5),
        ("elective-faculty", "Faculty electives", 35.5),
        ("enrichment", "University enrichment", 6.0),
        ("free-elective", "Free electives", 4.0),
        ("physical-education", "Physical Education", 2.0),
    ],
}

PROGRAM_METADATA: dict[str, dict[str, Any]] = {
    "009216-1-000": {
        "name": "הנדסת נתונים ומידע",
        "nameEn": "Data and Information Engineering",
        "totalCredits": 155.0,
    },
    "009009-1-000": {
        "name": "הנדסת תעשייה וניהול",
        "nameEn": "Industrial Engineering and Management",
        "totalCredits": 155.0,
    },
    "009118-1-000": {
        "name": "הנדסת מערכות מידע",
        "nameEn": "Information Systems Engineering",
        "totalCredits": 155.0,
    },
}

DNE_ADVISORY_GROUP_IDS = (
    "009216-1-000:semester-1-matrix",
    "009216-1-000:semester-2-matrix",
    "009216-1-000:semester-3-matrix",
    "009216-1-000:semester-4-matrix",
    "009216-1-000:semester-5-matrix",
    "009216-1-000:semester-7-matrix",
    "009216-1-000:semester-8-matrix",
    "009216-1-000:elective-ds-pool",
    "009216-1-000:elective-faculty-pool",
    "009216-1-000:cognition-track:requirements",
    "009216-1-000:math-analytics-track:requirements",
)

IEM_ADVISORY_GROUP_IDS = (
    "009009-1-000:semester-1-matrix",
    "009009-1-000:semester-2-matrix",
    "009009-1-000:semester-3-matrix",
    "009009-1-000:semester-4-matrix",
    "009009-1-000:semester-5-matrix",
    "009009-1-000:semester-6-matrix",
    "009009-1-000:semester-7-matrix",
    "009009-1-000:semester-8-matrix",
    "009009-1-000:ie-statistics-elective-chain",
    "009009-1-000:ie-behavior-science-chain",
    "009009-1-000:ie-focus-chain-game-theory",
    "009009-1-000:ie-focus-chain-advanced-industry",
    "009009-1-000:ie-focus-chain-operations-research",
    "009009-1-000:ie-additional-faculty-electives",
)

ISE_ADVISORY_GROUP_IDS = (
    "009118-1-000:semester-1-matrix",
    "009118-1-000:semester-2-matrix",
    "009118-1-000:semester-3-matrix",
    "009118-1-000:semester-4-matrix",
    "009118-1-000:semester-5-matrix",
    "009118-1-000:semester-7-matrix",
    "009118-1-000:semester-8-matrix",
    "009118-1-000:is-behavior-science-chain",
    "009118-1-000:is-focus-chain-performance",
    "009118-1-000:is-focus-chain-ml",
    "009118-1-000:is-focus-chain-game-theory",
    "009118-1-000:is-additional-faculty-electives",
)

ADVISORY_GROUP_IDS_BY_PROGRAM: dict[str, tuple[str, ...]] = {
    "009216-1-000": DNE_ADVISORY_GROUP_IDS,
    "009009-1-000": IEM_ADVISORY_GROUP_IDS,
    "009118-1-000": ISE_ADVISORY_GROUP_IDS,
}


async def ensure_development_catalog(database: AsyncIOMotorDatabase, settings: Settings | None = None) -> bool:
    """Insert sample catalog documents when degree_programs is empty. Returns True if seeded."""
    resolved = settings or get_settings()
    if resolved.environment != "development" or not resolved.auto_seed_catalog:
        return False

    existing = await database[resolved.degree_programs_collection].count_documents({})
    if existing > 0:
        return False

    await seed_minimal_catalog(database, resolved)
    logger.info(
        "Seeded vault-like development catalog (%d programs, %d advisory rules)",
        len(ALL_PROGRAMS),
        TOTAL_ADVISORY_RULES,
    )
    return True


async def seed_minimal_catalog(database: AsyncIOMotorDatabase, settings: Settings | None = None) -> None:
    resolved = settings or get_settings()
    await database[resolved.courses_collection].insert_many(
        [
            _course_doc(KNOWN_COURSE, "מתמטיקה דיסקרטית"),
            _course_doc("01040031", 'חדו"א 1'),
            _course_doc("02340117", "מבוא למדעי המחשב"),
        ]
    )
    await database[resolved.course_offerings_collection].insert_many(
        [
            {
                "productionKey": f"technion:course-offering:{KNOWN_COURSE}:2025:201",
                "courseNumber": KNOWN_COURSE,
                "academicYear": 2025,
                "semesterCode": 201,
                "semesterName": "spring",
                "scheduleGroups": [{"day": "Sunday", "time": "10:30-12:30"}],
                "examDates": {"moedA": "2025-06-01"},
                "instructors": "Dr. Example",
                "sourceFile": "courses_2025_201.json",
                "catalogVersion": "2025-2026",
                "status": "published",
            },
            {
                "productionKey": "technion:course-offering:02340117:2025:201",
                "courseNumber": "02340117",
                "academicYear": 2025,
                "semesterCode": 201,
                "semesterName": "spring",
                "scheduleGroups": [{"day": "Sunday", "time": "12:30-14:30"}],
                "examDates": {"moedA": "2025-06-01"},
                "instructors": "Dr. Example",
                "sourceFile": "courses_2025_201.json",
                "catalogVersion": "2025-2026",
                "status": "published",
            },
        ]
    )

    program_docs = [_program_doc(program_code) for program_code in ALL_PROGRAMS]
    await database[resolved.degree_programs_collection].insert_many(program_docs)

    hard_docs = [
        _hard_requirement_doc(program_code, slug, title, min_credits)
        for program_code, buckets in HARD_REQUIREMENT_SLUGS_BY_PROGRAM.items()
        for slug, title, min_credits in buckets
    ]
    await database[resolved.degree_requirements_collection].insert_many(hard_docs)

    advisory_docs = [
        _advisory_rule_doc(group_id)
        for program_code in ALL_PROGRAMS
        for group_id in ADVISORY_GROUP_IDS_BY_PROGRAM[program_code]
    ]
    assert len(advisory_docs) == TOTAL_ADVISORY_RULES
    await database[resolved.catalog_rules_collection].insert_many(advisory_docs)


def _program_doc(program_code: str) -> dict[str, Any]:
    meta = PROGRAM_METADATA[program_code]
    return {
        "productionKey": f"technion-dds:program:{program_code}:2025-2026",
        "institutionId": "technion",
        "programCode": program_code,
        "name": meta["name"],
        "nameEn": meta["nameEn"],
        "totalCredits": meta["totalCredits"],
        "catalogYear": 2025,
        "catalogVersion": "2025-2026",
        "status": "published",
        "paths": [],
        "sourceMetadata": {
            "curationReport": {
                "vaultSignoff": {
                    "signedOffBy": "vault-wiki",
                    "signoffSource": "vault-wiki",
                }
            }
        },
    }


def _hard_requirement_doc(
    program_code: str,
    slug: str,
    title: str,
    min_credits: float,
) -> dict[str, Any]:
    group_id = f"{program_code}:{slug}"
    return {
        "productionKey": f"technion-dds:requirement:{group_id}:2025-2026",
        "institutionId": "technion",
        "programCode": program_code,
        "requirementGroupId": group_id,
        "title": title,
        "requirementType": "core" if slug == "core-mandatory" else "elective",
        "minCredits": min_credits,
        "courseReferences": [],
        "ruleExpression": {"type": "credit_bucket", "operator": "min_credits"},
        "ruleIsExecutable": True,
        "isMandatory": slug == "core-mandatory",
        "advisoryOnly": False,
        "catalogYear": 2025,
        "catalogVersion": "2025-2026",
        "status": "published",
    }


def _advisory_rule_doc(requirement_group_id: str) -> dict[str, Any]:
    program_code = requirement_group_id.split(":", 1)[0]
    title = requirement_group_id.split(":", 1)[1].replace("-", " ").replace(":", " ")
    course_refs: list[dict[str, Any]] = []
    if requirement_group_id == ADVISORY_RULE_ID:
        course_refs = [{"courseNumber": KNOWN_COURSE, "titleHint": "מתמטיקה דיסקרטית"}]

    rule_type = "semester_matrix" if "semester-" in requirement_group_id else "course_pool"
    rule_expression: dict[str, Any] = (
        {"type": "semester_matrix", "operator": "all_of", "semester": 1}
        if rule_type == "semester_matrix"
        else {"type": "course_pool", "operator": "min_credits"}
    )

    return {
        "productionKey": f"technion-dds:advisory:{requirement_group_id}:2025-2026",
        "institutionId": "technion",
        "programCode": program_code,
        "requirementGroupId": requirement_group_id,
        "recordType": "advisory_requirement_group",
        "title": title,
        "requirementType": "core" if "semester-" in requirement_group_id else "elective",
        "courseReferences": course_refs,
        "ruleExpression": rule_expression,
        "ruleIsExecutable": False,
        "advisoryOnly": True,
        "enforceInGraduationProgress": False,
        "manualReviewRequired": True,
        "isMandatory": False,
        "catalogYear": 2025,
        "catalogVersion": "2025-2026",
        "status": "published",
    }


def _course_doc(course_number: str, title_hebrew: str) -> dict[str, Any]:
    return {
        "productionKey": f"technion:course:{course_number}",
        "institutionId": "technion",
        "courseNumber": course_number,
        "titleHebrew": title_hebrew,
        "title": title_hebrew,
        "credits": 4.0,
        "faculty": "הפקולטה למדעי הנתונים וההחלטות",
        "catalogYear": 2025,
        "catalogVersion": "2025-2026",
        "metadata": {"degreeRequirementsInferred": False},
        "status": "published",
    }
