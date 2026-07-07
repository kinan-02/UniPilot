"""In-memory registry of read-only specialist agents (Phase 10).

Deterministic and side-effect free: call `build_default_specialist_agent_registry()`
to get a fresh registry populated with the three Phase 10 specialists. No
database or LLM access happens at registry-construction time.
"""

from __future__ import annotations

from collections.abc import Awaitable, Callable

from app.agent.specialists.course_catalog_agent import run_course_catalog_agent
from app.agent.specialists.graduation_progress_agent import run_graduation_progress_agent
from app.agent.specialists.requirement_explanation_agent import run_requirement_explanation_agent
from app.agent.specialists.schemas import SpecialistAgentInput, SpecialistAgentOutput

SpecialistAgentFn = Callable[..., Awaitable[SpecialistAgentOutput]]


class SpecialistAgentNotFoundError(KeyError):
    """Raised by `SpecialistAgentRegistry.require` for an unregistered agent name."""


class SpecialistAgentRegistry:
    """Queryable, in-memory catalog of executable specialist agents."""

    def __init__(self) -> None:
        self._agents: dict[str, SpecialistAgentFn] = {}

    def register(self, agent_name: str, fn: SpecialistAgentFn, *, overwrite: bool = False) -> None:
        if not overwrite and agent_name in self._agents:
            raise ValueError(f"specialist_agent_already_registered: {agent_name}")
        self._agents[agent_name] = fn

    def get(self, agent_name: str) -> SpecialistAgentFn | None:
        return self._agents.get(agent_name)

    def require(self, agent_name: str) -> SpecialistAgentFn:
        try:
            return self._agents[agent_name]
        except KeyError as exc:
            raise SpecialistAgentNotFoundError(agent_name) from exc

    def has(self, agent_name: str) -> bool:
        return agent_name in self._agents

    def list_agents(self) -> list[str]:
        return sorted(self._agents)


def build_default_specialist_agent_registry() -> SpecialistAgentRegistry:
    """Fresh registry containing exactly the three Phase 10 read-only specialists.

    Write/proposal-capable specialists (`transcript_import_agent`,
    `semester_planning_agent`, and any future `action_proposal_agent`/
    `profile_update_agent`) are deliberately never registered here.
    """
    registry = SpecialistAgentRegistry()
    registry.register("graduation_progress_agent", run_graduation_progress_agent)
    registry.register("course_catalog_agent", run_course_catalog_agent)
    registry.register("requirement_explanation_agent", run_requirement_explanation_agent)
    return registry


__all__ = [
    "SpecialistAgentFn",
    "SpecialistAgentNotFoundError",
    "SpecialistAgentRegistry",
    "build_default_specialist_agent_registry",
    "SpecialistAgentInput",
    "SpecialistAgentOutput",
]
