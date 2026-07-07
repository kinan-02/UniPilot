#!/usr/bin/env python3
"""CLI for offline autonomous agent replay evaluation (Phase 23 + Phase 26)."""

from __future__ import annotations

import argparse
import asyncio
import json
import sys
from pathlib import Path

# Allow running as `python scripts/run_agent_replay_eval.py` from services/agent.
_AGENT_ROOT = Path(__file__).resolve().parents[1]
if str(_AGENT_ROOT) not in sys.path:
    sys.path.insert(0, str(_AGENT_ROOT))

from app.agent.evaluation.case_loader import load_eval_cases
from app.agent.evaluation.full_shadow_reporting import build_full_shadow_eval_report, render_full_shadow_markdown_report
from app.agent.evaluation.reporting import build_eval_report, render_markdown_eval_report
from app.agent.evaluation.replay_runner import run_eval_cases
from app.retrieval.evaluation.progress import SingleBarProgress


def _parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Run UniPilot offline agent replay evaluation.")
    parser.add_argument("--cases", required=True, help="Path to eval case file or directory")
    parser.add_argument(
        "--mode",
        choices=["gates_only", "shadow_replay", "full_llm_shadow_replay"],
        default="gates_only",
    )
    parser.add_argument("--output", help="JSON report output path")
    parser.add_argument("--markdown", help="Markdown report output path")
    parser.add_argument("--fail-on-failed-cases", action="store_true")
    parser.add_argument("--allow-real-llm", action="store_true", help="Explicitly allow real LLM (non-deterministic)")
    parser.add_argument("--max-cases", type=int, default=None)
    parser.add_argument("--max-reasoning-calls", type=int, default=None, help="Per-case reasoning call budget")
    parser.add_argument("--lab-config", help="Optional JSON file with Settings overrides for lab mode")
    parser.add_argument(
        "--no-progress",
        action="store_true",
        help="Disable the single in-place progress bar",
    )
    return parser.parse_args()


def _load_lab_config(path: str | None) -> dict[str, object] | None:
    if not path:
        return None
    payload = json.loads(Path(path).read_text(encoding="utf-8"))
    return payload if isinstance(payload, dict) else None


async def _main_async(args: argparse.Namespace) -> int:
    if args.mode == "full_llm_shadow_replay" and not args.allow_real_llm:
        print(
            json.dumps(
                {
                    "error": "full_llm_shadow_replay_requires_allow_real_llm",
                    "message": "Pass --allow-real-llm to run full LLM shadow replay lab mode.",
                }
            ),
            file=sys.stderr,
        )
        return 2

    cases = load_eval_cases(args.cases, strict=True)
    lab_overrides = _load_lab_config(args.lab_config)

    progress = SingleBarProgress(
        total=max(1, len(cases)),
        desc="Agent replay",
        disable=args.no_progress,
    )
    try:
        results = await run_eval_cases(
            cases,
            mode=args.mode,  # type: ignore[arg-type]
            allow_real_llm=bool(args.allow_real_llm),
            max_cases=args.max_cases,
            max_reasoning_calls=args.max_reasoning_calls,
            settings_overrides=lab_overrides,
            progress=progress,
        )
    finally:
        progress.close()

    if args.mode == "full_llm_shadow_replay":
        report = build_full_shadow_eval_report(results, cases=cases, allow_real_llm=bool(args.allow_real_llm))
        markdown = render_full_shadow_markdown_report(report)
    else:
        report = build_eval_report(
            results,
            cases=cases,
            mode=args.mode,
            allow_real_llm=bool(args.allow_real_llm),
        )
        markdown = render_markdown_eval_report(report)

    if args.output:
        Path(args.output).write_text(json.dumps(report, indent=2), encoding="utf-8")
    if args.markdown:
        Path(args.markdown).write_text(markdown, encoding="utf-8")

    summary = report.get("summary") or {}
    failed = int(summary.get("failed_cases") or summary.get("failedCases") or 0)
    errored = int(summary.get("errored_cases") or summary.get("erroredCases") or 0)

    print(json.dumps({"summary": summary, "failedCases": len(report.get("failedCases") or [])}))

    if args.fail_on_failed_cases and (failed or errored):
        return 1
    return 0


def main() -> None:
    args = _parse_args()
    raise SystemExit(asyncio.run(_main_async(args)))


if __name__ == "__main__":
    main()
