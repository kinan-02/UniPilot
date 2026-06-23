"""Integration tests for general Technion buckets in graduation progress."""

from __future__ import annotations

from typing import Any

import pytest
from bson import ObjectId

from app.config import get_settings
from tests.fixtures.completed_course_fixtures import build_completed_course_payload
from tests.fixtures.graduation_progress_fixtures import PROGRAM_CODE, seed_graduation_progress_fixtures
from tests.integration.test_graduation_progress_integration import register_access_token

GENERAL_TECHNION_SUFFIXES = ("enrichment", "free-elective", "physical-education")


async def seed_general_technion_requirements(database, program_id: str) -> None:
    settings = get_settings()
    await database[settings.degree_requirements_collection].insert_many(
        [
            _general_bucket(program_id, "enrichment", "University enrichment", 6.0),
            _general_bucket(program_id, "free-elective", "Free electives", 4.0),
            _general_bucket(program_id, "physical-education", "Physical education", 2.0),
        ]
    )
    await database[settings.catalog_rules_collection].insert_many(
        [
            _general_pool("enrichment-pool", "enrichment", ["039405"]),
            _general_pool("free-elective-pool", "free-elective", []),
            _general_pool("physical-education-pool", "physical-education", ["039408", "039409"]),
        ]
    )


def _general_bucket(program_id: str, suffix: str, title: str, min_credits: float) -> dict[str, Any]:
    return {
        "productionKey": f"technion-dds:requirement:{PROGRAM_CODE}:{suffix}:2025-2026",
        "institutionId": "technion",
        "programCode": PROGRAM_CODE,
        "requirementGroupId": f"{PROGRAM_CODE}:{suffix}",
        "title": title,
        "requirementType": "enrichment" if suffix != "free-elective" else "elective",
        "minCredits": min_credits,
        "courseReferences": [],
        "ruleExpression": {"type": "credit_bucket", "operator": "min_credits"},
        "ruleIsExecutable": True,
        "isMandatory": False,
        "advisoryOnly": False,
        "catalogYear": 2025,
        "catalogVersion": "2025-2026",
        "status": "published",
        "degreeProgramId": ObjectId(program_id),
    }


def _general_pool(pool_suffix: str, bucket_suffix: str, prefixes: list[str]) -> dict[str, Any]:
    return {
        "productionKey": f"technion-dds:pool:{PROGRAM_CODE}:{pool_suffix}:2025-2026",
        "institutionId": "technion",
        "programCode": PROGRAM_CODE,
        "requirementGroupId": f"{PROGRAM_CODE}:{pool_suffix}",
        "linkedCreditBucketId": f"{PROGRAM_CODE}:{bucket_suffix}",
        "recordType": "catalog_rule",
        "title": pool_suffix,
        "ruleExpression": {
            "type": "course_pool",
            "operator": "min_credits",
            **({"allowedPrefixes": prefixes} if prefixes else {}),
        },
        "courseReferences": [],
        "enforceInGraduationProgress": True,
        "status": "published",
    }


@pytest.mark.asyncio
async def test_graduation_progress_includes_general_technion_buckets(auth_client, mongo_database):
    fixtures = await seed_graduation_progress_fixtures(mongo_database)
    await seed_general_technion_requirements(mongo_database, fixtures["programId"])

    pe_course = await mongo_database[get_settings().courses_collection].insert_one(
        {
            "productionKey": "technion:course:03940800",
            "institutionId": "technion",
            "courseNumber": "03940800",
            "title": "Physical Education",
            "titleHebrew": "Physical Education",
            "credits": 1.0,
            "catalogYear": 2025,
            "catalogVersion": "2025-2026",
            "status": "published",
        }
    )
    enrichment_course = await mongo_database[get_settings().courses_collection].insert_one(
        {
            "productionKey": "technion:course:03940580",
            "institutionId": "technion",
            "courseNumber": "03940580",
            "title": "Enrichment",
            "titleHebrew": "Enrichment",
            "credits": 3.0,
            "catalogYear": 2025,
            "catalogVersion": "2025-2026",
            "status": "published",
        }
    )

    token = await register_access_token(auth_client, "grad-general-technion@example.com")
    profile = await auth_client.post(
        "/student-profile",
        headers={"Authorization": f"Bearer {token}"},
        json={
            "institutionId": "technion",
            "programType": "BSc",
            "degreeId": fixtures["programId"],
            "catalogYear": 2025,
            "currentSemesterCode": "2025-1",
            "academicPath": {"trackSlug": "track-data-information-engineering"},
        },
    )
    assert profile.status_code in {200, 201}

    for course_id, credits in [(str(pe_course.inserted_id), 1.0), (str(enrichment_course.inserted_id), 3.0)]:
        create = await auth_client.post(
            "/completed-courses",
            headers={"Authorization": f"Bearer {token}"},
            json=build_completed_course_payload(
                course_id,
                creditsEarned=credits,
                semesterCode="2024-1",
                grade=88,
            ),
        )
        assert create.status_code == 201

    response = await auth_client.get(
        "/graduation-progress",
        headers={"Authorization": f"Bearer {token}"},
    )
    assert response.status_code == 200
    progress = response.json()["data"]["graduationProgress"]
    suffixes = {
        bucket["requirementGroupId"].split(":")[-1] for bucket in progress["requirementProgress"]
    }
    for suffix in GENERAL_TECHNION_SUFFIXES:
        assert suffix in suffixes

    pe = next(
        bucket
        for bucket in progress["requirementProgress"]
        if bucket["requirementGroupId"].endswith(":physical-education")
    )
    enrichment = next(
        bucket
        for bucket in progress["requirementProgress"]
        if bucket["requirementGroupId"].endswith(":enrichment")
    )
    assert pe["eligibilityEnforcement"] == "strict_pool"
    assert pe["creditsCompleted"] == 1.0
    assert enrichment["eligibilityEnforcement"] == "strict_pool"
    assert enrichment["creditsCompleted"] == 3.0

    graph_response = await auth_client.get(
        "/graduation-progress/curriculum-graph",
        headers={"Authorization": f"Bearer {token}"},
    )
    assert graph_response.status_code == 200
    pool_suffixes = {
        pool["groupId"].split(":")[-1] for pool in graph_response.json()["data"]["curriculumGraph"]["electiveBuckets"]
    }
    assert "enrichment-pool" in pool_suffixes
    assert "free-elective-pool" in pool_suffixes
    assert "physical-education-pool" in pool_suffixes
