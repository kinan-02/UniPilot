"""`mutate_state` -- apply a hypothetical change to a state object
(docs/agent/AGENT_VISION.md §5, primitive 7). A small, cheap, deterministic
transform -- never a capability of its own, always feeds `search_over_state`."""

from __future__ import annotations

from typing import Any

from pydantic import BaseModel, Field

from app.agent_core.tools.envelope import ToolOutputEnvelope, not_implemented_envelope
from app.agent_core.tools.registry import ToolDescriptor

TOOL_NAME = "mutate_state"


class MutateStateInput(BaseModel):
    base_state: dict[str, Any] = Field(default_factory=dict)
    change: dict[str, Any] = Field(default_factory=dict)


async def run_mutate_state(payload: MutateStateInput) -> ToolOutputEnvelope:
    return not_implemented_envelope(TOOL_NAME)


DESCRIPTOR = ToolDescriptor(
    name=TOOL_NAME,
    description="Apply a hypothetical change (fail/drop/retake a course, delay a semester, "
    "change track) to a state object, producing a perturbed state for search_over_state.",
    input_model=MutateStateInput,
    output_model=ToolOutputEnvelope,
    side_effect="compute",
    callable=run_mutate_state,
)
