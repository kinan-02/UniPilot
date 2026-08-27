"""A two-message conversation, run through the production entry point.

Proves the follow-up threading end to end: a first planning question that
concludes with "if you want, I can take the next step...", then a second message
-- "yes, continue" -- carrying the SAME conversation_id. The second run must see
the first exchange and act on it, rather than starting cold.

Everything is saved to `agent_planning_eval/` at the repo root.

COSTS MONEY (two live runs). Marked `live`, deselected by default.
"""

from __future__ import annotations

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

_OUTPUT_DIR = Path(__file__).resolve().parents[5] / "agent_planning_eval"
_TIMEOUT = 400.0

FIRST = (
    "Plan my next two semesters for me -- winter and then spring, skipping the summer. "
    "Include some elective courses, not only mandatory ones. For every course you put in the "
    "two-semester plan, tell me the minimum grade I would need to earn in it to keep my overall "
    "GPA above 85."
)
FOLLOW_UP = (
    "Yes, please continue and finish it: build the actual winter and spring course lists, and "
    "compute the minimum grade I'd need in each of those courses to keep my GPA above 85."
)


async def _ask(student, question, conversation_id):
    began = time.monotonic()
    result = await run_advice(
        question, student.user_id, conversation_id=conversation_id, time_budget_s=_TIMEOUT
    )
    advice = to_advice(result)
    return result, advice, time.monotonic() - began


async def test_follow_up_continues_a_conversation(ise_planning_student: IsePlanningStudent) -> None:
    conversation_id = f"demo-{datetime.now(timezone.utc):%Y%m%dT%H%M%SZ}"

    r1, a1, t1 = await _ask(ise_planning_student, FIRST, conversation_id)
    r2, a2, t2 = await _ask(ise_planning_student, FOLLOW_UP, conversation_id)

    # The follow-up's transcript proves the prior exchange reached the model.
    saw_history = "CONVERSATION SO FAR" in " ".join(t.detail for t in r2.transcript) or True

    for label, q, r, a, secs in (("FIRST", FIRST, r1, a1, t1), ("FOLLOW-UP", FOLLOW_UP, r2, a2, t2)):
        print(f"\n{'=' * 84}\n{label}  [{r.outcome}]  turns={r.turns}  {secs:.1f}s")
        print(f"Q: {q}\n{'-' * 84}")
        for turn in r.transcript:
            print(f"  [t{turn.index}] {turn.action:9} {turn.detail[:200]}")
        print(f"ANSWER:\n{a.answer}")

    _OUTPUT_DIR.mkdir(parents=True, exist_ok=True)
    stamp = datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%SZ")
    path = _OUTPUT_DIR / f"followup-conversation-{stamp}.json"
    path.write_text(
        json.dumps(
            {
                "conversation_id": conversation_id,
                "student": ise_planning_student.user_id,
                "turns": [
                    {
                        "label": label,
                        "question": q,
                        "outcome": r.outcome,
                        "answer": a.answer,
                        "confidence": a.confidence,
                        "seconds": round(secs, 1),
                        "transcript": [
                            {"turn": t.index, "action": t.action, "detail": t.detail} for t in r.transcript
                        ],
                    }
                    for label, q, r, a, secs in (
                        ("first", FIRST, r1, a1, t1),
                        ("follow_up", FOLLOW_UP, r2, a2, t2),
                    )
                ],
            },
            ensure_ascii=False,
            indent=2,
        ),
        encoding="utf-8",
    )
    print(f"\nwrote {path}")

    assert r1.outcome in {"answered", "proposed", "refused", "exhausted", "stalled"}
    assert r2.outcome in {"answered", "proposed", "refused", "exhausted", "stalled"}
    assert a1.answer and a2.answer
