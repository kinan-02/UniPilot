"""Run conversation agent benchmark via HTTP API (true E2E)."""

from __future__ import annotations

import argparse
import asyncio
import json
import os
import sys
import time
from pathlib import Path
from typing import Any

from app.agent.evaluation.agent_http_runner import (
    build_http_client,
    run_agent_http_benchmark_case,
)
from app.agent.evaluation.benchmark_loader import (
    load_agent_benchmark_cases,
    merge_cases,
    sample_rag_agent_cases,
)
from app.agent.evaluation.eval_shared import filter_benchmark_cases, summarize_results
from app.retrieval.evaluation.progress import SingleBarProgress

DEFAULT_BASE_URL = os.getenv("AGENT_EVAL_API_BASE_URL", "http://localhost:8000").rstrip("/")


def _parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Run conversation agent benchmark through HTTP API routes.",
    )
    parser.add_argument(
        "--base-url",
        default=DEFAULT_BASE_URL,
        help=f"API base URL (default: {DEFAULT_BASE_URL})",
    )
    parser.add_argument(
        "--cases",
        type=Path,
        default=None,
        help="Path to agent_benchmark_cases.jsonl",
    )
    parser.add_argument(
        "--output",
        type=Path,
        default=Path("agent_eval_http_report.json"),
        help="JSON report output path",
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
        "--delay-ms",
        type=int,
        default=int(os.getenv("AGENT_EVAL_DELAY_MS", "6500")),
        help="Delay between cases to avoid AI rate limits (default 6500ms)",
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


async def _health_check(base_url: str) -> bool:
    client = build_http_client(timeout_sec=10.0)
    try:
        response = await client.get(f"{base_url}/health")
        return response.status_code == 200
    finally:
        await client.aclose()


async def _run(args: argparse.Namespace) -> int:
    base_url = str(args.base_url).rstrip("/")
    if not await _health_check(base_url):
        print(f"API not reachable at {base_url}/health", file=sys.stderr)
        return 2

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

    progress = SingleBarProgress(
        total=len(cases),
        desc="Agent HTTP eval",
        disable=args.quiet,
    )
    progress.set_phase("Running HTTP cases")

    started = time.perf_counter()
    results: list[dict[str, Any]] = []
    client = build_http_client()

    try:
        for index, case in enumerate(cases):
            result = await run_agent_http_benchmark_case(
                client,
                base_url=base_url,
                case=case,
            )
            results.append(result)
            progress.advance()

            if not args.quiet and result.get("status") != "pass":
                status = result.get("status")
                case_id = result.get("id")
                detail = result.get("reason") or "; ".join(result.get("failures") or [])
                SingleBarProgress.write(f"[{status}] {case_id}: {detail}")

            if args.fail_fast and result.get("status") == "fail":
                break

            if args.delay_ms > 0 and index < len(cases) - 1:
                await asyncio.sleep(args.delay_ms / 1000.0)
    finally:
        await client.aclose()

    progress.close()
    elapsed_sec = time.perf_counter() - started
    summary = summarize_results(results)

    report = {
        "evalType": "conversation_agent_http",
        "baseUrl": base_url,
        "elapsedSec": round(elapsed_sec, 2),
        "delayMs": args.delay_ms,
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
            f"\nAgent HTTP eval: {summary['passed']}/{summary['executed']} passed "
            f"({summary['passRate'] * 100:.1f}%), "
            f"{summary['skipped']} skipped, "
            f"report → {output_path}",
            file=sys.stderr,
        )

    return 0 if summary["failed"] == 0 else 1


def main() -> None:
    args = _parse_args()
    raise SystemExit(asyncio.run(_run(args)))


if __name__ == "__main__":
    main()
