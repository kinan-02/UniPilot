"""Parametrized security tests for invalid ObjectId path parameters."""

from __future__ import annotations

import pytest

from tests.integration.test_catalog_integration import register_access_token

VALID_PASSWORD = "StrongPass123!"

INVALID_OBJECT_IDS = [
    "not-an-id",
    "123",
    "665f2b0f",
    "zzzzzzzzzzzzzzzzzzzzzzzz",
]


@pytest.mark.asyncio
@pytest.mark.parametrize("invalid_id", INVALID_OBJECT_IDS)
async def test_completed_courses_reject_invalid_record_id(auth_client, invalid_id: str):
    token = await register_access_token(auth_client, f"bad-id-cc-{invalid_id}@example.com")

    for method, path, body in [
        ("GET", f"/completed-courses/{invalid_id}", None),
        ("PUT", f"/completed-courses/{invalid_id}", {"grade": 85}),
        ("DELETE", f"/completed-courses/{invalid_id}", None),
    ]:
        response = await auth_client.request(
            method,
            path,
            headers={"Authorization": f"Bearer {token}"},
            json=body,
        )
        assert response.status_code == 400, f"{method} {path}"


@pytest.mark.asyncio
@pytest.mark.parametrize("invalid_id", INVALID_OBJECT_IDS)
async def test_semester_plans_reject_invalid_plan_id(auth_client, invalid_id: str):
    token = await register_access_token(auth_client, f"bad-id-plan-{invalid_id}@example.com")

    for method, path, body in [
        ("GET", f"/semester-plans/{invalid_id}", None),
        ("DELETE", f"/semester-plans/{invalid_id}", None),
        ("PATCH", f"/semester-plans/{invalid_id}/share", {"shareEnabled": True}),
    ]:
        response = await auth_client.request(
            method,
            path,
            headers={"Authorization": f"Bearer {token}"},
            json=body,
        )
        assert response.status_code == 400, f"{method} {path}"


@pytest.mark.asyncio
@pytest.mark.parametrize("invalid_id", INVALID_OBJECT_IDS)
async def test_academic_risks_reject_invalid_analysis_id(auth_client, invalid_id: str):
    token = await register_access_token(auth_client, f"bad-id-risk-{invalid_id}@example.com")

    response = await auth_client.get(
        f"/academic-risks/{invalid_id}",
        headers={"Authorization": f"Bearer {token}"},
    )
    assert response.status_code == 400
