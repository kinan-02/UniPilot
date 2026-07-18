"""The Front Door -- scope gating + request decomposition only, no planning
(AGENT_ARCHITECTURE_V2.md §8.1).

For v1 of the rewrite this is the decomposition half: one cheap call turning the
question into the concrete sub-asks the Answer Boundary (§9) verifies against.
The presupposition fix lives here (§16.7): a question that takes a premise about
the student for granted must emit a concrete sub-ask that VERIFIES that premise
against the record -- a prompt-level "check premises" rule was falsified on the
mini model, so the check has to be a structural sub-ask the gate can enforce.

Scope gating (in_scope / decline) is decided in the SAME decomposer call -- an
out-of-scope question returns `in_scope=False` with a student-facing
`decline_reason`, and the runner short-circuits it into a polite decline before
the loop ever runs (§8.1). It fails OPEN: only an explicit `false` declines, so a
decomposer that omits the flag never silently refuses a legitimate question.
"""

from __future__ import annotations

import json
from dataclasses import dataclass, field

from app.agent_core.reasoning.llm_adapter import ChatLLMAdapter, LLMAdapterError

_DECOMPOSE_TIMEOUT_S = 60.0

_DECOMPOSER_SYSTEM = """You triage and decompose a Technion student's question. Output ONLY JSON.

SCOPE FIRST. You are an academic advisor for Technion students: courses, credits, prerequisites,
eligibility, requirements, grades, the student's own record, degree/track/minor planning, offerings
and schedules. If the question is clearly OUTSIDE that -- general chit-chat, coding help, world
facts, medical/legal/financial advice, anything not about this student's studies -- output
{"in_scope": false, "decline_reason": "<one short, student-facing sentence>"} and nothing else.
Otherwise output {"in_scope": true, "sub_asks": ["...", "..."]}: the concrete sub-questions that
must ALL be answered for the reply to be complete and correct.

Rules:
- Sub-asks are what the ANSWER must contain to be complete and honest -- NOT intermediate
  calculation steps. "How many credits remain?" is ONE sub-ask (the remaining number); the
  earned-so-far total used to compute it is not its own sub-ask.
- Each sub-ask is a SPECIFIC, checkable question, never an abstraction.
- PRESUPPOSITIONS (critical): if the question takes something about the student for
  granted -- "if I fail X this semester", "when I retake Y", "after I finish Z", "since I'm in
  year N" -- emit a concrete sub-ask that VERIFIES that premise against the student's record.
  Phrase it as the course's ACTUAL recorded status, NOT scoped to a specific semester: e.g.
  "Is course X already completed (with what grade and in which semester), in progress, or not
  yet taken?" Do NOT write "...this semester" into the sub-ask -- the honest answer is often
  that the course was completed EARLIER, which makes a 'fail it this semester' premise moot,
  and a semester-scoped sub-ask hides exactly that. A false premise would mislead, so the
  answer MUST surface the real status. Mandatory whenever a premise about the student is present.
- MINIMALITY (critical): emit ONLY the sub-asks the question actually raises. Do NOT inflate a
  sub-ask with clauses the question never mentioned (co-requisites, exclusions,
  department/year restrictions, registration holds, seats, academic standing) unless the
  question raises them. "Am I eligible for X?" is ONE sub-ask -- "Is the student eligible for X,
  and on what basis?" -- not a checklist of every conceivable restriction. Over-broad sub-asks
  make a correct, direct answer look incomplete and send the loop chasing things nobody asked.
- A simple factual question may have exactly one sub-ask."""


@dataclass(frozen=True)
class FrontDoorResult:
    sub_asks: list[str] = field(default_factory=list)
    in_scope: bool = True
    decline_reason: str | None = None


async def decompose(
    adapter: ChatLLMAdapter, question: str, *, temperature: float, reasoning_effort: str
) -> FrontDoorResult:
    """§8: the question -> concrete sub-asks, presuppositions made explicit.

    Fails open: a decomposer failure falls back to the whole question as a single
    sub-ask, so a boundary hiccup never blocks the loop.
    """
    try:
        out = await adapter.complete_json(
            system_prompt=_DECOMPOSER_SYSTEM,
            user_prompt=json.dumps({"question": question}, ensure_ascii=False),
            temperature=temperature,
            thinking_enabled=True,
            reasoning_effort=reasoning_effort,
            timeout=_DECOMPOSE_TIMEOUT_S,
        )
    except LLMAdapterError:
        return FrontDoorResult(sub_asks=[question])
    # An explicit out-of-scope verdict short-circuits the loop with a polite
    # decline (§8.1); absence of the flag fails OPEN to answering, so a decomposer
    # that omits it never silently refuses a legitimate question.
    if out.get("in_scope") is False:
        reason = str(out.get("decline_reason") or "").strip()
        return FrontDoorResult(
            sub_asks=[],
            in_scope=False,
            decline_reason=reason or "That falls outside what I can help with as your academic advisor.",
        )
    subs = out.get("sub_asks")
    if isinstance(subs, list):
        cleaned = [str(s).strip() for s in subs if str(s).strip()]
        if cleaned:
            return FrontDoorResult(sub_asks=cleaned)
    return FrontDoorResult(sub_asks=[question])


__all__ = ["FrontDoorResult", "decompose"]
