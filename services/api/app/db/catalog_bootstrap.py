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
TOTAL_ADVISORY_RULES = 46

ADVISORY_COUNTS_BY_PROGRAM: dict[str, int] = {
    "009216-1-000": 14,
    "009009-1-000": 17,
    "009118-1-000": 15,
}

GENERAL_ADVISORY_POOL_SUFFIXES = (
    "enrichment-pool",
    "free-elective-pool",
    "physical-education-pool",
)

LINKED_CREDIT_BUCKET_BY_POOL_SUFFIX: dict[str, str] = {
    "elective-ds-pool": "elective-ds",
    "elective-faculty-pool": "elective-faculty",
    "enrichment-pool": "enrichment",
    "free-elective-pool": "free-elective",
    "physical-education-pool": "physical-education",
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
        "wikiPage": "track-data-information-engineering",
    },
    "009009-1-000": {
        "name": "הנדסת תעשייה וניהול",
        "nameEn": "Industrial Engineering and Management",
        "totalCredits": 155.0,
        "wikiPage": "track-industrial-engineering-management",
    },
    "009118-1-000": {
        "name": "הנדסת מערכות מידע",
        "nameEn": "Information Systems Engineering",
        "totalCredits": 155.0,
        "wikiPage": "track-information-systems-engineering",
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
    "009216-1-000:enrichment-pool",
    "009216-1-000:free-elective-pool",
    "009216-1-000:physical-education-pool",
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
    "009009-1-000:enrichment-pool",
    "009009-1-000:free-elective-pool",
    "009009-1-000:physical-education-pool",
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
    "009118-1-000:enrichment-pool",
    "009118-1-000:free-elective-pool",
    "009118-1-000:physical-education-pool",
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

    programs_existing = await database[resolved.degree_programs_collection].count_documents({})
    faculties_existing = await database[resolved.catalog_faculties_collection].count_documents({})
    path_options_existing = await database[resolved.catalog_path_options_collection].count_documents({})

    if programs_existing > 0 and faculties_existing > 0 and path_options_existing > 0:
        return False

    if programs_existing == 0:
        await seed_minimal_catalog(database, resolved)
        logger.info(
            "Seeded vault-like development catalog (%d programs, %d advisory rules)",
            len(ALL_PROGRAMS),
            TOTAL_ADVISORY_RULES,
        )
        return True

    if faculties_existing == 0 or path_options_existing == 0:
        await _seed_catalog_faculties_and_path_options(database, resolved)
        logger.info("Seeded missing catalog faculties/path options for development")
        return True

    return False


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
    await _seed_catalog_faculties_and_path_options(database, resolved)


async def _seed_catalog_faculties_and_path_options(
    database: AsyncIOMotorDatabase,
    settings: Settings,
) -> None:
    faculty_doc = {
        "productionKey": "technion:faculty:faculty-dds:2025-2026",
        "institutionId": "technion",
        "facultyId": "faculty-dds",
        "wikiSlug": "faculty-dds",
        "name": "הפקולטה למדעי הנתונים וההחלטות",
        "nameHe": "הפקולטה למדעי הנתונים וההחלטות",
        "nameEn": "Faculty of Data Science and Decisions",
        "aliases": ["DDS"],
        "catalogYear": 2025,
        "catalogVersion": "2025-2026",
        "status": "published",
    }
    await database[settings.catalog_faculties_collection].insert_one(faculty_doc)

    track_options = [
        (
            "track-data-information-engineering",
            "009216-1-000",
            "הנדסת נתונים ומידע",
            "Data and Information Engineering",
        ),
        (
            "track-industrial-engineering-management",
            "009009-1-000",
            "הנדסת תעשייה וניהול",
            "Industrial Engineering and Management",
        ),
        (
            "track-information-systems-engineering",
            "009118-1-000",
            "הנדסת מערכות מידע",
            "Information Systems Engineering",
        ),
    ]
    path_docs = []
    for wiki_slug, program_code, name_he, name_en in track_options:
        path_docs.append(
            {
                "productionKey": f"technion:path-option:technion:dds:{wiki_slug}:2025-2026",
                "optionKey": f"technion:dds:{wiki_slug}",
                "institutionId": "technion",
                "facultyId": "faculty-dds",
                "wikiSlug": wiki_slug,
                "kind": "bsc_track",
                "name": name_he,
                "nameHe": name_he,
                "nameEn": name_en,
                "studyLevels": ["BSc"],
                "selectableAsPrimary": True,
                "linkedProgramCode": program_code,
                "catalogYear": 2025,
                "catalogVersion": "2025-2026",
                "status": "published",
            }
        )
    path_docs.extend(
        [
            {
                "productionKey": "technion:path-option:technion:dds:program-excellence:2025-2026",
                "optionKey": "technion:dds:program-excellence",
                "institutionId": "technion",
                "facultyId": "faculty-dds",
                "wikiSlug": "program-excellence",
                "kind": "special_program",
                "name": "תוכנית מצוינות פקולטית",
                "nameHe": "תוכנית מצוינות פקולטית",
                "nameEn": "Faculty Excellence Program",
                "studyLevels": ["BSc", "MSc"],
                "selectableAsPrimary": False,
                "catalogYear": 2025,
                "catalogVersion": "2025-2026",
                "status": "published",
            },
            {
                "productionKey": "technion:path-option:technion:dds:minor-robotics:2025-2026",
                "optionKey": "technion:dds:minor-robotics",
                "institutionId": "technion",
                "facultyId": "faculty-dds",
                "wikiSlug": "minor-robotics",
                "kind": "minor",
                "name": "מינור רובוטיקה",
                "nameHe": "מינור רובוטיקה",
                "nameEn": "Robotics Minor",
                "studyLevels": ["BSc"],
                "selectableAsPrimary": False,
                "catalogYear": 2025,
                "catalogVersion": "2025-2026",
                "status": "published",
            },
            {
                "productionKey": "technion:path-option:technion:dds:grad-data-science:2025-2026",
                "optionKey": "technion:dds:grad-data-science",
                "institutionId": "technion",
                "facultyId": "faculty-dds",
                "wikiSlug": "grad-data-science",
                "kind": "graduate_program",
                "name": "מדעי נתונים ומידע",
                "nameHe": "מדעי נתונים ומידע",
                "nameEn": "Data Science",
                "studyLevels": ["MSc", "PhD"],
                "selectableAsPrimary": True,
                "catalogYear": 2025,
                "catalogVersion": "2025-2026",
                "status": "published",
            },
        ]
    )
    if path_docs:
        await database[settings.catalog_path_options_collection].insert_many(path_docs)


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
        "metadata": {
            "facultyId": "faculty-dds",
            "faculty": "dds",
            "wikiPage": PROGRAM_METADATA[program_code].get("wikiPage"),
            "programKind": "bsc_track",
        },
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
    pool_suffix = requirement_group_id.split(":", 1)[1]
    title = pool_suffix.replace("-", " ").replace(":", " ")
    course_refs: list[dict[str, Any]] = []
    if requirement_group_id == ADVISORY_RULE_ID:
        course_refs = [{"courseNumber": KNOWN_COURSE, "titleHint": "מתמטיקה דיסקרטית"}]

    rule_type = "semester_matrix" if "semester-" in requirement_group_id else "course_pool"
    rule_expression: dict[str, Any] = (
        {"type": "semester_matrix", "operator": "all_of", "semester": 1}
        if rule_type == "semester_matrix"
        else {"type": "course_pool", "operator": "min_credits"}
    )
    if pool_suffix == "enrichment-pool":
        rule_expression = {
            "type": "course_pool",
            "operator": "min_credits",
            "allowedPrefixes": ["039405"],
        }
    elif pool_suffix == "physical-education-pool":
        rule_expression = {
            "type": "course_pool",
            "operator": "min_credits",
            "allowedPrefixes": ["039408", "039409"],
        }

    document: dict[str, Any] = {
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
    linked_bucket_suffix = LINKED_CREDIT_BUCKET_BY_POOL_SUFFIX.get(pool_suffix)
    if linked_bucket_suffix:
        document["linkedCreditBucketId"] = f"{program_code}:{linked_bucket_suffix}"
    return document


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
