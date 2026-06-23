"""Integration tests for curriculum graph endpoint."""

from __future__ import annotations

import pytest

from app.config import get_settings
from tests.fixtures.graduation_progress_fixtures import seed_graduation_progress_fixtures
from tests.integration.test_semester_plans_integration import (
    create_profile,
    register_access_token,
)


@pytest.mark.asyncio
async def test_curriculum_graph_returns_semester_lanes(auth_client, mongo_database):
    fixtures = await seed_graduation_progress_fixtures(mongo_database)
    token = await register_access_token(auth_client, "curriculum-graph@example.com")
    await create_profile(
        auth_client,
        token,
        degree_id=fixtures["programId"],
        extra={
            "academicPath": {
                "trackSlug": "track-data-information-engineering",
            },
        },
    )

    response = await auth_client.get(
        "/graduation-progress/curriculum-graph",
        headers={"Authorization": f"Bearer {token}"},
    )
    assert response.status_code == 200
    body = response.json()
    assert body["success"] is True
    graph = body["data"]["curriculumGraph"]
    assert graph["programCode"] == "009216-1-000"
    assert len(graph["semesterLanes"]) >= 1
    assert len(graph["nodes"]) >= 1
    assert graph["viewDefault"] == "semester_swimlanes"
    assert len(graph["electiveBuckets"]) >= 1
    ds_pool = next(
        bucket
        for bucket in graph["electiveBuckets"]
        if bucket.get("groupId", "").endswith(":elective-ds-pool")
    )
    assert ds_pool["explorerReady"] is True
    assert ds_pool["linkedCreditBucketId"] == "009216-1-000:elective-ds"


@pytest.mark.asyncio
async def test_curriculum_graph_requires_profile(auth_client):
    token = await register_access_token(auth_client, "curriculum-no-profile@example.com")
    response = await auth_client.get(
        "/graduation-progress/curriculum-graph",
        headers={"Authorization": f"Bearer {token}"},
    )
    assert response.status_code == 404
    assert "profile" in response.json()["error"].lower()


@pytest.mark.asyncio
async def test_curriculum_graph_requires_degree(auth_client, mongo_database):
    await seed_graduation_progress_fixtures(mongo_database)
    token = await register_access_token(auth_client, "curriculum-no-degree@example.com")
    await auth_client.post(
        "/student-profile",
        headers={"Authorization": f"Bearer {token}"},
        json={
            "institutionId": "technion",
            "programType": "BSc",
            "catalogYear": 2025,
            "currentSemesterCode": "2025-1",
        },
    )
    response = await auth_client.get(
        "/graduation-progress/curriculum-graph",
        headers={"Authorization": f"Bearer {token}"},
    )
    assert response.status_code == 400
    assert "degree must be selected" in response.json()["error"].lower()


@pytest.mark.asyncio
async def test_curriculum_graph_requires_track_configuration(auth_client, mongo_database):
    settings = get_settings()
    program_insert = await mongo_database[settings.degree_programs_collection].insert_one(
        {
            "productionKey": "technion-dds:program:009999-9-999:2025-2026",
            "institutionId": "technion",
            "programCode": "009999-9-999",
            "name": "Trackless program",
            "totalCredits": 120.0,
            "catalogYear": 2025,
            "catalogVersion": "2025-2026",
            "metadata": {},
            "status": "published",
        }
    )
    token = await register_access_token(auth_client, "curriculum-no-track@example.com")
    await auth_client.post(
        "/student-profile",
        headers={"Authorization": f"Bearer {token}"},
        json={
            "institutionId": "technion",
            "programType": "BSc",
            "degreeId": str(program_insert.inserted_id),
            "catalogYear": 2025,
            "currentSemesterCode": "2025-1",
        },
    )
    response = await auth_client.get(
        "/graduation-progress/curriculum-graph",
        headers={"Authorization": f"Bearer {token}"},
    )
    assert response.status_code == 400
    assert "track" in response.json()["error"].lower()


@pytest.mark.asyncio
async def test_curriculum_graph_returns_400_when_degree_not_found(auth_client, mongo_database):
    from bson import ObjectId
    from datetime import datetime, timezone

    from app.security.jwt import create_access_token

    ghost_user_oid = ObjectId()
    ghost_degree_id = ObjectId()
    await mongo_database["student_profiles"].insert_one(
        {
            "userId": ghost_user_oid,
            "institutionId": "technion",
            "programType": "BSc",
            "catalogYear": 2025,
            "currentSemesterCode": "2025-1",
            "degreeId": ghost_degree_id,
            "academicPath": {"trackSlug": "track-data-information-engineering"},
            "preferences": {},
            "revision": 1,
            "createdAt": datetime.now(timezone.utc),
            "updatedAt": datetime.now(timezone.utc),
        }
    )
    token = create_access_token(user_id=str(ghost_user_oid), email="ghost-graph-degree@example.com")

    response = await auth_client.get(
        "/graduation-progress/curriculum-graph",
        headers={"Authorization": f"Bearer {token}"},
    )
    assert response.status_code == 400
    assert "degree" in response.json()["error"].lower()


@pytest.mark.asyncio
async def test_curriculum_graph_returns_404_when_curriculum_unavailable(auth_client, mongo_database):
    from app.config import get_settings

    settings = get_settings()
    program_insert = await mongo_database[settings.degree_programs_collection].insert_one(
        {
            "productionKey": "technion-dds:program:009216-1-000:2025-2026",
            "institutionId": "technion",
            "programCode": "009216-1-000",
            "name": "IE",
            "catalogYear": 2025,
            "catalogVersion": "2025-2026",
            "metadata": {"wikiPage": "track-data-information-engineering"},
            "status": "published",
        }
    )
    token = await register_access_token(auth_client, "curriculum-unavailable@example.com")
    await auth_client.post(
        "/student-profile",
        headers={"Authorization": f"Bearer {token}"},
        json={
            "institutionId": "technion",
            "programType": "BSc",
            "degreeId": str(program_insert.inserted_id),
            "catalogYear": 2025,
            "currentSemesterCode": "2025-1",
            "academicPath": {"trackSlug": "track-data-information-engineering"},
        },
    )

    response = await auth_client.get(
        "/graduation-progress/curriculum-graph",
        headers={"Authorization": f"Bearer {token}"},
    )
    assert response.status_code == 404
    assert "curriculum" in response.json()["error"].lower()
