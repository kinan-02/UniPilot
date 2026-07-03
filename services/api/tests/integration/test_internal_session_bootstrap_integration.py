"""Integration tests for internal session bootstrap route."""

from __future__ import annotations

import pytest

from tests.fixtures.completed_course_fixtures import (
    build_completed_course_payload,
    seed_production_course_fixture,
)
from tests.fixtures.graduation_progress_fixtures import seed_graduation_progress_fixtures


@pytest.mark.asyncio
async def test_internal_session_bootstrap_requires_token(auth_client, monkeypatch) -> None:
    monkeypatch.setenv("INTERNAL_SERVICE_TOKEN", "unipilot_dev_internal_service_token_change_in_production")
    from app.config import get_settings

    get_settings.cache_clear()

    response = await auth_client.get("/internal/session-bootstrap/users/000000000000000000000000")
    assert response.status_code == 401

    get_settings.cache_clear()


@pytest.mark.asyncio
async def test_internal_session_bootstrap_returns_context_and_graduation(
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
        {"email": "internal-bootstrap@example.com", "passwordHash": "hash"}
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
        f"/internal/session-bootstrap/users/{user_id}",
        headers={"X-Internal-Service-Token": "unipilot_dev_internal_service_token_change_in_production"},
    )
    assert response.status_code == 200
    payload = response.json()
    assert payload["success"] is True
    data = payload["data"]
    context = data["userContext"]
    assert context["user_id"] == user_id
    assert catalog["courseNumber"] in context["completed_courses"]
    assert data["graduationStatus"] == "ok"
    assert isinstance(data["graduationProgress"], dict)
    assert data["graduationError"] is None
    assert data["planningReady"] is True
    assert isinstance(data["planningContext"], dict)
    assert data["planningContext"]["status"] == "ok"
    assert catalog["courseNumber"] in data["planningContext"]["transcriptCourseNumbers"]

    get_settings.cache_clear()
