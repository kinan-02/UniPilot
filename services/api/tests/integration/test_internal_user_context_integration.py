"""Integration tests for internal user context route."""

from __future__ import annotations

import pytest

from tests.fixtures.completed_course_fixtures import (
    build_completed_course_payload,
    seed_production_course_fixture,
)
from tests.fixtures.graduation_progress_fixtures import seed_graduation_progress_fixtures


@pytest.mark.asyncio
async def test_internal_user_context_requires_token(auth_client, monkeypatch) -> None:
    monkeypatch.setenv("INTERNAL_SERVICE_TOKEN", "unipilot_dev_internal_service_token_change_in_production")
    from app.config import get_settings

    get_settings.cache_clear()

    response = await auth_client.get("/internal/user-context/users/000000000000000000000000")
    assert response.status_code == 401

    get_settings.cache_clear()


@pytest.mark.asyncio
async def test_internal_user_context_returns_profile_and_transcript(
    auth_client,
    mongo_database,
    monkeypatch,
) -> None:
    monkeypatch.setenv("INTERNAL_SERVICE_TOKEN", "unipilot_dev_internal_service_token_change_in_production")
    from app.config import get_settings
    from app.repositories.completed_course_repository import create_completed_course

    get_settings.cache_clear()

    fixtures = await seed_graduation_progress_fixtures(mongo_database)
    catalog = await seed_production_course_fixture(mongo_database)
    user = await mongo_database.users.insert_one(
        {"email": "internal-context@example.com", "passwordHash": "hash"}
    )
    user_id = str(user.inserted_id)

    await mongo_database.student_profiles.insert_one(
        {
            "userId": user.inserted_id,
            "degreeId": fixtures["programId"],
            "academicPath": {"trackSlug": "track-data-information-engineering"},
            "currentSemesterCode": "2025-1",
            "preferences": {},
        }
    )
    await create_completed_course(
        mongo_database,
        user_id,
        build_completed_course_payload(catalog["courseId"]),
    )

    response = await auth_client.get(
        f"/internal/user-context/users/{user_id}",
        headers={"X-Internal-Service-Token": "unipilot_dev_internal_service_token_change_in_production"},
    )
    assert response.status_code == 200
    payload = response.json()
    assert payload["success"] is True
    context = payload["data"]["userContext"]
    assert context["user_id"] == user_id
    assert catalog["courseNumber"] in context["completed_courses"]
    assert context["track_slug"] == "track-data-information-engineering"
    assert context["plan_semester_code"] == "2025-1"

    get_settings.cache_clear()
