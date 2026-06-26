#!/usr/bin/env python3
"""Quick multi-feature API scenario checks against a running Docker stack."""

from __future__ import annotations

import json
import sys
import uuid

import httpx

BASE = "http://localhost:8000"
PASSWORD = "StrongPass123!"


def fail(msg: str) -> None:
    print(f"FAIL: {msg}")
    sys.exit(1)


def ok(msg: str) -> None:
    print(f"OK: {msg}")


def main() -> None:
    email = f"scenario-{uuid.uuid4().hex[:10]}@example.com"
    token: str | None = None
    course_id: str | None = None
    plan_id: str | None = None

    with httpx.Client(base_url=BASE, timeout=30.0) as client:
        # Auth: register + login + me
        r = client.post("/auth/register", json={"email": email, "password": PASSWORD})
        if r.status_code != 201:
            fail(f"register -> {r.status_code} {r.text}")
        token = r.json()["data"]["accessToken"]
        ok("register")

        r = client.post("/auth/login", json={"email": email, "password": PASSWORD})
        if r.status_code not in (200, 429):
            fail(f"login -> {r.status_code}")
        ok("login")

        headers = {"Authorization": f"Bearer {token}"}
        r = client.get("/auth/me", headers=headers)
        if r.status_code != 200:
            fail(f"me -> {r.status_code}")
        ok("auth/me")

        # Validation: bad login on a fresh client (no prior auth spam on this session)
        with httpx.Client(base_url=BASE, timeout=30.0) as guest:
            r = guest.post("/auth/login", json={"email": "bad", "password": PASSWORD})
            if r.status_code not in (400, 429):
                fail(f"login invalid email expected 400/429 got {r.status_code}")
        ok("auth validation")

        # Catalog
        r = client.get("/catalog/courses", headers=headers, params={"limit": 5, "q": "02340117"})
        if r.status_code != 200 or not r.json()["data"]["items"]:
            fail(f"catalog search -> {r.status_code}")
        course = r.json()["data"]["items"][0]
        course_id = course.get("id")
        ok(f"catalog search ({course['courseNumber']})")

        r = client.get(f"/catalog/courses/{course['courseNumber']}", headers=headers)
        if r.status_code != 200:
            fail(f"catalog detail -> {r.status_code}")
        ok("catalog detail")

        r = client.get("/catalog/degree-programs", headers=headers)
        if r.status_code != 200 or not r.json()["data"]["items"]:
            fail("degree programs empty")
        degree_id = r.json()["data"]["items"][0]["id"]
        ok("degree programs")

        # Minimal profile required before persisting plans
        r = client.post(
            "/student-profile",
            headers=headers,
            json={
                "institutionId": "technion",
                "programType": "BSc",
                "degreeId": degree_id,
                "catalogYear": 2025,
                "currentSemesterCode": "2025-2",
            },
        )
        if r.status_code not in (200, 201):
            fail(f"profile create -> {r.status_code} {r.text}")
        ok("profile create")

        # Manual plan
        r = client.post(
            "/semester-plans",
            headers=headers,
            json={
                "name": "Scenario manual plan",
                "status": "draft",
                "semesters": [
                    {
                        "semesterCode": "2025-2",
                        "goalCredits": 10,
                        "plannedCourses": [{"courseId": course_id, "category": "manual"}],
                    }
                ],
            },
        )
        if r.status_code != 201:
            fail(f"manual plan create -> {r.status_code} {r.text}")
        plan_id = r.json()["data"]["semesterPlan"]["id"]
        ok("manual plan create")

        # Completed course
        r = client.post(
            "/completed-courses",
            headers=headers,
            json={
                "courseId": course_id,
                "grade": 85,
                "semesterCode": "2024-1",
                "creditsEarned": course.get("credits") or 3,
            },
        )
        if r.status_code != 201:
            fail(f"completed course -> {r.status_code} {r.text}")
        completed_id = r.json()["data"]["completedCourse"]["id"]
        ok("completed course create")

        # Graduation progress
        r = client.get("/graduation-progress", headers=headers)
        if r.status_code != 200:
            fail(f"graduation progress -> {r.status_code}")
        ok("graduation progress")

        # Auto plan generate
        r = client.post(
            "/semester-plans/generate",
            headers=headers,
            json={"semesterCode": "2025-2", "maxCredits": 12},
        )
        if r.status_code != 201:
            fail(f"plan generate -> {r.status_code} {r.text}")
        ok("auto plan generate")

        # Academic risks
        r = client.post("/academic-risks/analyze", headers=headers, json={"planId": plan_id})
        if r.status_code != 201:
            fail(f"risk analyze -> {r.status_code} {r.text}")
        risk_id = r.json()["data"]["academicRiskAnalysis"]["id"]
        ok("academic risk analyze")

        r = client.get(f"/academic-risks/{risk_id}", headers=headers)
        if r.status_code != 200:
            fail(f"risk get -> {r.status_code}")
        ok("academic risk get")

        # Security: no token (fresh client — avoids refresh-cookie session reuse)
        with httpx.Client(base_url=BASE, timeout=30.0) as guest:
            r = guest.get("/semester-plans")
            if r.status_code != 401:
                fail(f"unauth plans expected 401 got {r.status_code}")
        ok("auth enforcement")

        # Cleanup completed course
        r = client.delete(f"/completed-courses/{completed_id}", headers=headers)
        if r.status_code != 200:
            fail(f"completed delete -> {r.status_code}")
        ok("completed course delete")

    print("\nAll scenario checks passed.")


if __name__ == "__main__":
    main()
