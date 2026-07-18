"""The Answer Boundary -- the single verification (AGENT_ARCHITECTURE_V2.md §9).

Replaces V1's entire verification network (Planner Council, critics, Specialist
Router re-checks, per-step success-checks, Monitor). Runs once, at the end:

1. Grounding check (`resolve_final`) -- CODE, no LLM, always. Slot-fill the prose
   from fact refs, then require every numeral in the rendered prose to trace to a
   slotted fact (or to the student's own question). The model literally cannot
   write `92.5`; it writes `{gap}` bound to a computed ref.
2. Completeness check (`completeness_gate`) -- <=1 LLM call. Does the answer
   address every sub-ask? The one verification LLM call V2 permits, run once over
   the finished answer, not per step. Fails OPEN.
"""

from __future__ import annotations

import json
import re
from typing import Any

from app.agent_core.loop.working_set import Fact
from app.agent_core.reasoning.llm_adapter import ChatLLMAdapter, LLMAdapterError

_NUM = re.compile(r"\d+(?:\.\d+)?")
_SLOT = re.compile(r"\{(\w+)\}")
_GATE_TIMEOUT_S = 60.0

_COMPLETENESS_SYSTEM = """You verify whether a DRAFT answer addresses every required sub-question.
Output ONLY JSON: {"unaddressed": ["<verbatim sub-ask>", ...]} -- list each sub-ask the
draft does NOT substantively address; empty list if all are addressed.

A sub-ask is "addressed" only if the draft states the relevant fact. "I could not determine
it" counts as addressed ONLY for genuinely external/unknowable facts -- NEVER for a sub-ask
about the student's OWN record (their status/grade on a course, their completed courses),
because that data is always in the record and must be looked up. For a status sub-ask, the
draft must actually REFLECT the status (e.g. that the course is already completed, with the
grade) -- merely NAMING the course, or claiming it could not be determined, does NOT count.

IMPORTANT distinction -- reporting the ACTUAL recorded status IS addressing the sub-ask, even
when that status is "already completed in an earlier semester (state the grade and that
semester) and therefore NOT currently in progress." A course passed in a prior semester
legitimately has no current-semester attempt; a draft that gives the real grade and semester
and notes there is no current attempt HAS addressed the status -- and correctly surfaces a
false "failing it this semester" premise, which is exactly what the student needs. Reject ONLY
a draft that names NO concrete status or grade at all for the course (a bare "I could not
determine it"). A stated grade like "85 in 2025-1" is an addressed status, not a cop-out."""


def resolve_final(
    question: str, facts: dict[str, Fact], prose: str, fact_refs: dict[str, Any]
) -> tuple[str, list[str]]:
    """Slot-fill the prose from fact refs, then run the deterministic grounding
    backstop. Returns (rendered_prose, problems): any numeral in the final prose
    that traces to no slotted fact and did not come from the student's question,
    plus any unresolved or non-scalar slot.

    §4.2: every slot must bind to a fact whose value is a scalar. A slot bound to
    no fact (a compute that never produced its fact) or to a whole record/list is
    a grounding failure -- flagged, so the answer is rejected and the model must
    `select` the specific field or fix the ref.
    """
    slotted_values: list[str] = []
    unresolved: list[str] = []

    def _sub(match: re.Match) -> str:
        slot = match.group(1)
        ref = fact_refs.get(slot)
        if ref in facts:
            value = facts[ref].value
            # A None-valued fact must never render the literal "None" into an
            # answer (a live eval shipped "target semester None"). Treat it as
            # unresolved so the draft is rejected and the model drops the slot or
            # fills it with a real value.
            if value is None:
                unresolved.append(f"{slot}->None (fact has no value; drop this slot)")
                return match.group(0)
            # A list of scalars renders comma-separated -- this is how a "list my
            # courses" answer slots an enumerated fact (e.g. select(field=...) over
            # the completed-courses list). Still grounded: every element traces to
            # the fact. A list/dict of records stays non-scalar (select a field).
            if isinstance(value, list) and all(not isinstance(item, (dict, list)) for item in value):
                rendered_value = ", ".join(str(item) for item in value)
                slotted_values.append(rendered_value)
                return rendered_value
            if isinstance(value, (dict, list)):
                unresolved.append(f"{slot}->non-scalar {type(value).__name__} (select a scalar field)")
                return match.group(0)
            rendered_value = str(value)
            slotted_values.append(rendered_value)
            return rendered_value
        unresolved.append(f"{slot}->{ref}")
        return match.group(0)

    rendered = _SLOT.sub(_sub, prose)
    allowed: set[str] = set()
    for slotted in slotted_values:
        allowed.update(_NUM.findall(slotted))
    allowed.update(_NUM.findall(question))  # echoing a code from the question is fine
    problems = [tok for tok in _NUM.findall(rendered) if tok not in allowed]
    problems += [f"unresolved_slot:{u}" for u in unresolved]
    return rendered, problems


async def completeness_gate(
    adapter: ChatLLMAdapter,
    question: str,
    sub_asks: list[str],
    answer: str,
    *,
    temperature: float,
    reasoning_effort: str,
) -> list[str]:
    """§9.2: the sub-asks the draft answer leaves unaddressed (empty = complete).

    Fails OPEN -- a gate-call failure returns "complete" rather than trapping the
    student behind a broken checker; the turn budget still bounds continuations.
    """
    try:
        out = await adapter.complete_json(
            system_prompt=_COMPLETENESS_SYSTEM,
            user_prompt=json.dumps(
                {"question": question, "sub_asks": sub_asks, "draft_answer": answer},
                ensure_ascii=False,
            ),
            temperature=temperature,
            thinking_enabled=True,
            reasoning_effort=reasoning_effort,
            timeout=_GATE_TIMEOUT_S,
        )
    except LLMAdapterError:
        return []
    unaddressed = out.get("unaddressed")
    if isinstance(unaddressed, list):
        return [str(s).strip() for s in unaddressed if str(s).strip()]
    return []


__all__ = ["resolve_final", "completeness_gate"]
