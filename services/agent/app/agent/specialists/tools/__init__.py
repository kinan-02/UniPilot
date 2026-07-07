"""Specialist Tool Observation Layer (Phase 12) -- shadow-only.

Deterministic, bounded, read-only observations a specialist agent may
receive alongside `compiled_context`/`dependency_outputs` before its
`ReasoningBlock` call. See `observation_builder.build_specialist_observations`
for the entry point, and `docs/agent/CURRENT_STATE.md`'s Phase 12 section
for the full design.

Importing this package has no side effects: nothing here touches a
database, calls an internal API, or calls an LLM/`ReasoningBlock`. Every
observation is read-only and `side_effect_level="none"` by construction
(see `registry.ObservationDescriptor`) -- there is no way to register a
write/proposal observation through this package.
"""

from __future__ import annotations

from app.agent.specialists.tools.observation_builder import build_specialist_observations
from app.agent.specialists.tools.registry import (
    ObservationDescriptor,
    SpecialistObservationNotFoundError,
    SpecialistObservationRegistry,
    build_default_observation_registry,
)
from app.agent.specialists.tools.safety import (
    FORBIDDEN_OBSERVATION_KEYS,
    is_observation_descriptor_safe,
    sanitize_observation_payload,
)
from app.agent.specialists.tools.schemas import (
    SpecialistObservation,
    SpecialistObservationBundle,
    SpecialistObservationRequest,
    SpecialistObservationSource,
    SpecialistObservationStatus,
)

__all__ = [
    "FORBIDDEN_OBSERVATION_KEYS",
    "ObservationDescriptor",
    "SpecialistObservation",
    "SpecialistObservationBundle",
    "SpecialistObservationNotFoundError",
    "SpecialistObservationRegistry",
    "SpecialistObservationRequest",
    "SpecialistObservationSource",
    "SpecialistObservationStatus",
    "build_default_observation_registry",
    "build_specialist_observations",
    "is_observation_descriptor_safe",
    "sanitize_observation_payload",
]
