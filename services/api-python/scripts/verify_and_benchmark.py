#!/usr/bin/env python3
"""Extensive Docker verification + performance benchmark for api-python (Phases 1-16)."""

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
        self.degree_program_id: str | None = None

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
        "/graduation-progress",
        "/semester-plans",
        "/semester-plans/generate",
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


async def run_graduation_progress(
    v: Verifier,
    client: httpx.AsyncClient,
    *,
    degree_program_id: str | None,
    course_id: str | None,
) -> None:
    if not degree_program_id:
        v.warn("skipping graduation progress Docker tests — no degree_programs._id resolved")
        return

    grad_email = f"grad-verify-{uuid.uuid4().hex[:8]}@example.com"
    reg = await v.request(
        client,
        "POST",
        "/auth/register",
        json_body={"email": grad_email, "password": PASSWORD},
        expected=201,
        label="graduation user register",
    )
    grad_token = reg.json()["data"]["accessToken"]

    await v.request(
        client,
        "GET",
        "/graduation-progress",
        token=grad_token,
        expected=404,
        label="graduation no profile",
    )

    await v.request(
        client,
        "POST",
        "/student-profile",
        token=grad_token,
        json_body={
            "institutionId": "technion",
            "programType": "BSc",
            "degreeId": degree_program_id,
            "catalogYear": 2025,
            "currentSemesterCode": "2025-1",
        },
        expected=201,
        label="graduation profile with degreeId",
    )

    r = await v.request(
        client,
        "GET",
        "/graduation-progress",
        token=grad_token,
        expected=200,
        label="graduation not_started",
    )
    progress = r.json()["data"]["graduationProgress"]
    if progress.get("statusSummary") == "not_started" and progress.get("completedCredits") == 0:
        v.ok("graduation progress not_started with zero credits")
    else:
        v.fail(f"unexpected initial graduation progress: {progress.get('statusSummary')}")

    if progress.get("totalRequiredCredits") == 155:
        v.ok("graduation totalRequiredCredits=155 (DDS production program)")
    else:
        v.warn(f"totalRequiredCredits={progress.get('totalRequiredCredits')} (expected 155 for DDS)")

    req_progress = progress.get("requirementProgress") or []
    ds_buckets = [x for x in req_progress if str(x.get("requirementGroupId", "")).endswith(":elective-ds")]
    faculty_buckets = [x for x in req_progress if "elective-faculty" in str(x.get("requirementGroupId", ""))]
    if ds_buckets and ds_buckets[0].get("eligibilityEnforcement") == "strict_pool":
        v.ok("elective-ds bucket uses strict_pool enforcement (Phase 15.0)")
    else:
        v.warn("elective-ds strict_pool not confirmed — check pool promotion data")

    if faculty_buckets and faculty_buckets[0].get("eligibilityEnforcement") == "strict_pool":
        v.ok("elective-faculty bucket uses strict_pool enforcement (Phase 15.0)")
    else:
        v.warn("elective-faculty strict_pool not confirmed")

    if progress.get("assumptions"):
        v.ok("graduation response includes assumptions[]")
    else:
        v.fail("graduation assumptions[] missing")

    if course_id:
        await v.request(
            client,
            "POST",
            "/completed-courses",
            token=grad_token,
            json_body={
                "courseId": course_id,
                "semesterCode": "2024-1",
                "grade": 82,
                "creditsEarned": 2,
                "attempt": 1,
            },
            expected=201,
            label="graduation completed course add",
        )

        r2 = await v.request(
            client,
            "GET",
            "/graduation-progress",
            token=grad_token,
            expected=200,
            label="graduation after completed course",
        )
        after = r2.json()["data"]["graduationProgress"]
        if after.get("completedCredits", 0) >= 2:
            v.ok(f"graduation completedCredits={after.get('completedCredits')} after course add")
        else:
            v.fail(f"graduation credits not updated: {after.get('completedCredits')}")

        if after.get("statusSummary") in {"in_progress", "not_started"}:
            v.ok(f"graduation statusSummary={after.get('statusSummary')} after partial progress")
        else:
            v.warn(f"unexpected status after one course: {after.get('statusSummary')}")

    await v.request(
        client,
        "DELETE",
        "/student-profile",
        token=grad_token,
        expected=200,
        label="graduation profile cleanup",
    )


async def run_semester_plans(
    v: Verifier,
    client: httpx.AsyncClient,
    *,
    degree_program_id: str | None,
    semester_one_course_id: str | None,
    semester_one_course_number: str | None,
    semester_one_matrix_numbers: list[str],
) -> None:
    """Phase 16 — semester planner E2E using live production semester_matrix rules."""
    if not degree_program_id:
        v.warn("skipping semester plan Docker tests — no degree_programs._id resolved")
        return

    if not semester_one_matrix_numbers:
        v.warn("skipping semester plan matrix assertions — no semester-1 matrix courses in Mongo")
        return

    plan_email = f"plan-verify-{uuid.uuid4().hex[:8]}@example.com"
    reg = await v.request(
        client,
        "POST",
        "/auth/register",
        json_body={"email": plan_email, "password": PASSWORD},
        expected=201,
        label="semester plan user register",
    )
    if reg.status_code != 201:
        v.fail("semester plan user register failed — skipping remaining semester plan E2E")
        return
    plan_token = reg.json()["data"]["accessToken"]

    await v.request(
        client,
        "GET",
        "/semester-plans",
        token=plan_token,
        expected=200,
        label="semester plan list without profile (empty history)",
    )

    await v.request(
        client,
        "POST",
        "/semester-plans/generate",
        token=plan_token,
        json_body={"semesterCode": "2025-2"},
        expected=404,
        label="semester plan generate without profile",
    )

    await v.request(
        client,
        "POST",
        "/student-profile",
        token=plan_token,
        json_body={
            "institutionId": "technion",
            "programType": "BSc",
            "degreeId": degree_program_id,
            "catalogYear": 2025,
            "currentSemesterCode": "2025-1",
            "preferences": {"maxCreditsPerSemester": 18},
        },
        expected=201,
        label="semester plan profile with degreeId",
    )

    gen = await v.request(
        client,
        "POST",
        "/semester-plans/generate",
        token=plan_token,
        json_body={"semesterCode": "2025-2", "maxCredits": 12},
        expected=201,
        label="semester plan generate",
    )
    plan = gen.json()["data"]["semesterPlan"]
    assumptions = plan.get("assumptions") or {}
    explanation = plan.get("explanation") or {}

    if plan.get("plannerType") == "deterministic":
        v.ok("semester plan plannerType=deterministic")
    else:
        v.fail(f"semester plan plannerType unexpected: {plan.get('plannerType')}")

    if assumptions.get("mandatorySource") == "semester_matrix":
        v.ok("semester plan mandatorySource=semester_matrix (catalog table)")
    else:
        v.fail(f"semester plan mandatorySource unexpected: {assumptions.get('mandatorySource')}")

    matrix_rule_count = int(assumptions.get("semesterMatrixRuleCount") or 0)
    if matrix_rule_count >= 1:
        v.ok(f"semester plan loaded semesterMatrixRuleCount={matrix_rule_count}")
    else:
        v.fail("semester plan semesterMatrixRuleCount missing or zero")

    if explanation.get("rulesApplied") and any(
        "semester matrix" in rule.lower() for rule in explanation["rulesApplied"]
    ):
        v.ok("semester plan rulesApplied mentions semester matrix")
    else:
        v.fail("semester plan rulesApplied missing semester matrix rule")

    planned = (plan.get("semesters") or [{}])[0].get("plannedCourses") or []
    planned_numbers = [course.get("courseNumber") for course in planned]
    if planned:
        v.ok(f"semester plan recommended {len(planned)} course(s)")
    else:
        v.warn("semester plan returned empty plannedCourses on fresh transcript")

    matrix_hits = [number for number in planned_numbers if number in semester_one_matrix_numbers]
    if matrix_hits:
        v.ok(f"semester plan includes semester-1 matrix courses: {matrix_hits[:3]}")
    elif planned:
        v.warn(
            f"semester plan courses {planned_numbers[:5]} did not intersect semester-1 matrix "
            f"{semester_one_matrix_numbers[:5]} — may be blocked by prerequisites/workload"
        )

    if planned and all(course.get("category") == "mandatory" for course in planned):
        v.ok("semester plan initial recommendations are mandatory (matrix-sourced)")
    elif planned:
        v.warn("semester plan mixed mandatory/elective on first generate")

    plan_id = plan.get("id")
    if not plan_id:
        v.fail("semester plan missing id")
        return

    await v.request(
        client,
        "GET",
        "/semester-plans",
        token=plan_token,
        expected=200,
        label="semester plan list",
    )

    get_resp = await v.request(
        client,
        "GET",
        f"/semester-plans/{plan_id}",
        token=plan_token,
        expected=200,
        label="semester plan get by id",
    )
    if get_resp.json()["data"]["semesterPlan"]["id"] == plan_id:
        v.ok("semester plan get returns same id")
    else:
        v.fail("semester plan get id mismatch")

    await v.request(
        client,
        "POST",
        "/semester-plans/generate",
        token=plan_token,
        json_body={"semesterCode": "2025-2", "maxCredits": 12, "userId": "evil"},
        expected=400,
        label="semester plan rejects unknown field",
    )

    await v.request(
        client,
        "POST",
        "/semester-plans/generate",
        token=plan_token,
        json_body={"semesterCode": "2025-3", "maxCredits": 6},
        expected=400,
        label="semester plan rejects invalid semesterCode",
    )

    if semester_one_course_id and semester_one_course_number:
        await v.request(
            client,
            "POST",
            "/completed-courses",
            token=plan_token,
            json_body={
                "courseId": semester_one_course_id,
                "semesterCode": "2024-1",
                "grade": 85,
                "creditsEarned": 4,
                "attempt": 1,
            },
            expected=201,
            label="semester plan completed matrix course",
        )

        regen = await v.request(
            client,
            "POST",
            "/semester-plans/generate",
            token=plan_token,
            json_body={"semesterCode": "2025-2", "maxCredits": 12, "name": "After completion"},
            expected=201,
            label="semester plan regenerate after completion",
        )
        regen_plan = regen.json()["data"]["semesterPlan"]
        regen_numbers = [
            course.get("courseNumber")
            for course in (regen_plan.get("semesters") or [{}])[0].get("plannedCourses") or []
        ]
        if semester_one_course_number not in regen_numbers:
            v.ok(f"completed matrix course {semester_one_course_number} excluded from replan")
        else:
            v.fail(
                f"completed matrix course {semester_one_course_number} still recommended after completion"
            )

    await v.request(
        client,
        "DELETE",
        "/student-profile",
        token=plan_token,
        expected=200,
        label="semester plan profile cleanup",
    )


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
            "grade": 82,
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
        json_body={"grade": 95},
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
            "grade": 82,
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
        ("graduation_progress", "GET", "/graduation-progress", token, None, 50),
        ("completed_list", "GET", "/completed-courses", token, None, 50),
        (
            "semester_plan_generate",
            "POST",
            "/semester-plans/generate",
            token,
            {"semesterCode": "2025-2", "maxCredits": 12},
            20,
        ),
        ("semester_plan_list", "GET", "/semester-plans", token, None, 30),
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
    from pathlib import Path

    repo_root = Path(__file__).resolve().parents[3]

    mongo_eval = (
        'const out={};'
        'const c=db.courses.findOne({courseNumber:"00104000",status:"published"});'
        'if(c) out.courseId=c._id.toString();'
        'const p=db.degree_programs.findOne({programCode:"009216-1-000",status:"published"});'
        'if(p) out.degreeProgramId=p._id.toString();'
        'const m=db.catalog_rules.findOne({programCode:"009216-1-000",'
        '"ruleExpression.type":"semester_matrix","requirementGroupId":/semester-1-matrix/});'
        'if(m){'
        '  out.semesterOneMatrixNumbers=(m.courseReferences||[]).map(r=>r.courseNumber).filter(Boolean);'
        '  const first=(m.courseReferences||[]).find(r=>r.courseNumber);'
        '  if(first){'
        '    const mc=db.courses.findOne({courseNumber:first.courseNumber,status:"published"});'
        '    if(mc){ out.semesterOneCourseId=mc._id.toString(); out.semesterOneCourseNumber=first.courseNumber; }'
        '  }'
        '}'
        'const matrixCount=db.catalog_rules.countDocuments({programCode:"009216-1-000",'
        '"ruleExpression.type":"semester_matrix",status:"published"});'
        'out.semesterMatrixRuleCount=matrixCount;'
        'print(JSON.stringify(out));'
    )

    proc_mongo = subprocess.run(
        [
            "docker", "compose", "exec", "-T", "mongo",
            "mongosh", "-u", "unipilot", "-p", "unipilot_dev_password",
            "--authenticationDatabase", "admin", "unipilot_python", "--quiet",
            "--eval",
            mongo_eval,
        ],
        capture_output=True,
        text=True,
        cwd=str(repo_root),
    )
    mongo_bootstrap = json.loads(proc_mongo.stdout.strip() or "{}")
    course_id = mongo_bootstrap.get("courseId")
    degree_program_id = mongo_bootstrap.get("degreeProgramId")
    semester_one_course_id = mongo_bootstrap.get("semesterOneCourseId")
    semester_one_course_number = mongo_bootstrap.get("semesterOneCourseNumber")
    semester_one_matrix_numbers = mongo_bootstrap.get("semesterOneMatrixNumbers") or []

    if not course_id:
        print("WARN: could not resolve course ObjectId from Mongo; skipping completed-course Docker tests")
    if not degree_program_id:
        print("WARN: could not resolve degree_programs._id from Mongo; skipping graduation/semester plan tests")
    if mongo_bootstrap.get("semesterMatrixRuleCount", 0) == 0:
        print("WARN: no semester_matrix catalog rules in Mongo; semester plan matrix E2E may be limited")
    else:
        print(
            f"INFO: found {mongo_bootstrap.get('semesterMatrixRuleCount')} semester_matrix rules; "
            f"semester-1 courses sample: {semester_one_matrix_numbers[:5]}"
        )

    v = Verifier()
    async with httpx.AsyncClient(base_url=BASE_URL, timeout=30.0) as client:
        await run_functional_verification(v, client)
        if course_id:
            await run_completed_courses(v, client, course_id)
        await run_graduation_progress(
            v,
            client,
            degree_program_id=degree_program_id or None,
            course_id=course_id or None,
        )
        await run_semester_plans(
            v,
            client,
            degree_program_id=degree_program_id or None,
            semester_one_course_id=semester_one_course_id,
            semester_one_course_number=semester_one_course_number,
            semester_one_matrix_numbers=semester_one_matrix_numbers,
        )

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
            # Ensure benchmark user can hit graduation + semester plan endpoints
            profile_resp = await client.get("/student-profile", headers={"Authorization": f"Bearer {bench_token}"})
            if profile_resp.status_code == 404:
                if degree_program_id:
                    await client.post(
                        "/student-profile",
                        headers={"Authorization": f"Bearer {bench_token}"},
                        json={
                            "institutionId": "technion",
                            "programType": "BSc",
                            "degreeId": degree_program_id,
                            "catalogYear": 2025,
                            "currentSemesterCode": "2025-1",
                        },
                    )
            bench_results = await run_benchmarks(client, bench_token)

    # Mongo integrity counts
    proc2 = subprocess.run(
        [
            "docker", "compose", "exec", "-T", "mongo",
            "mongosh", "-u", "unipilot", "-p", "unipilot_dev_password",
            "--authenticationDatabase", "admin", "unipilot_python", "--quiet",
            "--eval",
            'print(JSON.stringify({courses:db.courses.countDocuments(),offerings:db.course_offerings.countDocuments(),programs:db.degree_programs.countDocuments(),requirements:db.degree_requirements.countDocuments(),rules:db.catalog_rules.countDocuments(),semesterMatrixRules:db.catalog_rules.countDocuments({"programCode":"009216-1-000","ruleExpression.type":"semester_matrix",status:"published"}),semesterPlans:db.semester_plans.countDocuments(),completed:db.completed_courses.countDocuments()}))',
        ],
        capture_output=True,
        text=True,
        cwd=str(repo_root),
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
    report_path = repo_root / "services" / "api-python" / "scripts" / "verify_report.json"
    with open(report_path, "w", encoding="utf-8") as f:
        json.dump(report, f, indent=2, ensure_ascii=False)
    print(f"\nFull report written to {report_path}")

    return 1 if v.failed else 0


if __name__ == "__main__":
    sys.exit(asyncio.run(main()))
