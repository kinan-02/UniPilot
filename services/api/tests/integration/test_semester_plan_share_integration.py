import pytest

from tests.fixtures.graduation_progress_fixtures import seed_graduation_progress_fixtures
from tests.integration.test_semester_plans_integration import (
    create_profile,
    register_access_token,
)


@pytest.mark.asyncio
async def test_enable_share_and_fetch_public_plan(auth_client, mongo_database):
    fixtures = await seed_graduation_progress_fixtures(mongo_database)
    token = await register_access_token(auth_client, "share-plan@example.com")
    await create_profile(auth_client, token, degree_id=fixtures["programId"])

    create_response = await auth_client.post(
        "/semester-plans",
        headers={"Authorization": f"Bearer {token}"},
        json={
            "name": "Shareable Plan",
            "semesterCode": "2025-2",
            "plannedCourses": [{"courseId": fixtures["courseAId"]}],
        },
    )
    plan_id = create_response.json()["data"]["semesterPlan"]["id"]

    share_response = await auth_client.patch(
        f"/semester-plans/{plan_id}/share",
        headers={"Authorization": f"Bearer {token}"},
        json={"shareEnabled": True},
    )
    assert share_response.status_code == 200
    shared_plan = share_response.json()["data"]["semesterPlan"]
    assert shared_plan["shareEnabled"] is True
    share_token = shared_plan["shareToken"]
    assert share_token

    public_response = await auth_client.get(f"/semester-plans/shared/{share_token}")
    assert public_response.status_code == 200
    public_plan = public_response.json()["data"]["semesterPlan"]
    assert public_plan["readOnly"] is True
    assert public_plan.get("shareToken") is None
    assert public_plan["name"] == "Shareable Plan"


@pytest.mark.asyncio
async def test_disabled_share_returns_not_found(auth_client, mongo_database):
    fixtures = await seed_graduation_progress_fixtures(mongo_database)
    token = await register_access_token(auth_client, "share-disabled@example.com")
    await create_profile(auth_client, token, degree_id=fixtures["programId"])

    create_response = await auth_client.post(
        "/semester-plans",
        headers={"Authorization": f"Bearer {token}"},
        json={
            "name": "Private Plan",
            "semesterCode": "2025-2",
            "plannedCourses": [{"courseId": fixtures["courseAId"]}],
        },
    )
    plan_id = create_response.json()["data"]["semesterPlan"]["id"]

    enable_response = await auth_client.patch(
        f"/semester-plans/{plan_id}/share",
        headers={"Authorization": f"Bearer {token}"},
        json={"shareEnabled": True},
    )
    share_token = enable_response.json()["data"]["semesterPlan"]["shareToken"]

    disable_response = await auth_client.patch(
        f"/semester-plans/{plan_id}/share",
        headers={"Authorization": f"Bearer {token}"},
        json={"shareEnabled": False},
    )
    assert disable_response.status_code == 200
    assert disable_response.json()["data"]["semesterPlan"]["shareEnabled"] is False

    public_response = await auth_client.get(f"/semester-plans/shared/{share_token}")
    assert public_response.status_code == 404


@pytest.mark.asyncio
async def test_share_requires_owner(auth_client, mongo_database):
    fixtures = await seed_graduation_progress_fixtures(mongo_database)
    owner_token = await register_access_token(auth_client, "share-owner@example.com")
    other_token = await register_access_token(auth_client, "share-other@example.com")
    await create_profile(auth_client, owner_token, degree_id=fixtures["programId"])
    await create_profile(auth_client, other_token, degree_id=fixtures["programId"])

    create_response = await auth_client.post(
        "/semester-plans",
        headers={"Authorization": f"Bearer {owner_token}"},
        json={
            "name": "Owner Plan",
            "semesterCode": "2025-2",
            "plannedCourses": [{"courseId": fixtures["courseAId"]}],
        },
    )
    plan_id = create_response.json()["data"]["semesterPlan"]["id"]

    response = await auth_client.patch(
        f"/semester-plans/{plan_id}/share",
        headers={"Authorization": f"Bearer {other_token}"},
        json={"shareEnabled": True},
    )
    assert response.status_code == 404
