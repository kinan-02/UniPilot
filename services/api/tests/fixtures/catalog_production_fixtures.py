"""Synthetic production-like catalog fixtures for API tests."""

from __future__ import annotations

from typing import Any

from app.config import get_settings

EXCLUDED_COURSE = "00960226"
KNOWN_COURSE = "00940345"
KNOWN_PROGRAM = "009216-1-000"
HARD_REQUIREMENT_ID = "009216-1-000:core-mandatory"
ADVISORY_RULE_ID = "009216-1-000:semester-1-matrix"


async def seed_catalog_production_fixtures(database) -> None:
    settings = get_settings()
    await database[settings.courses_collection].insert_many(
        [
            _course_doc(KNOWN_COURSE, "מתמטיקה דיסקרטית"),
            _course_doc("01040031", "חדו\"א 1"),
        ]
    )
    await database[settings.course_offerings_collection].insert_one(
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
        }
    )
    await database[settings.degree_programs_collection].insert_one(
        {
            "productionKey": f"technion-dds:program:{KNOWN_PROGRAM}:2025-2026",
            "institutionId": "technion",
            "programCode": KNOWN_PROGRAM,
            "name": "הנדסת נתונים ומידע",
            "nameEn": "Data Science and Engineering",
            "totalCredits": 155.0,
            "catalogYear": 2025,
            "catalogVersion": "2025-2026",
            "status": "published",
            "paths": [],
        }
    )
    await database[settings.degree_requirements_collection].insert_one(
        {
            "productionKey": f"technion-dds:requirement:{HARD_REQUIREMENT_ID}:2025-2026",
            "institutionId": "technion",
            "programCode": KNOWN_PROGRAM,
            "requirementGroupId": HARD_REQUIREMENT_ID,
            "title": "Core mandatory",
            "requirementType": "core",
            "minCredits": 108.0,
            "courseReferences": [],
            "ruleExpression": {"type": "credit_bucket", "operator": "min_credits"},
            "ruleIsExecutable": True,
            "isMandatory": True,
            "advisoryOnly": False,
            "catalogYear": 2025,
            "catalogVersion": "2025-2026",
            "status": "published",
        }
    )
    await database[settings.catalog_rules_collection].insert_one(
        {
            "productionKey": f"technion-dds:advisory-rule:catalog:{ADVISORY_RULE_ID}:2025-2026",
            "institutionId": "technion",
            "programCode": KNOWN_PROGRAM,
            "requirementGroupId": ADVISORY_RULE_ID,
            "recordType": "catalog_rule",
            "title": "Semester 1 matrix",
            "requirementType": "core",
            "courseReferences": [{"courseNumber": KNOWN_COURSE, "titleHint": "מתמטיקה דיסקרטית"}],
            "ruleExpression": {"type": "semester_matrix", "operator": "all_of", "semester": 1},
            "ruleIsExecutable": False,
            "advisoryOnly": True,
            "enforceInGraduationProgress": False,
            "manualReviewRequired": True,
            "isMandatory": False,
            "catalogYear": 2025,
            "catalogVersion": "2025-2026",
            "status": "published",
        }
    )


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
