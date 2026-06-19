#!/usr/bin/env python3
"""Extensive Docker verification + performance benchmark for api-python (Phases 1-14)."""

from __future__ import annotations

import asyncio
import json
import statistics
import sys
import time
import uuid
from dataclasses import dataclass, field
from typing import Any

import httpx

BASE_URL = "http://localhost:8000"
PASSWORD = "StrongPass123!"


@dataclass
class BenchResult:
    name: str
    samples_ms: list[float] = field(default_factory=list)
    status_codes: list[int] = field(default_factory=list)
    errors: list[str] = field(default_factory=list)

    def add(self, elapsed_ms: float, status: int, error: str | None = None) -> None:
        self.samples_ms.append(elapsed_ms)
        self.status_codes.append(status)
        if error:
            self.errors.append(error)

    def summary(self) -> dict[str, Any]:
        if not self.samples_ms:
            return {"name": self.name, "count": 0, "errors": self.errors}
        sorted_ms = sorted(self.samples_ms)
        p95_idx = max(0, int(len(sorted_ms) * 0.95) - 1)
        return {
            "name": self.name,
            "count": len(self.samples_ms),
            "ok": sum(1 for c in self.status_codes if 200 <= c < 300),
            "errors": len(self.errors),
            "status_codes": dict(sorted({c: self.status_codes.count(c) for c in set(self.status_codes)}.items())),
            "min_ms": round(min(self.samples_ms), 2),
            "mean_ms": round(statistics.mean(self.samples_ms), 2),
            "p50_ms": round(statistics.median(self.samples_ms), 2),
            "p95_ms": round(sorted_ms[p95_idx], 2),
            "max_ms": round(max(self.samples_ms), 2),
        }


class Verifier:
    def __init__(self) -> None:
        self.passed: list[str] = []
        self.failed: list[str] = []
        self.warnings: list[str] = []
        self.token: str | None = None
        self.user_id: str | None = None
        self.course_id: str | None = None
        self.completed_id: str | None = None

    def ok(self, msg: str) -> None:
        self.passed.append(msg)

    def fail(self, msg: str) -> None:
        self.failed.append(msg)

    def warn(self, msg: str) -> None:
        self.warnings.append(msg)

    async def request(
        self,
        client: httpx.AsyncClient,
        method: str,
        path: str,
        *,
        token: str | None = None,
        json_body: dict | None = None,
        expected: int | tuple[int, ...] | None = None,
        label: str | None = None,
    ) -> httpx.Response:
        headers = {}
        if token:
            headers["Authorization"] = f"Bearer {token}"
        response = await client.request(method, path, headers=headers, json=json_body)
        name = label or f"{method} {path}"
        if expected is not None:
            allowed = (expected,) if isinstance(expected, int) else expected
            if response.status_code not in allowed:
                self.fail(f"{name}: expected {allowed}, got {response.status_code} — {response.text[:200]}")
            else:
                self.ok(f"{name}: {response.status_code}")
        return response


async def bench_request(
    client: httpx.AsyncClient,
    bench: BenchResult,
    method: str,
    path: str,
    *,
    token: str | None = None,
    json_body: dict | None = None,
) -> None:
    headers = {"Authorization": f"Bearer {token}"} if token else {}
    start = time.perf_counter()
    try:
        response = await client.request(method, path, headers=headers, json=json_body)
        elapsed = (time.perf_counter() - start) * 1000
        bench.add(elapsed, response.status_code)
    except Exception as exc:  # noqa: BLE001
        elapsed = (time.perf_counter() - start) * 1000
        bench.add(elapsed, 0, str(exc))


async def run_functional_verification(v: Verifier, client: httpx.AsyncClient) -> None:
    # Health (no auth)
    r = await v.request(client, "GET", "/health", expected=200, label="health")
    body = r.json()
    if body.get("service") == "api-python" and body.get("status") == "ok":
        v.ok("health payload identifies api-python (status ok)")
    else:
        v.fail(f"health payload unexpected: {body}")

    # Auth - register unique user
    email = f"verify-{uuid.uuid4().hex[:10]}@example.com"
    r = await v.request(
        client,
        "POST",
        "/auth/register",
        json_body={"email": email, "password": PASSWORD},
        expected=201,
        label="auth register",
    )
    data = r.json()["data"]
    v.token = data["accessToken"]
    v.user_id = data["user"]["id"]

    # Auth - me
    await v.request(client, "GET", "/auth/me", token=v.token, expected=200, label="auth me")

    # Auth - login
    await v.request(
        client,
        "POST",
        "/auth/login",
        json_body={"email": email, "password": PASSWORD},
        expected=200,
        label="auth login",
    )

    # Protected without token
    for path in [
        "/student-profile",
        "/catalog/courses?limit=1",
        "/completed-courses",
    ]:
        await v.request(client, "GET", path, expected=401, label=f"no auth {path}")

    # Student profile CRUD
    await v.request(
        client,
        "POST",
        "/student-profile",
        token=v.token,
        json_body={
            "institutionId": "technion",
            "programType": "BSc",
            "catalogYear": 2025,
            "currentSemesterCode": "2025-1",
        },
        expected=201,
        label="profile create",
    )
    await v.request(client, "GET", "/student-profile", token=v.token, expected=200, label="profile get")
    await v.request(
        client,
        "PUT",
        "/student-profile",
        token=v.token,
        json_body={"programType": "BSc-Data"},
        expected=200,
        label="profile update",
    )

    # Catalog
    r = await v.request(
        client,
        "GET",
        "/catalog/courses?limit=5",
        token=v.token,
        expected=200,
        label="catalog courses list",
    )
    courses_body = r.json()["data"]
    if courses_body.get("total", 0) >= 2000:
        v.ok(f"catalog courses total={courses_body['total']} (production scale)")
    else:
        v.warn(f"catalog courses total={courses_body.get('total')} — expected ~2204 in promoted env")

    first_course = courses_body["items"][0]["courseNumber"]
    await v.request(
        client,
        "GET",
        f"/catalog/courses/{first_course}",
        token=v.token,
        expected=200,
        label="catalog course detail",
    )

    # Excluded course 404
    await v.request(
        client,
        "GET",
        "/catalog/courses/00960226",
        token=v.token,
        expected=404,
        label="excluded course 00960226",
    )

    # Hard vs advisory separation
    r = await v.request(
        client,
        "GET",
        "/catalog/degree-programs/009216-1-000/catalog-summary",
        token=v.token,
        expected=200,
        label="catalog summary",
    )
    summary = r.json()["data"]["catalogSummary"]
    hard = summary.get("hardRequirements", [])
    advisory = summary.get("advisoryRules", [])
    if hard and all(h.get("requirementEnforcement") == "hard" for h in hard):
        v.ok("hard requirements labeled requirementEnforcement=hard")
    else:
        v.fail("hard requirements missing or mislabeled")
    if advisory and all(
        a.get("advisoryOnly") is True and a.get("enforceInGraduationProgress") is False
        for a in advisory
    ):
        v.ok("advisory rules correctly non-enforced")
    else:
        v.fail("advisory rules missing or mislabeled")

    # Resolve course ObjectId via catalog search
    r = await v.request(
        client,
        "GET",
        "/catalog/courses?courseNumber=00104000&limit=1",
        token=v.token,
        expected=200,
        label="catalog lookup 00104000",
    )
    # Need Mongo _id — get from completed course create after lookup via list isn't enough
    # Use mongosh-equivalent: fetch via repeated catalog isn't exposing id; use docker exec output
    # Instead POST with course from first list item - we need ObjectId from DB
    # Workaround: list doesn't return id; completed courses need courseId ObjectId
    # Query catalog detail doesn't expose _id either. Use subprocess in main() for course_id.

    # Completed courses - will be done after course_id resolved in main


async def run_completed_courses(v: Verifier, client: httpx.AsyncClient, course_id: str) -> None:
    v.course_id = course_id
    r = await v.request(
        client,
        "POST",
        "/completed-courses",
        token=v.token,
        json_body={
            "courseId": course_id,
            "semesterCode": "2024-1",
            "grade": "A",
            "creditsEarned": 2,
            "attempt": 1,
        },
        expected=201,
        label="completed course create",
    )
    v.completed_id = r.json()["data"]["completedCourse"]["id"]

    await v.request(client, "GET", "/completed-courses", token=v.token, expected=200, label="completed list")
    await v.request(
        client,
        "GET",
        f"/completed-courses/{v.completed_id}",
        token=v.token,
        expected=200,
        label="completed get",
    )
    await v.request(
        client,
        "PUT",
        f"/completed-courses/{v.completed_id}",
        token=v.token,
        json_body={"grade": "A+"},
        expected=200,
        label="completed update",
    )
    await v.request(
        client,
        "DELETE",
        f"/completed-courses/{v.completed_id}",
        token=v.token,
        expected=200,
        label="completed delete",
    )

    # Unknown course
    await v.request(
        client,
        "POST",
        "/completed-courses",
        token=v.token,
        json_body={
            "courseId": "665f2b0f2a3f7b2a1a9a7fff",
            "semesterCode": "2024-1",
            "grade": "A",
            "creditsEarned": 2,
        },
        expected=400,
        label="completed unknown course",
    )

    # Cleanup profile
    await v.request(client, "DELETE", "/student-profile", token=v.token, expected=200, label="profile delete")


async def run_benchmarks(client: httpx.AsyncClient, token: str) -> list[dict[str, Any]]:
    benches: list[BenchResult] = []

    scenarios = [
        ("health", "GET", "/health", None, None, 100),
        ("auth_login", "POST", "/auth/login", None, {"email": "phase14-docker@example.com", "password": PASSWORD}, 50),
        ("catalog_list_50", "GET", "/catalog/courses?limit=50", token, None, 50),
        ("catalog_list_200", "GET", "/catalog/courses?limit=200", token, None, 30),
        ("catalog_search_he", "GET", "/catalog/courses?q=מתמטיקה&limit=50", token, None, 30),
        ("catalog_summary", "GET", "/catalog/degree-programs/009216-1-000/catalog-summary", token, None, 30),
        ("catalog_requirements", "GET", "/catalog/degree-programs/009216-1-000/requirements", token, None, 30),
        ("completed_list", "GET", "/completed-courses", token, None, 50),
    ]

    results: list[dict[str, Any]] = []
    for name, method, path, tok, body, n in scenarios:
        bench = BenchResult(name=name)
        for _ in range(n):
            await bench_request(client, bench, method, path, token=tok, json_body=body)
        results.append(bench.summary())

    # Concurrent catalog load
    concurrent_bench = BenchResult(name="catalog_list_50_concurrent_x20")
    async def one() -> None:
        await bench_request(client, concurrent_bench, "GET", "/catalog/courses?limit=50", token=token)

    await asyncio.gather(*[one() for _ in range(20)])
    results.append(concurrent_bench.summary())

    return results


async def main() -> int:
    import subprocess

    # Resolve production course ObjectId from Mongo
    proc = subprocess.run(
        [
            "docker", "compose", "exec", "-T", "mongo",
            "mongosh", "-u", "unipilot", "-p", "unipilot_dev_password",
            "--authenticationDatabase", "admin", "unipilot_python", "--quiet",
            "--eval",
            'const c=db.courses.findOne({courseNumber:"00104000",status:"published"}); if(c) print(c._id.toString())',
        ],
        capture_output=True,
        text=True,
        cwd="/Users/tymoribrahim/Desktop/כתיבת תוכנה בלמידת מכונה/UniPilot",
    )
    course_id = proc.stdout.strip()
    if not course_id:
        print("WARN: could not resolve course ObjectId from Mongo; skipping completed-course Docker tests")

    v = Verifier()
    async with httpx.AsyncClient(base_url=BASE_URL, timeout=30.0) as client:
        await run_functional_verification(v, client)
        if course_id:
            await run_completed_courses(v, client, course_id)

        # Use existing user for login benchmark if register user can't be reused
        bench_token = v.token
        if not bench_token:
            login = await client.post(
                "/auth/login",
                json={"email": "phase14-docker@example.com", "password": PASSWORD},
            )
            if login.status_code == 200:
                bench_token = login.json()["data"]["accessToken"]

        bench_results = []
        if bench_token:
            bench_results = await run_benchmarks(client, bench_token)

    # Mongo integrity counts
    proc2 = subprocess.run(
        [
            "docker", "compose", "exec", "-T", "mongo",
            "mongosh", "-u", "unipilot", "-p", "unipilot_dev_password",
            "--authenticationDatabase", "admin", "unipilot_python", "--quiet",
            "--eval",
            'print(JSON.stringify({courses:db.courses.countDocuments(),offerings:db.course_offerings.countDocuments(),programs:db.degree_programs.countDocuments(),requirements:db.degree_requirements.countDocuments(),rules:db.catalog_rules.countDocuments(),completed:db.completed_courses.countDocuments()}))',
        ],
        capture_output=True,
        text=True,
        cwd="/Users/tymoribrahim/Desktop/כתיבת תוכנה בלמידת מכונה/UniPilot",
    )
    mongo_counts = json.loads(proc2.stdout.strip() or "{}")

    report = {
        "functional": {
            "passed": len(v.passed),
            "failed": len(v.failed),
            "warnings": len(v.warnings),
            "failures": v.failed,
            "warnings_list": v.warnings,
        },
        "mongo_counts": mongo_counts,
        "benchmarks": bench_results,
    }

    print("=" * 60)
    print("FUNCTIONAL VERIFICATION")
    print("=" * 60)
    print(f"PASSED: {len(v.passed)}")
    print(f"FAILED: {len(v.failed)}")
    print(f"WARNINGS: {len(v.warnings)}")
    if v.failed:
        print("\nFailures:")
        for f in v.failed:
            print(f"  - {f}")
    if v.warnings:
        print("\nWarnings:")
        for w in v.warnings:
            print(f"  - {w}")

    print("\n" + "=" * 60)
    print("MONGO COUNTS (unipilot_python)")
    print("=" * 60)
    print(json.dumps(mongo_counts, indent=2))

    print("\n" + "=" * 60)
    print("PERFORMANCE BENCHMARKS (Docker localhost:8000)")
    print("=" * 60)
    for b in bench_results:
        print(json.dumps(b, indent=2))

    # Write JSON report
    report_path = "/Users/tymoribrahim/Desktop/כתיבת תוכנה בלמידת מכונה/UniPilot/services/api-python/scripts/verify_report.json"
    with open(report_path, "w", encoding="utf-8") as f:
        json.dump(report, f, indent=2, ensure_ascii=False)
    print(f"\nFull report written to {report_path}")

    return 1 if v.failed else 0


if __name__ == "__main__":
    sys.exit(asyncio.run(main()))
