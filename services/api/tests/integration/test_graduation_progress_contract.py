"""Response contract invariants for graduation progress endpoints."""

from __future__ import annotations

import pytest

from tests.fixtures.completed_course_fixtures import build_completed_course_payload
from tests.fixtures.graduation_progress_fixtures import seed_graduation_progress_fixtures
from tests.integration.test_graduation_progress_integration import register_access_token

REQUIRED_PROGRESS_KEYS = frozenset(
    {
        "degreeId",
        "completedCredits",
        "totalRequiredCredits",
        "creditsRemaining",
        "completionPercentage",
        "statusSummary",
        "requirementProgress",
        "missingRequirements",
    }
)

REQUIRED_BUCKET_KEYS = frozenset(
    {
        "requirementGroupId",
        "title",
        "status",
        "minCredits",
        "creditsCompleted",
        "creditsRemaining",
        "eligibilityEnforcement",
    }
)

REQUIRED_GRAPH_KEYS = frozenset(
    {
        "trackSlug",
        "programCode",
        "catalogYear",
        "viewDefault",
        "semesterLanes",
        "nodes",
        "edges",
        "electiveBuckets",
    }
)


async def _seed_profile(client, token: str, program_id: str) -> None:
    response = await client.post(
        "/student-profile",
        headers={"Authorization": f"Bearer {token}"},
        json={
            "institutionId": "technion",
            "programType": "BSc",
            "degreeId": program_id,
            "catalogYear": 2025,
            "currentSemesterCode": "2025-1",
            "academicPath": {"trackSlug": "track-data-information-engineering"},
        },
    )
    assert response.status_code in {200, 201}


@pytest.mark.asyncio
async def test_graduation_progress_response_contract(auth_client, mongo_database):
    fixtures = await seed_graduation_progress_fixtures(mongo_database)
    token = await register_access_token(auth_client, "grad-contract@example.com")
    await _seed_profile(auth_client, token, fixtures["programId"])

    for course_id, credits in [
        (fixtures["courseBId"], 3.5),
        (fixtures["courseAId"], 4.0),
    ]:
        create = await auth_client.post(
            "/completed-courses",
            headers={"Authorization": f"Bearer {token}"},
            json=build_completed_course_payload(
                course_id,
                creditsEarned=credits,
                semesterCode="2024-1",
                grade=82,
            ),
        )
        assert create.status_code == 201

    response = await auth_client.get(
        "/graduation-progress",
        headers={"Authorization": f"Bearer {token}"},
    )
    assert response.status_code == 200
    envelope = response.json()
    assert envelope["success"] is True
    assert envelope["error"] is None

    progress = envelope["data"]["graduationProgress"]
    assert REQUIRED_PROGRESS_KEYS.issubset(progress.keys())
    assert 0 <= progress["completionPercentage"] <= 100
    assert progress["completedCredits"] <= progress["totalRequiredCredits"]
    assert progress["creditsRemaining"] >= 0

    for bucket in progress["requirementProgress"]:
        assert REQUIRED_BUCKET_KEYS.issubset(bucket.keys())
        assert bucket["creditsCompleted"] >= 0
        assert bucket["creditsRemaining"] >= 0
        assert bucket["minCredits"] >= 0

    missing_ids = {item["requirementGroupId"] for item in progress["missingRequirements"]}
    in_progress_ids = {
        bucket["requirementGroupId"]
        for bucket in progress["requirementProgress"]
        if bucket["status"] != "complete"
    }
    assert missing_ids.issubset(in_progress_ids)


@pytest.mark.asyncio
async def test_curriculum_graph_response_contract(auth_client, mongo_database):
    fixtures = await seed_graduation_progress_fixtures(mongo_database)
    token = await register_access_token(auth_client, "grad-graph-contract@example.com")
    await _seed_profile(auth_client, token, fixtures["programId"])

    response = await auth_client.get(
        "/graduation-progress/curriculum-graph",
        headers={"Authorization": f"Bearer {token}"},
    )
    assert response.status_code == 200
    graph = response.json()["data"]["curriculumGraph"]
    assert REQUIRED_GRAPH_KEYS.issubset(graph.keys())

    for pool in graph["electiveBuckets"]:
        assert pool.get("groupId")
        assert pool.get("rule")
        assert "explorerReady" in pool
        if pool["explorerReady"]:
            assert isinstance(pool.get("courses"), list)
            assert pool.get("courseCount", 0) >= 0

    ds_pool = next(
        bucket
        for bucket in graph["electiveBuckets"]
        if bucket.get("groupId", "").endswith(":elective-ds-pool")
    )
    assert ds_pool["linkedCreditBucketId"] == "009216-1-000:elective-ds"
