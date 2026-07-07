"""Deterministic Specialist Observation Registry (Phase 12).

In-memory, insertion-ordered catalog of `ObservationDescriptor`s -- the
Phase 12 analogue of `specialists.registry.SpecialistAgentRegistry` and
`capabilities.registry.CapabilityRegistry`. Deterministic and side-effect
free: constructing/querying a registry never touches a database, an
internal API, or an LLM.

Every descriptor declares itself read-only with `side_effect_level="none"`
-- there is deliberately no way to register a write/proposal observation
through this registry (no such fields exist on `ObservationDescriptor`).
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Literal

from app.agent.specialists.tools.schemas import SpecialistObservationSource

ObservationSideEffectLevel = Literal["none"]


class SpecialistObservationNotFoundError(KeyError):
    """Raised by `SpecialistObservationRegistry.require` for an unknown observation name."""


@dataclass(frozen=True)
class ObservationDescriptor:
    """Metadata describing one deterministic, read-only observation kind."""

    name: str
    description: str
    allowed_specialists: tuple[str, ...]
    source: SpecialistObservationSource
    read_only: bool = True
    side_effect_level: ObservationSideEffectLevel = "none"
    max_summary_items: int = 10
    forbidden_keys: frozenset[str] = field(default_factory=frozenset)


class SpecialistObservationRegistry:
    """Queryable, insertion-ordered catalog of observation descriptors."""

    def __init__(self) -> None:
        self._descriptors: dict[str, ObservationDescriptor] = {}

    def register(self, descriptor: ObservationDescriptor, *, overwrite: bool = False) -> None:
        if not overwrite and descriptor.name in self._descriptors:
            raise ValueError(f"observation_already_registered: {descriptor.name}")
        self._descriptors[descriptor.name] = descriptor

    def get(self, name: str) -> ObservationDescriptor | None:
        return self._descriptors.get(name)

    def require(self, name: str) -> ObservationDescriptor:
        try:
            return self._descriptors[name]
        except KeyError as exc:
            raise SpecialistObservationNotFoundError(name) from exc

    def has(self, name: str) -> bool:
        return name in self._descriptors

    def list_names(self) -> list[str]:
        """Deterministic registration order (not alphabetical)."""
        return list(self._descriptors)

    def list_descriptors(self) -> list[ObservationDescriptor]:
        return list(self._descriptors.values())

    def allowed_observations_for_specialist(self, specialist_agent_name: str) -> list[str]:
        """Registry-order list of observation names `specialist_agent_name` may receive."""
        return [
            name
            for name, descriptor in self._descriptors.items()
            if specialist_agent_name in descriptor.allowed_specialists
        ]


# ---------------------------------------------------------------------------
# Phase 12 spec's exact per-specialist allowed-observation mapping.
# ---------------------------------------------------------------------------

GRADUATION_PROGRESS_AGENT = "graduation_progress_agent"
COURSE_CATALOG_AGENT = "course_catalog_agent"
REQUIREMENT_EXPLANATION_AGENT = "requirement_explanation_agent"

SPECIALIST_ALLOWED_OBSERVATIONS: dict[str, tuple[str, ...]] = {
    GRADUATION_PROGRESS_AGENT: (
        "profile_summary",
        "completed_courses_summary",
        "graduation_audit_summary",
        "requirement_bucket_summary",
        "conversation_assumption_summary",
    ),
    COURSE_CATALOG_AGENT: (
        "profile_summary",
        "completed_courses_summary",
        "course_catalog_summary",
        "prerequisite_summary",
        "offering_summary",
        "requirement_contribution_summary",
        "wiki_snippet_summary",
        "conversation_assumption_summary",
    ),
    REQUIREMENT_EXPLANATION_AGENT: (
        "profile_summary",
        "requirement_bucket_summary",
        "course_catalog_summary",
        "requirement_contribution_summary",
        "wiki_snippet_summary",
        "conversation_assumption_summary",
    ),
}


def _allowed_specialists_for(observation_name: str) -> tuple[str, ...]:
    return tuple(
        specialist
        for specialist, observations in SPECIALIST_ALLOWED_OBSERVATIONS.items()
        if observation_name in observations
    )


def build_default_observation_registry() -> SpecialistObservationRegistry:
    """Fresh registry with the exact Phase 12 observation set, in a fixed,
    deterministic (registration) order.

    Every descriptor is `read_only=True`/`side_effect_level="none"` --
    there is no write/proposal observation registered here, by construction.
    """
    registry = SpecialistObservationRegistry()
    descriptors = (
        ObservationDescriptor(
            name="profile_summary",
            description="Compact student profile (degree program, track, catalog year, current semester).",
            allowed_specialists=_allowed_specialists_for("profile_summary"),
            source="agent_context_pack",
            max_summary_items=10,
        ),
        ObservationDescriptor(
            name="completed_courses_summary",
            description="Count and compact sample of completed course numbers already on file.",
            allowed_specialists=_allowed_specialists_for("completed_courses_summary"),
            source="agent_context_pack",
            max_summary_items=15,
        ),
        ObservationDescriptor(
            name="graduation_audit_summary",
            description="Compact graduation-audit numbers already computed deterministically.",
            allowed_specialists=_allowed_specialists_for("graduation_audit_summary"),
            source="deterministic_summary",
            max_summary_items=10,
        ),
        ObservationDescriptor(
            name="requirement_bucket_summary",
            description="Compact list of degree requirement buckets already loaded for the program.",
            allowed_specialists=_allowed_specialists_for("requirement_bucket_summary"),
            source="agent_context_pack",
            max_summary_items=10,
        ),
        ObservationDescriptor(
            name="course_catalog_summary",
            description="Compact catalog record for the course already resolved in context.",
            allowed_specialists=_allowed_specialists_for("course_catalog_summary"),
            source="agent_context_pack",
            max_summary_items=1,
        ),
        ObservationDescriptor(
            name="prerequisite_summary",
            description="Compact prerequisite-eligibility result already computed for the course.",
            allowed_specialists=_allowed_specialists_for("prerequisite_summary"),
            source="agent_context_pack",
            max_summary_items=10,
        ),
        ObservationDescriptor(
            name="offering_summary",
            description="Compact offering summary already resolved for the course/semester.",
            allowed_specialists=_allowed_specialists_for("offering_summary"),
            source="agent_context_pack",
            max_summary_items=5,
        ),
        ObservationDescriptor(
            name="requirement_contribution_summary",
            description="Compact requirement-contribution result already resolved for the course.",
            allowed_specialists=_allowed_specialists_for("requirement_contribution_summary"),
            source="agent_context_pack",
            max_summary_items=10,
        ),
        ObservationDescriptor(
            name="wiki_snippet_summary",
            description="Capped list of already-retrieved wiki snippet previews (title + short preview only).",
            allowed_specialists=_allowed_specialists_for("wiki_snippet_summary"),
            source="retrieval",
            max_summary_items=5,
            forbidden_keys=frozenset({"content"}),
        ),
        ObservationDescriptor(
            name="conversation_assumption_summary",
            description="Already-recorded conversation/context assumptions.",
            allowed_specialists=_allowed_specialists_for("conversation_assumption_summary"),
            source="conversation_memory",
            max_summary_items=10,
        ),
    )
    for descriptor in descriptors:
        registry.register(descriptor)
    return registry


__all__ = [
    "COURSE_CATALOG_AGENT",
    "GRADUATION_PROGRESS_AGENT",
    "REQUIREMENT_EXPLANATION_AGENT",
    "SPECIALIST_ALLOWED_OBSERVATIONS",
    "ObservationDescriptor",
    "ObservationSideEffectLevel",
    "SpecialistObservationNotFoundError",
    "SpecialistObservationRegistry",
    "build_default_observation_registry",
]
