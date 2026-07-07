"""Synthesis capability entry point (Phase 21)."""

from __future__ import annotations

from typing import Any

from app.agent.synthesis.schemas import SynthesisInput, SynthesisOutput
from app.agent.synthesis.synthesis_agent import run_synthesis
from app.config import Settings, get_settings


async def run_synthesis_capability(
    *,
    synthesis_input: SynthesisInput,
    settings: Settings | None = None,
) -> SynthesisOutput:
    """Read-only synthesis capability — diagnostic candidate only."""
    cfg = settings or get_settings()
    return await run_synthesis(synthesis_input, settings=cfg)


def synthesis_capability_metadata() -> dict[str, Any]:
    return {
        "name": "synthesis_composer_capability",
        "readOnly": True,
        "sideEffectLevel": "none",
        "safeForShadowExecution": True,
    }
