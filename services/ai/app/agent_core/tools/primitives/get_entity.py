"""`get_entity` -- structured fetch of any named record (docs/agent/AGENT_VISION.md §5, primitive 1)."""

from __future__ import annotations

from pydantic import BaseModel

from app.agent_core.tools.envelope import ToolOutputEnvelope, not_implemented_envelope
from app.agent_core.tools.registry import ToolDescriptor

TOOL_NAME = "get_entity"


class GetEntityInput(BaseModel):
    entity_type: str
    entity_id: str


async def run_get_entity(payload: GetEntityInput) -> ToolOutputEnvelope:
    return not_implemented_envelope(TOOL_NAME)


DESCRIPTOR = ToolDescriptor(
    name=TOOL_NAME,
    description="Structured fetch of any named record: course, track, program, minor, "
    "regulation topic, student profile, completed courses, saved plans.",
    input_model=GetEntityInput,
    output_model=ToolOutputEnvelope,
    side_effect="read",
    callable=run_get_entity,
)
