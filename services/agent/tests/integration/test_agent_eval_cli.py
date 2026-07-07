"""Integration tests for offline eval CLI (Phase 23)."""

from __future__ import annotations

import json
import subprocess
import sys
from pathlib import Path

_AGENT_ROOT = Path(__file__).resolve().parents[2]
_SCRIPT = _AGENT_ROOT / "scripts" / "run_agent_replay_eval.py"
_FIXTURES = _AGENT_ROOT / "tests" / "fixtures" / "eval_cases"


def _run_cli(*extra: str) -> subprocess.CompletedProcess[str]:
    return subprocess.run(
        [sys.executable, str(_SCRIPT), *extra],
        cwd=str(_AGENT_ROOT),
        capture_output=True,
        text=True,
        check=False,
    )


def test_cli_writes_json_report(tmp_path: Path) -> None:
    out = tmp_path / "report.json"
    proc = _run_cli("--cases", str(_FIXTURES), "--mode", "gates_only", "--output", str(out))
    assert proc.returncode == 0, proc.stderr
    assert out.is_file()
    payload = json.loads(out.read_text(encoding="utf-8"))
    assert "summary" in payload


def test_cli_writes_markdown_report(tmp_path: Path) -> None:
    md = tmp_path / "report.md"
    proc = _run_cli("--cases", str(_FIXTURES), "--mode", "gates_only", "--markdown", str(md))
    assert proc.returncode == 0, proc.stderr
    text = md.read_text(encoding="utf-8")
    assert "# UniPilot Agent Offline Eval Report" in text


def test_fail_on_failed_cases_exits_nonzero(tmp_path: Path) -> None:
    bad = tmp_path / "bad.json"
    bad.write_text(
        json.dumps(
            {
                "id": "bad_case",
                "name": "Bad",
                "kind": "course_question",
                "user_message": "x",
                "compact_context": {"intent": "course_question"},
                "expected": {"expected_intent": "wrong_intent"},
            }
        ),
        encoding="utf-8",
    )
    proc = _run_cli(
        "--cases",
        str(bad),
        "--mode",
        "gates_only",
        "--fail-on-failed-cases",
    )
    assert proc.returncode == 1


def test_report_contains_no_forbidden_keys(tmp_path: Path) -> None:
    out = tmp_path / "report.json"
    proc = _run_cli("--cases", str(_FIXTURES), "--output", str(out))
    assert proc.returncode == 0, proc.stderr
    text = out.read_text(encoding="utf-8")
    assert "raw_context" not in text
    assert "chain_of_thought" not in text


def test_allow_real_llm_defaults_false(tmp_path: Path) -> None:
    out = tmp_path / "report.json"
    proc = _run_cli("--cases", str(_FIXTURES), "--output", str(out))
    assert proc.returncode == 0, proc.stderr
    payload = json.loads(out.read_text(encoding="utf-8"))
    assert payload.get("allowRealLlm") is False
    assert payload.get("deterministic") is True
