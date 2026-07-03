"""Agent plugin protocol for MAS negotiation."""

from __future__ import annotations

from typing import Protocol, runtime_checkable

from app.orchestrator.blackboard import Blackboard
from app.orchestrator.types import AgentTurn


@runtime_checkable
class AgentPlugin(Protocol):
    """Contract for registerable MAS agents."""

    role: str

    async def run(self, blackboard: Blackboard) -> AgentTurn:
        """Execute one agent step against the shared blackboard."""
        ...
