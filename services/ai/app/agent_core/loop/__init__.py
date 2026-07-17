"""The V2 agent loop (docs/agent/AGENT_ARCHITECTURE_V2.md).

A single thinking-ON reasoning loop over a fabrication-proof substrate, replacing
V1's orchestration org chart. `run_agent_loop` is the entry point.
"""

from __future__ import annotations

from app.agent_core.loop.runner import AgentLoopResult, run_agent_loop
from app.agent_core.loop.working_set import Fact, WorkingSet

__all__ = ["AgentLoopResult", "run_agent_loop", "Fact", "WorkingSet"]
