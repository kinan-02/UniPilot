"""`traverse_relationship` -- generic graph walk (docs/agent/AGENT_VISION.md §5, primitive 3)."""

from __future__ import annotations

from typing import Literal

from pydantic import BaseModel

from app.agent_core.tools.envelope import ToolOutputEnvelope, not_implemented_envelope
from app.agent_core.tools.registry import ToolDescriptor

TOOL_NAME = "traverse_relationship"


class TraverseRelationshipInput(BaseModel):
    entity: str
    relation: str
    direction: Literal["forward", "backward"] = "forward"


async def run_traverse_relationship(payload: TraverseRelationshipInput) -> ToolOutputEnvelope:
    return not_implemented_envelope(TOOL_NAME)


DESCRIPTOR = ToolDescriptor(
    name=TOOL_NAME,
    description="Generic graph walk, parameterized by relation type and direction "
    "(prerequisites, dependents, requirement contribution, track membership, etc.).",
    input_model=TraverseRelationshipInput,
    output_model=ToolOutputEnvelope,
    side_effect="read",
    callable=run_traverse_relationship,
)
