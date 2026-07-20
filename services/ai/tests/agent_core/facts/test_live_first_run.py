"""First live run of the new tool layer -- phase 11c.

One question, one real student, one real model. Everything below the model has
been deterministic and tested; this is the first time a model has to actually
drive it.

The case is `credits_remaining` from the ISE eval, chosen deliberately: its
historic failure was the model typing `155 - 62.5` as literals, which is the
exact bug the grounding invariant exists to prevent. If the new layer works, the
same derivation happens through refs and the answer carries a slot.

COSTS MONEY. Marked `live`, deselected by default.

    cd services/ai && ./.venv/bin/python -m pytest \\
        tests/agent_core/facts/test_live_first_run.py -s -m live -o addopts=""
"""

from __future__ import annotations

import json
import os
from datetime import datetime, timezone
from pathlib import Path

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

QUESTION = "How many credits do I still need to complete my degree?"
MAX_TURNS = 8

_LOG_DIR = Path(__file__).resolve().parents[1] / "live_eval_logs"


async def test_first_live_run(ise_planning_student: IsePlanningStudent) -> None:
    adapter = build_adapter()
    assert adapter is not None, "credentials resolved as available but no adapter was built"

    database = await get_database()
    # Through the production assembly, not a hand-built context. The earlier
    # version wrote `DispatchContext(database=..., schemas=REGISTRY)`, which
    # wires no retriever, no extractor and no derived sources -- so the run
    # advertised five of the eight tools and could not have exercised the
    # wiring it was meant to prove. A live run that tests a context production
    # never builds is an expensive way to learn nothing.
    context = build_context(database)

    # The student's identity is the one fact given rather than derived -- the
    # loop cannot ask who is asking.
    context.facts["me"] = HeldFact(
        value=Scalar(ScalarKind.IDENTIFIER, ise_planning_student.user_id),
        basis=Basis.OFFICIAL_RECORD,
    )

    print(f"\n{'=' * 78}\nQ: {QUESTION}")
    print(f"student: {ise_planning_student.user_id}   credits earned (fixture): "
          f"{ise_planning_student.credits_earned}")
    print(f"tools:   {[spec.name for spec in available_tools(context)]}")
    print(f"sources: {sorted(context.schemas)}")
    print(f"{'-' * 78}")

    result = await run_loop(QUESTION, adapter, context, max_turns=MAX_TURNS)

    for turn in result.transcript:
        print(f"  [t{turn.index}] {turn.action:9} {turn.detail[:400]}")

    print(f"{'-' * 78}")
    print(f"outcome: {result.outcome}   turns: {result.turns}")
    if result.answer:
        print(f"basis:   {result.answer.basis.label}")
        print(f"facts:   {list(result.answer.used)}")
        print(f"\nANSWER:  {result.answer.text}")
        for name, how in result.answer.derivations:
            print(f"           {name} = {how}")
    if result.reason:
        print(f"reason:  {result.reason}")

    print(f"\nfacts held at the end ({len(result.facts)}):")
    for name, held in result.facts.items():
        shape = type(held.value).__name__
        print(f"   {name:24} {shape:11} basis={held.basis.label}")

    _LOG_DIR.mkdir(parents=True, exist_ok=True)
    stamp = datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%SZ")
    path = _LOG_DIR / f"facts_first_live_run-{stamp}.json"
    path.write_text(
        json.dumps(
            {
                "question": QUESTION,
                "student": ise_planning_student.user_id,
                "credits_earned_per_fixture": ise_planning_student.credits_earned,
                "outcome": result.outcome,
                "turns": result.turns,
                "answer": result.answer.text if result.answer else None,
                "basis": result.answer.basis.label if result.answer else None,
                "used_facts": list(result.answer.used) if result.answer else [],
                "derivations": dict(result.answer.derivations) if result.answer else {},
                "reason": result.reason,
                "transcript": [
                    {"turn": t.index, "action": t.action, "detail": t.detail} for t in result.transcript
                ],
            },
            ensure_ascii=False,
            indent=2,
        ),
        encoding="utf-8",
    )
    print(f"\nwrote {path}")

    # Deliberately weak. This run exists to SHOW what a real model does with the
    # layer; asserting a correct answer on the first attempt would turn a
    # diagnostic into a pass/fail with nothing learned from the failure.
    assert result.outcome in {"answered", "refused", "stalled", "exhausted"}
    if result.answer is not None:
        assert result.answer.used, "an accepted answer must stand on at least one fact"
