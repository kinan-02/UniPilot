"""Integration tests for import real-world eval cases CLI (Phase 26)."""

from __future__ import annotations

import json
import subprocess
import sys
from pathlib import Path

from app.agent.evaluation.case_loader import load_eval_cases

_AGENT_ROOT = Path(__file__).resolve().parents[2]
_SCRIPT = _AGENT_ROOT / "scripts" / "import_real_world_eval_cases.py"


def test_imports_jsonl_to_eval_case_files(tmp_path: Path) -> None:
    input_path = tmp_path / "cases.jsonl"
    input_path.write_text(
        json.dumps(
            {
                "anonymized_user_message": "What electives remain for CS?",
                "tags": ["graduation_progress"],
                "reviewer_expected_outcome": {"expected_workflow": "graduation_progress_workflow"},
            }
        )
        + "\n",
        encoding="utf-8",
    )
    output_dir = tmp_path / "out"
    proc = subprocess.run(
        [sys.executable, str(_SCRIPT), "--input", str(input_path), "--output-dir", str(output_dir), "--strict"],
        cwd=str(_AGENT_ROOT),
        capture_output=True,
        text=True,
        check=False,
    )
    assert proc.returncode == 0, proc.stderr
    cases = load_eval_cases(output_dir, strict=True)
    assert len(cases) == 1
    assert "real_world_like" in cases[0].tags


def test_dry_run_writes_no_files(tmp_path: Path) -> None:
    input_path = tmp_path / "cases.json"
    input_path.write_text(
        json.dumps({"anonymized_user_message": "Safe anonymized question about electives."}),
        encoding="utf-8",
    )
    output_dir = tmp_path / "out"
    proc = subprocess.run(
        [
            sys.executable,
            str(_SCRIPT),
            "--input",
            str(input_path),
            "--output-dir",
            str(output_dir),
            "--dry-run",
        ],
        cwd=str(_AGENT_ROOT),
        capture_output=True,
        text=True,
        check=False,
    )
    assert proc.returncode == 0, proc.stderr
    assert not output_dir.exists() or not list(output_dir.glob("*.json"))


def test_strict_unsafe_input_exits_nonzero(tmp_path: Path) -> None:
    input_path = tmp_path / "unsafe.json"
    input_path.write_text(
        json.dumps({"anonymized_user_message": "Email me at secret@example.com"}),
        encoding="utf-8",
    )
    proc = subprocess.run(
        [
            sys.executable,
            str(_SCRIPT),
            "--input",
            str(input_path),
            "--output-dir",
            str(tmp_path / "out"),
            "--strict",
        ],
        cwd=str(_AGENT_ROOT),
        capture_output=True,
        text=True,
        check=False,
    )
    assert proc.returncode != 0


def test_generated_files_load_through_case_loader(tmp_path: Path) -> None:
    input_path = tmp_path / "cases.json"
    input_path.write_text(
        json.dumps(
            {
                "anonymized_user_message": "Explain faculty electives vs free electives",
                "tags": ["requirement_explanation"],
            }
        ),
        encoding="utf-8",
    )
    output_dir = tmp_path / "out"
    subprocess.run(
        [sys.executable, str(_SCRIPT), "--input", str(input_path), "--output-dir", str(output_dir), "--strict"],
        cwd=str(_AGENT_ROOT),
        check=True,
    )
    cases = load_eval_cases(output_dir, strict=True)
    assert cases[0].kind == "requirement_explanation"


def test_output_contains_no_forbidden_keys(tmp_path: Path) -> None:
    input_path = tmp_path / "cases.json"
    input_path.write_text(json.dumps({"anonymized_user_message": "Safe course question about prerequisites."}), encoding="utf-8")
    output_dir = tmp_path / "out"
    subprocess.run(
        [sys.executable, str(_SCRIPT), "--input", str(input_path), "--output-dir", str(output_dir), "--strict"],
        cwd=str(_AGENT_ROOT),
        check=True,
    )
    text = (output_dir / sorted(output_dir.glob("*.json"))[0]).read_text(encoding="utf-8")
    assert "chain_of_thought" not in text
    assert "raw_transcript" not in text
