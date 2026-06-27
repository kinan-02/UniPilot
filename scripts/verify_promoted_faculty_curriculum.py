#!/usr/bin/env python3
"""Verify promoted faculty curriculum: progress buckets/pools + semester plan generation."""

from __future__ import annotations

import argparse
import json
import os
import subprocess
import sys
import uuid
from dataclasses import dataclass, field
from pathlib import Path

import httpx

REPO_ROOT = Path(__file__).resolve().parents[1]
PASSWORD = "StrongPass123!"


def _resolve_base_url() -> str:
    port = os.environ.get("API_PORT")
    if not port:
        env_file = REPO_ROOT / ".env"
        if env_file.is_file():
            for line in env_file.read_text(encoding="utf-8").splitlines():
                if line.startswith("API_PORT="):
                    port = line.split("=", 1)[1].strip()
                    break
    return f"http://{os.environ.get('API_HOST', 'localhost')}:{port or '8000'}"


def _flush_auth_rate_limits() -> None:
    scan = subprocess.run(
        [
            "docker",
            "compose",
            "exec",
            "-T",
            "redis",
            "redis-cli",
            "--scan",
            "--pattern",
            "rl:auth:*",
        ],
        capture_output=True,
        text=True,
        cwd=str(REPO_ROOT),
    )
    keys = [line.strip() for line in scan.stdout.splitlines() if line.strip()]
    if not keys:
        return
    subprocess.run(
        ["docker", "compose", "exec", "-T", "redis", "redis-cli", "DEL", *keys],
        capture_output=True,
        text=True,
        cwd=str(REPO_ROOT),
        check=False,
    )


@dataclass
class FacultyCheckResult:
    faculty_id: str
    track_slug: str
    program_code: str | None
    blockers: list[str] = field(default_factory=list)
    warnings: list[str] = field(default_factory=list)

    @property
    def ok(self) -> bool:
        return not self.blockers


def _register(client: httpx.Client, base_url: str) -> str:
    email = f"verify-curriculum-{uuid.uuid4().hex[:10]}@example.com"
    response = client.post(
        f"{base_url}/auth/register",
        json={"email": email, "password": PASSWORD},
    )
    if response.status_code != 201:
        raise RuntimeError(f"register failed ({response.status_code}): {response.text[:300]}")
    return response.json()["data"]["accessToken"]


def _matrix_rich_primary_track(
    client: httpx.Client,
    base_url: str,
    token: str,
    faculty_id: str,
) -> dict | None:
    headers = {"Authorization": f"Bearer {token}"}
    options_response = client.get(
        f"{base_url}/catalog/path-options",
        headers=headers,
        params={"facultyId": faculty_id, "programType": "BSc", "primaryOnly": True},
    )
    if options_response.status_code != 200:
        raise RuntimeError(
            f"path-options failed for {faculty_id} ({options_response.status_code}): "
            f"{options_response.text[:300]}"
        )

    best: dict | None = None
    best_matrix_count = -1
    for option in options_response.json()["data"]["items"]:
        program_code = option.get("linkedProgramCode")
        if not program_code or not option.get("linkedDegreeProgramId"):
            continue
        summary_response = client.get(
            f"{base_url}/catalog/degree-programs/{program_code}/catalog-summary",
            headers=headers,
        )
        if summary_response.status_code != 200:
            continue
        summary = summary_response.json()["data"]["catalogSummary"]
        program = summary.get("program") or {}
        metadata = program.get("metadata") or {}
        canonical_track = (
            option.get("curriculumWikiSlug")
            or (program.get("metadata") or {}).get("wikiPage")
            or option.get("wikiSlug")
        )
        profile_track_slug = option.get("wikiSlug") or canonical_track
        advisory_rules = summary["advisoryRules"]
        matrix_count = sum(
            1
            for rule in advisory_rules
            if "semester-" in str(rule.get("requirementGroupId", ""))
        )
        if matrix_count > best_matrix_count:
            best_matrix_count = matrix_count
            best = {
                "facultyId": faculty_id,
                "wikiSlug": profile_track_slug,
                "curriculumWikiSlug": canonical_track,
                "linkedDegreeProgramId": option.get("linkedDegreeProgramId"),
                "linkedProgramCode": program_code,
                "matrixCount": matrix_count,
            }
    return best


def _discover_primary_tracks(client: httpx.Client, base_url: str, token: str) -> list[dict]:
    headers = {"Authorization": f"Bearer {token}"}
    faculties_response = client.get(
        f"{base_url}/catalog/academic-faculties",
        headers=headers,
        params={"programType": "BSc", "withPathOptionsOnly": True},
    )
    if faculties_response.status_code != 200:
        raise RuntimeError(
            f"academic-faculties failed ({faculties_response.status_code}): "
            f"{faculties_response.text[:300]}"
        )

    tracks: list[dict] = []
    for faculty in faculties_response.json()["data"]["items"]:
        faculty_id = faculty["facultyId"]
        primary = _matrix_rich_primary_track(client, base_url, token, faculty_id)
        if primary is None:
            tracks.append(
                {
                    "facultyId": faculty_id,
                    "wikiSlug": None,
                    "linkedDegreeProgramId": None,
                    "linkedProgramCode": None,
                    "matrixCount": 0,
                }
            )
        else:
            tracks.append(primary)
    return tracks


def _verify_faculty(
    client: httpx.Client,
    base_url: str,
    *,
    faculty_id: str,
    track_slug: str | None,
    degree_id: str | None,
    program_code: str | None,
) -> FacultyCheckResult:
    result = FacultyCheckResult(
        faculty_id=faculty_id,
        track_slug=track_slug or "",
        program_code=program_code,
    )
    if not track_slug or not degree_id:
        result.blockers.append("no primary BSc track with linked degree program")
        return result

    token = _register(client, base_url)
    headers = {"Authorization": f"Bearer {token}"}
    profile_track = track_slug
    profile_response = client.post(
        f"{base_url}/student-profile",
        headers=headers,
        json={
            "institutionId": "technion",
            "programType": "BSc",
            "degreeId": degree_id,
            "catalogYear": 2025,
            "currentSemesterCode": "2025-1",
            "academicPath": {"trackSlug": profile_track},
        },
    )
    if profile_response.status_code not in {200, 201}:
        result.blockers.append(
            f"profile onboarding failed ({profile_response.status_code}): "
            f"{profile_response.text[:200]}"
        )
        return result

    progress_response = client.get(f"{base_url}/graduation-progress", headers=headers)
    if progress_response.status_code != 200:
        result.blockers.append(f"graduation-progress failed ({progress_response.status_code})")
        return result
    progress = progress_response.json()["data"]["graduationProgress"]
    buckets = progress.get("requirementProgress") or []
    if not buckets:
        result.blockers.append("graduation-progress returned no requirement buckets")
    elif len(buckets) < 3:
        result.warnings.append(f"graduation-progress returned only {len(buckets)} buckets")

    graph_response = client.get(f"{base_url}/graduation-progress/curriculum-graph", headers=headers)
    if graph_response.status_code != 200:
        result.blockers.append(f"curriculum-graph failed ({graph_response.status_code})")
        return result
    graph = graph_response.json()["data"]["curriculumGraph"]
    semester_lanes = graph.get("semesterLanes") or []
    elective_buckets = graph.get("electiveBuckets") or []
    if not semester_lanes:
        result.blockers.append("curriculum graph has no semester lanes (matrices missing)")
    if not elective_buckets:
        result.blockers.append("curriculum graph has no elective pools")

    plan_response = client.post(
        f"{base_url}/semester-plans/generate",
        headers=headers,
        json={"semesterCode": "2025-2", "maxCredits": 12},
    )
    if plan_response.status_code != 201:
        result.blockers.append(f"semester-plans/generate failed ({plan_response.status_code})")
        return result

    plan = plan_response.json()["data"]["semesterPlan"]
    planned = (plan.get("semesters") or [{}])[0].get("plannedCourses") or []
    explanation = plan.get("explanation") or {}
    if not planned:
        result.blockers.append("semester plan generated with zero planned courses")
    elif explanation.get("partialPlan") and len(planned) == 0:
        result.blockers.append("semester plan is partial-only with no courses")

    return result


def run_verification(*, base_url: str, faculty_filter: str | None = None) -> int:
    _flush_auth_rate_limits()
    results: list[FacultyCheckResult] = []

    with httpx.Client(timeout=60.0) as client:
        health = client.get(f"{base_url}/health")
        if health.status_code != 200:
            print(f"API health check failed ({health.status_code})", file=sys.stderr)
            return 2

        token = _register(client, base_url)
        tracks = _discover_primary_tracks(client, base_url, token)
        if faculty_filter:
            tracks = [track for track in tracks if track["facultyId"] == faculty_filter]
            if not tracks:
                print(f"No faculty matched filter: {faculty_filter}", file=sys.stderr)
                return 2

        for track in tracks:
            if track.get("matrixCount", 0) == 0 and track.get("wikiSlug"):
                results.append(
                    FacultyCheckResult(
                        faculty_id=track["facultyId"],
                        track_slug=track.get("wikiSlug") or "",
                        program_code=track.get("linkedProgramCode"),
                        blockers=["no semester matrices on any primary BSc track"],
                    )
                )
                continue
            result = _verify_faculty(
                client,
                base_url,
                faculty_id=track["facultyId"],
                track_slug=track.get("wikiSlug"),
                degree_id=track.get("linkedDegreeProgramId"),
                program_code=track.get("linkedProgramCode"),
            )
            results.append(result)

    failed = [result for result in results if not result.ok]
    for result in results:
        status = "OK" if result.ok else "FAIL"
        line = (
            f"[{status}] {result.faculty_id} track={result.track_slug} "
            f"program={result.program_code or 'n/a'}"
        )
        if result.warnings:
            line += f" warnings={'; '.join(result.warnings)}"
        if result.blockers:
            line += f" blockers={'; '.join(result.blockers)}"
        print(line)

    summary = {
        "checked": len(results),
        "passed": len(results) - len(failed),
        "failed": len(failed),
        "failures": [
            {
                "facultyId": result.faculty_id,
                "trackSlug": result.track_slug,
                "programCode": result.program_code,
                "blockers": result.blockers,
                "warnings": result.warnings,
            }
            for result in failed
        ],
    }
    print(json.dumps(summary, indent=2, ensure_ascii=False))
    return 1 if failed else 0


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--base-url",
        default=_resolve_base_url(),
        help="API base URL (default: from API_PORT / .env)",
    )
    parser.add_argument(
        "--faculty-id",
        default=None,
        help="Verify a single facultyId (default: all promoted faculties with BSc tracks)",
    )
    args = parser.parse_args()
    return run_verification(base_url=args.base_url.rstrip("/"), faculty_filter=args.faculty_id)


if __name__ == "__main__":
    raise SystemExit(main())
