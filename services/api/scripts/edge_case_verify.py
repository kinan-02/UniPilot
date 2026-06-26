#!/usr/bin/env python3
"""Live edge-case verification against Docker API + MongoDB."""

from __future__ import annotations

import asyncio
import json
import sys
import uuid
from dataclasses import dataclass, field
from datetime import datetime, timezone
from pathlib import Path

import httpx

BASE_URL = "http://localhost:8000"
PASSWORD = "StrongPass123!"
REFRESH_TOKEN_COOKIE = "unipilot_refresh_token"
REPORT_PATH = Path(__file__).with_name("edge_case_verify_report.json")


@dataclass
class EdgeVerifier:
    base_url: str = BASE_URL
    token: str | None = None
    passed: list[str] = field(default_factory=list)
    failed: list[str] = field(default_factory=list)

    def ok(self, label: str) -> None:
        self.passed.append(label)
        print(f"  PASS  {label}")

    def fail(self, label: str, detail: str) -> None:
        self.failed.append(f"{label}: {detail}")
        print(f"  FAIL  {label} — {detail}")

    async def request(
        self,
        client: httpx.AsyncClient,
        method: str,
        path: str,
        *,
        expected: int | set[int],
        label: str,
        json_body: dict | None = None,
        token: str | None = None,
        cookies: dict[str, str] | None = None,
    ) -> httpx.Response:
        headers = {}
        if token or self.token:
            headers["Authorization"] = f"Bearer {token or self.token}"
        response = await client.request(
            method,
            path,
            json=json_body,
            headers=headers,
            cookies=cookies or None,
        )
        expected_set = {expected} if isinstance(expected, int) else set(expected)
        if response.status_code in expected_set:
            self.ok(label)
        else:
            self.fail(label, f"expected {sorted(expected_set)}, got {response.status_code}")
        return response

    def _extract_cookie(self, response: httpx.Response, name: str) -> str | None:
        for header in response.headers.get_list("set-cookie"):
            if header.startswith(f"{name}="):
                value = header.split("=", 1)[1].split(";", 1)[0]
                return value
        return response.cookies.get(name)

    async def run(self) -> int:
        print(f"Edge-case verify @ {self.base_url}")
        async with httpx.AsyncClient(base_url=self.base_url, timeout=30.0) as client:
            health = await client.get("/health")
            if health.status_code != 200:
                self.fail("health", str(health.status_code))
                return 1
            self.ok("health ok")

            # Empty catalog (fresh DB or after wipe)
            await self.request(client, "GET", "/catalog/courses?limit=5", expected=401, label="catalog unauthenticated")

            email = f"edge-{uuid.uuid4().hex[:10]}@example.com"
            reg = await self.request(
                client,
                "POST",
                "/auth/register",
                expected=201,
                label="register",
                json_body={"email": email, "password": PASSWORD},
            )
            if reg.status_code != 201:
                return 1
            self.token = reg.json()["data"]["accessToken"]

            empty = await self.request(
                client,
                "GET",
                "/catalog/courses?limit=5",
                expected=200,
                label="empty catalog list",
            )
            if empty.status_code == 200:
                total = empty.json()["data"]["total"]
                if total == 0:
                    self.ok("empty catalog total=0")
                else:
                    self.ok(f"catalog populated total={total}")

            await self.request(
                client,
                "GET",
                "/catalog/courses?limit=10&offset=999999",
                expected=200,
                label="offset beyond total",
            )

            for query, label in [
                ("limit=0", "catalog limit=0 rejected"),
                ("offset=-1", "catalog offset=-1 rejected"),
                ("limit=201", "catalog limit=201 rejected"),
            ]:
                await self.request(
                    client,
                    "GET",
                    f"/catalog/courses?{query}",
                    expected=400,
                    label=label,
                )

            refresh_email = f"edge-refresh-{uuid.uuid4().hex[:10]}@example.com"
            refresh_reg = await client.post(
                "/auth/register",
                json={"email": refresh_email, "password": PASSWORD},
            )
            if refresh_reg.status_code == 201:
                old_refresh = self._extract_cookie(refresh_reg, REFRESH_TOKEN_COOKIE)
                if old_refresh:
                    first_refresh = await client.post(
                        "/auth/refresh",
                        cookies={REFRESH_TOKEN_COOKIE: old_refresh},
                    )
                    if first_refresh.status_code == 200:
                        self.ok("refresh rotation succeeds")
                        reuse = await client.post(
                            "/auth/refresh",
                            cookies={REFRESH_TOKEN_COOKIE: old_refresh},
                        )
                        if reuse.status_code == 401:
                            self.ok("refresh reuse rejected")
                        else:
                            self.fail("refresh reuse rejected", f"got {reuse.status_code}")
                    else:
                        self.fail("refresh rotation succeeds", f"got {first_refresh.status_code}")
                else:
                    self.fail("refresh cookie present", "missing refresh cookie on register")
            else:
                self.fail("refresh register", f"got {refresh_reg.status_code}")

            await self.request(client, "GET", "/catalog/courses/123", expected=400, label="invalid course number")
            await self.request(client, "GET", "/catalog/courses/00999999", expected=404, label="missing course")
            await self.request(
                client,
                "GET",
                "/catalog/degree-programs/bad-code/requirements",
                expected=400,
                label="invalid program code",
            )
            await self.request(
                client,
                "GET",
                "/catalog/offerings?courseNumbers=,,",
                expected=400,
                label="empty batch offerings",
            )
            await self.request(
                client,
                "GET",
                "/catalog/courses?academicYear=2025",
                expected=400,
                label="semester pair incomplete",
            )
            await self.request(
                client,
                "GET",
                "/catalog/courses?q=__no_match_xyz__",
                expected=200,
                label="search no match",
            )
            await self.request(client, "GET", "/graduation-progress", expected=404, label="graduation no profile")
            await self.request(
                client,
                "POST",
                "/semester-plans/generate",
                expected=404,
                label="plan generate no profile",
                json_body={"semesterCode": "2025-1"},
            )
            await self.request(
                client,
                "POST",
                "/auth/register",
                expected=400,
                label="weak password rejected",
                json_body={"email": f"weak-{uuid.uuid4().hex[:6]}@example.com", "password": "x"},
            )

            profile_email = f"edge-profile-{uuid.uuid4().hex[:10]}@example.com"
            profile_reg = await self.request(
                client,
                "POST",
                "/auth/register",
                expected=201,
                label="profile edge user register",
                json_body={"email": profile_email, "password": PASSWORD},
            )
            profile_token = (
                profile_reg.json()["data"]["accessToken"] if profile_reg.status_code == 201 else None
            )

            await self.request(
                client,
                "POST",
                "/student-profile",
                expected=201,
                label="student profile create",
                token=profile_token,
                json_body={
                    "institutionId": "technion",
                    "programType": "BSc",
                    "catalogYear": 2025,
                    "currentSemesterCode": "2025-1",
                },
            )
            await self.request(
                client,
                "POST",
                "/student-profile",
                expected=409,
                label="duplicate student profile rejected",
                token=profile_token,
                json_body={
                    "institutionId": "technion",
                    "programType": "BSc",
                    "catalogYear": 2025,
                    "currentSemesterCode": "2025-1",
                },
            )

            degree_email = f"edge-degree-{uuid.uuid4().hex[:10]}@example.com"
            degree_reg = await self.request(
                client,
                "POST",
                "/auth/register",
                expected=201,
                label="degree edge user register",
                json_body={"email": degree_email, "password": PASSWORD},
            )
            degree_token = (
                degree_reg.json()["data"]["accessToken"] if degree_reg.status_code == 201 else None
            )
            await self.request(
                client,
                "POST",
                "/student-profile",
                expected=400,
                label="invalid degreeId format rejected",
                token=degree_token,
                json_body={
                    "institutionId": "technion",
                    "programType": "BSc",
                    "catalogYear": 2025,
                    "currentSemesterCode": "2025-1",
                    "degreeId": "not-a-valid-object-id",
                },
            )
            await self.request(
                client,
                "POST",
                "/student-profile",
                expected=400,
                label="missing degree program rejected",
                token=degree_token,
                json_body={
                    "institutionId": "technion",
                    "programType": "BSc",
                    "catalogYear": 2025,
                    "currentSemesterCode": "2025-1",
                    "degreeId": "665f2b0f2a3f7b2a1a9a7fff",
                },
            )

            # If catalog is populated, verify excluded course and dedupe invariants
            progs = await client.get(
                "/catalog/degree-programs",
                headers={"Authorization": f"Bearer {self.token}"},
            )
            prog_data = progs.json().get("data") or {} if progs.status_code == 200 else {}
            prog_items = prog_data.get("items") or []
            prog_total = prog_data.get("total", len(prog_items))
            if progs.status_code == 200 and prog_total >= 1:
                await self.request(client, "GET", "/catalog/courses/00960226", expected=404, label="excluded course")
                items = prog_items
                adv = hard = 0
                for p in items:
                    code = p["programCode"]
                    ar = await client.get(
                        f"/catalog/degree-programs/{code}/advisory-rules",
                        headers={"Authorization": f"Bearer {self.token}"},
                    )
                    hr = await client.get(
                        f"/catalog/degree-programs/{code}/requirements",
                        headers={"Authorization": f"Bearer {self.token}"},
                    )
                    adv += len(ar.json()["data"]["advisoryRules"])
                    hard += len(hr.json()["data"]["requirements"])
                if adv > 0 and hard > 0:
                    self.ok(f"catalog advisory/hard totals {adv}/{hard}")
                elif adv == 0 and hard == 0:
                    self.ok("catalog programs without requirements yet")
                else:
                    self.fail("advisory/hard totals", f"got {adv}/{hard}")

        report = {
            "generated_at": datetime.now(timezone.utc).isoformat(),
            "base_url": self.base_url,
            "passed": len(self.passed),
            "failed": len(self.failed),
            "failures": self.failed,
            "checks_passed": self.passed,
        }
        REPORT_PATH.write_text(json.dumps(report, indent=2), encoding="utf-8")
        print(f"\nReport: {REPORT_PATH}")
        print(f"Summary: {len(self.passed)} passed, {len(self.failed)} failed")
        return 1 if self.failed else 0


def main() -> int:
    return asyncio.run(EdgeVerifier().run())


if __name__ == "__main__":
    sys.exit(main())
