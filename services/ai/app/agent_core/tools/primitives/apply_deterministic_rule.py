"""`apply_deterministic_rule` -- arithmetic/validation given an already-identified
rule and already-retrieved facts (docs/agent/AGENT_VISION.md §5, primitive 6).
Never involves an LLM call at execution time -- only the LLM's decision to
invoke it does (§4)."""

from __future__ import annotations

from typing import Any

from pydantic import BaseModel, Field

from app.agent_core.tools.envelope import ToolOutputEnvelope, not_implemented_envelope
from app.agent_core.tools.registry import ToolDescriptor

TOOL_NAME = "apply_deterministic_rule"


class ApplyDeterministicRuleInput(BaseModel):
    rule: dict[str, Any] = Field(default_factory=dict)
    facts: dict[str, Any] = Field(default_factory=dict)


async def run_apply_deterministic_rule(payload: ApplyDeterministicRuleInput) -> ToolOutputEnvelope:
    return not_implemented_envelope(TOOL_NAME)


DESCRIPTOR = ToolDescriptor(
    name=TOOL_NAME,
    description="Apply a deterministic rule to given facts (credit totals, threshold checks). "
    "Pure computation -- must return 'insufficient to determine' rather than a best guess.",
    input_model=ApplyDeterministicRuleInput,
    output_model=ToolOutputEnvelope,
    side_effect="compute",
    callable=run_apply_deterministic_rule,
)
