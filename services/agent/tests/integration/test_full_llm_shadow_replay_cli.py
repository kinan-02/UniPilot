"""Integration tests for full LLM shadow replay CLI (Phase 26)."""

from __future__ import annotations

import asyncio
import json
import subprocess
import sys
from pathlib import Path

from app.agent.evaluation.full_shadow_reporting import build_full_shadow_eval_report, render_full_shadow_markdown_report
from app.agent.evaluation.replay_runner import run_eval_cases
from app.agent.evaluation.case_loader import load_eval_cases

_AGENT_ROOT = Path(__file__).resolve().parents[2]
_SCRIPT = _AGENT_ROOT / "scripts" / "run_agent_replay_eval.py"
_CASES = _AGENT_ROOT / "tests" / "fixtures" / "eval_cases_real_world_like"


def test_full_llm_shadow_replay_without_allow_real_llm_exits_nonzero() -> None:
    proc = subprocess.run(
        [
            sys.executable,
            str(_SCRIPT),
            "--cases",
            str(_CASES),
            "--mode",
            "full_llm_shadow_replay",
        ],
        cwd=str(_AGENT_ROOT),
        capture_output=True,
        text=True,
        check=False,
    )
    assert proc.returncode == 2
    assert "full_llm_shadow_replay_requires_allow_real_llm" in proc.stderr


def test_full_llm_shadow_replay_with_mocked_case_runs(tmp_path: Path) -> None:
    cases = load_eval_cases(_CASES / "real_world_like_mixed_he_en_course_question.json", strict=True)
    cases[0] = cases[0].model_copy(
        update={
            "mock_reasoning_outputs": [
                {
                    "contract_name": "intent_classifier_v1",
                    "output": {"decision_summary": "ok", "confidence": 0.9, "primary_intent": "course_question"},
                }
            ]
        }
    )
    results = asyncio.run(
        run_eval_cases(cases, mode="full_llm_shadow_replay", allow_real_llm=True, max_cases=1)
    )
    assert results
    report = build_full_shadow_eval_report(results, cases=cases, allow_real_llm=True)
    output = tmp_path / "report.json"
    output.write_text(json.dumps(report, indent=2), encoding="utf-8")
    assert output.is_file()


def test_json_and_markdown_reports_written(tmp_path: Path) -> None:
    cases = load_eval_cases(_CASES / "real_world_like_vague_graduation_progress.json", strict=True)
    results = asyncio.run(
        run_eval_cases(cases, mode="full_llm_shadow_replay", allow_real_llm=True, max_cases=1)
    )
    report = build_full_shadow_eval_report(results, cases=cases, allow_real_llm=True)
    markdown = render_full_shadow_markdown_report(report)
    assert report["mode"] == "full_llm_shadow_replay"
    assert markdown.startswith("# UniPilot Agent Offline Eval Report")


def test_report_marks_real_llm_used() -> None:
    cases = load_eval_cases(_CASES / "real_world_like_ambiguous_course_prereq.json", strict=True)
    results = asyncio.run(
        run_eval_cases(cases, mode="full_llm_shadow_replay", allow_real_llm=True, max_cases=1)
    )
    report = build_full_shadow_eval_report(results, allow_real_llm=True)
    assert report.get("allowRealLlm") is True
    assert report.get("fullShadow", {}).get("realLlmUsed") is True


def test_no_forbidden_keys_in_report() -> None:
    cases = load_eval_cases(_CASES / "real_world_like_requirement_slang_typos.json", strict=True)
    results = asyncio.run(
        run_eval_cases(cases, mode="full_llm_shadow_replay", allow_real_llm=True, max_cases=1)
    )
    report = build_full_shadow_eval_report(results, allow_real_llm=True)
    text = json.dumps(report).lower()
    assert "chain_of_thought" not in text
    assert "raw_prompt" not in text
    assert "candidate_answer_text" not in text
    assert "caseResults" in report
    assert "schemaValidationFailures" in report["fullShadow"]
