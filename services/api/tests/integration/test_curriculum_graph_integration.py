"""Integration tests for curriculum graph endpoint."""

from __future__ import annotations

import pytest

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
