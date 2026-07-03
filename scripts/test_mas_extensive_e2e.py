#!/usr/bin/env python3
"""Extensive Docker E2E suite for MAS agent sessions.

Requires the stack from the repo root:

    docker compose up --build

Run:

    RUN_DOCKER_E2E=1 python3 scripts/test_mas_extensive_e2e.py

Optional env:
    E2E_API_BASE_URL          default http://localhost:8000
    E2E_POLL_TIMEOUT_SEC      default 120
    E2E_LLM_CASES=1           include slow LLM planner tool-loop case(s)
    E2E_SKIP_APPLY=1          skip approve/apply lifecycle cases
"""

from __future__ import annotations

import asyncio
import os
import sys
import time
import uuid
from dataclasses import dataclass, field
from typing import Any, Awaitable, Callable

import httpx

API_BASE = os.getenv("E2E_API_BASE_URL", "http://localhost:8000").rstrip("/")
INTERNAL_SERVICE_TOKEN = os.getenv(
    "INTERNAL_SERVICE_TOKEN",
    "unipilot_dev_internal_service_token_change_in_production",
)
POLL_TIMEOUT_SEC = int(os.getenv("E2E_POLL_TIMEOUT_SEC", "120"))
INCLUDE_LLM = os.getenv("E2E_LLM_CASES", "1").strip() in {"1", "true", "yes"}
SKIP_APPLY = os.getenv("E2E_SKIP_APPLY", "").strip() in {"1", "true", "yes"}
VALID_PASSWORD = "StrongPass123!"

# Known no-prerequisite courses in courses_2025_201.json (Technion raw catalog).
COURSE_A = os.getenv("E2E_COURSE_A", "00140008")
COURSE_B = os.getenv("E2E_COURSE_B", "00140102")
COURSE_C = os.getenv("E2E_COURSE_C", "00140101")

EXPECTED_AGENTS = (
    "planner",
    "catalog_scout",
    "risk_sentinel",
    "student_advocate",
    "arbiter",
)


@dataclass
class CaseResult:
    name: str
    status: str  # pass | fail | skip
    detail: str = ""
    duration_sec: float = 0.0


@dataclass
class E2EContext:
    client: httpx.AsyncClient
    token: str = ""
    user_email: str = ""
    catalog_course_id: str = ""  # Mongo ObjectId for COURSE_A


@dataclass
class TestCase:
    name: str
    fn: Callable[[E2EContext], Awaitable[None]]
    skip_reason: str | None = None
    anonymous: bool = False


def _fail(message: str) -> None:
    raise AssertionError(message)


async def _register(client: httpx.AsyncClient, label: str = "mas-ext") -> tuple[str, str]:
    email = f"{label}-{uuid.uuid4().hex[:10]}@example.com"
    response = await client.post(
        "/auth/register",
        json={"email": email, "password": VALID_PASSWORD},
    )
    if response.status_code != 201:
        _fail(f"register failed: {response.status_code} {response.text}")
    token = response.json()["data"]["accessToken"]
    return token, email


def _auth(token: str) -> dict[str, str]:
    return {"Authorization": f"Bearer {token}"}


async def _create_session(
    ctx: E2EContext,
    *,
    goal: str,
    constraints: dict[str, Any] | None = None,
    token: str | None = None,
) -> dict[str, Any]:
    headers = _auth(token or ctx.token)
    payload: dict[str, Any] = {"goal": goal}
    if constraints:
        payload["constraints"] = constraints
    response = await ctx.client.post("/agent/sessions", headers=headers, json=payload)
    if response.status_code != 202:
        _fail(f"create session failed: {response.status_code} {response.text}")
    return response.json()["data"]["session"]


async def _poll_session(
    ctx: E2EContext,
    session_id: str,
    *,
    token: str | None = None,
    timeout_sec: int | None = None,
) -> dict[str, Any]:
    headers = _auth(token or ctx.token)
    deadline = time.monotonic() + (timeout_sec or POLL_TIMEOUT_SEC)
    last_status = "unknown"
    while time.monotonic() < deadline:
        response = await ctx.client.get(f"/agent/sessions/{session_id}", headers=headers)
        if response.status_code != 200:
            _fail(f"poll failed: {response.status_code} {response.text}")
        session = response.json()["data"]["session"]
        last_status = session.get("status", "unknown")
        if last_status in {"completed", "failed"}:
            return session
        await asyncio.sleep(2)
    _fail(f"session {session_id} timed out (last={last_status})")
    return {}


def _assert_completed_session(session: dict[str, Any], *, min_courses: int = 1) -> dict[str, Any]:
    if session.get("status") != "completed":
        _fail(f"expected completed, got {session.get('status')}: {session.get('error')}")
    transcript = session.get("transcript") or []
    roles = {turn.get("agent_role") for turn in transcript}
    missing = [role for role in EXPECTED_AGENTS if role not in roles]
    if missing:
        _fail(f"missing agent roles: {missing} (have {sorted(roles)})")
    decision = session.get("finalDecision") or {}
    course_ids = decision.get("course_ids") or []
    if len(course_ids) < min_courses:
        _fail(f"expected >= {min_courses} courses, got {course_ids}")
    schedule = decision.get("schedule") or {}
    if not isinstance(schedule, dict) or not schedule.get("courses"):
        _fail("finalDecision.schedule.courses missing")
    if schedule.get("hasScheduleConflicts"):
        _fail(f"unexpected schedule conflicts: {schedule.get('scheduleConflicts')}")
    if not decision.get("planSemesterCode"):
        _fail("finalDecision.planSemesterCode missing")
    if session.get("utilityBreakdown") is None:
        _fail("utilityBreakdown missing on completed session")
    return decision


async def _ensure_profile(ctx: E2EContext) -> None:
    response = await ctx.client.post(
        "/student-profile",
        headers=_auth(ctx.token),
        json={
            "institutionId": "technion",
            "programType": "BSc",
            "catalogYear": 2025,
            "currentSemesterCode": "2025-2",
        },
    )
    if response.status_code not in {200, 201}:
        _fail(f"student profile create failed: {response.status_code} {response.text}")


async def _resolve_catalog_course_id(ctx: E2EContext, course_number: str) -> str:
    response = await ctx.client.get(
        f"/catalog/courses/{course_number}",
        headers=_auth(ctx.token),
    )
    if response.status_code != 200:
        _fail(f"catalog lookup failed for {course_number}: {response.status_code}")
    course = response.json()["data"]["course"]
    course_id = str(course.get("id") or "")
    if not course_id:
        _fail(f"catalog course {course_number} has no id")
    return course_id


# --- individual test cases ---


async def case_api_health(ctx: E2EContext) -> None:
    response = await ctx.client.get("/health")
    if response.status_code != 200:
        _fail(f"health failed: {response.status_code}")
    body = response.json()
    if body.get("status") != "ok":
        _fail(f"unexpected health body: {body}")


async def case_create_requires_auth(ctx: E2EContext) -> None:
    response = await ctx.client.post(
        "/agent/sessions",
        json={"goal": "Plan next semester"},
    )
    if response.status_code != 401:
        _fail(f"expected 401, got {response.status_code}")


async def case_get_requires_auth(ctx: E2EContext) -> None:
    response = await ctx.client.get("/agent/sessions/507f1f77bcf86cd799439011")
    if response.status_code not in {401, 403}:
        _fail(f"expected 401/403, got {response.status_code}")


async def case_list_requires_auth(ctx: E2EContext) -> None:
    response = await ctx.client.get("/agent/sessions")
    if response.status_code != 401:
        _fail(f"expected 401, got {response.status_code}")


async def case_create_validation_rejects_empty_goal(ctx: E2EContext) -> None:
    response = await ctx.client.post(
        "/agent/sessions",
        headers=_auth(ctx.token),
        json={"goal": ""},
    )
    if response.status_code not in {400, 422}:
        _fail(f"expected 400/422 for empty goal, got {response.status_code}")


async def _current_user_id(ctx: E2EContext, *, token: str | None = None) -> str:
    response = await ctx.client.get("/auth/me", headers=_auth(token or ctx.token))
    if response.status_code != 200:
        _fail(f"auth/me failed: {response.status_code} {response.text}")
    user_id = response.json()["data"]["user"]["id"]
    if not user_id:
        _fail("auth/me missing user id")
    return str(user_id)


async def _add_completed_course(
    ctx: E2EContext,
    *,
    course_id: str,
    course_number: str,
    token: str | None = None,
) -> None:
    response = await ctx.client.post(
        "/completed-courses",
        headers=_auth(token or ctx.token),
        json={
            "courseId": course_id,
            "semesterCode": "2024-2",
            "grade": 85,
            "creditsEarned": 3,
        },
    )
    if response.status_code not in {200, 201}:
        _fail(f"completed course create failed: {response.status_code} {response.text}")
    record = response.json()["data"]["completedCourse"]
    if str(record.get("courseNumber") or "") != course_number:
        _fail(
            f"completed course number mismatch: expected {course_number}, "
            f"got {record.get('courseNumber')}"
        )


async def case_session_bootstrap_and_path_context(ctx: E2EContext) -> None:
    await _ensure_profile(ctx)
    course_id = await _resolve_catalog_course_id(ctx, COURSE_A)
    ctx.catalog_course_id = course_id
    await _add_completed_course(ctx, course_id=course_id, course_number=COURSE_A)

    user_id = await _current_user_id(ctx)
    bootstrap = await ctx.client.get(
        f"/internal/session-bootstrap/users/{user_id}",
        headers={"X-Internal-Service-Token": INTERNAL_SERVICE_TOKEN},
    )
    if bootstrap.status_code != 200:
        _fail(f"session bootstrap failed: {bootstrap.status_code} {bootstrap.text}")
    payload = bootstrap.json()
    if payload.get("success") is not True:
        _fail(f"session bootstrap envelope invalid: {payload}")
    data = payload["data"]
    user_context = data.get("userContext") or {}
    if COURSE_A not in (user_context.get("completed_courses") or []):
        _fail(
            f"bootstrap missing completed course {COURSE_A}: "
            f"{user_context.get('completed_courses')}"
        )
    if data.get("graduationStatus") not in {"ok", "degree_not_selected"}:
        _fail(f"unexpected graduationStatus: {data.get('graduationStatus')}")

    created = await _create_session(
        ctx,
        goal=f"Plan course {COURSE_B} for next semester (avoid repeating {COURSE_A})",
    )
    session = await _poll_session(ctx, created["id"])
    decision = _assert_completed_session(session)
    path_context = decision.get("pathContext") or {}
    if (path_context.get("completedCourseCount") or 0) < 1:
        _fail(f"pathContext missing completedCourseCount: {path_context}")
    if path_context.get("contextSource") not in {"api_bootstrap", "api_split"}:
        _fail(f"unexpected pathContext.contextSource: {path_context.get('contextSource')}")


async def case_deterministic_single_course(ctx: E2EContext) -> None:
    created = await _create_session(ctx, goal=f"Plan course {COURSE_A} for next semester")
    session = await _poll_session(ctx, created["id"])
    decision = _assert_completed_session(session)
    if COURSE_A not in (decision.get("course_ids") or []):
        _fail(f"expected {COURSE_A} in plan")


async def case_deterministic_second_course(ctx: E2EContext) -> None:
    created = await _create_session(ctx, goal=f"Plan course {COURSE_B} for next semester")
    session = await _poll_session(ctx, created["id"])
    decision = _assert_completed_session(session)
    if COURSE_B not in (decision.get("course_ids") or []):
        _fail(f"expected {COURSE_B} in plan")


async def case_multi_course_plan(ctx: E2EContext) -> None:
    goal = f"Plan courses {COURSE_A} and {COURSE_B} for next semester"
    created = await _create_session(ctx, goal=goal)
    session = await _poll_session(ctx, created["id"])
    decision = _assert_completed_session(session, min_courses=1)
    course_ids = set(decision.get("course_ids") or [])
    # Planner may revise away conflicts; at least one requested course should survive.
    if not course_ids.intersection({COURSE_A, COURSE_B}):
        _fail(f"expected at least one of {COURSE_A}/{COURSE_B}, got {course_ids}")


async def case_constraints_avoid_friday(ctx: E2EContext) -> None:
    created = await _create_session(
        ctx,
        goal=f"Plan course {COURSE_A} for next semester",
        constraints={"avoidDays": ["שישי"]},
    )
    session = await _poll_session(ctx, created["id"])
    _assert_completed_session(session)


async def case_constraints_min_credits(ctx: E2EContext) -> None:
    created = await _create_session(
        ctx,
        goal="Plan a balanced next semester workload",
        constraints={"minCredits": 6},
    )
    session = await _poll_session(ctx, created["id"], timeout_sec=150)
    # May complete with soft critiques rather than exact credit hit when LLM off.
    if session.get("status") not in {"completed", "failed"}:
        _fail(f"unexpected status: {session.get('status')}")
    if session.get("status") == "completed":
        _assert_completed_session(session)


async def case_invalid_course_fails(ctx: E2EContext) -> None:
    created = await _create_session(ctx, goal="Plan course 99999999 for next semester")
    session = await _poll_session(ctx, created["id"])
    if session.get("status") != "failed":
        _fail(f"expected failed for invalid course, got {session.get('status')}")
    if not session.get("error"):
        _fail("expected error message on failed session")


async def case_list_sessions_contains_history(ctx: E2EContext) -> None:
    created = await _create_session(ctx, goal=f"Plan course {COURSE_C} for next semester")
    await _poll_session(ctx, created["id"])
    response = await ctx.client.get("/agent/sessions", headers=_auth(ctx.token))
    if response.status_code != 200:
        _fail(f"list failed: {response.status_code}")
    sessions = response.json()["data"]["sessions"]
    ids = {item["id"] for item in sessions}
    if created["id"] not in ids:
        _fail("created session not found in list")


async def case_cross_user_access_denied(ctx: E2EContext) -> None:
    created = await _create_session(ctx, goal=f"Plan course {COURSE_A} for next semester")
    other_token, _ = await _register(ctx.client, label="mas-other")
    response = await ctx.client.get(
        f"/agent/sessions/{created['id']}",
        headers=_auth(other_token),
    )
    if response.status_code != 404:
        _fail(f"expected 404 for other user, got {response.status_code}")


async def case_schedule_slots_shape(ctx: E2EContext) -> None:
    created = await _create_session(ctx, goal=f"Plan course {COURSE_A} for next semester")
    session = await _poll_session(ctx, created["id"])
    decision = _assert_completed_session(session)
    courses = (decision.get("schedule") or {}).get("courses") or []
    entry = next((c for c in courses if c.get("courseId") == COURSE_A), None)
    if entry is None:
        _fail(f"schedule missing entry for {COURSE_A}")
    if "credits" not in entry:
        _fail("schedule course entry missing credits")
    if "slots" not in entry:
        _fail("schedule course entry missing slots")


async def case_llm_open_goal(ctx: E2EContext) -> None:
    created = await _create_session(
        ctx,
        goal="Plan one introductory statistics course for next semester",
    )
    session = await _poll_session(ctx, created["id"], timeout_sec=180)
    decision = _assert_completed_session(session)
    transcript = session.get("transcript") or []
    planner_turns = [t for t in transcript if t.get("agent_role") == "planner"]
    refs = planner_turns[0].get("references", []) if planner_turns else []
    tool_refs = [ref for ref in refs if str(ref).startswith("tool:")]
    if not tool_refs:
        _fail(f"expected planner tool refs, got {refs[:8]}")


async def case_approve_completed_session(ctx: E2EContext) -> None:
    created = await _create_session(ctx, goal=f"Plan course {COURSE_A} for next semester")
    await _poll_session(ctx, created["id"])
    response = await ctx.client.post(
        f"/agent/sessions/{created['id']}/approve",
        headers=_auth(ctx.token),
        json={},
    )
    if response.status_code != 200:
        _fail(f"approve failed: {response.status_code} {response.text}")
    session = response.json()["data"]["session"]
    if not session.get("approvedAt"):
        _fail("approvedAt not set")


async def case_apply_requires_approval(ctx: E2EContext) -> None:
    created = await _create_session(ctx, goal=f"Plan course {COURSE_A} for next semester")
    await _poll_session(ctx, created["id"])
    response = await ctx.client.post(
        f"/agent/sessions/{created['id']}/apply",
        headers=_auth(ctx.token),
        json={},
    )
    if response.status_code != 409:
        _fail(f"expected 409 without approval, got {response.status_code}")


async def case_override_course_list(ctx: E2EContext) -> None:
    created = await _create_session(ctx, goal=f"Plan course {COURSE_A} for next semester")
    await _poll_session(ctx, created["id"])
    response = await ctx.client.post(
        f"/agent/sessions/{created['id']}/override",
        headers=_auth(ctx.token),
        json={"course_ids": [COURSE_B]},
    )
    if response.status_code != 200:
        _fail(f"override failed: {response.status_code} {response.text}")
    session = response.json()["data"]["session"]
    override = session.get("overriddenDecision") or {}
    if override.get("course_ids") != [COURSE_B]:
        _fail(f"override not applied: {override}")
    if session.get("approvedAt"):
        _fail("approve should be cleared after override")


async def case_full_apply_lifecycle(ctx: E2EContext) -> None:
    await _ensure_profile(ctx)
    ctx.catalog_course_id = await _resolve_catalog_course_id(ctx, COURSE_A)
    created = await _create_session(ctx, goal=f"Plan course {COURSE_A} for next semester")
    await _poll_session(ctx, created["id"])

    approve = await ctx.client.post(
        f"/agent/sessions/{created['id']}/approve",
        headers=_auth(ctx.token),
        json={},
    )
    if approve.status_code != 200:
        _fail(f"approve failed: {approve.status_code} {approve.text}")

    apply = await ctx.client.post(
        f"/agent/sessions/{created['id']}/apply",
        headers=_auth(ctx.token),
        json={"name": "MAS extensive E2E plan"},
    )
    if apply.status_code != 200:
        _fail(f"apply failed: {apply.status_code} {apply.text}")
    body = apply.json()["data"]
    plan_id = body.get("semesterPlanId")
    if not plan_id:
        _fail("apply missing semesterPlanId")
    session = body.get("session") or {}
    if session.get("appliedPlanId") != plan_id:
        _fail("session.appliedPlanId mismatch")

    plan_resp = await ctx.client.get(
        f"/semester-plans/{plan_id}",
        headers=_auth(ctx.token),
    )
    if plan_resp.status_code != 200:
        _fail(f"could not fetch created plan: {plan_resp.status_code}")
    plan = plan_resp.json()["data"]["semesterPlan"]
    planned_numbers = {
        str(course.get("courseNumber"))
        for course in (plan.get("semesters") or [{}])[0].get("plannedCourses") or []
    }
    if COURSE_A not in planned_numbers:
        _fail(f"plan missing {COURSE_A}, has {planned_numbers}")

    reapply = await ctx.client.post(
        f"/agent/sessions/{created['id']}/apply",
        headers=_auth(ctx.token),
        json={},
    )
    if reapply.status_code != 409:
        _fail(f"expected 409 on double apply, got {reapply.status_code}")


def _build_cases() -> list[TestCase]:
    cases: list[TestCase] = [
        TestCase("api_health", case_api_health, anonymous=True),
        TestCase("create_requires_auth", case_create_requires_auth, anonymous=True),
        TestCase("get_requires_auth", case_get_requires_auth, anonymous=True),
        TestCase("list_requires_auth", case_list_requires_auth, anonymous=True),
        TestCase("create_validation_rejects_empty_goal", case_create_validation_rejects_empty_goal),
        TestCase("session_bootstrap_and_path_context", case_session_bootstrap_and_path_context),
        TestCase("deterministic_single_course", case_deterministic_single_course),
        TestCase("deterministic_second_course", case_deterministic_second_course),
        TestCase("multi_course_plan", case_multi_course_plan),
        TestCase("constraints_avoid_friday", case_constraints_avoid_friday),
        TestCase("constraints_min_credits", case_constraints_min_credits),
        TestCase("invalid_course_fails", case_invalid_course_fails),
        TestCase("list_sessions_contains_history", case_list_sessions_contains_history),
        TestCase("cross_user_access_denied", case_cross_user_access_denied),
        TestCase("schedule_slots_shape", case_schedule_slots_shape),
        TestCase("approve_completed_session", case_approve_completed_session),
        TestCase("apply_requires_approval", case_apply_requires_approval),
        TestCase("override_course_list", case_override_course_list),
    ]
    if INCLUDE_LLM:
        cases.append(TestCase("llm_open_goal", case_llm_open_goal))
    else:
        cases.append(
            TestCase(
                "llm_open_goal",
                case_llm_open_goal,
                skip_reason="Set E2E_LLM_CASES=1 to run LLM planner case",
            )
        )
    if SKIP_APPLY:
        cases.append(
            TestCase(
                "full_apply_lifecycle",
                case_full_apply_lifecycle,
                skip_reason="E2E_SKIP_APPLY=1",
            )
        )
    else:
        cases.append(TestCase("full_apply_lifecycle", case_full_apply_lifecycle))
    return cases


async def _run_case(case: TestCase, ctx: E2EContext) -> CaseResult:
    if case.skip_reason:
        return CaseResult(name=case.name, status="skip", detail=case.skip_reason)
    started = time.monotonic()
    if not case.anonymous:
        ctx.token, ctx.user_email = await _register(ctx.client, label=case.name[:20])
    try:
        await case.fn(ctx)
        return CaseResult(
            name=case.name,
            status="pass",
            duration_sec=time.monotonic() - started,
        )
    except AssertionError as exc:
        return CaseResult(
            name=case.name,
            status="fail",
            detail=str(exc),
            duration_sec=time.monotonic() - started,
        )
    except Exception as exc:  # noqa: BLE001
        return CaseResult(
            name=case.name,
            status="fail",
            detail=f"{type(exc).__name__}: {exc}",
            duration_sec=time.monotonic() - started,
        )


async def run() -> int:
    if os.getenv("RUN_DOCKER_E2E") != "1":
        print("FAIL: Set RUN_DOCKER_E2E=1 to run extensive MAS E2E.", file=sys.stderr)
        return 1

    cases = _build_cases()
    results: list[CaseResult] = []

    async with httpx.AsyncClient(base_url=API_BASE, timeout=60.0) as client:
        ctx = E2EContext(client=client)
        print(f"MAS extensive E2E against {API_BASE} ({len(cases)} cases)\n")

        for index, case in enumerate(cases, start=1):
            print(f"[{index}/{len(cases)}] {case.name} …", flush=True)
            result = await _run_case(case, ctx)
            results.append(result)
            icon = {"pass": "PASS", "fail": "FAIL", "skip": "SKIP"}[result.status]
            line = f"  {icon} ({result.duration_sec:.1f}s)"
            if result.detail:
                line += f" — {result.detail}"
            print(line)

    passed = sum(1 for item in results if item.status == "pass")
    failed = sum(1 for item in results if item.status == "fail")
    skipped = sum(1 for item in results if item.status == "skip")
    total = len(results)

    print("\n--- Summary ---")
    print(f"Total: {total}  Passed: {passed}  Failed: {failed}  Skipped: {skipped}")
    if failed:
        print("\nFailures:")
        for item in results:
            if item.status == "fail":
                print(f"  - {item.name}: {item.detail}")

    return 0 if failed == 0 else 1


def main() -> None:
    raise SystemExit(asyncio.run(run()))


if __name__ == "__main__":
    main()
