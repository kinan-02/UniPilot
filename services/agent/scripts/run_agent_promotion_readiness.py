#!/usr/bin/env python3
"""CLI for eval-guided promotion readiness scorecards (Phase 24)."""

from __future__ import annotations

import argparse
import asyncio
import json
import sys
from pathlib import Path

_AGENT_ROOT = Path(__file__).resolve().parents[1]
if str(_AGENT_ROOT) not in sys.path:
    sys.path.insert(0, str(_AGENT_ROOT))

from app.agent.evaluation.case_loader import load_eval_cases
from app.agent.evaluation.policy_hardening import build_policy_hardening_recommendations
from app.agent.evaluation.readiness_policy import (
    default_promotion_candidates,
    evaluate_promotion_readiness,
)
from app.agent.evaluation.readiness_reporting import render_readiness_markdown_report
from app.agent.evaluation.readiness_schemas import ReadinessThresholds
from app.agent.evaluation.readiness_scorecard import build_readiness_scorecard
from app.agent.evaluation.replay_runner import run_eval_cases
from app.agent.evaluation.suite_loader import load_eval_suites
from app.retrieval.evaluation.progress import SingleBarProgress


def _parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Run UniPilot promotion readiness scorecard.")
    parser.add_argument("--cases", required=True, help="Path to eval cases")
    parser.add_argument("--suites", required=True, help="Path to eval suite manifests")
    parser.add_argument("--mode", choices=["gates_only", "shadow_replay"], default="gates_only")
    parser.add_argument("--output", help="JSON report output path")
    parser.add_argument("--markdown", help="Markdown report output path")
    parser.add_argument("--thresholds", help="Optional JSON file with ReadinessThresholds overrides")
    parser.add_argument("--candidate", action="append", default=[], help="Filter to candidate id")
    parser.add_argument(
        "--fail-on-not-ready",
        action="append",
        default=[],
        help="Exit nonzero if candidate is not ready for limited/broader promotion",
    )
    parser.add_argument(
        "--fail-on-any-blocking",
        action="store_true",
        help="Exit nonzero if any candidate has blocking reasons",
    )
    parser.add_argument(
        "--no-progress",
        action="store_true",
        help="Disable the single in-place progress bar",
    )
    return parser.parse_args()


def _load_thresholds(path: str | None) -> ReadinessThresholds:
    if not path:
        return ReadinessThresholds()
    data = json.loads(Path(path).read_text(encoding="utf-8"))
    return ReadinessThresholds.model_validate(data)


async def _main_async(args: argparse.Namespace) -> int:
    cases = load_eval_cases(args.cases, strict=True)
    suites = load_eval_suites(args.suites)
    thresholds = _load_thresholds(args.thresholds)

    progress = SingleBarProgress(
        total=max(1, len(cases)),
        desc="Promotion readiness",
        disable=args.no_progress,
    )
    try:
        results = await run_eval_cases(
            cases,
            mode=args.mode,  # type: ignore[arg-type]
            allow_real_llm=False,
            progress=progress,
        )
    finally:
        progress.close()

    candidates = default_promotion_candidates()
    if args.candidate:
        allowed = set(args.candidate)
        candidates = [item for item in candidates if item.id in allowed]

    scorecard = build_readiness_scorecard(
        eval_results=results,
        suites=suites,
        cases=cases,
        candidates=candidates,
        thresholds=thresholds,
    )

    decisions = [
        evaluate_promotion_readiness(
            candidate=candidate,
            eval_results=results,
            suites=suites,
            cases=cases,
            thresholds=thresholds,
        )
        for candidate in candidates
    ]
    recommendations = build_policy_hardening_recommendations(
        eval_results=results,
        readiness_decisions=decisions,
    )
    scorecard["recommendations"] = recommendations
    scorecard["mode"] = args.mode
    scorecard["deterministic"] = True

    if args.output:
        Path(args.output).write_text(json.dumps(scorecard, indent=2), encoding="utf-8")
    if args.markdown:
        Path(args.markdown).write_text(render_readiness_markdown_report(scorecard), encoding="utf-8")

    print(
        json.dumps(
            {
                "summary": scorecard.get("summary"),
                "recommendationCount": len(recommendations),
            }
        )
    )

    exit_code = 0
    decision_by_id = {item.candidate_id: item for item in decisions}

    for candidate_id in args.fail_on_not_ready:
        decision = decision_by_id.get(candidate_id)
        if decision is None:
            exit_code = 1
            continue
        if not decision.passed:
            exit_code = 1

    if args.fail_on_any_blocking:
        if any(decision.blocking_reasons for decision in decisions):
            exit_code = 1

    return exit_code


def main() -> None:
    args = _parse_args()
    raise SystemExit(asyncio.run(_main_async(args)))


if __name__ == "__main__":
    main()
