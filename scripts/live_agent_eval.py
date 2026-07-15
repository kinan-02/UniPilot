#!/usr/bin/env python3
"""Live eval: calls run_agent_turn() directly against the real LLM.

Usage (from services/ai/):
    python ../../scripts/live_agent_eval.py

Requires OPENAI_API_KEY (or equivalent) in the environment or .env.
"""

from __future__ import annotations

import asyncio
import json
import logging
import os
import sys
import time
from pathlib import Path

# Make sure app imports work
sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "services" / "ai"))

os.environ.setdefault("ACADEMIC_WIKI_PATH", str(Path(__file__).resolve().parents[1] / "services" / "data-engineering" / "data" / "catalog_valut" / "catalog_valut" / "wiki"))
os.environ.setdefault("ACADEMIC_TECHNION_RAW_DIR", str(Path(__file__).resolve().parents[1] / "services" / "data-engineering" / "data" / "raw" / "technion"))

from app.agent_core.reasoning.llm_adapter import ChatLLMAdapter
from app.agent_core.reasoning.reasoning_budget import BudgetedLLMAdapter
from app.agent_core.complexity_classifier.complexity_classifier import classify_complexity
from app.agent_core.reasoning_effort import build_reasoning_config
from app.agent_core.request_understanding.request_understanding import understand_request
from app.agent_core.roles.roster import build_default_role_roster
from app.agent_core.tools.default_registry import build_default_tool_registry
from app.agent_core.turn import run_agent_turn

logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(name)s: %(message)s")
logger = logging.getLogger("live_eval")

# ── Eval questions spanning all 4 complexity tiers ──────────────────────
EVAL_QUESTIONS = [
    {
        "question": "What is course 234218?",
        "expected_tier": "low",
        "description": "Simple fact lookup - single course entity",
    },
    {
        "question": "What are my remaining graduation requirements?",
        "expected_tier": "low",
        "description": "Direct data lookup - student progress",
    },
    {
        "question": "Am I eligible to take Data Structures next semester?",
        "expected_tier": "medium",
        "description": "Cross-referencing - prerequisites vs student record",
    },
    {
        "question": "If I fail Linear Algebra this semester, how does that affect my graduation timeline?",
        "expected_tier": "high",
        "description": "Hypothetical reasoning - cascading consequences",
    },
    {
        "question": "Write me a poem about graduation",
        "expected_tier": "out_of_scope",
        "description": "Out-of-scope - boundary handler should reject",
    },
]


async def run_single_eval(question_data: dict, adapter_factory, idx: int) -> dict:
    """Run a single question through the agent and collect metrics."""
    question = question_data["question"]
    expected_tier = question_data["expected_tier"]

    logger.info("=" * 70)
    logger.info("Q%d: %s", idx + 1, question)
    logger.info("Expected tier: %s | %s", expected_tier, question_data["description"])
    logger.info("-" * 70)

    adapter = adapter_factory()
    streaming_queue: asyncio.Queue[str | None] = asyncio.Queue()
    streamed_chunks: list[str] = []

    # Collect streamed text in the background
    async def collect_chunks():
        while True:
            chunk = await streaming_queue.get()
            if chunk is None:
                break
            streamed_chunks.append(chunk)

    plan_id = f"eval-{idx + 1}"
    role_roster = build_default_role_roster()
    tool_registry = build_default_tool_registry()

    t0 = time.perf_counter()

    # First, run RU separately to get the complexity tier
    ru_t0 = time.perf_counter()
    understanding = await understand_request(
        original_user_message=question,
        llm_adapter=adapter,
        block_id=f"{plan_id}-ru",
    )
    ru_elapsed = time.perf_counter() - ru_t0
    logger.info("  RU: in_scope=%s, sub_asks=%s (%.1fs)", understanding.in_scope, understanding.sub_asks, ru_elapsed)

    # Classify complexity (only if in-scope)
    actual_tier = "out_of_scope"
    reasoning_config = None
    cc_elapsed = 0.0
    if understanding.in_scope:
        cc_t0 = time.perf_counter()
        actual_tier = await classify_complexity(
            sub_asks=understanding.sub_asks,
            constraints=understanding.constraints,
            open_questions=understanding.open_questions,
            implies_action_request=understanding.implies_action_request,
            confidence=understanding.confidence,
            llm_adapter=adapter,
            block_id=f"{plan_id}-cc",
        )
        cc_elapsed = time.perf_counter() - cc_t0
        reasoning_config = build_reasoning_config(actual_tier)
        logger.info("  CC: tier=%s (%.1fs)", actual_tier, cc_elapsed)
        logger.info("  Config: planner_thinking=%s, effort=%s, timeout=%.0fs, max_rounds=%d",
                     reasoning_config.planner_thinking_enabled,
                     reasoning_config.planner_reasoning_effort,
                     reasoning_config.planner_timeout,
                     reasoning_config.max_planner_invocations)
    else:
        logger.info("  CC: SKIPPED (out of scope)")

    # Now run the full turn
    adapter2 = adapter_factory()
    chunk_task = asyncio.create_task(collect_chunks())

    turn_t0 = time.perf_counter()
    try:
        understanding2, state, final_entry, clarification = await asyncio.wait_for(
            run_agent_turn(
                original_user_message=question,
                user_id="eval-user-1",
                llm_adapter=adapter2,
                role_roster=role_roster,
                tool_registry=tool_registry,
                plan_id=plan_id,
                streaming_queue=streaming_queue,
            ),
            timeout=120.0,
        )
    except asyncio.TimeoutError:
        await streaming_queue.put(None)
        await chunk_task
        total_elapsed = time.perf_counter() - t0
        logger.error("  TIMEOUT after %.1fs", total_elapsed)
        return {
            "question": question,
            "expected_tier": expected_tier,
            "actual_tier": actual_tier,
            "status": "TIMEOUT",
            "total_seconds": round(total_elapsed, 1),
        }

    await streaming_queue.put(None)
    await chunk_task
    turn_elapsed = time.perf_counter() - turn_t0
    total_elapsed = time.perf_counter() - t0

    # Extract answer
    answer = ""
    if final_entry:
        answer = final_entry.data.get("answer_text", "")
    elif clarification:
        answer = clarification

    # Log results
    status = "OK"
    if not understanding2.in_scope:
        status = "OUT_OF_SCOPE"
    elif final_entry is None and clarification:
        status = "CLARIFICATION"
    elif final_entry is None:
        status = "NO_ANSWER"

    logger.info("  Status: %s", status)
    logger.info("  Steps: %d | Streamed chunks: %d", len(state.entries), len(streamed_chunks))
    logger.info("  Turn time: %.1fs | Total: %.1fs", turn_elapsed, total_elapsed)
    logger.info("  Answer (first 200 chars): %s", answer[:200])
    logger.info("")

    return {
        "question": question,
        "expected_tier": expected_tier,
        "actual_tier": actual_tier,
        "status": status,
        "ru_seconds": round(ru_elapsed, 1),
        "cc_seconds": round(cc_elapsed, 1),
        "turn_seconds": round(turn_elapsed, 1),
        "total_seconds": round(total_elapsed, 1),
        "steps": len(state.entries),
        "streamed_chunks": len(streamed_chunks),
        "answer_preview": answer[:300],
        "tier_match": (expected_tier == actual_tier) or (expected_tier == "out_of_scope" and not understanding2.in_scope),
    }


async def main():
    logger.info("======================================================================")
    logger.info("              UniPilot Agent -- Live Evaluation Run                    ")
    logger.info("======================================================================")
    logger.info("")

    def adapter_factory():
        return BudgetedLLMAdapter(ChatLLMAdapter(), max_calls=30)

    results = []
    for i, q in enumerate(EVAL_QUESTIONS):
        try:
            result = await run_single_eval(q, adapter_factory, i)
            results.append(result)
        except Exception as e:
            logger.error("Q%d CRASHED: %s", i + 1, e, exc_info=True)
            results.append({
                "question": q["question"],
                "expected_tier": q["expected_tier"],
                "status": "CRASHED",
                "error": str(e),
            })

    # Summary table
    logger.info("=" * 70)
    logger.info("SUMMARY")
    logger.info("=" * 70)
    logger.info("%-4s %-12s %-12s %-15s %-8s %-6s", "#", "Expected", "Actual", "Status", "Time", "Match")
    logger.info("-" * 70)
    for i, r in enumerate(results):
        logger.info("%-4d %-12s %-12s %-15s %-8s %-6s",
                     i + 1,
                     r.get("expected_tier", "?"),
                     r.get("actual_tier", "?"),
                     r.get("status", "?"),
                     f"{r.get('total_seconds', '?')}s",
                     "Y" if r.get("tier_match") else "N")
    logger.info("=" * 70)

    # Write JSON report
    report_path = Path(__file__).resolve().parent / "live_eval_report.json"
    with open(report_path, "w") as f:
        json.dump(results, f, indent=2, ensure_ascii=False)
    logger.info("Report written to: %s", report_path)


if __name__ == "__main__":
    asyncio.run(main())
