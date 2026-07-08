"""`extract_temporal_pattern` -- mine a time-indexed historical record for a
pattern and project forward with confidence (docs/agent/AGENT_VISION.md §5,
primitive 5). Generalizes future-offering prediction (§2.3) to any
time-indexed fact."""

from __future__ import annotations

from pydantic import BaseModel

from app.agent_core.tools.envelope import ToolOutputEnvelope, not_implemented_envelope
from app.agent_core.tools.registry import ToolDescriptor

TOOL_NAME = "extract_temporal_pattern"


class ExtractTemporalPatternInput(BaseModel):
    fact_type: str
    entity: str


async def run_extract_temporal_pattern(payload: ExtractTemporalPatternInput) -> ToolOutputEnvelope:
    return not_implemented_envelope(TOOL_NAME)


DESCRIPTOR = ToolDescriptor(
    name=TOOL_NAME,
    description="Mine a time-indexed historical record for a pattern and project forward "
    "with an explicit confidence/pattern basis -- never asserted as a published fact.",
    input_model=ExtractTemporalPatternInput,
    output_model=ToolOutputEnvelope,
    side_effect="compute",
    callable=run_extract_temporal_pattern,
)
