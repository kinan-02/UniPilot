"""Integration tests for internal graduation progress route."""

from __future__ import annotations

import pytest

from tests.fixtures.graduation_progress_fixtures import PROGRAM_CODE, seed_graduation_progress_fixtures


@pytest.mark.asyncio
async def test_internal_graduation_progress_requires_token(auth_client, monkeypatch) -> None:
    monkeypatch.setenv("INTERNAL_SERVICE_TOKEN", "unipilot_dev_internal_service_token_change_in_production")
    from app.config import get_settings

    get_settings.cache_clear()

    response = await auth_client.get("/internal/graduation-progress/users/000000000000000000000000")
    assert response.status_code == 401

    get_settings.cache_clear()


@pytest.mark.asyncio
async def test_internal_graduation_progress_returns_progress(auth_client, mongo_database, monkeypatch) -> None:
    monkeypatch.setenv("INTERNAL_SERVICE_TOKEN", "unipilot_dev_internal_service_token_change_in_production")
    from app.config import get_settings

    get_settings.cache_clear()

    fixtures = await seed_graduation_progress_fixtures(mongo_database)
    user = await mongo_database.users.insert_one(
        {"email": "internal-progress@example.com", "passwordHash": "hash"}
    )
    user_id = str(user.inserted_id)

    await mongo_database.student_profiles.insert_one(
        {
            "userId": user.inserted_id,
            "degreeId": fixtures["programId"],
            "academicPath": {"trackSlug": "data-information-engineering"},
        }
    )

    response = await auth_client.get(
        f"/internal/graduation-progress/users/{user_id}",
        headers={"X-Internal-Service-Token": "unipilot_dev_internal_service_token_change_in_production"},
    )
    assert response.status_code == 200
    payload = response.json()
    assert payload["success"] is True
    progress = payload["data"]["graduationProgress"]
    assert progress["degreeCode"] == PROGRAM_CODE
    assert progress["completedCredits"] == 0

    get_settings.cache_clear()


@pytest.mark.asyncio
async def test_internal_graduation_progress_preview_projects_additional_course(
    auth_client,
    mongo_database,
    monkeypatch,
) -> None:
    monkeypatch.setenv("INTERNAL_SERVICE_TOKEN", "unipilot_dev_internal_service_token_change_in_production")
    from app.config import get_settings

    get_settings.cache_clear()

    fixtures = await seed_graduation_progress_fixtures(mongo_database)
    user = await mongo_database.users.insert_one(
        {"email": "internal-preview@example.com", "passwordHash": "hash"}
    )
    user_id = str(user.inserted_id)

    await mongo_database.student_profiles.insert_one(
        {
            "userId": user.inserted_id,
            "degreeId": fixtures["programId"],
            "academicPath": {"trackSlug": "data-information-engineering"},
        }
    )

    baseline = await auth_client.get(
        f"/internal/graduation-progress/users/{user_id}",
        headers={"X-Internal-Service-Token": "unipilot_dev_internal_service_token_change_in_production"},
    )
    assert baseline.status_code == 200
    baseline_progress = baseline.json()["data"]["graduationProgress"]
    assert baseline_progress["completedCredits"] == 0

    response = await auth_client.post(
        f"/internal/graduation-progress/preview/users/{user_id}",
        headers={"X-Internal-Service-Token": "unipilot_dev_internal_service_token_change_in_production"},
        json={"additional_course_numbers": ["00940411"]},
    )
    assert response.status_code == 200
    payload = response.json()
    assert payload["success"] is True
    progress = payload["data"]["graduationProgress"]
    assert progress["completedCredits"] == 3.5
    assert progress["previewMeta"]["source"] == "api_recompute"
    assert progress["previewMeta"]["additionalCourseNumbers"] == ["00940411"]
    assert progress["previewMeta"]["completedCourseCount"] == 1

    get_settings.cache_clear()
