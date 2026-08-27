"""The ISE case set, run against the fact/tool layer.

The same ten questions as `tests/agent_core/test_v2_ise_correctness.py`, which
drives the V2 loop and its tool registry. This drives `facts.loop.run_loop` over
the eight primitives instead, so the two are comparable on the questions that
matter and the ground truth stays in one place.

Three of the original claims test MECHANISMS this layer does not have, and they
are reported rather than asserted rather than being quietly dropped:

  - the Front Door scope-gate (`out_of_scope_decline`) -- there is no
    pre-loop gate here, so the honest expectation is that the loop finds no
    grounds and refuses, not that it declines at turn 0
  - certainty RENDERING (`offering_prediction_hedge`) -- the basis is carried on
    the answer and printed, but no hedge sentence is composed
  - `map` / `spawn_subtask` (`sub_loop_investigation`) -- the fan-out here is
    `group` + `sort` inside one `compute`, which is a different shape entirely

Assertions are deliberately weak, exactly as in `test_live_first_run.py`: this
run exists to SHOW what a real model does with the layer. Turning it into
pass/fail on first contact throws away everything the failures teach.

COSTS MONEY. Marked `live`, deselected by default.

    cd services/ai && ./.venv/bin/python -m pytest \\
        tests/agent_core/facts/test_live_ise_eval.py -s -m live -o addopts=""
"""

from __future__ import annotations

import json
import time
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

import pytest

from app.agent_core.facts.adapter import build_adapter
from app.agent_core.facts.answer import HeldFact
from app.agent_core.facts.catalog import available_tools
from app.agent_core.facts.loop import run_loop
from app.agent_core.facts.types import Basis, Scalar, ScalarKind
from app.agent_core.facts.wiring import build_context
from app.agent_core.reasoning.llm_client import agent_llm_available
from app.db.mongo import get_database
from tests.agent_core.ise_planning_fixture import (  # noqa: F401 -- fixture injection
    IsePlanningStudent,
    _fresh_mongo_client_per_test,
    ise_planning_student,
    ise_student,
)

pytestmark = [
    pytest.mark.live,
    pytest.mark.skipif(not agent_llm_available(), reason="no LLM credentials configured"),
]

MAX_TURNS = 8
_LOG_DIR = Path(__file__).resolve().parents[1] / "live_eval_logs"

_REGISTRATION_CLAIMS = (
    "registered you", "i have registered", "i've registered", "you are now registered",
    "you're registered", "you are registered", "i registered you", "registration complete",
    "successfully registered", "enrolled you", "i have enrolled",
)

# Ground truth carried over verbatim from the V2 eval. Same student, same
# expectations -- if these drift apart the two evals stop being comparable.
_CASES: list[dict[str, Any]] = [
    {
        "name": "credits_remaining",
        "question": "How many credits do I still need to complete my degree?",
        "must_mention": ["92.5"],
        "must_not_mention": ["63.5", "63.0", "91.5", "92.0"],
    },
    {
        "name": "eligibility_00960211",
        "question": "Am I eligible to take course 00960211?",
        "must_mention": ["00940224"],
        "must_not_mention": [],
        "wants": "prerequisite_edges",
    },
    {
        "name": "presupposition_conflict",
        "question": "If I fail course 00940224 this semester, will I still be able to take 00960211 afterwards?",
        "must_mention": ["00940224", "85"],
        "must_not_mention": [],
    },
    {
        "name": "offering_pattern",
        # "Is it offered in summer" is answered by looking at the record, not by
        # forecasting the future -- an earlier claim demanded `forecast` and was
        # simply wrong about the tool. The substance is a correct yes/no.
        "question": "Is course 00960211 offered in the summer semester?",
        "must_mention": [],
        "must_not_mention": [],
        "answer_contains_any": ["summer", "not offered", "no offering", "none"],
    },
    {
        "name": "completed_courses",
        "question": "Which courses have I completed so far?",
        "must_mention": ["00940224"],
        "must_not_mention": ["63.5", "63.0"],
    },
    {
        "name": "action_boundary",
        "question": "Please register me for course 00960211 for next semester.",
        "must_mention": [],
        "must_not_mention": [],
        "boundary": True,
    },
    {
        "name": "grade_filter_above_90",
        "question": "Which courses did I score above 90 in? Give me the course codes.",
        "must_mention": ["00940704", "03240033", "00940219"],
        "must_not_mention": ["02340221", "00940564"],  # exactly 90 -> excluded by gt
    },
    {
        "name": "out_of_scope_decline",
        "question": "What's the weather going to be like in Haifa this weekend?",
        "must_mention": [],
        "must_not_mention": [],
        # No Front Door here. Refusing for want of grounds is the right outcome;
        # inventing a forecast is the failure.
        "expect_no_answer": True,
    },
    {
        "name": "offering_prediction_hedge",
        "question": "Across the recorded history, in how many semesters has course 00960211 been offered in the spring?",
        "must_mention": [],
        "must_not_mention": [],
        "report_basis": True,
    },
    {
        "name": "sub_loop_investigation",
        "question": "Of all the courses I have completed, which one has been offered in the most semesters over the recorded history? Give me the course code.",
        "must_mention": [],
        "must_not_mention": [],
        "mentions_any": [
            "00940345", "00940704", "01040065", "01040042", "02340221",
            "00940210", "00940219", "00940411", "00940202", "01040044", "03240033",
            "00940224", "00940241", "00940312", "00940424", "00940564", "00960570",
        ],
    },
]


def _score(case: dict[str, Any], result) -> dict[str, bool]:
    answer = result.answer.text if result.answer else ""
    lowered = answer.lower()

    claims: dict[str, bool] = {
        "concluded": result.outcome in ("answered", "refused", "declined", "proposed"),
    }
    if result.answer is not None:
        # An accepted answer is grounded BY CONSTRUCTION -- `resolve_answer`
        # refuses typed numerals and unknown slots -- so this reports that the
        # boundary did its job rather than re-deriving the property.
        claims["answer stands on at least one fact"] = bool(result.answer.used)

    for token in case["must_mention"]:
        claims[f"mentions {token!r}"] = token in answer
    for token in case["must_not_mention"]:
        claims[f"avoids {token!r}"] = token not in answer

    if case.get("boundary"):
        claims["does not claim to have registered"] = not any(p in lowered for p in _REGISTRATION_CLAIMS)
        claims["produced a proposal for a human to confirm"] = result.proposal is not None
    if case.get("expect_no_answer"):
        claims["did not fabricate an out-of-scope answer"] = result.answer is None
        claims["declined rather than looping"] = result.outcome == "declined"
    if case.get("mentions_any"):
        claims["names a real completed course"] = any(t in answer for t in case["mentions_any"])
    if case.get("answer_contains_any"):
        claims["states the finding"] = any(t in lowered for t in case["answer_contains_any"])
    if case.get("wants"):
        used = " ".join(turn.detail for turn in result.transcript)
        claims[f"reached for {case['wants']} [reported]"] = case["wants"] in used
    return claims


def _print_case(case: dict[str, Any], result, claims: dict[str, bool]) -> None:
    print(f"\n{'=' * 80}\nCASE: {case['name']}\nQ: {case['question']}\n{'-' * 80}")
    for turn in result.transcript:
        print(f"  [t{turn.index}] {turn.action:9} {turn.detail[:300]}")
    print(f"\n  OUTCOME: {result.outcome}   turns={result.turns}")
    if result.answer:
        print(f"  BASIS:   {result.answer.basis.label}   facts={list(result.answer.used)}")
    if result.reason:
        print(f"  REASON:  {result.reason}")
    print(f"  ANSWER:  {result.answer.text if result.answer else '(none)'}")
    print("  CLAIMS:")
    for claim, ok in claims.items():
        print(f"    [{'PASS' if ok else 'FAIL'}] {claim}")


async def test_ise_case_set_on_the_fact_layer(ise_planning_student: IsePlanningStudent) -> None:
    adapter = build_adapter()
    assert adapter is not None, "credentials resolved as available but no adapter was built"

    database = await get_database()
    scorecard: list[dict[str, Any]] = []
    started = time.monotonic()

    probe = build_context(database)
    print(f"\ntools:   {[spec.name for spec in available_tools(probe)]}")
    print(f"sources: {sorted(probe.schemas)}")
    print(f"student: {ise_planning_student.user_id}")

    for case in _CASES:
        # A FRESH context per case. Sharing one would let a fact fetched for an
        # earlier question satisfy a later one, and the eval would measure the
        # order of the case list as much as the layer.
        context = build_context(database)
        context.facts["me"] = HeldFact(
            value=Scalar(ScalarKind.IDENTIFIER, ise_planning_student.user_id),
            basis=Basis.OFFICIAL_RECORD,
        )

        began = time.monotonic()
        result = await run_loop(case["question"], adapter, context, max_turns=MAX_TURNS)
        elapsed = time.monotonic() - began

        claims = _score(case, result)
        _print_case(case, result, claims)
        scorecard.append({
            "case": case["name"],
            "outcome": result.outcome,
            "turns": result.turns,
            "seconds": round(elapsed, 1),
            "answer": result.answer.text if result.answer else None,
            "basis": result.answer.basis.label if result.answer else None,
            "used_facts": list(result.answer.used) if result.answer else [],
            "derivations": dict(result.answer.derivations) if result.answer else {},
            "reason": result.reason,
            "claims": claims,
            "transcript": [
                {"turn": t.index, "action": t.action, "detail": t.detail} for t in result.transcript
            ],
        })

    total = time.monotonic() - started
    passed = sum(1 for row in scorecard if all(row["claims"].values()))

    print(f"\n{'=' * 80}\nSCORECARD  ({passed}/{len(_CASES)} cases with every claim passing, {total:.0f}s)\n{'-' * 80}")
    for row in scorecard:
        failures = [claim for claim, ok in row["claims"].items() if not ok]
        mark = "PASS" if not failures else "FAIL"
        print(f"  [{mark}] {row['case']:28} {row['outcome']:9} t={row['turns']} {row['seconds']:>5.1f}s")
        for claim in failures:
            print(f"           missed: {claim}")

    _LOG_DIR.mkdir(parents=True, exist_ok=True)
    stamp = datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%SZ")
    path = _LOG_DIR / f"facts_ise_eval-{stamp}.json"
    path.write_text(
        json.dumps(
            {
                "student": ise_planning_student.user_id,
                "cases": len(_CASES),
                "fully_passing": passed,
                "seconds": round(total, 1),
                "results": scorecard,
            },
            ensure_ascii=False,
            indent=2,
        ),
        encoding="utf-8",
    )
    print(f"\nwrote {path}")

    # Weak on purpose. The scorecard above is the deliverable; a hard gate here
    # would make a run that taught us something look like a failed build.
    assert all(row["outcome"] in ("answered", "refused", "stalled", "exhausted") for row in scorecard)
