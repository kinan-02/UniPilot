"""Composite ablation -- is a composite an OPTIMIZATION or a PREREQUISITE?

The question this exists to settle, from the 2026-07-19 architecture review:

  Our competence is supposed to come from the loop's ability to compose
  primitives. If instead it comes from having pre-solved each question shape as
  a composite, then the agent is not general -- it is a lookup table with a
  language model in front -- and every new capability (web browsing was the
  proposal) means another round of pre-solving an unbounded space.

The test is direct. Take a question the agent answers reliably, DELETE the
composite that answers it in one call, and run it again against the primitives:

  - still answers, slower  -> the composite was an optimization. The loop can
                              compose. Adding capability is a matter of adding
                              primitives.
  - wanders or exhausts    -> the composite was carrying it. The loop never
                              learned to compose, and the reliability we measure
                              is the tool library's, not the agent's.

Both arms run REPEATS, because the same eval showed 1.2x-4.0x turn spread on
identical input. A single run of each arm would compare two samples of noise --
the mistake made repeatedly while investigating this, and the reason the harness
takes N rather than assuming one is enough.

A PREDICTION, recorded before the first run so it can be wrong (2026-07-19):
`eligibility` and `prerequisite_gap` survive at ~2-3x the turns;
`graduation_audit` and `drop_impact` do not.

Run (needs dev Mongo up + OPENAI creds in the root .env):
    cd services/ai && python -m pytest tests/agent_core/test_composite_ablation.py -s -m live -o addopts=""

    ABLATION_REPEATS=5 python -m pytest ...   # more samples, more money
"""

from __future__ import annotations

import json
import os
import statistics
import time
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

import pytest

from app.agent_core.loop import run_agent_loop
from app.agent_core.reasoning.llm_client import agent_llm_available
from app.agent_core.loop.constitution import build_constitution, build_tool_catalog
from app.agent_core.tools.default_registry import build_default_tool_registry
from app.agent_core.tools.registry import ToolRegistry
from tests.agent_core.ise_planning_fixture import (  # noqa: F401 -- fixture injection
    IsePlanningStudent,
    _fresh_mongo_client_per_test,
    ise_planning_student,
    ise_student,
)

pytestmark = [
    pytest.mark.live,
    pytest.mark.skipif(not agent_llm_available(), reason="no LLM credentials configured (OPENAI_API_KEY)"),
]

_LOG_DIR = Path(__file__).resolve().parent / "live_eval_logs"
_REPEATS = int(os.environ.get("ABLATION_REPEATS", "3"))

# Each case pairs a question with the composite(s) that answer it directly. The
# `holds` token is the one fact that decides whether the ablated run is still
# CORRECT -- an ablation that answers fluently with the wrong number has failed,
# and turn count alone would score it as a pass.
_CASES: list[dict[str, Any]] = [
    {
        "name": "eligibility_00960211",
        "question": "Am I eligible to take course 00960211 based on my transcript?",
        "ablate": ["check_eligibility"],
        "holds": "00940224",  # the prerequisite it must still identify
        "note": "One composite call vs: read the course, read the transcript, compare prerequisites.",
    },
    {
        "name": "prerequisite_gap",
        "question": "What do I still need to complete before I'm allowed to take course 00970800?",
        "ablate": ["check_eligibility", "find_requirement_substitutes"],
        "holds": "00940594",
        "note": "The gap is one course; without the composite it must be derived from the prereq tree.",
    },
    {
        "name": "graduation_audit",
        "question": "Of the required courses in my track, how many have I finished and how many are left?",
        "ablate": ["audit_graduation_progress"],
        "holds": "16",  # 29 required, 13 done, 16 left
        "note": "Needs the track requirement list intersected with the transcript, then counted.",
    },
    {
        "name": "drop_impact",
        "question": "If I drop course 00960411 from this semester, how many credits will I be left with this spring?",
        "ablate": ["simulate_course_disruption"],
        "holds": "15.5",  # 19.0 planned - 3.5
        "note": "Filter the plan, subtract, report. Arithmetic the loop owns primitives for.",
    },
]


def _registry_without(excluded: list[str]) -> ToolRegistry:
    """The default registry minus `excluded`, rebuilt rather than mutated."""
    full = build_default_tool_registry()
    missing = [name for name in excluded if not full.has(name)]
    assert not missing, f"cannot ablate tools that do not exist: {missing}"

    ablated = ToolRegistry()
    for name in full.names():
        if name not in excluded:
            ablated.register(full.get(name))
    return ablated


def _prompt_leaks(registry: ToolRegistry, excluded: list[str]) -> dict[str, int]:
    """Ablated tool names the system prompt still mentions, and how often.

    `build_tool_catalog` iterates the registry, so the tool's own entry does
    vanish -- but two other things in `constitution.py` hardcode names: the
    cross-references inside OTHER tools' NOTEs ("get_course_profile or
    check_eligibility ..."), and the worked examples in the constitution body.

    This matters because it changes the experiment. A clean ablation asks "can
    the loop compose this from primitives"; a leaky one asks "can it recover
    after being told about a tool that isn't there" -- a different and easier
    question to fail. Measured per case and reported, rather than assumed away:
    the first version of this harness asserted the prompt was clean and it was
    not, for exactly one of the four cases.
    """
    prompt = build_constitution("ablation-probe", build_tool_catalog(registry))
    return {name: prompt.count(name) for name in excluded if name in prompt}


async def _run_arm(case: dict[str, Any], registry: ToolRegistry, user_id: str, arm: str) -> list[dict[str, Any]]:
    rows: list[dict[str, Any]] = []
    for attempt in range(1, _REPEATS + 1):
        result = await run_agent_loop(case["question"], user_id, registry)
        answered = result.outcome == "answered"
        row = {
            "arm": arm,
            "attempt": attempt,
            "outcome": result.outcome,
            "turns": result.turns,
            "llm_calls": result.llm_calls,
            "wall_clock_s": round(result.wall_clock_s, 1),
            # Correct, not merely fluent: an ablation that answers confidently
            # with the wrong number must not score as a survival.
            "holds_fact": case["holds"] in result.answer,
            "grounded": not result.ungrounded_numbers,
            "answer": result.answer,
        }
        rows.append(row)
        status = "OK " if answered and row["holds_fact"] else "FAIL"
        print(
            f"    [{arm:8}] {attempt}/{_REPEATS}  {status}  {result.outcome:17} "
            f"turns={result.turns:2} calls={result.llm_calls:2} {result.wall_clock_s:5.1f}s "
            f"holds({case['holds']})={row['holds_fact']}"
        )
    return rows


def _summarize(rows: list[dict[str, Any]]) -> dict[str, Any]:
    turns = [r["turns"] for r in rows]
    return {
        "n": len(rows),
        "answered": sum(1 for r in rows if r["outcome"] == "answered"),
        "correct": sum(1 for r in rows if r["holds_fact"]),
        "turns_median": statistics.median(turns),
        "turns_min": min(turns),
        "turns_max": max(turns),
        "calls_median": statistics.median([r["llm_calls"] for r in rows]),
    }


def _verdict(base: dict[str, Any], abl: dict[str, Any]) -> str:
    """What the pair of arms says about the composite.

    "Optimization" requires the ablated arm to stay CORRECT, not merely to
    finish -- and the cost multiple is reported rather than thresholded, because
    what counts as an acceptable slowdown is a judgement about the product, not
    something this harness should decide.
    """
    if abl["correct"] == 0:
        return "PREREQUISITE -- the loop cannot answer this without the composite"
    if abl["correct"] < abl["n"]:
        return f"FRAGILE -- correct {abl['correct']}/{abl['n']} without the composite"
    multiple = abl["turns_median"] / max(base["turns_median"], 1)
    return f"OPTIMIZATION -- still correct without it, at {multiple:.1f}x the turns"


async def test_composite_ablation(ise_planning_student: IsePlanningStudent) -> None:
    started = time.monotonic()
    report: list[dict[str, Any]] = []

    for case in _CASES:
        print(f"\n{'=' * 84}\nCASE {case['name']}   ablating {case['ablate']}")
        print(f"Q: {case['question']}\n{case['note']}\n{'-' * 84}")

        ablated_registry = _registry_without(case["ablate"])
        leaks = _prompt_leaks(ablated_registry, case["ablate"])
        if leaks:
            print(f"  CAVEAT: the prompt still mentions {leaks} -- this case measures RECOVERY")
            print("          from a described-but-absent tool, not composition from scratch.")

        baseline = await _run_arm(case, build_default_tool_registry(), ise_planning_student.user_id, "baseline")
        ablated = await _run_arm(case, ablated_registry, ise_planning_student.user_id, "ablated")

        base_summary, abl_summary = _summarize(baseline), _summarize(ablated)
        verdict = _verdict(base_summary, abl_summary)
        print(f"  -> {verdict}")
        report.append({
            "case": case["name"],
            "ablated_tools": case["ablate"],
            "baseline": base_summary,
            "ablated": abl_summary,
            "verdict": verdict,
            "prompt_leaks": leaks,
            "runs": baseline + ablated,
        })

    print(f"\n{'=' * 84}\nABLATION SUMMARY   ({_REPEATS} runs per arm, {time.monotonic() - started:.0f}s total)")
    print(f"{'case':26} {'baseline':>22} {'ablated':>22}  verdict")
    print("-" * 110)
    for row in report:
        base, abl = row["baseline"], row["ablated"]
        base_cell = f"{base['correct']}/{base['n']} ok, {base['turns_median']:.0f}t"
        abl_cell = f"{abl['correct']}/{abl['n']} ok, {abl['turns_median']:.0f}t"
        caveat = "  [leaky prompt]" if row["prompt_leaks"] else ""
        print(f"{row['case']:26} {base_cell:>22} {abl_cell:>22}  {row['verdict']}{caveat}")

    _LOG_DIR.mkdir(parents=True, exist_ok=True)
    stamp = datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%SZ")
    path = _LOG_DIR / f"composite_ablation-{stamp}.json"
    path.write_text(json.dumps(report, ensure_ascii=False, indent=2), encoding="utf-8")
    print(f"\nwrote {path}")

    # The harness MEASURES; it does not gate. A composite that turns out to be
    # load-bearing is a finding to act on, not a build to break -- failing here
    # would only pressure someone into deleting the case. The one thing that IS
    # asserted is that the baseline works, because a baseline that cannot answer
    # makes the ablated arm meaningless.
    broken = [row["case"] for row in report if row["baseline"]["correct"] == 0]
    assert not broken, f"baseline could not answer {broken} -- ablation results are not interpretable"
