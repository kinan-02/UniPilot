"""HTTP API setup for agent evaluation (register, profile, catalog)."""

from __future__ import annotations

import uuid
from dataclasses import dataclass, field
from typing import Any

import httpx

from app.agent.evaluation.agent_setup import DDS_PROGRAM_CODE, DDS_TRACK_SLUG

EVAL_PASSWORD = "AgentEvalPass123!"
DEFAULT_TIMEOUT_SEC = 120.0


@dataclass
class HttpEvalContext:
    email: str
    access_token: str
    conversation_id: str
    program_id: str | None = None
    seeded_courses: list[str] = field(default_factory=list)


@dataclass
class HttpSetupResult:
    ok: bool
    context: HttpEvalContext | None = None
    skip_reason: str | None = None


def _auth_headers(token: str) -> dict[str, str]:
    return {"Authorization": f"Bearer {token}"}


async def _request_with_retry(
    client: httpx.AsyncClient,
    method: str,
    url: str,
    *,
    max_attempts: int = 4,
    retry_statuses: frozenset[int] = frozenset({429, 502, 503, 504}),
    **kwargs: Any,
) -> httpx.Response:
    last_response: httpx.Response | None = None
    for attempt in range(max_attempts):
        response = await client.request(method, url, **kwargs)
        last_response = response
        if response.status_code not in retry_statuses:
            return response
        await _backoff_sleep(attempt)
    assert last_response is not None
    return last_response


async def _backoff_sleep(attempt: int) -> None:
    import asyncio

    await asyncio.sleep(min(2.0 ** attempt, 8.0))


async def setup_http_eval_user(
    client: httpx.AsyncClient,
    *,
    base_url: str,
    case_id: str,
    setup: dict[str, Any] | None = None,
) -> HttpSetupResult:
    """Register a user and optionally seed profile/courses via public API routes."""
    setup = setup or {}
    suffix = uuid.uuid4().hex[:10]
    email = f"agent-http-{case_id}-{suffix}@example.com"

    register_response = await _request_with_retry(
        client,
        "POST",
        f"{base_url}/auth/register",
        json={"email": email, "password": EVAL_PASSWORD},
    )
    if register_response.status_code != 201:
        return HttpSetupResult(
            ok=False,
            skip_reason=f"register failed: HTTP {register_response.status_code}",
        )

    access_token = register_response.json()["data"]["accessToken"]
    headers = _auth_headers(access_token)
    program_id: str | None = None
    seeded_courses: list[str] = []

    if setup.get("profileTemplate") == "dds_track":
        program_code = str(setup.get("programCode") or DDS_PROGRAM_CODE)
        program_response = await _request_with_retry(
            client,
            "GET",
            f"{base_url}/catalog/degree-programs/{program_code}",
            headers=headers,
        )
        if program_response.status_code != 200:
            return HttpSetupResult(
                ok=False,
                skip_reason=f"program {program_code!r} not found (HTTP {program_response.status_code})",
            )

        program = program_response.json()["data"]["program"]
        program_id = str(program["id"])

        profile_payload = {
            "institutionId": "technion",
            "programType": "BSc",
            "degreeId": program_id,
            "catalogYear": int(setup.get("catalogYear") or program.get("catalogYear") or 2025),
            "currentSemesterCode": str(setup.get("currentSemesterCode") or "2025-1"),
            "academicPath": {
                "trackSlug": str(setup.get("trackSlug") or DDS_TRACK_SLUG),
            },
            "preferences": setup.get("preferences") or {},
        }
        profile_response = await _request_with_retry(
            client,
            "POST",
            f"{base_url}/student-profile",
            headers=headers,
            json=profile_payload,
        )
        if profile_response.status_code not in {200, 201}:
            return HttpSetupResult(
                ok=False,
                skip_reason=f"student profile failed: HTTP {profile_response.status_code}",
            )

        for course_number in list(setup.get("completedCourseNumbers") or []):
            course_response = await _request_with_retry(
                client,
                "GET",
                f"{base_url}/catalog/courses/{course_number}",
                headers=headers,
            )
            if course_response.status_code != 200:
                if setup.get("skipIfMissingCatalog", True):
                    return HttpSetupResult(
                        ok=False,
                        skip_reason=f"course {course_number!r} not found (HTTP {course_response.status_code})",
                    )
                continue

            course_id = str(course_response.json()["data"]["course"]["id"])
            completed_response = await _request_with_retry(
                client,
                "POST",
                f"{base_url}/completed-courses",
                headers=headers,
                json={
                    "courseId": course_id,
                    "semesterCode": str(setup.get("completedSemesterCode") or "2024-1"),
                    "grade": 85,
                    "gradePoints": 85,
                    "creditsEarned": 3,
                    "attempt": 1,
                },
            )
            if completed_response.status_code not in {200, 201}:
                return HttpSetupResult(
                    ok=False,
                    skip_reason=(
                        f"completed course {course_number!r} failed: "
                        f"HTTP {completed_response.status_code}"
                    ),
                )
            seeded_courses.append(str(course_number))

    conversation_response = await _request_with_retry(
        client,
        "POST",
        f"{base_url}/agent/conversations",
        headers=headers,
        json={"title": f"HTTP eval: {case_id}"},
    )
    if conversation_response.status_code != 200:
        return HttpSetupResult(
            ok=False,
            skip_reason=f"create conversation failed: HTTP {conversation_response.status_code}",
        )

    conversation_id = str(conversation_response.json()["data"]["conversation"]["id"])
    return HttpSetupResult(
        ok=True,
        context=HttpEvalContext(
            email=email,
            access_token=access_token,
            conversation_id=conversation_id,
            program_id=program_id,
            seeded_courses=seeded_courses,
        ),
    )
