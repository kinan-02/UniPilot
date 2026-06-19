import pytest
from bson import ObjectId

from app.config import get_settings
from app.repositories.completed_course_repository import (
    create_completed_course,
    find_completed_courses_by_user_id,
)
from tests.fixtures.completed_course_fixtures import (
    build_completed_course_payload,
    seed_production_course_fixture,
)

VALID_PASSWORD = "StrongPass123!"


async def register_access_token(client, email: str) -> str:
    response = await client.post(
        "/auth/register",
        json={"email": email, "password": VALID_PASSWORD},
    )
    assert response.status_code == 201
    return response.json()["data"]["accessToken"]


@pytest.mark.asyncio
async def test_create_list_get_update_delete_completed_course_flow(auth_client, mongo_database):
    catalog = await seed_production_course_fixture(mongo_database)
    access_token = await register_access_token(auth_client, "completed-flow@example.com")

    create_response = await auth_client.post(
        "/completed-courses",
        headers={"Authorization": f"Bearer {access_token}"},
        json=build_completed_course_payload(catalog["courseId"], semesterCode="2023-1", grade="A"),
    )
    assert create_response.status_code == 201
    created = create_response.json()["data"]["completedCourse"]
    assert created["courseId"] == catalog["courseId"]
    assert created["courseNumber"] == catalog["courseNumber"]
    assert created["source"] == "manual"
    record_id = created["id"]

    list_response = await auth_client.get(
        "/completed-courses",
        headers={"Authorization": f"Bearer {access_token}"},
    )
    assert list_response.status_code == 200
    listed = list_response.json()["data"]["completedCourses"]
    assert len(listed) == 1
    assert listed[0]["id"] == record_id

    get_response = await auth_client.get(
        f"/completed-courses/{record_id}",
        headers={"Authorization": f"Bearer {access_token}"},
    )
    assert get_response.status_code == 200
    assert get_response.json()["data"]["completedCourse"]["grade"] == "A"

    update_response = await auth_client.put(
        f"/completed-courses/{record_id}",
        headers={"Authorization": f"Bearer {access_token}"},
        json={"grade": "A+", "creditsEarned": 4},
    )
    assert update_response.status_code == 200
    assert update_response.json()["data"]["completedCourse"]["grade"] == "A+"

    delete_response = await auth_client.delete(
        f"/completed-courses/{record_id}",
        headers={"Authorization": f"Bearer {access_token}"},
    )
    assert delete_response.status_code == 200
    assert delete_response.json()["data"]["deleted"] is True

    missing_response = await auth_client.get(
        f"/completed-courses/{record_id}",
        headers={"Authorization": f"Bearer {access_token}"},
    )
    assert missing_response.status_code == 404


@pytest.mark.asyncio
async def test_get_before_create_returns_404(auth_client):
    access_token = await register_access_token(auth_client, "completed-missing@example.com")
    response = await auth_client.get(
        f"/completed-courses/{ObjectId()}",
        headers={"Authorization": f"Bearer {access_token}"},
    )
    assert response.status_code == 404


@pytest.mark.asyncio
async def test_create_with_missing_catalog_course_returns_400(auth_client):
    access_token = await register_access_token(auth_client, "completed-no-course@example.com")
    response = await auth_client.post(
        "/completed-courses",
        headers={"Authorization": f"Bearer {access_token}"},
        json=build_completed_course_payload(str(ObjectId())),
    )
    assert response.status_code == 400
    assert "catalog" in response.json()["error"].lower()


@pytest.mark.asyncio
async def test_create_with_excluded_course_number_not_in_catalog(auth_client, mongo_database):
    settings = get_settings()
    excluded_count = await mongo_database[settings.courses_collection].count_documents(
        {"courseNumber": "00960226"}
    )
    assert excluded_count == 0

    access_token = await register_access_token(auth_client, "completed-excluded@example.com")
    response = await auth_client.post(
        "/completed-courses",
        headers={"Authorization": f"Bearer {access_token}"},
        json=build_completed_course_payload(str(ObjectId())),
    )
    assert response.status_code == 400


@pytest.mark.asyncio
async def test_duplicate_create_returns_409(auth_client, mongo_database):
    catalog = await seed_production_course_fixture(mongo_database)
    access_token = await register_access_token(auth_client, "completed-dup@example.com")
    payload = build_completed_course_payload(catalog["courseId"])

    first = await auth_client.post(
        "/completed-courses",
        headers={"Authorization": f"Bearer {access_token}"},
        json=payload,
    )
    assert first.status_code == 201

    duplicate = await auth_client.post(
        "/completed-courses",
        headers={"Authorization": f"Bearer {access_token}"},
        json=payload,
    )
    assert duplicate.status_code == 409


@pytest.mark.asyncio
async def test_invalid_record_id_returns_400(auth_client):
    access_token = await register_access_token(auth_client, "completed-bad-id@example.com")
    response = await auth_client.get(
        "/completed-courses/not-an-id",
        headers={"Authorization": f"Bearer {access_token}"},
    )
    assert response.status_code == 400


@pytest.mark.asyncio
async def test_list_rejects_unknown_query_params(auth_client):
    access_token = await register_access_token(auth_client, "completed-query@example.com")
    response = await auth_client.get(
        "/completed-courses?courseNumber=00104000",
        headers={"Authorization": f"Bearer {access_token}"},
    )
    assert response.status_code == 400


@pytest.mark.asyncio
async def test_completed_course_creation_does_not_write_catalog_collections(
    auth_client,
    mongo_database,
):
    settings = get_settings()
    catalog = await seed_production_course_fixture(mongo_database)
    courses_before = await mongo_database[settings.courses_collection].count_documents({})
    requirements_before = await mongo_database[settings.degree_requirements_collection].count_documents({})
    rules_before = await mongo_database[settings.catalog_rules_collection].count_documents({})

    access_token = await register_access_token(auth_client, "completed-readonly@example.com")
    response = await auth_client.post(
        "/completed-courses",
        headers={"Authorization": f"Bearer {access_token}"},
        json=build_completed_course_payload(catalog["courseId"]),
    )
    assert response.status_code == 201

    assert await mongo_database[settings.courses_collection].count_documents({}) == courses_before
    assert (
        await mongo_database[settings.degree_requirements_collection].count_documents({})
        == requirements_before
    )
    assert await mongo_database[settings.catalog_rules_collection].count_documents({}) == rules_before


@pytest.mark.asyncio
async def test_repository_scopes_list_by_user_id(mongo_database):
    catalog = await seed_production_course_fixture(mongo_database)
    user_a = str(ObjectId())
    user_b = str(ObjectId())

    await create_completed_course(
        mongo_database,
        user_a,
        {**build_completed_course_payload(catalog["courseId"]), "source": "manual"},
    )
    await create_completed_course(
        mongo_database,
        user_b,
        {
            **build_completed_course_payload(catalog["courseId"], attempt=2),
            "source": "manual",
        },
    )

    user_a_records = await find_completed_courses_by_user_id(mongo_database, user_a)
    user_b_records = await find_completed_courses_by_user_id(mongo_database, user_b)

    assert user_a_records["total"] == 1
    assert user_b_records["total"] == 1
