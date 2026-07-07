"""In-memory registry of `CapabilityDescriptor`s (Phase 4).

Deterministic, synchronous, no database/LLM access — safe to construct at
import time or fresh per-call. Nothing here executes a capability; this is
purely a queryable catalog for a future planner (Phase 5+) to reason over.
"""

from __future__ import annotations

from app.agent.capabilities.schemas import CapabilityDescriptor, CapabilityType


class CapabilityNotFoundError(KeyError):
    """Raised by `CapabilityRegistry.require` for an unknown capability name."""


class DuplicateCapabilityError(ValueError):
    """Raised when registering a capability name that already exists."""


class CapabilityRegistry:
    """Queryable, in-memory catalog of the system's capabilities."""

    def __init__(self) -> None:
        self._capabilities: dict[str, CapabilityDescriptor] = {}

    def register(self, capability: CapabilityDescriptor, *, overwrite: bool = False) -> None:
        if not overwrite and capability.name in self._capabilities:
            raise DuplicateCapabilityError(f"capability_already_registered: {capability.name}")
        self._capabilities[capability.name] = capability

    def list_capabilities(self) -> list[CapabilityDescriptor]:
        return [self._capabilities[name] for name in sorted(self._capabilities)]

    def get(self, name: str) -> CapabilityDescriptor | None:
        return self._capabilities.get(name)

    def require(self, name: str) -> CapabilityDescriptor:
        try:
            return self._capabilities[name]
        except KeyError as exc:
            raise CapabilityNotFoundError(name) from exc

    def has(self, name: str) -> bool:
        return name in self._capabilities

    def names(self) -> list[str]:
        return sorted(self._capabilities)

    def find_by_intent(self, intent: str) -> list[CapabilityDescriptor]:
        return [
            capability
            for capability in self.list_capabilities()
            if intent in capability.supported_intents
        ]

    def find_by_type(self, capability_type: CapabilityType) -> list[CapabilityDescriptor]:
        return [
            capability
            for capability in self.list_capabilities()
            if capability.type == capability_type
        ]

    def find_for_task_category(self, task_category: str) -> list[CapabilityDescriptor]:
        return [
            capability
            for capability in self.list_capabilities()
            if task_category in capability.supported_task_categories
        ]

    def find_enabled(self) -> list[CapabilityDescriptor]:
        return [capability for capability in self.list_capabilities() if capability.enabled]
