"""Integration tests for promotion readiness CLI (Phase 24)."""

from __future__ import annotations

import json
import subprocess
import sys
from pathlib import Path

_AGENT_ROOT = Path(__file__).resolve().parents[2]
_SCRIPT = _AGENT_ROOT / "scripts" / "run_agent_promotion_readiness.py"
_CASES = _AGENT_ROOT / "tests" / "fixtures" / "eval_cases"
_SUITES = _AGENT_ROOT / "tests" / "fixtures" / "eval_suites"


def _run_cli(*extra: str) -> subprocess.CompletedProcess[str]:
    return subprocess.run(
        [sys.executable, str(_SCRIPT), *extra],
        cwd=str(_AGENT_ROOT),
        capture_output=True,
        text=True,
        check=False,
    )


def test_readiness_cli_runs_over_fixtures() -> None:
    proc = _run_cli("--cases", str(_CASES), "--suites", str(_SUITES), "--mode", "gates_only")
    assert proc.returncode == 0, proc.stderr


def test_readiness_cli_writes_json_report(tmp_path: Path) -> None:
    out = tmp_path / "readiness.json"
    proc = _run_cli(
        "--cases",
        str(_CASES),
        "--suites",
        str(_SUITES),
        "--output",
        str(out),
    )
    assert proc.returncode == 0, proc.stderr
    payload = json.loads(out.read_text(encoding="utf-8"))
    assert "summary" in payload
    assert "candidates" in payload


def test_readiness_cli_writes_markdown_report(tmp_path: Path) -> None:
    md = tmp_path / "readiness.md"
    proc = _run_cli(
        "--cases",
        str(_CASES),
        "--suites",
        str(_SUITES),
        "--markdown",
        str(md),
    )
    assert proc.returncode == 0, proc.stderr
    assert "# UniPilot Agent Promotion Readiness Report" in md.read_text(encoding="utf-8")


def test_fail_on_not_ready_exits_nonzero(tmp_path: Path) -> None:
    thresholds = tmp_path / "thresholds.json"
    thresholds.write_text(
        json.dumps({"min_pass_rate": 1.0, "min_candidate_case_count": 100}),
        encoding="utf-8",
    )
    proc = _run_cli(
        "--cases",
        str(_CASES),
        "--suites",
        str(_SUITES),
        "--thresholds",
        str(thresholds),
        "--fail-on-not-ready",
        "workflow_promotion.graduation_progress_workflow",
    )
    assert proc.returncode == 1


def test_fail_on_any_blocking_exits_nonzero_when_blocked(tmp_path: Path) -> None:
    thresholds = tmp_path / "thresholds.json"
    thresholds.write_text(
        json.dumps({"min_pass_rate": 1.0, "min_candidate_case_count": 100}),
        encoding="utf-8",
    )
    proc = _run_cli(
        "--cases",
        str(_CASES),
        "--suites",
        str(_SUITES),
        "--thresholds",
        str(thresholds),
        "--fail-on-any-blocking",
    )
    assert proc.returncode == 1


def test_report_contains_no_forbidden_keys(tmp_path: Path) -> None:
    out = tmp_path / "readiness.json"
    proc = _run_cli("--cases", str(_CASES), "--suites", str(_SUITES), "--output", str(out))
    assert proc.returncode == 0, proc.stderr
    text = out.read_text(encoding="utf-8")
    assert "raw_context" not in text
    assert "chain_of_thought" not in text
