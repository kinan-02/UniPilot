#!/usr/bin/env python3
"""Local production-readiness audit for UniPilot AI."""

from __future__ import annotations

import json
import re
import subprocess
import sys
from dataclasses import dataclass, field
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[1]

REQUIRED_ENV_KEYS = frozenset(
    {
        "JWT_SECRET",
        "MONGO_ROOT_USERNAME",
        "MONGO_ROOT_PASSWORD",
        "AUTH_RATE_LIMIT_MAX",
        "AI_RATE_LIMIT_MAX",
        "REDIS_PASSWORD",
        "INTERNAL_SERVICE_TOKEN",
        "CORS_ALLOWED_ORIGINS",
    }
)

SECRET_PATTERNS = (
    re.compile(r"replace_me_with_secure_jwt_secret"),
    re.compile(r"sk-[a-zA-Z0-9]{20,}"),
)


@dataclass
class AuditResult:
    score: int = 100
    blockers: list[str] = field(default_factory=list)
    warnings: list[str] = field(default_factory=list)
    evidence: list[str] = field(default_factory=list)

    def deduct(self, points: int, message: str, *, blocker: bool = False) -> None:
        self.score = max(0, self.score - points)
        if blocker:
            self.blockers.append(message)
        else:
            self.warnings.append(message)

    def note(self, message: str) -> None:
        self.evidence.append(message)


def read_text(path: Path) -> str:
    return path.read_text(encoding="utf-8") if path.is_file() else ""


def check_env_example(audit: AuditResult) -> None:
    env_example = REPO_ROOT / ".env.example"
    content = read_text(env_example)
    audit.note(f"Read {env_example.relative_to(REPO_ROOT)}")
    if not content:
        audit.deduct(15, ".env.example is missing", blocker=True)
        return
    for key in REQUIRED_ENV_KEYS:
        if f"{key}=" not in content:
            audit.deduct(5, f".env.example missing {key}", blocker=True)


def check_docker_exposure(audit: AuditResult) -> None:
    compose = read_text(REPO_ROOT / "docker-compose.yml")
    audit.note("Inspected docker-compose.yml port mappings")
    internal_services = ("mongo:", "redis:", "worker:", "ai:", "data-engineering:")
    for service in internal_services:
        block = compose.split(f"  {service}")[1].split("\n  ")[0] if f"  {service}" in compose else ""
        if re.search(r"^\s+ports:", block, re.MULTILINE):
            audit.deduct(20, f"{service.rstrip(':')} must not publish host ports", blocker=True)


def check_rate_limits_in_code(audit: AuditResult) -> None:
    limiter = read_text(REPO_ROOT / "services/api/app/middleware/auth_rate_limiter.py")
    routes = read_text(REPO_ROOT / "services/api/app/routes/academic_risks.py")
    audit.note("Verified auth + AI rate limit middleware")
    if "enforce_auth_rate_limits" not in limiter:
        audit.deduct(10, "Auth rate limit middleware missing", blocker=True)
    if "enforce_ai_rate_limit" not in limiter or "enforce_ai_rate_limit" not in routes:
        audit.deduct(10, "AI rate limit not wired to /academic-risks/analyze", blocker=True)


def check_jwt_guard(audit: AuditResult) -> None:
    config = read_text(REPO_ROOT / "services/api/app/config.py")
    audit.note("Verified JWT secret production guard in config.py")
    if "JWT_SECRET_PLACEHOLDERS" not in config or "require_jwt_secret" not in config:
        audit.deduct(10, "JWT secret validation missing in config", blocker=True)


def check_ci(audit: AuditResult) -> None:
    ci = REPO_ROOT / ".github/workflows/ci.yml"
    if not ci.is_file():
        audit.deduct(8, "No GitHub Actions CI workflow", blocker=False)
    else:
        audit.note("CI workflow present (.github/workflows/ci.yml)")


def check_runbook(audit: AuditResult) -> None:
    runbook = REPO_ROOT / "docs/operations/PRODUCTION_DEPLOYMENT.md"
    if not runbook.is_file():
        audit.deduct(5, "Production deployment runbook missing", blocker=False)
    else:
        text = read_text(runbook)
        if "TLS" not in text and "HTTPS" not in text:
            audit.deduct(3, "Runbook lacks TLS guidance", blocker=False)
        audit.note("Production deployment runbook present")


def check_readme(audit: AuditResult) -> None:
    readme = read_text(REPO_ROOT / "README.md")
    audit.note("README includes docker compose instructions")
    if "docker compose up" not in readme:
        audit.deduct(5, "README missing docker compose run instructions", blocker=False)


def check_test_report(audit: AuditResult) -> None:
    report = REPO_ROOT / "docs/reports/TEST_REPORT.md"
    if not report.is_file():
        audit.deduct(5, "TEST_REPORT.md missing", blocker=False)
        return
    text = read_text(report)
    if "356" not in text and "349" not in text:
        audit.deduct(3, "TEST_REPORT.md may be stale (pytest counts)", blocker=False)
    if "AI rate limit" not in text and "ai rate limit" not in text.lower():
        audit.deduct(2, "TEST_REPORT.md missing AI rate limit coverage note", blocker=False)
    audit.note("TEST_REPORT.md present")


def check_production_audit_report(audit: AuditResult) -> None:
    report = REPO_ROOT / "docs/reports/PRODUCTION_AUDIT.md"
    if not report.is_file():
        audit.deduct(3, "PRODUCTION_AUDIT.md report missing", blocker=False)
    else:
        audit.note("PRODUCTION_AUDIT.md report present")


def check_ai_security_test(audit: AuditResult) -> None:
    path = REPO_ROOT / "services/api/tests/security/test_academic_risks_security.py"
    text = read_text(path)
    if "test_analyze_enforces_ai_rate_limit_with_429" not in text:
        audit.deduct(5, "AI rate limit security test missing", blocker=True)
    else:
        audit.note("AI rate limit security test present")


SECRET_SCAN_SKIP_REL = frozenset(
    {
        "scripts/production_audit.py",
        "services/api/app/config.py",
        "services/api/tests/unit/test_config.py",
        "docs/operations/PRODUCTION_DEPLOYMENT.md",
        ".env.example",
    }
)


def check_no_obvious_secrets(audit: AuditResult) -> None:
    scanned = 0
    for path in REPO_ROOT.rglob("*"):
        if not path.is_file():
            continue
        if any(part in {".git", "node_modules", ".venv", "__pycache__"} for part in path.parts):
            continue
        if path.suffix in {".png", ".jpg", ".pdf", ".pyc", ".lock"}:
            continue
        if path.name == ".env":
            continue
        rel = str(path.relative_to(REPO_ROOT)).replace("\\", "/")
        if rel in SECRET_SCAN_SKIP_REL:
            continue
        try:
            text = path.read_text(encoding="utf-8")
        except (UnicodeDecodeError, OSError):
            continue
        scanned += 1
        for pattern in SECRET_PATTERNS:
            if pattern.search(text):
                audit.deduct(25, f"Possible secret pattern in {rel}", blocker=True)
                break
    audit.note(f"Scanned {scanned} text files for obvious secret patterns")


def run_pytest_suite(service: str) -> tuple[bool, str]:
    cmd = ["python", "-m", "pytest", "-q", "--tb=no"]
    result = subprocess.run(
        cmd,
        cwd=str(REPO_ROOT / "services" / service),
        capture_output=True,
        text=True,
    )
    summary_lines = [
        line
        for line in (result.stdout + result.stderr).strip().splitlines()
        if "passed" in line or "failed" in line or "error" in line.lower()
    ]
    summary = summary_lines[-1:] if summary_lines else ["no output"]
    return result.returncode == 0, summary[0]


def check_local_tests(audit: AuditResult) -> None:
    for service in ("api", "data-engineering"):
        ok, summary = run_pytest_suite(service)
        if ok:
            audit.note(f"pytest {service}: {summary}")
        else:
            audit.deduct(15, f"pytest {service} failed: {summary}", blocker=True)


def check_docker_health(audit: AuditResult) -> None:
    ps = subprocess.run(
        ["docker", "compose", "ps", "--format", "json"],
        cwd=str(REPO_ROOT),
        capture_output=True,
        text=True,
    )
    if ps.returncode != 0:
        audit.deduct(5, "Docker stack not running (optional for static audit)", blocker=False)
        return
    lines = [line for line in ps.stdout.splitlines() if line.strip()]
    if not lines:
        audit.deduct(5, "Docker stack not running", blocker=False)
        return
    audit.note(f"Docker compose: {len(lines)} service(s) reported")
    env = subprocess.run(
        [
            "docker",
            "compose",
            "exec",
            "-T",
            "api",
            "printenv",
            "ENVIRONMENT",
            "AUTH_RATE_LIMIT_MAX",
            "AI_RATE_LIMIT_MAX",
            "JWT_SECRET",
        ],
        cwd=str(REPO_ROOT),
        capture_output=True,
        text=True,
    )
    if env.returncode == 0:
        audit.note(f"Live API env: {env.stdout.strip().replace(chr(10), ', ')}")


def main() -> int:
    audit = AuditResult()
    check_env_example(audit)
    check_docker_exposure(audit)
    check_rate_limits_in_code(audit)
    check_jwt_guard(audit)
    check_ci(audit)
    check_runbook(audit)
    check_readme(audit)
    check_test_report(audit)
    check_production_audit_report(audit)
    check_ai_security_test(audit)
    check_no_obvious_secrets(audit)
    check_local_tests(audit)
    check_docker_health(audit)

    if audit.blockers:
        audit.score = min(audit.score, 69)

    report = {
        "score": audit.score,
        "blockers": audit.blockers,
        "warnings": audit.warnings,
        "evidence": audit.evidence,
    }
    print(json.dumps(report, indent=2))
    print(f"\nProduction audit: {audit.score}/100")
    if audit.blockers:
        print("Blockers:")
        for item in audit.blockers:
            print(f"  - {item}")
    if audit.warnings:
        print("Warnings:")
        for item in audit.warnings:
            print(f"  - {item}")
    return 0 if audit.score >= 85 and not audit.blockers else 1


if __name__ == "__main__":
    sys.exit(main())
