"""`interpret_text` -- LLM-reasoning extraction of a rule/fact from wiki prose
(docs/agent/AGENT_VISION.md §5, primitive 4). One of only two primitives
where an LLM call is intrinsic to the operation itself (§4)."""

from __future__ import annotations

from pydantic import BaseModel

from app.agent_core.tools.envelope import ToolOutputEnvelope, not_implemented_envelope
from app.agent_core.tools.registry import ToolDescriptor

TOOL_NAME = "interpret_text"


class InterpretTextInput(BaseModel):
    source: str
    question: str


async def run_interpret_text(payload: InterpretTextInput) -> ToolOutputEnvelope:
    return not_implemented_envelope(TOOL_NAME)


DESCRIPTOR = ToolDescriptor(
    name=TOOL_NAME,
    description="Extract a rule/fact/interpretation from wiki prose for a specific question. "
    "Must return 'cannot determine' rather than guess; must cite the exact source read.",
    input_model=InterpretTextInput,
    output_model=ToolOutputEnvelope,
    side_effect="read",
    callable=run_interpret_text,
)
