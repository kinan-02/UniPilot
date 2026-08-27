"""A single, deliberately-tractable planning request, through the production entry.

Simpler than the two-semester case on purpose, to isolate what the agent CAN
complete once the worst frictions are removed:

  - ONE term (winter), so there is a single slot and no winter/spring split.
  - GPA floor 80, which the fixture student (GPA ~83.9) already CLEARS -- so
    "maintain above 80" is satisfiable and every per-course minimum grade is a
    real, low, reachable number, not the impossible >100 an 85 floor forces.

It still exercises the whole spine: remaining courses, wiki-sourced elective
typing, `optimize` placement, the per-course threshold, and the `:detail` render.

Everything is saved to `agent_planning_eval/` at the repo root.

COSTS MONEY (one live run). Marked `live`, deselected by default.
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

QUESTION = (
    "Plan my next winter semester only -- just the one term. Include some elective "
    "courses, not only mandatory ones. For every course you put in the winter plan, "
    "tell me the minimum grade I would need to earn in it to keep my overall GPA above 80."
)


async def test_winter_only_above_80(ise_planning_student: IsePlanningStudent) -> None:
    conversation_id = f"winter-{datetime.now(timezone.utc):%Y%m%dT%H%M%SZ}"

    began = time.monotonic()
    result = await run_advice(
        QUESTION, ise_planning_student.user_id, conversation_id=conversation_id, time_budget_s=_TIMEOUT
    )
    secs = time.monotonic() - began
    advice = to_advice(result)

    print(f"\n{'=' * 84}\n[{result.outcome}]  turns={result.turns}  {secs:.1f}s")
    print(f"Q: {QUESTION}\n{'-' * 84}")
    for turn in result.transcript:
        print(f"  [t{turn.index}] {turn.action:9} {turn.detail[:200]}")
    print(f"ANSWER:\n{advice.answer}")

    _OUTPUT_DIR.mkdir(parents=True, exist_ok=True)
    stamp = datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%SZ")
    path = _OUTPUT_DIR / f"winter-plan-{stamp}.json"
    path.write_text(
        json.dumps(
            {
                "conversation_id": conversation_id,
                "student": ise_planning_student.user_id,
                "question": QUESTION,
                "outcome": result.outcome,
                "answer": advice.answer,
                "confidence": advice.confidence,
                "seconds": round(secs, 1),
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

    assert result.outcome in {"answered", "proposed", "refused", "exhausted", "stalled"}
    assert advice.answer
