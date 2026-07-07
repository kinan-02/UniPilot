"""Integration tests for activation manifest builder CLI (Phase 25)."""

from __future__ import annotations

import json
import subprocess
import sys
from pathlib import Path

_AGENT_ROOT = Path(__file__).resolve().parents[2]
_SCRIPT = _AGENT_ROOT / "scripts" / "build_promotion_activation_manifest.py"


def test_build_activation_manifest_cli_writes_draft(tmp_path: Path) -> None:
    report = tmp_path / "readiness.json"
    report.write_text(
        json.dumps(
            {
                "candidates": [
                    {
                        "candidateId": "synthesis_text_promotion.course_question_workflow",
                        "level": "ready_for_limited_promotion",
                        "passRate": 1.0,
                    }
                ]
            }
        ),
        encoding="utf-8",
    )
    output = tmp_path / "manifest.json"
    proc = subprocess.run(
        [
            sys.executable,
            str(_SCRIPT),
            "--readiness-report",
            str(report),
            "--candidate",
            "synthesis_text_promotion.course_question_workflow",
            "--level",
            "ready_for_limited_promotion",
            "--reviewed-by",
            "manual-review",
            "--output",
            str(output),
        ],
        cwd=str(_AGENT_ROOT),
        capture_output=True,
        text=True,
        check=False,
    )
    assert proc.returncode == 0, proc.stderr
    payload = json.loads(output.read_text(encoding="utf-8"))
    assert payload["candidates"][0]["approved"] is True
    assert payload["reviewedBy"] == "manual-review"
    assert "chain_of_thought" not in output.read_text(encoding="utf-8")
