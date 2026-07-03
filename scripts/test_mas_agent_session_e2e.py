#!/usr/bin/env python3
"""Docker E2E: POST /agent/sessions → poll → assert MAS transcript.

Requires the stack from the repo root:

    docker compose up --build

Run:

    RUN_DOCKER_E2E=1 python3 scripts/test_mas_agent_session_e2e.py

Optional env:
    E2E_API_BASE_URL  default http://localhost:8000
    E2E_POLL_TIMEOUT_SEC  default 90 (120 when E2E_LLM_GOAL=1)
    E2E_COURSE_ID  default 00140008 (deterministic path; must exist in catalog)
    E2E_LLM_GOAL=1  goal without course codes → exercises Planner graph tool loop
                      (uses OPENAI_* from .env via docker-compose MAS_OPENAI_* fallback)
"""

from __future__ import annotations

import asyncio
import os
import sys
import time
import uuid

import httpx

API_BASE = os.getenv("E2E_API_BASE_URL", "http://localhost:8000").rstrip("/")
USE_LLM_GOAL = os.getenv("E2E_LLM_GOAL", "").strip() in {"1", "true", "yes"}
POLL_TIMEOUT_SEC = int(
    os.getenv("E2E_POLL_TIMEOUT_SEC", "120" if USE_LLM_GOAL else "90")
)
VALID_PASSWORD = "StrongPass123!"
# Must exist in ACADEMIC_DEFAULT_SEMESTER_FILE (courses_2025_201.json) with no prerequisites.
E2E_COURSE_ID = os.getenv("E2E_COURSE_ID", "00140008")
LLM_GOAL = (
    "Plan one introductory statistics course for Spring 2026 next semester"
)


def _fail(message: str) -> None:
    print(f"FAIL: {message}", file=sys.stderr)
    raise SystemExit(1)


async def _register(client: httpx.AsyncClient) -> str:
    email = f"mas-e2e-{uuid.uuid4().hex[:10]}@example.com"
    response = await client.post(
        "/auth/register",
        json={"email": email, "password": VALID_PASSWORD},
    )
    if response.status_code != 201:
        _fail(f"register failed: {response.status_code} {response.text}")
    token = response.json()["data"]["accessToken"]
    return token


async def _poll_session(
    client: httpx.AsyncClient,
    token: str,
    session_id: str,
) -> dict:
    headers = {"Authorization": f"Bearer {token}"}
    deadline = time.monotonic() + POLL_TIMEOUT_SEC
    last_status = "unknown"

    while time.monotonic() < deadline:
        response = await client.get(f"/agent/sessions/{session_id}", headers=headers)
        if response.status_code != 200:
            _fail(f"poll failed: {response.status_code} {response.text}")

        session = response.json()["data"]["session"]
        last_status = session.get("status", "unknown")
        if last_status in {"completed", "failed"}:
            return session

        await asyncio.sleep(2)

    _fail(f"session {session_id} did not finish within {POLL_TIMEOUT_SEC}s (last={last_status})")
    return {}


async def run() -> None:
    if os.getenv("RUN_DOCKER_E2E") != "1":
        _fail("Set RUN_DOCKER_E2E=1 to run this Docker E2E script.")

    async with httpx.AsyncClient(base_url=API_BASE, timeout=30.0) as client:
        health = await client.get("/health")
        if health.status_code != 200:
            _fail(f"API health check failed at {API_BASE}/health")

        token = await _register(client)
        headers = {"Authorization": f"Bearer {token}"}

        goal = LLM_GOAL if USE_LLM_GOAL else f"Plan course {E2E_COURSE_ID} for next semester"
        create = await client.post(
            "/agent/sessions",
            headers=headers,
            json={"goal": goal},
        )
        if create.status_code != 202:
            _fail(f"create session failed: {create.status_code} {create.text}")

        session_id = create.json()["data"]["session"]["id"]
        print(f"Created agent session {session_id}, polling…")

        session = await _poll_session(client, token, session_id)

    if session.get("status") != "completed":
        _fail(f"expected completed, got {session.get('status')}: {session.get('error')}")

    transcript = session.get("transcript") or []
    roles = {turn.get("agent_role") for turn in transcript}
    for expected in ("planner", "catalog_scout", "risk_sentinel", "student_advocate", "arbiter"):
        if expected not in roles:
            _fail(f"missing agent role in transcript: {expected} (have {sorted(roles)})")

    final_decision = session.get("finalDecision") or {}
    course_ids = final_decision.get("course_ids") or []
    schedule = final_decision.get("schedule") or {}
    if not isinstance(schedule, dict) or not schedule.get("courses"):
        _fail("expected schedule.courses in finalDecision")

    if USE_LLM_GOAL:
        planner_turns = [t for t in transcript if t.get("agent_role") == "planner"]
        refs = planner_turns[0].get("references", []) if planner_turns else []
        tool_refs = [ref for ref in refs if str(ref).startswith("tool:")]
        if not tool_refs:
            _fail(f"expected planner graph tool refs in transcript, got {refs[:8]}")
        if not course_ids:
            _fail("expected at least one course in finalDecision from LLM planner")
    elif E2E_COURSE_ID not in course_ids:
        _fail(f"expected course {E2E_COURSE_ID} in finalDecision, got {course_ids}")

    mode = "llm_tool_loop" if USE_LLM_GOAL else "deterministic"
    print(f"PASS: MAS agent session E2E ({mode})")
    print(f"  session_id={session_id}")
    print(f"  rounds={session.get('rounds')}")
    print(f"  transcript_turns={len(transcript)}")
    print(f"  course_ids={course_ids}")


def main() -> None:
    asyncio.run(run())


if __name__ == "__main__":
    main()
