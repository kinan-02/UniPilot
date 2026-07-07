#!/usr/bin/env python3
"""CLI for golden-set final answer evaluation."""

from __future__ import annotations

import argparse
import asyncio
import json
import sys
import time
from pathlib import Path

_AGENT_ROOT = Path(__file__).resolve().parents[1]
if str(_AGENT_ROOT) not in sys.path:
    sys.path.insert(0, str(_AGENT_ROOT))

from app.agent.evaluation.eval_thresholds import (
    evaluate_thresholds,
    load_eval_thresholds,
    resolve_suite_thresholds,
)
from app.agent.evaluation.eval_timing import CaseTiming, aggregate_timing_summary
from app.agent.evaluation.final_answer_eval import (
    JudgeMode,
    build_final_answer_eval_report,
    load_golden_answer_cases,
    render_final_answer_markdown_report,
)
from app.agent.evaluation.final_answer_runner import AgentEvalMode, run_final_answer_eval_case
from app.agent.evaluation.trace_logging import (
    TraceConfig,
    validate_trace_dir,
    validate_unsafe_raw_llm_mode,
    write_case_trace_files,
    write_trace_index,
    compact_trace_events_for_report,
)
from app.agent.evaluation.wiki_eval_cache import cache_stats
from app.config import get_settings
from app.retrieval.cache_warmup import warmup_retrieval_caches
from app.retrieval.evaluation.mongo_eval import close_eval_database, resolve_eval_database
from app.retrieval.evaluation.progress import SingleBarProgress


def _parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Run UniPilot golden-set final answer evaluation.")
    parser.add_argument(
        "--cases",
        default="eval_sets/eval_cases.json",
        help="Path to golden answer eval set JSON",
    )
    parser.add_argument("--output", help="JSON report output path")
    parser.add_argument("--markdown", help="Markdown report output path")
    parser.add_argument("--max-cases", type=int, default=None)
    parser.add_argument("--case-id", action="append", default=[], help="Run only these case IDs")
    parser.add_argument(
        "--agent-mode",
        choices=["full_live", "deterministic_fast"],
        default="full_live",
        help="Agent invocation mode (default: full_live)",
    )
    parser.add_argument(
        "--mode",
        choices=["local_agent"],
        default="local_agent",
        help="Deprecated alias — use --agent-mode instead",
    )
    parser.add_argument(
        "--allow-real-llm",
        action="store_true",
        help="Explicitly allow real LLM calls for full_live agent and optional LLM judge",
    )
    parser.add_argument(
        "--fallback-to-full-live",
        action="store_true",
        help="When deterministic_fast cannot handle a case, fall back to full_live (requires --allow-real-llm)",
    )
    parser.add_argument(
        "--judge-mode",
        choices=["deterministic", "llm", "hybrid"],
        default="deterministic",
        help="How to compare final answers against key facts",
    )
    parser.add_argument("--lab-config", help="Optional JSON file with Settings overrides")
    parser.add_argument(
        "--full-architecture",
        action="store_true",
        help=(
            "Enable full MAS stack (task understanding, planner, supervisor, "
            "specialists, synthesis, monitor, plan repair) via lab settings"
        ),
    )
    parser.add_argument("--require-mongo", action="store_true")
    parser.add_argument("--skip-warmup", action="store_true")
    parser.add_argument("--fail-on-failed-cases", action="store_true")
    parser.add_argument("--fail-on-threshold-violation", action="store_true")
    parser.add_argument("--include-full-answers", action="store_true")
    parser.add_argument("--no-progress", action="store_true")
    parser.add_argument(
        "--concurrency",
        type=int,
        default=1,
        help="Number of cases to run concurrently (default: 1)",
    )
    parser.add_argument(
        "--thresholds",
        help="Optional JSON file with suite threshold policy (eval_sets/eval_thresholds.json)",
    )
    parser.add_argument(
        "--trace-dir",
        help="Write per-case safe trace files under this directory (tmp/ or gitignored debug only)",
    )
    parser.add_argument(
        "--trace-on-failure",
        action="store_true",
        help="Write detailed traces only for failed/partial/errored cases",
    )
    parser.add_argument(
        "--trace-failure-dir",
        help="Directory for trace-on-failure output (default: tmp/final_answer_eval_failed_traces)",
    )
    parser.add_argument(
        "--trace-level",
        choices=["summary", "detailed"],
        default="detailed",
        help="Safe trace verbosity",
    )
    parser.add_argument(
        "--include-trace-events",
        action="store_true",
        help="Include compact trace events in the main JSON eval report",
    )
    parser.add_argument(
        "--unsafe-local-raw-llm-logs",
        action="store_true",
        help="DANGEROUS: write raw prompt/model output to trace_dir/raw_llm/ (local debug only)",
    )
    parser.add_argument(
        "--raw-llm-log-max-chars",
        type=int,
        default=200_000,
        help="Max chars per raw prompt/model output field in unsafe debug files",
    )
    return parser.parse_args()


def _load_lab_config(path: str | None) -> dict[str, object] | None:
    if not path:
        return None
    payload = json.loads(Path(path).read_text(encoding="utf-8"))
    return payload if isinstance(payload, dict) else None


def _select_cases(cases: list, args: argparse.Namespace) -> list:
    selected = cases
    if args.case_id:
        wanted = set(args.case_id)
        selected = [case for case in selected if case.id in wanted]
    if args.max_cases is not None:
        selected = selected[: args.max_cases]
    return selected


def _should_write_trace(result_status: str, *, trace_on_failure: bool) -> bool:
    if not trace_on_failure:
        return True
    return result_status in {"failed", "partial", "errored"}


async def _run_one_case(
    index: int,
    case,
    *,
    database,
    args: argparse.Namespace,
    lab_overrides: dict[str, object] | None,
    trace_config: TraceConfig | None,
    agent_mode: AgentEvalMode,
) -> tuple[int, object, object | None, CaseTiming]:
    result, case_trace, timing = await run_final_answer_eval_case(
        database,
        case,
        allow_real_llm=bool(args.allow_real_llm),
        judge_mode=args.judge_mode,  # type: ignore[arg-type]
        settings_overrides=lab_overrides,
        full_architecture=bool(args.full_architecture),
        trace_config=trace_config,
        agent_mode=agent_mode,
        require_mongo=bool(args.require_mongo),
        fallback_to_full_live=bool(args.fallback_to_full_live),
    )
    return index, result, case_trace, timing


async def _main_async(args: argparse.Namespace) -> int:
    agent_mode: AgentEvalMode = args.agent_mode  # type: ignore[assignment]

    if args.judge_mode in {"llm", "hybrid"} and not args.allow_real_llm:
        print(
            json.dumps(
                {
                    "error": "llm_judge_requires_allow_real_llm",
                    "message": "Pass --allow-real-llm when using --judge-mode llm or hybrid.",
                }
            ),
            file=sys.stderr,
        )
        return 2

    if agent_mode == "full_live" and not args.allow_real_llm:
        print(
            json.dumps(
                {
                    "error": "final_answer_eval_requires_allow_real_llm",
                    "message": "Pass --allow-real-llm for --agent-mode full_live.",
                }
            ),
            file=sys.stderr,
        )
        return 2

    if args.fallback_to_full_live and not args.allow_real_llm:
        print(
            json.dumps(
                {
                    "error": "fallback_requires_allow_real_llm",
                    "message": "Pass --allow-real-llm when using --fallback-to-full-live.",
                }
            ),
            file=sys.stderr,
        )
        return 2

    cases = load_golden_answer_cases(args.cases)
    selected = _select_cases(cases, args)
    if not selected:
        print("No cases selected.", file=sys.stderr)
        return 2

    settings = get_settings()
    database = None
    if agent_mode == "full_live" or args.require_mongo or args.fallback_to_full_live:
        database = await resolve_eval_database(settings=settings, require=args.require_mongo or agent_mode == "full_live")
        if database is None and (args.require_mongo or agent_mode == "full_live"):
            print("MongoDB unavailable; cannot run final answer eval.", file=sys.stderr)
            return 2

    if not args.skip_warmup:
        warmup_retrieval_caches(settings=settings)

    lab_overrides = _load_lab_config(args.lab_config)
    trace_config: TraceConfig | None = None
    trace_output_dir: Path | None = None

    if args.trace_on_failure:
        failure_dir = args.trace_failure_dir or "tmp/final_answer_eval_failed_traces"
        trace_output_dir = validate_trace_dir(failure_dir)
        trace_config = TraceConfig(
            trace_on_failure=True,
            trace_failure_dir=trace_output_dir,
            level=args.trace_level,  # type: ignore[arg-type]
            include_trace_events_in_report=bool(args.include_trace_events),
            unsafe_local_raw_llm_logs=bool(args.unsafe_local_raw_llm_logs),
            raw_llm_log_max_chars=int(args.raw_llm_log_max_chars),
        )
    elif args.trace_dir:
        trace_output_dir = validate_trace_dir(args.trace_dir)
        validate_unsafe_raw_llm_mode(
            trace_dir=trace_output_dir,
            enabled=bool(args.unsafe_local_raw_llm_logs),
        )
        if args.unsafe_local_raw_llm_logs:
            print(
                "WARNING: --unsafe-local-raw-llm-logs is enabled. "
                "Raw prompts/model outputs will be written under "
                f"{trace_output_dir / 'raw_llm'}. DO NOT COMMIT OR SHARE.",
                file=sys.stderr,
            )
        trace_config = TraceConfig(
            trace_dir=trace_output_dir,
            level=args.trace_level,  # type: ignore[arg-type]
            include_trace_events_in_report=bool(args.include_trace_events),
            unsafe_local_raw_llm_logs=bool(args.unsafe_local_raw_llm_logs),
            raw_llm_log_max_chars=int(args.raw_llm_log_max_chars),
        )

    concurrency = max(1, min(int(args.concurrency or 1), 4))
    progress = SingleBarProgress(
        total=max(1, len(selected)),
        desc="Final answer eval",
        disable=args.no_progress,
    )

    run_started = time.perf_counter()
    ordered_results: list = [None] * len(selected)
    ordered_traces: list = [None] * len(selected)
    ordered_timings: list[CaseTiming | None] = [None] * len(selected)
    traces_written: list = []

    try:
        if concurrency == 1:
            for index, case in enumerate(selected):
                progress.set_phase(f"Final answer eval [{index + 1}/{len(selected)}] {case.id}")
                _, result, case_trace, timing = await _run_one_case(
                    index,
                    case,
                    database=database,
                    args=args,
                    lab_overrides=lab_overrides,
                    trace_config=trace_config,
                    agent_mode=agent_mode,
                )
                ordered_results[index] = result
                ordered_timings[index] = timing
                if case_trace is not None and trace_output_dir is not None:
                    if _should_write_trace(result.status, trace_on_failure=bool(args.trace_on_failure)):
                        write_case_trace_files(case_trace, trace_dir=trace_output_dir)
                        traces_written.append(case_trace)
                        result_trace_path = str(trace_output_dir / f"{case.id}.json")
                    else:
                        result_trace_path = None
                    if result_trace_path and result.status != "passed":
                        result.warnings = [*result.warnings, f"tracePath:{result_trace_path}"]
                if result.status != "passed":
                    detail = "; ".join(result.failures or result.warnings or [])
                    SingleBarProgress.write(f"[{result.status}] {case.id}: {detail}")
                progress.advance(1)
        else:
            semaphore = asyncio.Semaphore(concurrency)

            async def _guarded(index: int, case) -> tuple[int, object, object | None, CaseTiming]:
                async with semaphore:
                    progress.set_phase(f"Final answer eval [{index + 1}/{len(selected)}] {case.id}")
                    outcome = await _run_one_case(
                        index,
                        case,
                        database=database,
                        args=args,
                        lab_overrides=lab_overrides,
                        trace_config=trace_config,
                        agent_mode=agent_mode,
                    )
                    progress.advance(1)
                    return outcome

            outcomes = await asyncio.gather(
                *[_guarded(index, case) for index, case in enumerate(selected)]
            )
            for index, result, case_trace, timing in sorted(outcomes, key=lambda item: item[0]):
                ordered_results[index] = result
                ordered_timings[index] = timing
                if case_trace is not None and trace_output_dir is not None:
                    if _should_write_trace(result.status, trace_on_failure=bool(args.trace_on_failure)):
                        write_case_trace_files(case_trace, trace_dir=trace_output_dir)
                        traces_written.append(case_trace)
                        if result.status != "passed":
                            result.warnings = [
                                *result.warnings,
                                f"tracePath:{trace_output_dir / f'{result.case_id}.json'}",
                            ]
                if result.status != "passed":
                    detail = "; ".join(result.failures or result.warnings or [])
                    SingleBarProgress.write(f"[{result.status}] {result.case_id}: {detail}")
    finally:
        progress.close()

    results = [item for item in ordered_results if item is not None]
    timings = [item for item in ordered_timings if item is not None]

    if trace_output_dir is not None and traces_written:
        write_trace_index(traces_written, trace_dir=trace_output_dir)

    total_run_ms = (time.perf_counter() - run_started) * 1000.0
    timing_summary = aggregate_timing_summary(timings, total_run_ms=total_run_ms)

    threshold_file = load_eval_thresholds(args.thresholds)
    suite_thresholds = resolve_suite_thresholds(threshold_file, cases_path=args.cases)

    report = build_final_answer_eval_report(
        results,
        judge_mode=args.judge_mode,  # type: ignore[arg-type]
        allow_real_llm=bool(args.allow_real_llm),
        include_full_answers=bool(args.include_full_answers),
        agent_mode=agent_mode,
        timings=timings,
        timing_summary=timing_summary,
        wiki_cache_stats=cache_stats(),
    )
    threshold_result = evaluate_thresholds(report, thresholds=suite_thresholds)
    report["thresholdEvaluation"] = threshold_result

    if trace_config is not None and args.include_trace_events:
        trace_by_case = {trace.case_id: trace for trace in traces_written}
        for item in report.get("caseResults") or []:
            trace = trace_by_case.get(str(item.get("caseId")))
            if trace is not None:
                item["traceEvents"] = compact_trace_events_for_report(trace.events)

    markdown = render_final_answer_markdown_report(
        report,
        include_full_answers=bool(args.include_full_answers),
    )

    if args.output:
        output_path = Path(args.output)
        output_path.parent.mkdir(parents=True, exist_ok=True)
        output_path.write_text(json.dumps(report, indent=2, ensure_ascii=False), encoding="utf-8")
    if args.markdown:
        markdown_path = Path(args.markdown)
        markdown_path.parent.mkdir(parents=True, exist_ok=True)
        markdown_path.write_text(markdown, encoding="utf-8")

    summary = report.get("summary") or {}
    print(
        json.dumps(
            {
                "summary": summary,
                "timingSummary": timing_summary,
                "thresholdPassed": threshold_result.get("passed"),
            },
            ensure_ascii=False,
        )
    )

    await close_eval_database()

    failed = int(summary.get("failed_cases") or 0)
    errored = int(summary.get("errored_cases") or 0)
    exit_code = 0
    if args.fail_on_failed_cases and (failed or errored):
        exit_code = 1
    if args.fail_on_threshold_violation and not threshold_result.get("passed", True):
        exit_code = 1
    return exit_code


def main() -> None:
    args = _parse_args()
    raise SystemExit(asyncio.run(_main_async(args)))


if __name__ == "__main__":
    main()
