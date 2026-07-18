"""V2 live correctness eval -- the 6 ise_correctness cases plus 4 that exercise
V2-only capabilities, same fixture student, run through the V2 agent loop
(`run_agent_loop`) instead of the V1 org chart (`run_agent_turn`).

Ground truth is the seeded ISE student (docs/agent/ISE_EVAL_FIXTURE.md), verified
end-to-end. Cases 1-6 and their checkable claims are ported verbatim from
tests/agent_core/test_ise_correctness_eval.py; 7-10 validate capabilities that only
exist in V2:

  1. credits_remaining     -> 92.5 remaining; never 63.x/91.5/92.0
  2. eligibility_00960211  -> reasons from prereq 00940224 (which the student holds)
  3. presupposition_conflict -> surfaces that 00940224 is already passed (grade 85)
  4. offering_pattern      -> a real, on-topic answer about 00960211
  5. completed_courses     -> lists the transcript; earned total, if stated, is real
  6. action_boundary       -> never claims to have registered the student
  7. grade_filter_above_90 -> select's NEW numeric comparison (gt): names only the
                              >90 courses (95/91/93 -> 00940704/03240033/00940219),
                              EXCLUDES the exactly-90 ones. The codes are numerals
                              absent from the question, so the grounding gate forces
                              a grounded `select` -- the case cannot be faked.
  8. out_of_scope_decline  -> the NEW Front Door scope-gate: an out-of-scope question
                              is DECLINED before the loop runs (no tools, no fabrication)
  9. offering_prediction_hedge -> the NEW certainty rendering (§4.2): a count that only
                              extract_temporal_pattern provides (predicted_pattern basis)
                              is forced by the grounding gate to be slotted, so the answer
                              renders the "On certainty:" hedge. Wires the offering path.
 10. sub_loop_investigation -> the NEW sub-loop mechanism (§6): a many-entity offering
                              search over the completed set. Whether the model SPAWNS is
                              its own judgment (the digesting substrate + parallel calls +
                              context discipline let it stay inline), so a spawn is REPORTED,
                              not required; grounding + naming a real course are the checks.

The loop's STRUCTURAL guarantee (no ungrounded number in the answer) is a hard
assertion for every case. The substantive correctness claims are reported
per-case (pass/fail) so one run shows exactly how V2 does on the full set.

Run (needs dev Mongo up + OPENAI creds in the root .env):
    cd services/ai && python -m pytest tests/agent_core/test_v2_ise_correctness.py -s -m live -o addopts=""
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
from tests.agent_core.ise_student_fixture import (  # noqa: F401 -- pytest fixture injection
    IseStudent,
    _fresh_mongo_client_per_test,
    ise_student,
)

pytestmark = [
    pytest.mark.live,
    pytest.mark.skipif(not agent_llm_available(), reason="no LLM credentials configured (OPENAI_API_KEY)"),
]

# Alongside every other live-eval artefact (see live_eval_logging.py); gitignored
# per-run, so history accumulates locally without landing in the repo. This was an
# absolute path into one machine's session scratchpad, which silently wrote nowhere
# useful for anyone else -- and run-over-run comparison is the whole point of keeping
# the scorecard.
_LOG_DIR = Path(__file__).resolve().parent / "live_eval_logs"

# Phrases that would be a false claim of having performed the registration action.
_REGISTRATION_CLAIMS = (
    "registered you",
    "i have registered",
    "i've registered",
    "you are now registered",
    "you're registered",
    "you are registered",
    "i registered you",
    "registration complete",
    "successfully registered",
    "enrolled you",
    "i have enrolled",
)

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
    },
    {
        "name": "presupposition_conflict",
        "question": "If I fail course 00940224 this semester, will I still be able to take 00960211 afterwards?",
        "must_mention": ["00940224", "85"],
        "must_not_mention": [],
    },
    {
        "name": "offering_pattern",
        "question": "Is course 00960211 offered in the summer semester?",
        "must_mention": ["00960211"],
        "must_not_mention": [],
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
        # V2-only: select's numeric comparison. The qualifying codes are 8-digit
        # numerals absent from the question, so the grounding backstop will REJECT
        # any that are not slotted from a fact -- the only groundable path is
        # `select where grade > 90, field courseNumber`, then slot the list. Grades:
        # 00940704=95, 03240033=93, 00940219=91 (>90); 02340221=90, 00940564=90 (=90).
        "name": "grade_filter_above_90",
        "question": "Which courses did I score above 90 in? Give me the course codes.",
        "must_mention": ["00940704", "03240033", "00940219"],
        "must_not_mention": ["02340221", "00940564"],  # exactly 90 -> excluded by gt (not gte)
    },
    {
        # V2-only: the Front Door scope-gate. A question with nothing to do with the
        # student's studies must be DECLINED before the loop runs -- not answered
        # with an invented fact, not wandered on.
        "name": "out_of_scope_decline",
        "question": "What's the weather going to be like in Haifa this weekend?",
        "must_mention": [],
        "must_not_mention": [],
        "scope_decline": True,
    },
    {
        # V2-only: certainty RENDERING (§4.2) over the offering-prediction path.
        # "In how many semesters..." forces a count that ONLY extract_temporal_pattern
        # supplies -- a predicted_pattern fact -- and the grounding gate forces that
        # numeral to be slotted, so a grounded answer must render the hedge. We do not
        # assert the count (raw-offering-data dependent); we assert the hedge appears.
        "name": "offering_prediction_hedge",
        "question": "Across the recorded history, in how many semesters has course 00960211 been offered in the spring?",
        "must_mention": [],
        "must_not_mention": [],
        "certainty_hedge": True,
    },
    {
        # V2-only: sub-loops (§6). A many-entity offering search over the completed set
        # (17 courses) -- the kind of iterative investigation a child loop can isolate.
        # Whether the model SPAWNS is its own judgment: the digesting substrate, parallel
        # tool-calls, and the raw-payload-hiding context discipline often let it stay
        # inline, so "used a sub-loop" is REPORTED, not required. The substantive checks
        # are that it concludes with a grounded answer naming a real completed course.
        "name": "sub_loop_investigation",
        "question": "Of all the courses I have completed, which one has been offered in the most semesters over the recorded history? Give me the course code.",
        "must_mention": [],
        "must_not_mention": [],
        "mentions_any": [
            "00940345", "00940704", "01040065", "01040042", "02340221",
            "00940210", "00940219", "00940411", "00940202", "01040044", "03240033",
            "00940224", "00940241", "00940312", "00940424", "00940564", "00960570",
        ],
        "report_spawn": True,
    },
]


def _score_case(case: dict[str, Any], result) -> dict[str, Any]:
    answer = result.answer or ""
    lowered = answer.lower()
    claims: dict[str, bool] = {
        # A polite out-of-scope decline is a valid conclusion, not a failure.
        "concluded": result.outcome in ("answered", "clarified", "declined"),
        "grounded (no ungrounded numerals)": not result.ungrounded_numbers,
    }
    if answer.strip():
        claims["answered in English"] = detect_message_language(answer) == ENGLISH
    for token in case["must_mention"]:
        claims[f"mentions {token!r}"] = token in answer
    for token in case["must_not_mention"]:
        claims[f"avoids {token!r}"] = token not in answer
    if case.get("boundary"):
        claims["does not claim to have registered"] = not any(p in lowered for p in _REGISTRATION_CLAIMS)
    if case.get("scope_decline"):
        claims["declined as out-of-scope"] = result.outcome == "declined"
        claims["declined before running any tool"] = result.turns == 0
    if case.get("certainty_hedge"):
        # §4.2: a slotted predicted_pattern fact appends the "On certainty:" hedge.
        claims["renders a certainty hedge"] = "On certainty" in answer
    if case.get("mentions_any"):
        claims["names a real completed course"] = any(token in answer for token in case["mentions_any"])
    if case.get("report_spawn"):
        # REPORTED, not required -- surfaces HOW the model isolated the many-entity
        # fan-out. Since §19, `map` (a code-side parallel fan-out + a grounded
        # `select ... by` reduce) is the INTENDED path for this uniform aggregation;
        # a sub-loop is the heavier fallback. Either counts as "handled the fan-out";
        # neither is asserted -- both are informative.
        used = {
            call.get("tool")
            for step in result.transcript
            for call in step.get("calls", [])
        }
        claims["fanned out via map or a sub-loop [reported]"] = bool({"map", "spawn_subtask"} & used)
        claims["used the map path (§19, no sub-loop) [reported]"] = "map" in used
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
            # Without this the readability pass is invisible: run 3 shipped a
            # rewrite that dropped the certainty hedge and the course code, and
            # the log gave no way to tell whether polish had even applied.
            print(f"  [polish] applied={step['polish']['applied']}")
            continue
        if "forced_compose" in step:
            # Not a turn -- the exhaustion compose. It carries no thought, so
            # without this it printed as a phantom "turn N: None" and read as one
            # more empty turn than actually happened.
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


async def test_v2_ise_correctness(ise_student: IseStudent) -> None:
    registry = build_default_tool_registry()
    scorecard: list[dict[str, Any]] = []
    started = time.monotonic()

    for case in _CASES:
        result = await run_agent_loop(case["question"], ise_student.user_id, registry)
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

    # Summary scorecard.
    print(f"\n{'#' * 80}\nV2 ISE CORRECTNESS SCORECARD ({time.monotonic() - started:.0f}s total)\n{'#' * 80}")
    for row in scorecard:
        passed = sum(1 for ok in row["claims"].values() if ok)
        total = len(row["claims"])
        print(f"  {row['case']:<26} {row['outcome']:<10} "
              f"{passed}/{total} claims  ({row['turns']}t {row['llm_calls']}c {row['wall_clock_s']}s)")
    _LOG_DIR.mkdir(parents=True, exist_ok=True)
    stamp = datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%SZ")
    scorecard_path = _LOG_DIR / f"v2_ise_correctness-{stamp}.json"
    scorecard_path.write_text(json.dumps(scorecard, ensure_ascii=False, indent=2, default=str))
    print(f"\n  scorecard written to {scorecard_path}")

    # HARD gate: the loop's one structural promise -- every case grounds every
    # number. Correctness claims above are reported, not asserted, so one run
    # surfaces the full picture rather than aborting on the first substantive miss.
    grounding_failures = [
        (row["case"], row["ungrounded"]) for row in scorecard if row["ungrounded"]
    ]
    assert not grounding_failures, f"GROUNDING VIOLATIONS (typed numerals tracing to no fact): {grounding_failures}"


async def test_v2_spawn_subtask_capability(ise_student: IseStudent) -> None:
    """Targeted capability probe for sub-loops (§6). Case 10 REPORTS whether the
    model chooses to spawn; this one INSTRUCTS it to -- so it exercises, live, that
    the real model can FORM a valid spawn_subtask and the runner EXECUTES the child
    loop end-to-end against the real substrate, returning a grounded fact to the
    parent. (The deterministic mechanism proof is the fake-adapter unit test; this
    proves the live model reaches and drives it.)

    Live + model-dependent -- run with: cd services/ai && python -m pytest \
        tests/agent_core/test_v2_ise_correctness.py::test_v2_spawn_subtask_capability -s -m live -o addopts=""
    """
    registry = build_default_tool_registry()
    question = (
        "For course 00960211, use a sub-task (spawn_subtask) to mine its offering history in "
        "isolation and return only how many semesters it has been offered. Then report that number to me."
    )
    result = await run_agent_loop(question, ise_student.user_id, registry)

    spawned = any(
        call.get("tool") == "spawn_subtask"
        for step in result.transcript
        for call in step.get("calls", [])
    )
    _print_case(
        "spawn_subtask_capability",
        question,
        result,
        {
            "spawned a sub-task (spawn_subtask)": spawned,
            "concluded with an answer": result.outcome == "answered",
            "grounded (no ungrounded numerals)": not result.ungrounded_numbers,
            "sub-loop returned a promoted fact": bool(result.facts),
        },
    )

    # Structural guarantee (hard): a sub-loop must never break grounding.
    assert not result.ungrounded_numbers, f"ungrounded numerals via sub-loop: {result.ungrounded_numbers}"
    # The capability under test: the model formed a spawn and the child ran to a
    # grounded, promoted fact the parent could answer from.
    assert spawned, "model did not use spawn_subtask despite an explicit instruction"
    assert result.outcome == "answered", f"expected an answer, got {result.outcome}"
    assert result.facts, "sub-loop returned no promoted fact to the parent"
