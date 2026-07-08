"""Registry of the generic tool primitives (docs/agent/AGENT_VISION.md §5).

A `ToolDescriptor` pairs one primitive's typed input/output schema with its
callable and side-effect classification -- so a subagent's tool grant can be
expressed as a bounded subset of registered names (see roles.schemas
`RoleDefinition.tool_grant_ceiling` and subagents.tool_loop).
"""

from __future__ import annotations

from collections.abc import Awaitable, Callable
from typing import Literal

from pydantic import BaseModel

from app.agent_core.tools.envelope import ToolOutputEnvelope

ToolSideEffect = Literal["read", "compute", "propose"]

ToolCallable = Callable[[BaseModel], Awaitable[ToolOutputEnvelope]]


class ToolDescriptor(BaseModel):
    model_config = {"arbitrary_types_allowed": True}

    name: str
    description: str
    input_model: type[BaseModel]
    output_model: type[BaseModel]
    side_effect: ToolSideEffect
    callable: ToolCallable


class ToolNotFoundError(KeyError):
    """Raised by `ToolRegistry.get` for an unregistered tool name."""


class ToolRegistry:
    def __init__(self) -> None:
        self._tools: dict[str, ToolDescriptor] = {}

    def register(self, descriptor: ToolDescriptor, *, overwrite: bool = False) -> None:
        if descriptor.side_effect == "propose" and descriptor.name != "propose_action":
            raise ValueError(f"only propose_action may declare side_effect='propose': {descriptor.name}")
        if not overwrite and descriptor.name in self._tools:
            raise ValueError(f"tool_already_registered: {descriptor.name}")
        self._tools[descriptor.name] = descriptor

    def get(self, name: str) -> ToolDescriptor:
        try:
            return self._tools[name]
        except KeyError as exc:
            raise ToolNotFoundError(name) from exc

    def has(self, name: str) -> bool:
        return name in self._tools

    def names(self) -> list[str]:
        return sorted(self._tools)


__all__ = ["ToolSideEffect", "ToolCallable", "ToolDescriptor", "ToolNotFoundError", "ToolRegistry"]
