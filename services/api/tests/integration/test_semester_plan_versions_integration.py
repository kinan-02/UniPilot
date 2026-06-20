import pytest

from tests.fixtures.graduation_progress_fixtures import seed_graduation_progress_fixtures
from tests.integration.test_semester_plans_integration import (
    create_profile,
    register_access_token,
)


@pytest.mark.asyncio
async def test_create_semester_plan_version_forks_plan(auth_client, mongo_database):
    fixtures = await seed_graduation_progress_fixtures(mongo_database)
    token = await register_access_token(auth_client, "plan-version@example.com")
    await create_profile(auth_client, token, degree_id=fixtures["programId"])

    create_response = await auth_client.post(
        "/semester-plans",
        headers={"Authorization": f"Bearer {token}"},
        json={
            "name": "Original Plan",
            "semesterCode": "2025-2",
            "plannedCourses": [{"courseId": fixtures["courseAId"]}],
        },
    )
    source_plan = create_response.json()["data"]["semesterPlan"]
    source_id = source_plan["id"]

    version_response = await auth_client.post(
        f"/semester-plans/{source_id}/versions",
        headers={"Authorization": f"Bearer {token}"},
        json={"name": "Original Plan v2"},
    )

    assert version_response.status_code == 201
    body = version_response.json()["data"]
    forked = body["semesterPlan"]
    assert body["sourcePlanId"] == source_id
    assert forked["id"] != source_id
    assert forked["basePlanId"] == source_id
    assert forked["version"] == 2
    assert forked["status"] == "draft"
    assert forked["name"] == "Original Plan v2"
    assert len(forked["semesters"][0]["plannedCourses"]) == 1
    assert forked["assumptions"]["forkedFromPlanId"] == source_id


@pytest.mark.asyncio
async def test_create_version_from_generated_plan(auth_client, mongo_database):
    fixtures = await seed_graduation_progress_fixtures(mongo_database)
    token = await register_access_token(auth_client, "plan-version-generated@example.com")
    await create_profile(auth_client, token, degree_id=fixtures["programId"])

    generate_response = await auth_client.post(
        "/semester-plans/generate",
        headers={"Authorization": f"Bearer {token}"},
        json={"semesterCode": "2025-2", "maxCredits": 9},
    )
    source_plan = generate_response.json()["data"]["semesterPlan"]

    version_response = await auth_client.post(
        f"/semester-plans/{source_plan['id']}/versions",
        headers={"Authorization": f"Bearer {token}"},
        json={},
    )

    assert version_response.status_code == 201
    forked = version_response.json()["data"]["semesterPlan"]
    assert forked["plannerType"] == "deterministic"
    assert forked["version"] == 2
    assert forked["basePlanId"] == source_plan["id"]


@pytest.mark.asyncio
async def test_cannot_version_archived_plan(auth_client, mongo_database):
    fixtures = await seed_graduation_progress_fixtures(mongo_database)
    token = await register_access_token(auth_client, "plan-version-archived@example.com")
    await create_profile(auth_client, token, degree_id=fixtures["programId"])

    create_response = await auth_client.post(
        "/semester-plans",
        headers={"Authorization": f"Bearer {token}"},
        json={
            "name": "To Archive",
            "semesterCode": "2025-2",
            "plannedCourses": [{"courseId": fixtures["courseAId"]}],
        },
    )
    plan_id = create_response.json()["data"]["semesterPlan"]["id"]

    await auth_client.delete(
        f"/semester-plans/{plan_id}",
        headers={"Authorization": f"Bearer {token}"},
    )

    version_response = await auth_client.post(
        f"/semester-plans/{plan_id}/versions",
        headers={"Authorization": f"Bearer {token}"},
        json={},
    )
    assert version_response.status_code == 400
