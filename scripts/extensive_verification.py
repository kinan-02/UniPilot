#!/usr/bin/env python3
"""Run extensive UniPilot verification with a single tqdm progress bar."""

from __future__ import annotations

import argparse
import json
import os
import subprocess
import sys
from dataclasses import dataclass
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent


def ensure_python_packages() -> None:
    try:
        import tqdm  # noqa: F401
    except ImportError:
        subprocess.check_call([sys.executable, "-m", "pip", "install", "-q", "tqdm"])


ensure_python_packages()
from tqdm import tqdm  # noqa: E402


@dataclass
class Suite:
    name: str
    cwd: Path
    cmd: list[str]
    optional: bool = False


def run_captured(
    cmd: list[str],
    *,
    cwd: Path,
    env: dict[str, str],
) -> tuple[int, str, str]:
    result = subprocess.run(
        cmd,
        cwd=cwd,
        env=env,
        text=True,
        capture_output=True,
    )
    return result.returncode, result.stdout, result.stderr


def run_suite(
    suite: Suite,
    *,
    pythonpath: str | None = None,
    env_overrides: dict[str, str] | None = None,
) -> tuple[bool, str, str, str]:
    env = os.environ.copy()
    env.setdefault("PYTHONUNBUFFERED", "1")
    env.setdefault("UNIPILOT_SINGLE_PROGRESS", "1")
    if pythonpath:
        env["PYTHONPATH"] = pythonpath + os.pathsep + env.get("PYTHONPATH", "")
    if env_overrides:
        env.update(env_overrides)
    code, stdout, stderr = run_captured(suite.cmd, cwd=suite.cwd, env=env)
    if code == 0:
        return True, "", stdout, stderr
    detail = f"exit code {code}"
    return False, detail, stdout, stderr


def discover_vitest_files(web_dir: Path) -> list[Path]:
    src_dir = web_dir / "src"
    patterns = ("**/*.test.ts", "**/*.test.tsx")
    files: list[Path] = []
    for pattern in patterns:
        files.extend(src_dir.glob(pattern))
    return sorted(set(files))


def run_vitest_per_file(
    web_dir: Path,
    bar: tqdm,
    extra_args: list[str] | None = None,
) -> tuple[bool, list[str]]:
    files = discover_vitest_files(web_dir)
    if not files:
        tqdm.write("No Vitest files found.", file=sys.stderr)
        return False, ["no files"]

    failed: list[str] = []
    env = os.environ.copy()
    env.setdefault("UNIPILOT_SINGLE_PROGRESS", "1")

    for test_file in files:
        rel = test_file.relative_to(web_dir)
        bar.set_postfix_str(str(rel)[-48:], refresh=True)
        cmd = ["npm", "test", "--", "--run", str(rel), *(extra_args or [])]
        code, stdout, stderr = run_captured(cmd, cwd=web_dir, env=env)
        bar.update(1)
        if code != 0:
            failed.append(str(rel))
            tqdm.write(f"\nVitest failed: {rel}", file=sys.stderr)
            if stdout.strip():
                tqdm.write(stdout, file=sys.stderr)
            if stderr.strip():
                tqdm.write(stderr, file=sys.stderr)

    return len(failed) == 0, failed


def curl_ok(url: str) -> bool:
    result = subprocess.run(
        ["curl", "-sf", url],
        capture_output=True,
        text=True,
    )
    return result.returncode == 0


def build_suites(args: argparse.Namespace) -> tuple[list[Suite], str, str | None]:
    api_dir = ROOT / "services" / "api"
    web_dir = ROOT / "services" / "web"
    parser_dir = ROOT / "services" / "transcript-parser"

    api_python = sys.executable
    api_venv = api_dir / ".venv" / "bin" / "python"
    if api_venv.exists():
        api_python = str(api_venv)

    parser_python: str | None = None
    parser_venv = parser_dir / ".venv" / "bin" / "python"
    if parser_venv.exists():
        parser_python = str(parser_venv)

    pytest_plugin = "pytest_tqdm_plugin"
    pytest_base = [api_python, "-m", "pytest", "-p", pytest_plugin, "--tb=short", "-q"]

    parser_pytest_base = [
        (parser_python or api_python),
        "-m",
        "pytest",
        "-p",
        pytest_plugin,
        "--tb=short",
        "-q",
    ]

    suites: list[Suite] = []

    if args.smoke_only:
        suites.extend(
            [
                Suite(
                    "API progress & curriculum tests",
                    api_dir,
                    pytest_base
                    + [
                        "tests/unit/test_cross_track_equivalence.py",
                        "tests/unit/test_curriculum_graph.py",
                        "tests/unit/test_course_reference_keys.py",
                        "tests/unit/test_graduation_progress_calculator.py",
                        "tests/integration/test_graduation_progress_contract.py",
                        "tests/integration/test_curriculum_graph_integration.py",
                        "tests/integration/test_transcript_graduation_progress_integration.py",
                        "--no-cov",
                    ],
                ),
            ]
        )
    else:
        if args.no_cov:
            suites.extend(
                [
                    Suite(
                        "API unit tests",
                        api_dir,
                        pytest_base + ["tests/unit", "--no-cov"],
                    ),
                    Suite(
                        "API integration tests",
                        api_dir,
                        pytest_base + ["tests/integration", "--no-cov"],
                    ),
                    Suite(
                        "API security tests",
                        api_dir,
                        pytest_base + ["tests/security", "--no-cov"],
                    ),
                    Suite(
                        "API stress tests",
                        api_dir,
                        pytest_base + ["tests/stress", "--no-cov"],
                        optional=True,
                    ),
                ]
            )
        else:
            suites.append(
                Suite(
                    "API full pytest (100% coverage)",
                    api_dir,
                    pytest_base + ["tests"],
                ),
            )

    if parser_dir.exists():
        suites.append(
            Suite(
                "Transcript parser tests",
                parser_dir,
                parser_pytest_base + (["--no-cov"] if args.no_cov else []),
            ),
        )

    suites.append(
        Suite(
            "Web production build",
            web_dir,
            ["npm", "run", "build"],
        ),
    )

    return suites, api_python, parser_python


def count_steps(args: argparse.Namespace, suites: list[Suite], web_dir: Path) -> int:
    total = len(suites)
    if not args.skip_vitest:
        total += len(discover_vitest_files(web_dir))
    if not args.skip_docker:
        total += 2
    if not args.skip_e2e and not args.smoke_only:
        total += 1
    return total


def main() -> int:
    parser = argparse.ArgumentParser(description="Extensive UniPilot verification with tqdm")
    parser.add_argument("--smoke-only", action="store_true", help="Run progress-focused API tests only")
    parser.add_argument("--no-cov", action="store_true", help="Skip pytest coverage enforcement")
    parser.add_argument("--skip-vitest", action="store_true", help="Skip Vitest file-by-file run")
    parser.add_argument("--skip-docker", action="store_true", help="Skip live Docker health checks")
    parser.add_argument("--skip-e2e", action="store_true", help="Skip Playwright E2E")
    args = parser.parse_args()

    web_dir = ROOT / "services" / "web"
    api_port = os.environ.get("API_PORT", "8000")
    web_port = os.environ.get("WEB_PORT", "3000")

    results: list[tuple[str, bool, str]] = []
    plugin_path = str(ROOT / "scripts")
    suites, _api_python, _parser_python = build_suites(args)
    total_steps = count_steps(args, suites, web_dir)

    bar = tqdm(
        total=total_steps,
        desc="Verification",
        unit="step",
        file=sys.stderr,
        dynamic_ncols=True,
        leave=True,
        mininterval=0.1,
    )

    try:
        for suite in suites:
            bar.set_postfix_str(suite.name[:48], refresh=True)
            ok, detail, stdout, stderr = run_suite(suite, pythonpath=plugin_path)
            bar.update(1)
            results.append((suite.name, ok, detail))
            if not ok and not suite.optional:
                tqdm.write(f"\nFAILED: {suite.name} ({detail})", file=sys.stderr)
                if stdout.strip():
                    tqdm.write(stdout, file=sys.stderr)
                if stderr.strip():
                    tqdm.write(stderr, file=sys.stderr)

        if not args.skip_vitest:
            vitest_ok, failed = run_vitest_per_file(web_dir, bar)
            results.append(
                (
                    "Web Vitest (file-by-file)",
                    vitest_ok,
                    "" if vitest_ok else f"{len(failed)} failures",
                ),
            )

        if not args.skip_docker:
            checks = [
                ("API /health", f"http://localhost:{api_port}/health"),
                ("Web UI", f"http://localhost:{web_port}/"),
            ]
            for label, url in checks:
                bar.set_postfix_str(label[:48], refresh=True)
                ok = curl_ok(url)
                bar.update(1)
                results.append((label, ok, "" if ok else url))
                if not ok:
                    tqdm.write(f"FAILED: {label} ({url})", file=sys.stderr)

        if not args.skip_e2e and not args.smoke_only:
            bar.set_postfix_str("Playwright progress E2E", refresh=True)
            env = os.environ.copy()
            env.setdefault("UNIPILOT_SINGLE_PROGRESS", "1")
            code, stdout, stderr = run_captured(
                ["npm", "run", "test:e2e", "--", "--project=progress"],
                cwd=web_dir,
                env=env,
            )
            bar.update(1)
            results.append(
                (
                    "Playwright progress E2E",
                    code == 0,
                    "" if code == 0 else f"exit {code}",
                ),
            )
            if code != 0:
                tqdm.write("\nPlaywright E2E failed", file=sys.stderr)
                if stdout.strip():
                    tqdm.write(stdout, file=sys.stderr)
                if stderr.strip():
                    tqdm.write(stderr, file=sys.stderr)
    finally:
        bar.close()

    passed = sum(1 for _, ok, _ in results if ok)
    total = len(results)
    tqdm.write("\n" + "=" * 60, file=sys.stderr)
    tqdm.write("VERIFICATION SUMMARY", file=sys.stderr)
    tqdm.write("=" * 60, file=sys.stderr)
    for name, ok, detail in results:
        status = "PASS" if ok else "FAIL"
        suffix = f" ({detail})" if detail and not ok else ""
        tqdm.write(f"  [{status}] {name}{suffix}", file=sys.stderr)
    tqdm.write("-" * 60, file=sys.stderr)
    tqdm.write(f"  {passed}/{total} checks passed", file=sys.stderr)
    tqdm.write("=" * 60, file=sys.stderr)

    report_path = ROOT / "scripts" / "verification_report.json"
    report_path.write_text(
        json.dumps(
            {
                "passed": passed,
                "total": total,
                "results": [
                    {"name": name, "ok": ok, "detail": detail}
                    for name, ok, detail in results
                ],
            },
            indent=2,
        ),
        encoding="utf-8",
    )
    tqdm.write(f"Report written to {report_path}", file=sys.stderr)

    return 0 if passed == total else 1


if __name__ == "__main__":
    raise SystemExit(main())
