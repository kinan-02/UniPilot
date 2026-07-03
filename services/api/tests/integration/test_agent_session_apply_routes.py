"""Integration tests for MAS agent session approve/apply routes."""

from __future__ import annotations

from datetime import datetime, timezone
from unittest.mock import AsyncMock, patch

import pytest
from bson import ObjectId

from app.repositories.agent_session_repository import create_agent_session

VALID_PASSWORD = "StrongPass123!"


async def register_access_token(client, email: str) -> str:
    response = await client.post(
        "/auth/register",
        json={"email": email, "password": VALID_PASSWORD},
    )
    assert response.status_code == 201
    return response.json()["data"]["accessToken"]


async def _seed_completed_session(mongo_database, user_id: str) -> str:
    document = await create_agent_session(
        mongo_database,
        user_id=user_id,
        session_type="next_semester_plan",
        goal="Plan course 00140008",
        constraints={},
    )
    session_id = str(document["_id"])
    await mongo_database["agent_sessions"].update_one(
        {"_id": document["_id"]},
        {
            "$set": {
                "status": "completed",
                "finalDecision": {
                    "type": "next_semester_plan",
                    "course_ids": ["00140008"],
                    "semester_filename": "courses_2025_201.json",
                    "planSemesterCode": "2025-2",
                    "schedule": {"courses": [{"courseId": "00140008", "slots": []}]},
                },
                "updatedAt": datetime.now(timezone.utc),
            }
        },
    )
    return session_id


@pytest.mark.asyncio
async def test_approve_agent_session_marks_approved(auth_client, mongo_database):
    token = await register_access_token(auth_client, "mas-approve@example.com")
    user_id = (
        await mongo_database.users.find_one({"email": "mas-approve@example.com"})
    )["_id"]
    session_id = await _seed_completed_session(mongo_database, str(user_id))

    response = await auth_client.post(
        f"/agent/sessions/{session_id}/approve",
        headers={"Authorization": f"Bearer {token}"},
    )
    assert response.status_code == 200
    session = response.json()["data"]["session"]
    assert session["approvedAt"] is not None


@pytest.mark.asyncio
async def test_apply_agent_session_requires_approval(auth_client, mongo_database):
    token = await register_access_token(auth_client, "mas-apply-gate@example.com")
    user_id = (
        await mongo_database.users.find_one({"email": "mas-apply-gate@example.com"})
    )["_id"]
    session_id = await _seed_completed_session(mongo_database, str(user_id))

    response = await auth_client.post(
        f"/agent/sessions/{session_id}/apply",
        headers={"Authorization": f"Bearer {token}"},
        json={},
    )
    assert response.status_code == 409


@pytest.mark.asyncio
async def test_apply_agent_session_creates_plan(auth_client, mongo_database):
    token = await register_access_token(auth_client, "mas-apply-ok@example.com")
    user = await mongo_database.users.find_one({"email": "mas-apply-ok@example.com"})
    user_id = str(user["_id"])
    session_id = await _seed_completed_session(mongo_database, user_id)

    await mongo_database["student_profiles"].insert_one(
        {
            "_id": ObjectId(),
            "userId": user["_id"],
            "facultyId": "faculty-cs",
            "degreeProgramId": ObjectId(),
            "currentSemesterCode": "2025-2",
            "createdAt": datetime.now(timezone.utc),
            "updatedAt": datetime.now(timezone.utc),
        }
    )

    fake_course = {
        "_id": ObjectId(),
        "courseNumber": "00140008",
        "titleHebrew": "Test Course",
        "credits": 3,
        "status": "published",
    }

    with (
        patch(
            "app.services.agent_session_apply_service.catalog_repository.find_courses_by_numbers",
            new=AsyncMock(return_value=[fake_course]),
        ),
        patch(
            "app.services.agent_session_apply_service.suggest_semester_schedule",
            new=AsyncMock(
                return_value={
                    "status": "ok",
                    "selections": [
                        {
                            "courseNumber": "00140008",
                            "selectedLessonEvents": [
                                {"eventId": "lec-11", "type": "lecture", "group": "11"}
                            ],
                        }
                    ],
                    "skippedCourses": [],
                }
            ),
        ),
        patch(
            "app.services.agent_session_apply_service.create_manual_semester_plan",
            new=AsyncMock(
                return_value={
                    "status": "ok",
                    "plan": {"_id": ObjectId(), "name": "MAS plan"},
                }
            ),
        ),
    ):
        await auth_client.post(
            f"/agent/sessions/{session_id}/approve",
            headers={"Authorization": f"Bearer {token}"},
        )
        response = await auth_client.post(
            f"/agent/sessions/{session_id}/apply",
            headers={"Authorization": f"Bearer {token}"},
            json={"name": "MAS semester plan"},
        )

    assert response.status_code == 200
    body = response.json()["data"]
    assert body["semesterPlanId"]
    assert body["session"]["appliedPlanId"] == body["semesterPlanId"]
