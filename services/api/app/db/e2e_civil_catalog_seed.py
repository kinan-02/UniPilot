"""Minimal civil-engineering catalog for AUTO_SEED / E2E (non-DDS faculty smoke)."""

from __future__ import annotations

from typing import Any

from motor.motor_asyncio import AsyncIOMotorDatabase

from app.config import Settings, get_settings

CIVIL_PROGRAM_CODE = "001401-1-000"
CIVIL_TRACK_SLUG = "track-civil-engineering-structures"
CIVIL_FACULTY_ID = "faculty-civil-environmental-engineering"
CIVIL_KNOWN_COURSE = "00140008"

LINKED_CREDIT_BUCKET_BY_POOL_SUFFIX: dict[str, str] = {
    "enrichment-pool": "enrichment",
    "free-elective-pool": "free-elective",
    "physical-education-pool": "physical-education",
    "civil-hebrew-group-א-pool": "track-electives",
    "civil-hebrew-group-ב-pool": "track-electives",
}

HARD_BUCKETS: tuple[tuple[str, str, float], ...] = (
    ("mandatory-technion-and-faculty-courses", "Mandatory Technion and faculty courses", 89.0),
    ("track-mandatory-courses", "Track mandatory courses", 45.5),
    ("track-electives", "Track electives", 12.0),
    ("general-technion-electives", "General Technion electives", 12.0),
    ("enrichment", "University enrichment", 6.0),
    ("free-elective", "Free electives", 4.0),
    ("physical-education", "Physical education", 2.0),
)

SEMESTER_MATRICES: tuple[tuple[int, tuple[str, ...]], ...] = (
    (1, (CIVIL_KNOWN_COURSE, "00140102")),
    (2, ("00140104",)),
    (3, ("00140108",)),
    (4, ("00140149",)),
    (5, ("00140143",)),
    (6, ("00140131",)),
    (7, ("00140132",)),
    (8, ("00140145",)),
)

POOL_SUFFIXES: tuple[str, ...] = (
    "enrichment-pool",
    "free-elective-pool",
    "physical-education-pool",
    "civil-hebrew-group-א-pool",
    "civil-hebrew-group-ב-pool",
)

SEEDED_COURSES: tuple[tuple[str, str, float], ...] = (
    (CIVIL_KNOWN_COURSE, "מידע גרפי הנדסי", 3.0),
    ("00140102", "מבוא למכניקה הנדסית", 4.5),
    ("00140104", "תורת החוזק 1", 4.0),
    ("00140108", "סטטיקת מבנים", 4.0),
    ("03940800", "חינוך גופני", 1.0),
)


async def seed_e2e_civil_catalog(database: AsyncIOMotorDatabase, settings: Settings | None = None) -> None:
    """Insert a minimal published civil catalog for onboarding + planner E2E."""
    resolved = settings or get_settings()

    await database[resolved.courses_collection].insert_many(
        [_course_doc(number, title, credits) for number, title, credits in SEEDED_COURSES]
    )
    await database[resolved.course_offerings_collection].insert_many(
        [
            {
                "productionKey": f"technion:course-offering:{CIVIL_KNOWN_COURSE}:2025:201",
                "courseNumber": CIVIL_KNOWN_COURSE,
                "academicYear": 2025,
                "semesterCode": 201,
                "semesterName": "spring",
                "scheduleGroups": [
                    {"day": "Sunday", "time": "08:30-10:30", "type": "הרצאה", "group": "01"}
                ],
                "examDates": {"moedA": "2025-06-01"},
                "instructors": "Dr. Example",
                "sourceFile": "courses_2025_201.json",
                "catalogVersion": "2025-2026",
                "status": "published",
            },
            {
                "productionKey": "technion:course-offering:00140102:2025:201",
                "courseNumber": "00140102",
                "academicYear": 2025,
                "semesterCode": 201,
                "semesterName": "spring",
                "scheduleGroups": [
                    {"day": "Monday", "time": "10:30-12:30", "type": "הרצאה", "group": "01"}
                ],
                "examDates": {"moedA": "2025-06-01"},
                "instructors": "Dr. Example",
                "sourceFile": "courses_2025_201.json",
                "catalogVersion": "2025-2026",
                "status": "published",
            },
        ]
    )

    await database[resolved.degree_programs_collection].insert_one(_program_doc())
    await database[resolved.degree_requirements_collection].insert_many(
        [_hard_requirement_doc(slug, title, min_credits) for slug, title, min_credits in HARD_BUCKETS]
    )
    await database[resolved.catalog_rules_collection].insert_many(
        [_semester_matrix_doc(semester, course_numbers) for semester, course_numbers in SEMESTER_MATRICES]
        + [_pool_doc(suffix) for suffix in POOL_SUFFIXES]
    )

    await database[resolved.catalog_faculties_collection].insert_one(
        {
            "productionKey": "technion:faculty:faculty-civil-environmental-engineering:2025-2026",
            "institutionId": "technion",
            "facultyId": CIVIL_FACULTY_ID,
            "wikiSlug": CIVIL_FACULTY_ID,
            "name": "הפקולטה להנדסה אזרחית וסביבתית",
            "nameHe": "הפקולטה להנדסה אזרחית וסביבתית",
            "nameEn": "Faculty of Civil and Environmental Engineering",
            "aliases": ["Civil"],
            "catalogYear": 2025,
            "catalogVersion": "2025-2026",
            "status": "published",
        }
    )
    await database[resolved.catalog_path_options_collection].insert_one(
        {
            "productionKey": f"technion:path-option:technion:civil:{CIVIL_TRACK_SLUG}:2025-2026",
            "optionKey": f"technion:civil:{CIVIL_TRACK_SLUG}",
            "institutionId": "technion",
            "facultyId": CIVIL_FACULTY_ID,
            "wikiSlug": CIVIL_TRACK_SLUG,
            "kind": "bsc_track",
            "name": "מסלול הנדסה אזרחית – מבנים",
            "nameHe": "מסלול הנדסה אזרחית – מבנים",
            "nameEn": "Civil Engineering — Structures Track",
            "studyLevels": ["BSc"],
            "selectableAsPrimary": True,
            "linkedProgramCode": CIVIL_PROGRAM_CODE,
            "catalogYear": 2025,
            "catalogVersion": "2025-2026",
            "status": "published",
        }
    )


def _program_doc() -> dict[str, Any]:
    return {
        "productionKey": f"technion-civil:program:{CIVIL_PROGRAM_CODE}:2025-2026",
        "institutionId": "technion",
        "programCode": CIVIL_PROGRAM_CODE,
        "name": "מסלול הנדסה אזרחית – מבנים",
        "nameEn": "Civil Engineering — Structures Track",
        "totalCredits": 158.5,
        "catalogYear": 2025,
        "catalogVersion": "2025-2026",
        "status": "published",
        "paths": [],
        "metadata": {
            "facultyId": CIVIL_FACULTY_ID,
            "faculty": "civil-environmental-engineering",
            "wikiPage": CIVIL_TRACK_SLUG,
            "programKind": "bsc_track",
        },
    }


def _hard_requirement_doc(slug: str, title: str, min_credits: float) -> dict[str, Any]:
    group_id = f"{CIVIL_PROGRAM_CODE}:{slug}"
    return {
        "productionKey": f"technion-civil:requirement:{group_id}:2025-2026",
        "institutionId": "technion",
        "programCode": CIVIL_PROGRAM_CODE,
        "requirementGroupId": group_id,
        "title": title,
        "requirementType": "elective" if "elective" in slug or slug in {"enrichment", "physical-education"} else "core",
        "minCredits": min_credits,
        "courseReferences": [],
        "ruleExpression": {"type": "credit_bucket", "operator": "min_credits"},
        "ruleIsExecutable": True,
        "isMandatory": slug.startswith("mandatory") or slug.startswith("track-mandatory"),
        "advisoryOnly": False,
        "catalogYear": 2025,
        "catalogVersion": "2025-2026",
        "status": "published",
    }


def _semester_matrix_doc(semester: int, course_numbers: tuple[str, ...]) -> dict[str, Any]:
    group_id = f"{CIVIL_PROGRAM_CODE}:semester-{semester}-matrix"
    return {
        "productionKey": f"technion-civil:advisory:{group_id}:2025-2026",
        "institutionId": "technion",
        "programCode": CIVIL_PROGRAM_CODE,
        "requirementGroupId": group_id,
        "recordType": "catalog_rule",
        "title": f"Semester {semester} matrix",
        "ruleExpression": {"type": "semester_matrix", "operator": "all_of", "semester": semester},
        "courseReferences": [{"courseNumber": number} for number in course_numbers],
        "ruleIsExecutable": False,
        "advisoryOnly": True,
        "enforceInGraduationProgress": False,
        "manualReviewRequired": True,
        "isMandatory": False,
        "catalogYear": 2025,
        "catalogVersion": "2025-2026",
        "status": "published",
    }


def _pool_doc(pool_suffix: str) -> dict[str, Any]:
    group_id = f"{CIVIL_PROGRAM_CODE}:{pool_suffix}"
    rule_expression: dict[str, Any] = {"type": "course_pool", "operator": "min_credits"}
    if pool_suffix == "enrichment-pool":
        rule_expression["allowedPrefixes"] = ["039405"]
    elif pool_suffix == "physical-education-pool":
        rule_expression["allowedPrefixes"] = ["039408", "039409"]
    elif pool_suffix.startswith("civil-hebrew-group"):
        rule_expression["operator"] = "choose_credits"

    document: dict[str, Any] = {
        "productionKey": f"technion-civil:advisory:{group_id}:2025-2026",
        "institutionId": "technion",
        "programCode": CIVIL_PROGRAM_CODE,
        "requirementGroupId": group_id,
        "recordType": "catalog_rule",
        "title": pool_suffix.replace("-", " "),
        "ruleExpression": rule_expression,
        "courseReferences": [],
        "ruleIsExecutable": False,
        "advisoryOnly": True,
        "enforceInGraduationProgress": False,
        "manualReviewRequired": True,
        "isMandatory": False,
        "catalogYear": 2025,
        "catalogVersion": "2025-2026",
        "status": "published",
    }
    linked_bucket = LINKED_CREDIT_BUCKET_BY_POOL_SUFFIX.get(pool_suffix)
    if linked_bucket:
        document["linkedCreditBucketId"] = f"{CIVIL_PROGRAM_CODE}:{linked_bucket}"
    return document


def _course_doc(course_number: str, title_hebrew: str, credits: float) -> dict[str, Any]:
    return {
        "productionKey": f"technion:course:{course_number}",
        "institutionId": "technion",
        "courseNumber": course_number,
        "titleHebrew": title_hebrew,
        "title": title_hebrew,
        "credits": credits,
        "faculty": "הפקולטה להנדסה אזרחית וסביבתית",
        "catalogYear": 2025,
        "catalogVersion": "2025-2026",
        "metadata": {"degreeRequirementsInferred": False},
        "status": "published",
    }
