"""Synthesis / Final Answer Composer (Phase 21)."""

from app.agent.synthesis.capability import run_synthesis_capability, synthesis_capability_metadata
from app.agent.synthesis.diagnostics import build_synthesis_diagnostics, compare_synthesis_to_live_response
from app.agent.synthesis.fallback_composer import deterministic_synthesis
from app.agent.synthesis.input_builder import build_synthesis_input
from app.agent.synthesis.schemas import (
    EvidenceItem,
    SynthesisConflict,
    SynthesisInput,
    SynthesisOutput,
)
from app.agent.synthesis.synthesis_agent import run_synthesis, run_synthesis_diagnostics

__all__ = [
    "EvidenceItem",
    "SynthesisConflict",
    "SynthesisInput",
    "SynthesisOutput",
    "build_synthesis_diagnostics",
    "build_synthesis_input",
    "compare_synthesis_to_live_response",
    "deterministic_synthesis",
    "run_synthesis",
    "run_synthesis_capability",
    "run_synthesis_diagnostics",
    "synthesis_capability_metadata",
]
