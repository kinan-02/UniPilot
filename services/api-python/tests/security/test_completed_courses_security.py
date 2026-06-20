import pytest
from bson import ObjectId

from tests.fixtures.completed_course_fixtures import (
    build_completed_course_payload,
    insert_official_completed_course_for_tests,
    seed_production_course_fixture,
)

VALID_PASSWORD = "StrongPass123!"


async def register_user(client, email: str) -> tuple[str, str]:
    response = await client.post(
        "/auth/register",
        json={"email": email, "password": VALID_PASSWORD},
    )
    assert response.status_code == 201
    body = response.json()["data"]
    return body["accessToken"], body["user"]["id"]


@pytest.mark.asyncio
async def test_missing_jwt_returns_401(auth_client):
    response = await auth_client.get("/completed-courses")
    assert response.status_code == 401


@pytest.mark.asyncio
async def test_invalid_jwt_returns_401(auth_client):
    response = await auth_client.get(
        "/completed-courses",
        headers={"Authorization": "Bearer invalid-token"},
    )
    assert response.status_code == 401


@pytest.mark.asyncio
async def test_cross_user_get_returns_404(auth_client, mongo_database):
    catalog = await seed_production_course_fixture(mongo_database)
    token_a, user_a = await register_user(auth_client, "completed-user-a@example.com")
    token_b, _user_b = await register_user(auth_client, "completed-user-b@example.com")

    create_response = await auth_client.post(
        "/completed-courses",
        headers={"Authorization": f"Bearer {token_a}"},
        json=build_completed_course_payload(catalog["courseId"]),
    )
    record_id = create_response.json()["data"]["completedCourse"]["id"]

    cross_get = await auth_client.get(
        f"/completed-courses/{record_id}",
        headers={"Authorization": f"Bearer {token_b}"},
    )
    assert cross_get.status_code == 404


@pytest.mark.asyncio
async def test_cross_user_update_returns_404(auth_client, mongo_database):
    catalog = await seed_production_course_fixture(mongo_database)
    token_a, _ = await register_user(auth_client, "completed-update-a@example.com")
    token_b, _ = await register_user(auth_client, "completed-update-b@example.com")

    create_response = await auth_client.post(
        "/completed-courses",
        headers={"Authorization": f"Bearer {token_a}"},
        json=build_completed_course_payload(catalog["courseId"]),
    )
    record_id = create_response.json()["data"]["completedCourse"]["id"]

    cross_update = await auth_client.put(
        f"/completed-courses/{record_id}",
        headers={"Authorization": f"Bearer {token_b}"},
        json={"grade": 82},
    )
    assert cross_update.status_code == 404


@pytest.mark.asyncio
async def test_cross_user_delete_returns_404(auth_client, mongo_database):
    catalog = await seed_production_course_fixture(mongo_database)
    token_a, _ = await register_user(auth_client, "completed-delete-a@example.com")
    token_b, _ = await register_user(auth_client, "completed-delete-b@example.com")

    create_response = await auth_client.post(
        "/completed-courses",
        headers={"Authorization": f"Bearer {token_a}"},
        json=build_completed_course_payload(catalog["courseId"]),
    )
    record_id = create_response.json()["data"]["completedCourse"]["id"]

    cross_delete = await auth_client.delete(
        f"/completed-courses/{record_id}",
        headers={"Authorization": f"Bearer {token_b}"},
    )
    assert cross_delete.status_code == 404


@pytest.mark.asyncio
async def test_client_supplied_user_id_rejected_on_create(auth_client, mongo_database):
    catalog = await seed_production_course_fixture(mongo_database)
    token, _ = await register_user(auth_client, "completed-reject-user@example.com")

    response = await auth_client.post(
        "/completed-courses",
        headers={"Authorization": f"Bearer {token}"},
        json={
            **build_completed_course_payload(catalog["courseId"]),
            "userId": str(ObjectId()),
        },
    )
    assert response.status_code == 400


@pytest.mark.asyncio
async def test_client_supplied_id_rejected_on_create(auth_client, mongo_database):
    catalog = await seed_production_course_fixture(mongo_database)
    token, _ = await register_user(auth_client, "completed-reject-id@example.com")

    response = await auth_client.post(
        "/completed-courses",
        headers={"Authorization": f"Bearer {token}"},
        json={
            **build_completed_course_payload(catalog["courseId"]),
            "_id": str(ObjectId()),
        },
    )
    assert response.status_code == 400


@pytest.mark.asyncio
async def test_non_manual_update_returns_403(auth_client, mongo_database):
    catalog = await seed_production_course_fixture(mongo_database)
    token, user_id = await register_user(auth_client, "completed-official@example.com")

    official_record = await insert_official_completed_course_for_tests(
        mongo_database,
        user_id,
        build_completed_course_payload(catalog["courseId"], attempt=2),
    )

    response = await auth_client.put(
        f"/completed-courses/{official_record['_id']}",
        headers={"Authorization": f"Bearer {token}"},
        json={"grade": 82},
    )
    assert response.status_code == 403


@pytest.mark.asyncio
async def test_non_manual_delete_returns_403(auth_client, mongo_database):
    catalog = await seed_production_course_fixture(mongo_database)
    token, user_id = await register_user(auth_client, "completed-official-del@example.com")

    official_record = await insert_official_completed_course_for_tests(
        mongo_database,
        user_id,
        build_completed_course_payload(catalog["courseId"], attempt=3),
    )

    response = await auth_client.delete(
        f"/completed-courses/{official_record['_id']}",
        headers={"Authorization": f"Bearer {token}"},
    )
    assert response.status_code == 403
