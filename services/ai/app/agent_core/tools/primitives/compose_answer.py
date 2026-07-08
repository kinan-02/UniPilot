"""`compose_answer` -- turns structured, certainty-tagged results into grounded
prose (docs/agent/AGENT_VISION.md §5, primitive 9a). The other of only two
primitives where an LLM call is intrinsic to the operation itself (§4).
Mirrors `agent_core.synthesis.synthesis.compose_answer`, which is the
Orchestrator-level entry point that calls this tool at the end of a plan --
kept as a separate registry entry so it can also be invoked mid-plan if a
future step ever needs a partial composed summary."""

from __future__ import annotations

from typing import Any

from pydantic import BaseModel, Field

from app.agent_core.tools.envelope import ToolOutputEnvelope, not_implemented_envelope
from app.agent_core.tools.registry import ToolDescriptor

TOOL_NAME = "compose_answer"


class ComposeAnswerInput(BaseModel):
    facts_with_certainty: list[dict[str, Any]] = Field(default_factory=list)


async def run_compose_answer(payload: ComposeAnswerInput) -> ToolOutputEnvelope:
    return not_implemented_envelope(TOOL_NAME)


DESCRIPTOR = ToolDescriptor(
    name=TOOL_NAME,
    description="Compose grounded prose from accumulated, certainty-tagged results -- "
    "honoring every certainty tag rather than flattening them into uniform-sounding prose.",
    input_model=ComposeAnswerInput,
    output_model=ToolOutputEnvelope,
    side_effect="read",
    callable=run_compose_answer,
)
