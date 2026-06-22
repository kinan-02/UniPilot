"""Mongo fixtures for IE/IS elective chain integration regression tests."""

from __future__ import annotations

from typing import Any

from bson import ObjectId

from app.config import get_settings
from app.curriculum.pool_course_enrichment import (
    CHOOSE_N_CHAIN_FALLBACK_NUMBERS,
    FOCUS_CHAIN_FALLBACK_NUMBERS,
)
from tests.helpers.elective_chain_contract import iter_contract_pools

TRACK_METADATA: dict[str, dict[str, Any]] = {
    "009009-1-000": {
        "name": "הנדסת תעשייה וניהול",
        "nameEn": "Industrial Engineering and Management",
        "wikiPage": "track-industrial-engineering-management",
        "electiveCredits": 40.0,
        "coreCredits": 103.0,
    },
    "009118-1-000": {
        "name": "הנדסת מערכות מידע",
        "nameEn": "Information Systems Engineering",
        "wikiPage": "track-information-systems-engineering",
        "electiveCredits": 35.5,
        "coreCredits": 107.5,
    },
}


def _fallback_numbers(suffix: str) -> tuple[str, ...]:
    return CHOOSE_N_CHAIN_FALLBACK_NUMBERS.get(suffix) or FOCUS_CHAIN_FALLBACK_NUMBERS.get(suffix, ())


async def seed_track_chain_fixtures(database, *, program_code: str) -> dict[str, str]:
    """Seed a minimal published catalog with all contract chain pools for one track."""
    settings = get_settings()
    meta = TRACK_METADATA[program_code]
    track_entries = [
        entry for entry in iter_contract_pools(faculty_id="dds") if entry["programCode"] == program_code
    ]

    program_insert = await database[settings.degree_programs_collection].insert_one(
        {
            "productionKey": f"technion-dds:program:{program_code}:2025-2026",
            "institutionId": "technion",
            "programCode": program_code,
            "name": meta["name"],
            "nameEn": meta["nameEn"],
            "totalCredits": 155.0,
            "catalogYear": 2025,
            "catalogVersion": "2025-2026",
            "metadata": {"wikiPage": meta["wikiPage"], "faculty": "dds"},
            "status": "published",
        }
    )
    program_id = str(program_insert.inserted_id)

    course_numbers: set[str] = set()
    for entry in track_entries:
        course_numbers.update(_fallback_numbers(entry["suffix"]))

    course_ids: dict[str, str] = {}
    for number in sorted(course_numbers):
        padded = number.zfill(8)
        insert = await database[settings.courses_collection].insert_one(
            {
                "productionKey": f"technion:course:{padded}",
                "institutionId": "technion",
                "courseNumber": padded,
                "titleHebrew": f"Course {padded}",
                "title": f"Course {padded}",
                "credits": 3.0,
                "catalogYear": 2025,
                "catalogVersion": "2025-2026",
                "status": "published",
            }
        )
        course_ids[padded] = str(insert.inserted_id)

    await database[settings.degree_requirements_collection].insert_many(
        [
            {
                "productionKey": f"technion-dds:requirement:{program_code}:core-mandatory:2025-2026",
                "institutionId": "technion",
                "programCode": program_code,
                "requirementGroupId": f"{program_code}:core-mandatory",
                "title": "Required courses",
                "requirementType": "core",
                "minCredits": meta["coreCredits"],
                "courseReferences": [],
                "ruleExpression": {"type": "credit_bucket", "operator": "min_credits"},
                "ruleIsExecutable": True,
                "isMandatory": True,
                "advisoryOnly": False,
                "catalogYear": 2025,
                "catalogVersion": "2025-2026",
                "status": "published",
                "degreeProgramId": ObjectId(program_id),
            },
            {
                "productionKey": f"technion-dds:requirement:{program_code}:elective-faculty:2025-2026",
                "institutionId": "technion",
                "programCode": program_code,
                "requirementGroupId": f"{program_code}:elective-faculty",
                "title": "Faculty electives",
                "requirementType": "elective",
                "minCredits": meta["electiveCredits"],
                "courseReferences": [],
                "ruleExpression": {"type": "credit_bucket", "operator": "min_credits"},
                "ruleIsExecutable": True,
                "isMandatory": True,
                "advisoryOnly": False,
                "catalogYear": 2025,
                "catalogVersion": "2025-2026",
                "status": "published",
                "degreeProgramId": ObjectId(program_id),
            },
        ]
    )

    catalog_rules: list[dict[str, Any]] = []
    for entry in track_entries:
        suffix = entry["suffix"]
        numbers = _fallback_numbers(suffix)
        catalog_rules.append(
            {
                "productionKey": f"technion-dds:advisory-rule:req:{program_code}:{suffix}:2025-2026",
                "institutionId": "technion",
                "programCode": program_code,
                "requirementGroupId": f"{program_code}:{suffix}",
                "recordType": "advisory_requirement_group",
                "title": suffix,
                "catalogDescription": f"Contract description for {suffix}",
                "ruleExpression": {
                    "type": "course_pool",
                    "operator": entry["operator"],
                    "chooseCount": 1 if entry["operator"] == "choose_n" else 3,
                },
                "courseReferences": [{"courseNumber": number.zfill(8)} for number in numbers],
                "linkedCreditBucketId": f"{program_code}:elective-faculty",
                "advisoryOnly": True,
                "enforceInGraduationProgress": False,
                "status": "published",
            }
        )

    await database[settings.catalog_rules_collection].insert_many(
        [
            {
                "productionKey": f"technion-dds:advisory-rule:catalog:{program_code}:semester-1-matrix:2025-2026",
                "institutionId": "technion",
                "programCode": program_code,
                "requirementGroupId": f"{program_code}:semester-1-matrix",
                "recordType": "catalog_rule",
                "title": "Semester 1 matrix",
                "ruleExpression": {"type": "semester_matrix", "operator": "all_of", "semester": 1},
                "courseReferences": [{"courseNumber": next(iter(course_numbers)).zfill(8)}],
                "advisoryOnly": True,
                "enforceInGraduationProgress": False,
                "status": "published",
            },
            *catalog_rules,
        ]
    )

    return {
        "programId": program_id,
        "programCode": program_code,
        "trackSlug": meta["wikiPage"],
        "chainSuffixes": [entry["suffix"] for entry in track_entries],
    }
