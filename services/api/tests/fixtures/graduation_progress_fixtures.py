"""Fixtures for graduation progress tests."""

from __future__ import annotations

from typing import Any

from bson import ObjectId

from app.config import get_settings

PROGRAM_CODE = "009216-1-000"
TOTAL_CREDITS = 155.0


async def seed_graduation_progress_fixtures(database) -> dict[str, str]:
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
            "metadata": {"wikiPage": "track-data-information-engineering", "faculty": "dds"},
            "status": "published",
        }
    )
    program_id = str(program_insert.inserted_id)

    course_a = await database[settings.courses_collection].insert_one(_course("00940345", "מתמטיקה דיסקרטית", 4.0))
    course_b = await database[settings.courses_collection].insert_one(_course("00940411", "מבוא למדעי הנתונים", 3.5))
    course_c = await database[settings.courses_collection].insert_one(_course("09400101", "פקולטה בחירה", 3.0))
    course_d = await database[settings.courses_collection].insert_one(_course("01040031", "מבוא למדעי המחשב", 3.5))
    course_e = await database[settings.courses_collection].insert_one(_course("00940219", "מבני נתונים", 3.5))

    await database[settings.degree_requirements_collection].insert_many(
        [
            _bucket(program_id, "core-mandatory", "core mandatory", 108.0),
            _bucket(program_id, "elective-ds", "elective ds", 24.5),
            _bucket(program_id, "elective-faculty", "elective faculty", 10.5),
        ]
    )

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
                "courseReferences": [
                    {"courseNumber": "00940345"},
                    {"courseNumber": "01040031"},
                ],
                "advisoryOnly": True,
                "enforceInGraduationProgress": False,
                "status": "published",
            },
            {
                "productionKey": f"technion-dds:advisory-rule:catalog:{PROGRAM_CODE}:semester-2-matrix:2025-2026",
                "institutionId": "technion",
                "programCode": PROGRAM_CODE,
                "requirementGroupId": f"{PROGRAM_CODE}:semester-2-matrix",
                "recordType": "catalog_rule",
                "title": "Semester 2 matrix",
                "ruleExpression": {"type": "semester_matrix", "operator": "all_of", "semester": 2},
                "courseReferences": [{"courseNumber": "00940219"}],
                "advisoryOnly": True,
                "enforceInGraduationProgress": False,
                "status": "published",
            },
            {
                "productionKey": f"technion-dds:advisory-rule:catalog:{PROGRAM_CODE}:elective-ds-pool:2025-2026",
                "institutionId": "technion",
                "programCode": PROGRAM_CODE,
                "requirementGroupId": f"{PROGRAM_CODE}:elective-ds-pool",
                "recordType": "catalog_rule",
                "title": "Data science elective pool",
                "ruleExpression": {"type": "course_pool", "operator": "choose_credits"},
                "courseReferences": [{"courseNumber": "00940411"}],
                "advisoryOnly": True,
                "enforceInGraduationProgress": False,
                "status": "published",
            },
            {
                "productionKey": f"technion-dds:advisory-rule:catalog:{PROGRAM_CODE}:elective-faculty-pool:2025-2026",
                "institutionId": "technion",
                "programCode": PROGRAM_CODE,
                "requirementGroupId": f"{PROGRAM_CODE}:elective-faculty-pool",
                "recordType": "catalog_rule",
                "title": "Faculty elective pool",
                "ruleExpression": {
                    "type": "course_pool",
                    "operator": "choose_credits",
                    "allowedPrefixes": ["094"],
                },
                "courseReferences": [],
                "advisoryOnly": True,
                "enforceInGraduationProgress": False,
                "status": "published",
            },
        ]
    )

    return {
        "programId": program_id,
        "courseAId": str(course_a.inserted_id),
        "courseBId": str(course_b.inserted_id),
        "courseCId": str(course_c.inserted_id),
        "courseDId": str(course_d.inserted_id),
        "courseEId": str(course_e.inserted_id),
        "courseANumber": "00940345",
        "courseBNumber": "00940411",
        "courseCNumber": "09400101",
        "courseDNumber": "01040031",
        "courseENumber": "00940219",
    }


def _course(number: str, title: str, credits: float) -> dict[str, Any]:
    return {
        "productionKey": f"technion:course:{number}",
        "institutionId": "technion",
        "courseNumber": number,
        "titleHebrew": title,
        "title": title,
        "credits": credits,
        "catalogYear": 2025,
        "catalogVersion": "2025-2026",
        "status": "published",
    }


def _bucket(program_id: str, suffix: str, title: str, min_credits: float) -> dict[str, Any]:
    return {
        "productionKey": f"technion-dds:requirement:{PROGRAM_CODE}:{suffix}:2025-2026",
        "institutionId": "technion",
        "programCode": PROGRAM_CODE,
        "requirementGroupId": f"{PROGRAM_CODE}:{suffix}",
        "title": title,
        "requirementType": "elective" if "elective" in suffix else "core",
        "minCredits": min_credits,
        "courseReferences": [],
        "ruleExpression": {"type": "credit_bucket", "operator": "min_credits"},
        "ruleIsExecutable": True,
        "isMandatory": True,
        "advisoryOnly": False,
        "catalogYear": 2025,
        "catalogVersion": "2025-2026",
        "status": "published",
        "degreeProgramId": ObjectId(program_id),
    }
