"""`search_over_state` -- constrained search/optimization (docs/agent/AGENT_VISION.md
§5, primitive 8). Powers both semester-plan generation and what-if simulation
off the same engine (§3.3) -- and requirement-substitute search as the same
search with a different objective."""

from __future__ import annotations

from typing import Any

from pydantic import BaseModel, Field

from app.agent_core.tools.envelope import ToolOutputEnvelope, not_implemented_envelope
from app.agent_core.tools.registry import ToolDescriptor

TOOL_NAME = "search_over_state"


class SearchOverStateInput(BaseModel):
    state: dict[str, Any] = Field(default_factory=dict)
    constraints: dict[str, Any] = Field(default_factory=dict)
    objective: str


async def run_search_over_state(payload: SearchOverStateInput) -> ToolOutputEnvelope:
    return not_implemented_envelope(TOOL_NAME)


DESCRIPTOR = ToolDescriptor(
    name=TOOL_NAME,
    description="Constrained search/optimization over a state object given constraints "
    "and an objective -- the same engine for plan generation, what-if simulation, "
    "and requirement-substitute search, parameterized differently each time.",
    input_model=SearchOverStateInput,
    output_model=ToolOutputEnvelope,
    side_effect="compute",
    callable=run_search_over_state,
)
