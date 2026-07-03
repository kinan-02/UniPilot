"""Extended fixtures for graduation progress edge-case and Phase 15.1 tests."""

from __future__ import annotations

from typing import Any

from bson import ObjectId

from app.config import get_settings
from tests.fixtures.graduation_progress_fixtures import PROGRAM_CODE, TOTAL_CREDITS, _bucket, _course


async def seed_graduation_progress_15_1_fixtures(database) -> dict[str, str]:
    """Same as base fixtures but pools use linkedCreditBucketId (Phase 15.1)."""
    settings = get_settings()

    program_insert = await database[settings.degree_programs_collection].insert_one(
        {
            "productionKey": f"technion-dds:program:{PROGRAM_CODE}:2025-2026",
            "institutionId": "technion",
            "programCode": PROGRAM_CODE,
            "name": "הנדסת נתונים ומידע",
            "totalCredits": TOTAL_CREDITS,
            "catalogYear": 2025,
            "catalogVersion": "2025-2026",
            "status": "published",
        }
    )
    program_id = str(program_insert.inserted_id)

    course_ds = await database[settings.courses_collection].insert_one(
        _course("00940411", "מבוא למדעי הנתונים", 3.5)
    )
    course_faculty = await database[settings.courses_collection].insert_one(
        _course("09400101", "פקולטה בחירה", 3.0)
    )
    course_core = await database[settings.courses_collection].insert_one(
        _course("00940345", "מתמטיקה דיסקרטית", 4.0)
    )

    await database[settings.degree_requirements_collection].insert_many(
        [
            _bucket(program_id, "core-mandatory", "core mandatory", 108.0),
            _bucket(program_id, "elective-ds", "elective ds", 24.5),
            _bucket(program_id, "elective-faculty", "elective faculty", 10.5),
        ]
    )

    ds_bucket_group = f"{PROGRAM_CODE}:elective-ds"
    faculty_bucket_group = f"{PROGRAM_CODE}:elective-faculty"

    await database[settings.catalog_rules_collection].insert_many(
        [
            {
                "productionKey": f"technion-dds:advisory-rule:catalog:{PROGRAM_CODE}:semester-1-matrix:2025-2026",
                "institutionId": "technion",
                "programCode": PROGRAM_CODE,
                "requirementGroupId": f"{PROGRAM_CODE}:semester-1-matrix",
                "recordType": "catalog_rule",
                "title": "Semester 1 matrix",
                "ruleExpression": {"type": "semester_matrix", "operator": "all_of", "semester": 1},
                "courseReferences": [{"courseNumber": "00940345"}],
                "advisoryOnly": True,
                "enforceInGraduationProgress": False,
                "status": "published",
            },
            {
                "productionKey": f"technion-dds:pool:{PROGRAM_CODE}:custom-ds-pool:2025-2026",
                "institutionId": "technion",
                "programCode": PROGRAM_CODE,
                "requirementGroupId": f"{PROGRAM_CODE}:custom-ds-pool",
                "linkedCreditBucketId": ds_bucket_group,
                "recordType": "catalog_rule",
                "title": "DS pool via explicit link",
                "ruleExpression": {"type": "course_pool", "operator": "choose_credits"},
                "courseReferences": [{"courseNumber": "00940411"}],
                "enforceInGraduationProgress": True,
                "status": "published",
            },
            {
                "productionKey": f"technion-dds:pool:{PROGRAM_CODE}:custom-faculty-pool:2025-2026",
                "institutionId": "technion",
                "programCode": PROGRAM_CODE,
                "requirementGroupId": f"{PROGRAM_CODE}:custom-faculty-pool",
                "linkedCreditBucketId": faculty_bucket_group,
                "recordType": "catalog_rule",
                "title": "Faculty pool via explicit link",
                "ruleExpression": {
                    "type": "course_pool",
                    "operator": "choose_credits",
                    "allowedPrefixes": ["094", "097"],
                },
                "courseReferences": [],
                "enforceInGraduationProgress": True,
                "status": "published",
            },
        ]
    )

    return {
        "programId": program_id,
        "courseDsId": str(course_ds.inserted_id),
        "courseFacultyId": str(course_faculty.inserted_id),
        "courseCoreId": str(course_core.inserted_id),
    }


async def seed_minimal_program(database, *, with_pools: bool = True) -> dict[str, Any]:
    """Minimal single-bucket program for isolated calculator scenarios."""
    settings = get_settings()
    program_code = "TEST-001"

    program = await database[settings.degree_programs_collection].insert_one(
        {
            "programCode": program_code,
            "name": "Test Program",
            "totalCredits": 10.0,
            "catalogYear": 2025,
            "catalogVersion": "2025-2026",
            "status": "published",
        }
    )
    program_id = str(program.inserted_id)

    await database[settings.degree_requirements_collection].insert_one(
        {
            "programCode": program_code,
            "requirementGroupId": f"{program_code}:core-mandatory",
            "title": "Core",
            "requirementType": "core",
            "minCredits": 10.0,
            "isMandatory": True,
            "ruleExpression": {"type": "credit_bucket", "operator": "min_credits"},
            "ruleIsExecutable": True,
            "advisoryOnly": False,
            "status": "published",
        }
    )

    pools: list[dict[str, Any]] = []
    if with_pools:
        pools = []

    return {"programId": program_id, "programCode": program_code}
