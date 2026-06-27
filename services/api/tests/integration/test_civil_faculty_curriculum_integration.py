"""Integration tests for non-DDS civil faculty curriculum graph + planner."""

from __future__ import annotations

import pytest

from tests.fixtures.civil_curriculum_fixtures import seed_civil_curriculum_fixtures
from tests.integration.test_semester_plans_integration import (
    create_profile,
    register_access_token,
)


@pytest.mark.asyncio
async def test_civil_onboarding_progress_graph_and_semester_plan(auth_client, mongo_database):
    fixtures = await seed_civil_curriculum_fixtures(mongo_database)
    token = await register_access_token(auth_client, "civil-curriculum@example.com")
    await create_profile(
        auth_client,
        token,
        degree_id=fixtures["programId"],
        extra={"academicPath": {"trackSlug": fixtures["trackSlug"]}},
    )

    progress_response = await auth_client.get(
        "/graduation-progress",
        headers={"Authorization": f"Bearer {token}"},
    )
    assert progress_response.status_code == 200
    progress = progress_response.json()["data"]["graduationProgress"]
    assert len(progress["requirementProgress"]) >= 7
    bucket_suffixes = {
        bucket["requirementGroupId"].split(":")[-1] for bucket in progress["requirementProgress"]
    }
    assert "track-electives" in bucket_suffixes
    assert "enrichment" in bucket_suffixes

    graph_response = await auth_client.get(
        "/graduation-progress/curriculum-graph",
        headers={"Authorization": f"Bearer {token}"},
    )
    assert graph_response.status_code == 200
    graph = graph_response.json()["data"]["curriculumGraph"]
    assert graph["programCode"] == fixtures["programCode"]
    assert len(graph["semesterLanes"]) >= 8
    assert len(graph["electiveBuckets"]) >= 5
    pool_suffixes = {pool["groupId"].split(":")[-1] for pool in graph["electiveBuckets"]}
    assert "enrichment-pool" in pool_suffixes
    assert any(suffix.startswith("civil-hebrew-group") for suffix in pool_suffixes)

    plan_response = await auth_client.post(
        "/semester-plans/generate",
        headers={"Authorization": f"Bearer {token}"},
        json={"semesterCode": "2025-2", "maxCredits": 12},
    )
    assert plan_response.status_code == 201
    plan = plan_response.json()["data"]["semesterPlan"]
    planned = plan["semesters"][0]["plannedCourses"]
    assert len(planned) > 0
    assert plan["explanation"].get("partialPlan") is not True or len(planned) > 0
