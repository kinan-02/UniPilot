"""V2 live PLANNING eval -- the questions a student actually asks an advisor.

The 10-case correctness eval (`test_v2_ise_correctness.py`) is mostly single-fact
retrieval: one credit total, one eligibility check, one offering label. These six
cases are multi-step academic planning over the SAME seeded ISE student -- the
work an advisor does, where the answer is a conclusion drawn from several facts
rather than a field read out of a record.

They also cover a hole the older set could not reach: the fixture defined a spring
plan and never seeded it, so "is my registration valid?" -- the single most common
planning question there is -- had no data behind it. `ise_planning_fixture` seeds
it; see that module for the shape and provenance.

Ground truth, every value verified against the dev catalog BEFORE the assertion
was written (the standing rule for this fixture -- an eval that asserts an
invented number grades the agent against fiction):

  1 plan_eligibility_sweep -> 2 of the 6 planned courses are NOT eligible:
                              00970800 needs 00940594, 01140051 needs 01130013.
                              Six entities -> the `map` path (§19).
  2 prerequisite_gap       -> the one course standing between the student and
                              00970800 is 00940594.
  3 graduation_audit       -> the track has 29 required courses; 13 done, 16 left.
  4 pace_projection        -> 92.5 credits remain at ~20.8/semester (62.5 over 3),
                              so ~4-5 more semesters. The ESTIMATE is reported,
                              not asserted -- rounding and whether you round up
                              are both defensible; 92.5 is asserted because it is
                              a fact.
  5 load_comparison        -> spring plans 19.0 credits vs 20.5 last semester, so
                              it is LIGHTER. Tests a comparison across two
                              different sources (plan vs transcript).
  6 drop_impact            -> dropping 00960411 (3.5) from the 19.0 plan leaves
                              15.5. A what-if arithmetic over a filtered list.

Deliberately NOT included: "which semester did I do best in?" Verified means
86.00 (2024-1) and credit-weighted 84.46 (2025-1) name DIFFERENT semesters, so
both answers are correct and the case would grade noise.

As in the correctness eval, grounding is the one hard assertion; substantive
claims are reported so a single run shows the whole picture.

Run (needs dev Mongo up + OPENAI creds in the root .env):
    cd services/ai && python -m pytest tests/agent_core/test_v2_ise_planning.py -s -m live -o addopts=""
"""

from __future__ import annotations

import json
import time
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

import pytest

from app.agent_core.loop import run_agent_loop
from app.agent_core.reasoning.llm_client import agent_llm_available
from app.agent_core.response_language import ENGLISH, detect_message_language
from app.agent_core.tools.default_registry import build_default_tool_registry
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

_CASES: list[dict[str, Any]] = [
    {
        # The flagship planning question. Answering it means reading the plan,
        # checking six courses, and REPORTING A PROBLEM -- a correct answer here
        # is bad news, which is exactly what makes it worth asking.
        "name": "plan_eligibility_sweep",
        "question": (
            "I've registered for six courses this spring. Am I actually eligible for all of "
            "them, and if not, which ones are a problem and why?"
        ),
        # The BLOCKING prerequisites are the assertion, not the planned course
        # codes. Run 1 scored 6/8 on an answer that had determined nothing --
        # "I could not determine that any of your listed spring courses are
        # definitely eligible or ineligible" -- because listing the plan back
        # mentions 00970800 and 01140051 for free. 00940594 and 01130013 appear
        # ONLY if eligibility was actually checked, so they are what to assert.
        "must_mention": ["00940594", "01130013"],
        "must_not_mention": [],
        "mentions_all_reported": ["00970800", "01140051"],
        "report_fanout": True,
    },
    {
        "name": "prerequisite_gap",
        "question": "What do I still need to complete before I'm allowed to take course 00970800?",
        "must_mention": ["00940594"],
        "must_not_mention": [],
    },
    {
        "name": "graduation_audit",
        "question": "Of the required courses in my track, how many have I finished and how many are left?",
        "must_mention": ["16"],
        "must_not_mention": [],
        "mentions_all_reported": ["13", "29"],
    },
    {
        # A three-step chain: sum what is earned, derive a per-semester rate over
        # three completed terms, divide the remainder by it. No single tool
        # answers this.
        "name": "pace_projection",
        "question": (
            "I've finished three semesters so far. If I keep taking roughly the same load each "
            "semester, how many more semesters will I need before I can graduate?"
        ),
        "must_mention": ["92.5"],
        "must_not_mention": [],
        "report_semester_estimate": True,
    },
    {
        "name": "load_comparison",
        "question": "Is my course load this spring heavier or lighter than what I took last semester?",
        # "19" was the original assertion and it PASSED on a wrong answer: the
        # agent compared spring against 2024-1 ("5 courses totaling 19.5
        # credits") instead of last semester 2025-1, and "19" is a substring of
        # "19.5". Assert the semester it had to find (20.5) and forbid the one it
        # wrongly used -- a substring assertion on a number is not an assertion.
        "must_mention": ["20.5"],
        "must_not_mention": ["19.5"],
        "mentions_all_reported": ["19.0"],
        # 19.0 < 20.5, so any answer claiming a heavier spring is wrong.
        "must_not_claim": ["heavier", "more credits than", "harder load"],
    },
    {
        "name": "drop_impact",
        "question": "If I drop course 00960411 from this semester, how many credits will I be left with this spring?",
        "must_mention": ["15.5"],
        "must_not_mention": [],
    },
]


def _score_case(case: dict[str, Any], result) -> dict[str, bool]:
    answer = result.answer or ""
    lowered = answer.lower()
    claims: dict[str, bool] = {
        "concluded": result.outcome in ("answered", "clarified", "declined"),
        "grounded (no ungrounded numerals)": not result.ungrounded_numbers,
    }
    if answer.strip():
        claims["answered in English"] = detect_message_language(answer) == ENGLISH
    for token in case["must_mention"]:
        claims[f"mentions {token!r}"] = token in answer
    for token in case["must_not_mention"]:
        claims[f"avoids {token!r}"] = token not in answer
    for token in case.get("mentions_all_reported", []):
        claims[f"names {token!r} [reported]"] = token in answer
    for phrase in case.get("must_not_claim", []):
        claims[f"does not claim {phrase!r}"] = phrase not in lowered
    if case.get("report_fanout"):
        used = {call.get("tool") for step in result.transcript for call in step.get("calls", [])}
        claims["checked all six via map or a sub-loop [reported]"] = bool({"map", "spawn_subtask"} & used)
    if case.get("report_semester_estimate"):
        # 92.5 at ~20.8/semester is 4.44, so 4 or 5 are both defensible; anything
        # else means the rate was not actually derived from the record.
        claims["estimate is 4 or 5 semesters [reported]"] = any(
            f"{n}" in answer for n in ("4", "5")
        )
    return claims


def _print_case(case_name: str, question: str, result, claims: dict[str, bool]) -> None:
    print(f"\n{'=' * 80}\nCASE: {case_name}\nQ: {question}\n{'-' * 80}")
    print("  SUB-ASKS:")
    for sub in result.sub_asks:
        print(f"    - {sub}")
    for step in result.transcript:
        if "error" in step:
            print(f"  turn {step['turn']}: LLM ERROR {step['error']}")
            continue
        if "polish" in step:
            print(f"  [polish] applied={step['polish']['applied']}")
            continue
        if "forced_compose" in step:
            fc = step["forced_compose"]
            print(f"  [forced compose] attempts={fc['attempts']} composed={fc['composed']}")
            continue
        print(f"  turn {step['turn']}: {step.get('thought')}")
        for call in step.get("calls", []):
            payload = json.dumps(call.get("arguments") or {}, ensure_ascii=False, default=str)
            print(f"           -> {call.get('tool')}({payload[:220]})")
        if step.get("rejected_ungrounded"):
            print(f"           >>> REJECTED ungrounded: {step['rejected_ungrounded']}")
        if step.get("completeness_rejected"):
            print(f"           >>> COMPLETENESS rejected: {step['completeness_rejected']}")
    print(f"\n  OUTCOME: {result.outcome}   turns={result.turns} llm_calls={result.llm_calls} "
          f"wall={result.wall_clock_s:.1f}s")
    print(f"  ANSWER: {result.answer}")
    print("  CLAIMS:")
    for claim, ok in claims.items():
        print(f"    [{'PASS' if ok else 'FAIL'}] {claim}")


async def test_v2_ise_planning(ise_planning_student: IsePlanningStudent) -> None:
    registry = build_default_tool_registry()
    scorecard: list[dict[str, Any]] = []
    started = time.monotonic()

    for case in _CASES:
        result = await run_agent_loop(case["question"], ise_planning_student.user_id, registry)
        claims = _score_case(case, result)
        _print_case(case["name"], case["question"], result, claims)
        scorecard.append({
            "case": case["name"],
            "outcome": result.outcome,
            "turns": result.turns,
            "llm_calls": result.llm_calls,
            "wall_clock_s": round(result.wall_clock_s, 1),
            "answer": result.answer,
            "ungrounded": result.ungrounded_numbers,
            "claims": claims,
        })

    print(f"\n{'#' * 80}\nV2 ISE PLANNING SCORECARD ({time.monotonic() - started:.0f}s total)\n{'#' * 80}")
    for row in scorecard:
        passed = sum(1 for ok in row["claims"].values() if ok)
        print(f"  {row['case']:<26} {row['outcome']:<18} "
              f"{passed}/{len(row['claims'])} claims  ({row['turns']}t {row['llm_calls']}c {row['wall_clock_s']}s)")
    # Efficiency is a first-class result, not a footnote: turns and calls are what
    # the loop spends, and a change that answers correctly by wandering twice as
    # long is a regression the claim counts alone cannot show.
    total_turns = sum(row["turns"] for row in scorecard)
    total_calls = sum(row["llm_calls"] for row in scorecard)
    total_wall = sum(row["wall_clock_s"] for row in scorecard)
    print(
        f"\n  TOTALS: {total_turns} turns, {total_calls} llm calls, {total_wall:.0f}s "
        f"({total_turns / len(scorecard):.1f} turns and {total_calls / len(scorecard):.1f} calls per case)"
    )
    _LOG_DIR.mkdir(parents=True, exist_ok=True)
    stamp = datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%SZ")
    path = _LOG_DIR / f"v2_ise_planning-{stamp}.json"
    path.write_text(json.dumps(scorecard, ensure_ascii=False, indent=2, default=str))
    print(f"\n  scorecard written to {path}")

    # Same hard gate as the correctness eval: planning draws more inferences from
    # more facts, so if grounding were going to break anywhere it would be here.
    violations = [(row["case"], row["ungrounded"]) for row in scorecard if row["ungrounded"]]
    assert not violations, f"GROUNDING VIOLATIONS (typed numerals tracing to no fact): {violations}"
