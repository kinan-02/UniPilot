"""Run full conversation agent benchmark inside Docker."""

from __future__ import annotations

import argparse
import asyncio
import json
import sys
import time
from pathlib import Path
from typing import Any

from app.agent.evaluation.agent_eval_runner import run_agent_benchmark_case
from app.agent.evaluation.benchmark_loader import (
    load_agent_benchmark_cases,
    merge_cases,
    sample_rag_agent_cases,
)
from app.agent.evaluation.eval_shared import filter_benchmark_cases, summarize_results
from app.config import get_settings
from app.retrieval.cache_warmup import warmup_retrieval_caches
from app.retrieval.evaluation.mongo_eval import close_eval_database, resolve_eval_database
from app.retrieval.evaluation.progress import SingleBarProgress


def _parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Run conversation agent benchmark eval.")
    parser.add_argument(
        "--cases",
        type=Path,
        default=None,
        help="Path to agent_benchmark_cases.jsonl (default: bundled cases)",
    )
    parser.add_argument(
        "--output",
        type=Path,
        default=Path("agent_eval_report.json"),
        help="JSON report output path (relative to services/api cwd)",
    )
    parser.add_argument(
        "--category",
        action="append",
        default=[],
        help="Run only cases in this category (repeatable)",
    )
    parser.add_argument(
        "--limit",
        type=int,
        default=0,
        help="Max cases to run after filtering (0 = all)",
    )
    parser.add_argument(
        "--rag-sample",
        type=int,
        default=0,
        help="Add N course-question cases sampled from RAG benchmark",
    )
    parser.add_argument(
        "--require-mongo",
        action="store_true",
        help="Exit if MongoDB is unreachable",
    )
    parser.add_argument(
        "--skip-warmup",
        action="store_true",
        help="Skip wiki embedding cache warmup",
    )
    parser.add_argument(
        "--fail-fast",
        action="store_true",
        help="Stop on first failing case",
    )
    parser.add_argument(
        "--quiet",
        action="store_true",
        help="Only print summary JSON to stdout",
    )
    return parser.parse_args()


async def _run(args: argparse.Namespace) -> int:
    settings = get_settings()
    base_cases = load_agent_benchmark_cases(args.cases)
    extra_cases = (
        sample_rag_agent_cases(limit=args.rag_sample, intents={"course_question"})
        if args.rag_sample > 0
        else []
    )
    cases = filter_benchmark_cases(
        merge_cases(base_cases, extra_cases),
        categories=args.category,
        limit=args.limit,
    )

    if not cases:
        print("No benchmark cases to run.", file=sys.stderr)
        return 2

    database = await resolve_eval_database(settings=settings, require=args.require_mongo)
    if database is None:
        print("MongoDB unavailable; cannot run agent eval.", file=sys.stderr)
        return 2

    warmup_meta: dict[str, Any] = {"skipped": args.skip_warmup}
    if not args.skip_warmup:
        wiki_root = warmup_retrieval_caches(settings=settings)
        warmup_meta = {"skipped": False, "wikiRoot": wiki_root}

    progress = SingleBarProgress(
        total=len(cases),
        desc="Agent eval",
        disable=args.quiet,
    )
    progress.set_phase("Running cases")

    started = time.perf_counter()
    results: list[dict[str, Any]] = []
    for case in cases:
        result = await run_agent_benchmark_case(database, case)
        results.append(result)
        progress.advance()
        if not args.quiet and result.get("status") != "pass":
            status = result.get("status")
            case_id = result.get("id")
            detail = result.get("reason") or "; ".join(result.get("failures") or [])
            print(f"[{status}] {case_id}: {detail}", file=sys.stderr)
        if args.fail_fast and result.get("status") == "fail":
            break

    progress.close()
    elapsed_sec = time.perf_counter() - started
    summary = summarize_results(results)

    report = {
        "evalType": "conversation_agent",
        "elapsedSec": round(elapsed_sec, 2),
        "warmup": warmup_meta,
        "summary": summary,
        "cases": results,
    }

    output_path = args.output
    output_path.parent.mkdir(parents=True, exist_ok=True)
    output_path.write_text(json.dumps(report, indent=2, ensure_ascii=False), encoding="utf-8")

    if args.quiet:
        print(json.dumps(summary, indent=2))
    else:
        print(
            f"\nAgent eval: {summary['passed']}/{summary['executed']} passed "
            f"({summary['passRate'] * 100:.1f}%), "
            f"{summary['skipped']} skipped, "
            f"report → {output_path}",
            file=sys.stderr,
        )

    await close_eval_database()
    return 0 if summary["failed"] == 0 else 1


def main() -> None:
    args = _parse_args()
    raise SystemExit(asyncio.run(_run(args)))


if __name__ == "__main__":
    main()
