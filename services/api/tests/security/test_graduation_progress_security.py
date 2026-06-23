import pytest

from tests.fixtures.completed_course_fixtures import build_completed_course_payload
from tests.fixtures.graduation_progress_fixtures import seed_graduation_progress_fixtures

VALID_PASSWORD = "StrongPass123!"


async def register_access_token(client, email: str) -> str:
    response = await client.post(
        "/auth/register",
        json={"email": email, "password": VALID_PASSWORD},
    )
    assert response.status_code == 201
    return response.json()["data"]["accessToken"]


async def create_profile(client, token: str, program_id: str) -> None:
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
    assert response.status_code == 201


@pytest.mark.asyncio
async def test_graduation_progress_requires_jwt(auth_client):
    response = await auth_client.get("/graduation-progress")
    assert response.status_code == 401


@pytest.mark.asyncio
async def test_graduation_progress_invalid_jwt(auth_client):
    response = await auth_client.get(
        "/graduation-progress",
        headers={"Authorization": "Bearer invalid-token"},
    )
    assert response.status_code == 401


@pytest.mark.asyncio
async def test_curriculum_graph_requires_jwt(auth_client):
    response = await auth_client.get("/graduation-progress/curriculum-graph")
    assert response.status_code == 401


@pytest.mark.asyncio
async def test_curriculum_graph_invalid_jwt(auth_client):
    response = await auth_client.get(
        "/graduation-progress/curriculum-graph",
        headers={"Authorization": "Bearer invalid-token"},
    )
    assert response.status_code == 401


@pytest.mark.asyncio
@pytest.mark.parametrize(
    ("path", "query"),
    [
        ("/graduation-progress", "userId=665f2b0f2a3f7b2a1a9a7d01"),
        ("/graduation-progress", "studentId=665f2b0f2a3f7b2a1a9a7d02"),
        ("/graduation-progress/curriculum-graph", "user_id=665f2b0f2a3f7b2a1a9a7d03"),
    ],
)
async def test_progress_rejects_cross_user_query_params_with_403(
    auth_client,
    mongo_database,
    path: str,
    query: str,
):
    fixtures = await seed_graduation_progress_fixtures(mongo_database)
    token = await register_access_token(auth_client, f"progress-403-{query}@example.com")
    await create_profile(auth_client, token, fixtures["programId"])

    response = await auth_client.get(
        f"{path}?{query}",
        headers={"Authorization": f"Bearer {token}"},
    )
    assert response.status_code == 403
    assert "cross-user" in response.json()["error"].lower()


@pytest.mark.asyncio
async def test_progress_cross_user_data_isolation_at_http_layer(auth_client, mongo_database):
    fixtures = await seed_graduation_progress_fixtures(mongo_database)
    token_a = await register_access_token(auth_client, "progress-owner-a@example.com")
    token_b = await register_access_token(auth_client, "progress-owner-b@example.com")
    await create_profile(auth_client, token_a, fixtures["programId"])
    await create_profile(auth_client, token_b, fixtures["programId"])

    create = await auth_client.post(
        "/completed-courses",
        headers={"Authorization": f"Bearer {token_a}"},
        json=build_completed_course_payload(
            fixtures["courseBId"],
            creditsEarned=3.5,
            semesterCode="2024-1",
            grade=82,
        ),
    )
    assert create.status_code == 201

    progress_a = await auth_client.get(
        "/graduation-progress",
        headers={"Authorization": f"Bearer {token_a}"},
    )
    progress_b = await auth_client.get(
        "/graduation-progress",
        headers={"Authorization": f"Bearer {token_b}"},
    )
    assert progress_a.status_code == 200
    assert progress_b.status_code == 200
    assert progress_a.json()["data"]["graduationProgress"]["completedCredits"] == 3.5
    assert progress_b.json()["data"]["graduationProgress"]["completedCredits"] == 0


@pytest.mark.asyncio
async def test_graduation_progress_enforces_rate_limit_with_429(
    progress_security_client,
    mongo_database,
):
    fixtures = await seed_graduation_progress_fixtures(mongo_database)
    token = await register_access_token(progress_security_client, "progress-rate@example.com")
    await create_profile(progress_security_client, token, fixtures["programId"])

    first = await progress_security_client.get(
        "/graduation-progress",
        headers={"Authorization": f"Bearer {token}"},
    )
    second = await progress_security_client.get(
        "/graduation-progress",
        headers={"Authorization": f"Bearer {token}"},
    )
    assert first.status_code == 200
    assert second.status_code == 429


@pytest.mark.asyncio
async def test_curriculum_graph_enforces_rate_limit_with_429(
    progress_security_client,
    mongo_database,
):
    fixtures = await seed_graduation_progress_fixtures(mongo_database)
    token = await register_access_token(progress_security_client, "graph-rate@example.com")
    await create_profile(progress_security_client, token, fixtures["programId"])

    first = await progress_security_client.get(
        "/graduation-progress/curriculum-graph",
        headers={"Authorization": f"Bearer {token}"},
    )
    second = await progress_security_client.get(
        "/graduation-progress/curriculum-graph",
        headers={"Authorization": f"Bearer {token}"},
    )
    assert first.status_code == 200
    assert second.status_code == 429
