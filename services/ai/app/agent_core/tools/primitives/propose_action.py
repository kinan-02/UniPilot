"""`propose_action` -- the one generic write primitive (docs/agent/AGENT_VISION.md
§5, primitive 9b). Always proposal-only, never a direct mutation -- same
human-confirm boundary as the rest of the system. The only primitive allowed
to declare `side_effect="propose"` (enforced by `ToolRegistry.register`)."""

from __future__ import annotations

from typing import Any

from pydantic import BaseModel, Field

from app.agent_core.tools.envelope import ToolOutputEnvelope, not_implemented_envelope
from app.agent_core.tools.registry import ToolDescriptor

TOOL_NAME = "propose_action"


class ProposeActionInput(BaseModel):
    action_type: str
    payload: dict[str, Any] = Field(default_factory=dict)


async def run_propose_action(payload: ProposeActionInput) -> ToolOutputEnvelope:
    return not_implemented_envelope(TOOL_NAME)


DESCRIPTOR = ToolDescriptor(
    name=TOOL_NAME,
    description="Create a proposal for a write action (completed-course edit, profile "
    "change, plan change) -- never a direct mutation; always requires human confirmation.",
    input_model=ProposeActionInput,
    output_model=ToolOutputEnvelope,
    side_effect="propose",
    callable=run_propose_action,
)
