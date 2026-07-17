"""The Front Door -- scope gating + request decomposition only, no planning
(AGENT_ARCHITECTURE_V2.md §8.1).

For v1 of the rewrite this is the decomposition half: one cheap call turning the
question into the concrete sub-asks the Answer Boundary (§9) verifies against.
The presupposition fix lives here (§16.7): a question that takes a premise about
the student for granted must emit a concrete sub-ask that VERIFIES that premise
against the record -- a prompt-level "check premises" rule was falsified on the
mini model, so the check has to be a structural sub-ask the gate can enforce.

Scope gating (in_scope / decline) is threaded through `FrontDoorResult` but kept
open for v1 (the loop handles every question); it plugs into V1's kept
`boundary_handler` when wired (§17.4).
"""

from __future__ import annotations

import json
from dataclasses import dataclass, field

from app.agent_core.reasoning.llm_adapter import ChatLLMAdapter, LLMAdapterError

_DECOMPOSE_TIMEOUT_S = 60.0

_DECOMPOSER_SYSTEM = """You break a Technion student's question into the concrete sub-questions that
must ALL be answered for the reply to be complete and correct. Output ONLY JSON:
{"sub_asks": ["...", "..."]}.

Rules:
- Sub-asks are what the ANSWER must contain to be complete and honest -- NOT intermediate
  calculation steps. "How many credits remain?" is ONE sub-ask (the remaining number); the
  earned-so-far total used to compute it is not its own sub-ask.
- Each sub-ask is a SPECIFIC, checkable question, never an abstraction.
- PRESUPPOSITIONS (critical): if the question takes something about the student for
  granted -- "if I fail X", "when I retake Y", "after I finish Z", "since I'm in year N"
  -- emit a concrete sub-ask that VERIFIES that premise against the student's record,
  phrased as a direct lookup: e.g. "What is the student's current status and grade on
  course X?" -- NOT "verify the premise". A false premise (e.g. X is already passed) would
  make the answer misleading, so the answer MUST surface the real status -- this sub-ask is
  mandatory whenever a premise about the student is present.
- Keep it minimal -- only the sub-asks the answer genuinely must address. A simple factual
  question may have exactly one."""


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
    subs = out.get("sub_asks")
    if isinstance(subs, list):
        cleaned = [str(s).strip() for s in subs if str(s).strip()]
        if cleaned:
            return FrontDoorResult(sub_asks=cleaned)
    return FrontDoorResult(sub_asks=[question])


__all__ = ["FrontDoorResult", "decompose"]
