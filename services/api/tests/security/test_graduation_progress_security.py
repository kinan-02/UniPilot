import pytest

from tests.fixtures.graduation_progress_fixtures import seed_graduation_progress_fixtures

VALID_PASSWORD = "StrongPass123!"


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
