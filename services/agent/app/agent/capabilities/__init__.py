"""Capability Registry (Phase 4).

Describes, in a typed and queryable way, what the agent system can do
(workflows, future specialist agents, tools, internal APIs, retrieval,
validators, composers). Metadata only in Phase 4 — nothing here executes a
capability or influences live workflow selection. Importing this package
has no side effects.
"""

from __future__ import annotations

from app.agent.capabilities.default_registry import build_default_capability_registry
from app.agent.capabilities.registry import (
    CapabilityNotFoundError,
    CapabilityRegistry,
    DuplicateCapabilityError,
)
from app.agent.capabilities.schemas import (
    CapabilityContextContract,
    CapabilityDescriptor,
    CapabilityExecutionMetadata,
    CapabilityIOContract,
    CapabilityPermissionScope,
    CapabilityRiskLevel,
    CapabilitySideEffectLevel,
    CapabilityType,
    CapabilityWriteScope,
)
from app.agent.capabilities.source_of_truth import (
    SOURCE_OF_TRUTH_HIERARCHY,
    compare_source_trust,
    get_source_of_truth_rank,
    is_higher_trust,
)

__all__ = [
    "build_default_capability_registry",
    "CapabilityNotFoundError",
    "CapabilityRegistry",
    "DuplicateCapabilityError",
    "CapabilityContextContract",
    "CapabilityDescriptor",
    "CapabilityExecutionMetadata",
    "CapabilityIOContract",
    "CapabilityPermissionScope",
    "CapabilityRiskLevel",
    "CapabilitySideEffectLevel",
    "CapabilityType",
    "CapabilityWriteScope",
    "SOURCE_OF_TRUTH_HIERARCHY",
    "compare_source_trust",
    "get_source_of_truth_rank",
    "is_higher_trust",
]
