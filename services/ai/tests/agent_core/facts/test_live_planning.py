"""Complex academic-planning requests, run through the PRODUCTION entry point.

Two things at once:

  1. They exercise the fact/tool loop on genuinely multi-step planning
     questions -- reading a draft plan, totalling load, checking prerequisites,
     and (the second case) reasoning about future semesters, electives, and the
     grade needed to hold a GPA. That touches find, unnest (twice), the
     semi-join, difference, arithmetic and comparison in one request.

  2. They go through `run_advice` -- the same function `/advise` calls -- so a
     green run here is also proof the production wiring holds end to end.

The second case deliberately reaches past what the sources can feed: there is no
registry source for "electives" or for "future semesters", so it is a test of
the layer's HONESTY -- whether the model fabricates them or says it cannot.

The full transcript, the mapped response, and the run metrics are written to
`agent_planning_eval/` at the REPOSITORY ROOT, reachable directly from the
project directory rather than buried under the test tree.

COSTS MONEY. Marked `live`, deselected by default.

    cd services/ai && ./.venv/bin/python -m pytest \\
        tests/agent_core/facts/test_live_planning.py -s -m live -o addopts=""
"""

from __future__ import annotations

import asyncio
import json
import time
from datetime import datetime, timezone
from pathlib import Path

import pytest

from app.agent_core.facts.service import run_advice, to_advice
from app.agent_core.reasoning.llm_client import agent_llm_available
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

# Reachable straight from the project root, not from inside the test tree.
# parents: [0]=facts [1]=agent_core [2]=tests [3]=ai [4]=services [5]=<repo root>
_OUTPUT_DIR = Path(__file__).resolve().parents[5] / "agent_planning_eval"

REQUEST_TIMEOUT_S = 400.0
"""The only bound on a run: no turn cap, no model-call cap -- the loop takes as
many steps as it needs, and stops only if the whole request passes 400 seconds."""

PLAN_REVIEW = (
    "I've drafted a semester plan. Before I commit to it, check it for me: "
    "what is the total credit load of the plan, does it stay within my program's "
    "maximum credits per semester, and for each course in the plan, do my already-completed "
    "courses satisfy its prerequisites? If any planned course is still missing a prerequisite, "
    "tell me which course and which prerequisite."
)

TWO_SEMESTER_ELECTIVE_PLAN = (
    "Plan my next two semesters for me -- winter and then spring, skipping the summer. "
    "Include some elective courses, not only mandatory ones. For every course you put in the "
    "two-semester plan, tell me the minimum grade I would need to earn in it to keep my overall "
    "GPA above 85."
)


async def _run_and_save(student: IsePlanningStudent, question: str, label: str) -> None:
    progress: list[str] = []
    started = time.monotonic()

    # Through the PRODUCTION entrypoint -- the exact call `/advise` makes. Bounded
    # only by the 400s wall clock (graceful, transcript preserved); an outer
    # wait_for a hair above it is the hard backstop for a hung provider call,
    # which the between-turns budget check cannot interrupt on its own.
    result = await asyncio.wait_for(
        run_advice(question, student.user_id, on_progress=progress.append, time_budget_s=REQUEST_TIMEOUT_S),
        timeout=REQUEST_TIMEOUT_S + 20,
    )
    elapsed = time.monotonic() - started
    advice = to_advice(result)
    llm_calls = len({t.index for t in result.transcript}) + sum(
        1 for t in result.transcript if t.action == "call" and t.detail.startswith("interpret(")
    )

    print(f"\n{'=' * 84}\n{label.upper()} (through run_advice -- the production path)")
    print(f"student: {student.user_id}   planned credits (fixture): {student.plan_credits}")
    print(f"{'-' * 84}\nQ: {question}\n{'-' * 84}")
    for phrase in progress:
        print(f"  ~ {phrase}")
    print(f"{'-' * 84}")
    for turn in result.transcript:
        print(f"  [t{turn.index}] {turn.action:9} {turn.detail[:320]}")
    print(f"{'-' * 84}")
    print(f"outcome: {result.outcome}   turns: {result.turns}   llm_calls: {llm_calls}   {elapsed:.1f}s")
    print(f"status:  {advice.status}   confidence: {advice.confidence}   course_ids: {advice.course_ids}")
    print(f"\nANSWER:\n{advice.answer}")

    _OUTPUT_DIR.mkdir(parents=True, exist_ok=True)
    stamp = datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%SZ")

    json_path = _OUTPUT_DIR / f"{label}-{stamp}.json"
    json_path.write_text(
        json.dumps(
            {
                "label": label,
                "question": question,
                "student": student.user_id,
                "planned_credits_per_fixture": student.plan_credits,
                "outcome": result.outcome,
                "turns": result.turns,
                "llm_calls": llm_calls,
                "seconds": round(elapsed, 1),
                "advice": {
                    "answer": advice.answer,
                    "confidence": advice.confidence,
                    "status": advice.status,
                    "course_ids": advice.course_ids,
                    "sources": advice.sources,
                },
                "basis": result.answer.basis.label if result.answer else None,
                "used_facts": list(result.answer.used) if result.answer else [],
                "derivations": dict(result.answer.derivations) if result.answer else {},
                "reason": result.reason,
                "progress": progress,
                "facts_held": {name: type(held.value).__name__ for name, held in result.facts.items()},
                "transcript": [
                    {"turn": t.index, "action": t.action, "detail": t.detail} for t in result.transcript
                ],
            },
            ensure_ascii=False,
            indent=2,
        ),
        encoding="utf-8",
    )

    text_path = _OUTPUT_DIR / f"{label}-{stamp}.txt"
    lines = [
        label.upper(),
        "=" * 84,
        f"student:  {student.user_id}",
        f"outcome:  {result.outcome}   turns: {result.turns}   llm_calls: {llm_calls}   {elapsed:.1f}s",
        f"status:   {advice.status}   confidence: {advice.confidence}",
        "",
        "QUESTION:",
        question,
        "",
        "PROGRESS (what the student saw while waiting):",
        *(f"  ~ {p}" for p in progress),
        "",
        "TRANSCRIPT (every turn, deterministic below the model):",
        *(f"  [t{t.index}] {t.action:9} {t.detail}" for t in result.transcript),
        "",
        "ANSWER:",
        advice.answer,
    ]
    text_path.write_text("\n".join(lines), encoding="utf-8")
    print(f"\nwrote {json_path}\nwrote {text_path}")

    # Deliberately weak, like the other live diagnostics: this run SHOWS what the
    # model does with a hard planning question and proves the production path
    # runs. The transcript is the deliverable, not a pass/fail gate.
    assert result.outcome in {"answered", "refused", "declined", "proposed", "stalled", "exhausted"}
    assert advice.answer, "the route must always ship some student-facing text"


async def test_complex_planning_request(ise_planning_student: IsePlanningStudent) -> None:
    await _run_and_save(ise_planning_student, PLAN_REVIEW, "plan-review")


async def test_two_semester_elective_plan(ise_planning_student: IsePlanningStudent) -> None:
    await _run_and_save(ise_planning_student, TWO_SEMESTER_ELECTIVE_PLAN, "two-semester-electives")
