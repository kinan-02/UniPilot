"""Deterministic Specialist Observation Builder (Phase 12) -- shadow-only.

Builds a bounded `SpecialistObservationBundle` for one specialist-agent call
from already-available in-memory data only:

1. An already-built `AgentContextPack` (duck-typed via `Any`, passed in --
   never rebuilt/re-fetched here; see `app.agent.context_builder` for the
   module that actually builds one, and
   `specialists.context.build_agent_context_pack_summary` for the existing
   Phase 10 precedent of accepting one this same way).
2. The specialist's already-compiled `compiled_context` dict.
3. Already-computed `dependency_outputs` (other subtasks' compact
   `output_summary`s from the supervisor blackboard).

Never touches a database, never calls an internal API, never calls an LLM
or `ReasoningBlock`, never performs a write, and never raises -- a
per-observation failure degrades to `status="failed"`/`"missing"` for that
one observation only, never crashes the caller. Every built summary is
passed through `safety.sanitize_observation_payload` before being attached
to the returned bundle.
"""

from __future__ import annotations

import logging
from collections.abc import Callable
from typing import Any

from app.agent.specialists.tools import adapters, summarizers
from app.agent.specialists.tools.registry import (
    ObservationDescriptor,
    SpecialistObservationRegistry,
    build_default_observation_registry,
)
from app.agent.specialists.tools.safety import sanitize_observation_payload
from app.agent.specialists.tools.schemas import (
    SpecialistObservation,
    SpecialistObservationBundle,
    SpecialistObservationRequest,
)

logger = logging.getLogger(__name__)

_MISSING_SOURCE_WARNING = "observation_source_unavailable"
_BUILD_FAILED_WARNING = "observation_build_failed"
_NOT_ALLOWED_WARNING_PREFIX = "observation_not_allowed_for_specialist"
_UNKNOWN_WARNING_PREFIX = "observation_unknown"
_OVER_BUDGET_WARNING_PREFIX = "observation_omitted_max_count_reached"

# Fail-closed hard ceiling: a misconfigured/hostile caller can never make
# the builder produce an unbounded number of observations, regardless of
# `SpecialistObservationRequest.max_observations`.
_HARD_MAX_OBSERVATIONS = 20

_ObservationBuilderResult = tuple[dict[str, Any] | None, str]
_ObservationBuilderFn = Callable[[SpecialistObservationRequest, Any, ObservationDescriptor], _ObservationBuilderResult]


def _build_profile_summary(
    request: SpecialistObservationRequest, agent_context_pack: Any, _descriptor: ObservationDescriptor
) -> _ObservationBuilderResult:
    pack_profile = adapters.user_context_of(agent_context_pack).get("profile")
    if isinstance(pack_profile, dict) and pack_profile:
        return summarizers.summarize_profile(pack_profile), "agent_context_pack"

    fields = adapters.profile_fields(agent_context_pack=agent_context_pack, compiled_context=request.compiled_context)
    if fields is None:
        return None, "agent_context_pack"
    return summarizers.summarize_profile(fields), "compiled_context"


def _build_completed_courses_summary(
    _request: SpecialistObservationRequest, agent_context_pack: Any, descriptor: ObservationDescriptor
) -> _ObservationBuilderResult:
    fields = adapters.completed_courses_fields(agent_context_pack=agent_context_pack)
    if fields is None:
        return None, "agent_context_pack"
    return (
        summarizers.summarize_completed_courses(fields, max_items=descriptor.max_summary_items),
        "agent_context_pack",
    )


def _build_graduation_audit_summary(
    request: SpecialistObservationRequest, agent_context_pack: Any, descriptor: ObservationDescriptor
) -> _ObservationBuilderResult:
    audit = adapters.graduation_audit_fields(
        agent_context_pack=agent_context_pack, dependency_outputs=request.dependency_outputs
    )
    if audit is None:
        return None, "deterministic_summary"
    return (
        summarizers.summarize_graduation_audit(audit, max_items=descriptor.max_summary_items),
        "deterministic_summary",
    )


def _build_requirement_bucket_summary(
    _request: SpecialistObservationRequest, agent_context_pack: Any, descriptor: ObservationDescriptor
) -> _ObservationBuilderResult:
    buckets = adapters.requirement_bucket_fields(agent_context_pack=agent_context_pack)
    if buckets is None:
        return None, "agent_context_pack"
    return (
        summarizers.summarize_requirement_buckets(buckets, max_items=descriptor.max_summary_items),
        "agent_context_pack",
    )


def _build_course_catalog_summary(
    _request: SpecialistObservationRequest, agent_context_pack: Any, _descriptor: ObservationDescriptor
) -> _ObservationBuilderResult:
    course = adapters.course_catalog_fields(agent_context_pack=agent_context_pack)
    if course is None:
        return None, "agent_context_pack"
    return summarizers.summarize_course_catalog(course), "agent_context_pack"


def _build_prerequisite_summary(
    _request: SpecialistObservationRequest, agent_context_pack: Any, _descriptor: ObservationDescriptor
) -> _ObservationBuilderResult:
    result = adapters.prerequisite_fields(agent_context_pack=agent_context_pack)
    if result is None:
        return None, "agent_context_pack"
    return summarizers.summarize_prerequisites(result), "agent_context_pack"


def _build_offering_summary(
    _request: SpecialistObservationRequest, agent_context_pack: Any, descriptor: ObservationDescriptor
) -> _ObservationBuilderResult:
    fields = adapters.offering_fields(agent_context_pack=agent_context_pack)
    if fields is None:
        return None, "agent_context_pack"
    return summarizers.summarize_offering(fields, max_items=descriptor.max_summary_items), "agent_context_pack"


def _build_requirement_contribution_summary(
    _request: SpecialistObservationRequest, agent_context_pack: Any, _descriptor: ObservationDescriptor
) -> _ObservationBuilderResult:
    contribution = adapters.requirement_contribution_fields(agent_context_pack=agent_context_pack)
    if contribution is None:
        return None, "agent_context_pack"
    return summarizers.summarize_requirement_contribution(contribution), "agent_context_pack"


def _build_wiki_snippet_summary(
    request: SpecialistObservationRequest, agent_context_pack: Any, descriptor: ObservationDescriptor
) -> _ObservationBuilderResult:
    snippets = adapters.wiki_snippet_fields(
        agent_context_pack=agent_context_pack, compiled_context=request.compiled_context
    )
    if not snippets:
        return None, "retrieval"
    return summarizers.summarize_wiki_snippets(snippets, max_items=descriptor.max_summary_items), "retrieval"


def _build_conversation_assumption_summary(
    request: SpecialistObservationRequest, agent_context_pack: Any, descriptor: ObservationDescriptor
) -> _ObservationBuilderResult:
    assumptions = adapters.conversation_assumption_fields(
        agent_context_pack=agent_context_pack, compiled_context=request.compiled_context
    )
    if not assumptions:
        return None, "conversation_memory"
    return (
        summarizers.summarize_conversation_assumptions(assumptions, max_items=descriptor.max_summary_items),
        "conversation_memory",
    )


_OBSERVATION_BUILDERS: dict[str, _ObservationBuilderFn] = {
    "profile_summary": _build_profile_summary,
    "completed_courses_summary": _build_completed_courses_summary,
    "graduation_audit_summary": _build_graduation_audit_summary,
    "requirement_bucket_summary": _build_requirement_bucket_summary,
    "course_catalog_summary": _build_course_catalog_summary,
    "prerequisite_summary": _build_prerequisite_summary,
    "offering_summary": _build_offering_summary,
    "requirement_contribution_summary": _build_requirement_contribution_summary,
    "wiki_snippet_summary": _build_wiki_snippet_summary,
    "conversation_assumption_summary": _build_conversation_assumption_summary,
}


def _resolve_requested_names(
    request: SpecialistObservationRequest, *, allowed: list[str]
) -> tuple[list[str], list[str], list[str]]:
    """Returns `(names_to_build, omitted_names, warnings)`, all deterministic.

    `allowed` is already in registry order. When the caller doesn't
    restrict `allowed_observations`, every allowed observation for this
    specialist is a candidate; otherwise only the intersection (still
    resolved back into registry order, never caller order) is.
    """
    allowed_set = set(allowed)
    requested = list(request.allowed_observations) if request.allowed_observations else list(allowed)

    omitted: list[str] = []
    warnings: list[str] = []
    candidates: list[str] = []
    for name in requested:
        if name not in allowed_set:
            omitted.append(name)
            warnings.append(f"{_NOT_ALLOWED_WARNING_PREFIX}:{name}")
            continue
        if name not in candidates:
            candidates.append(name)

    # Re-sort into registry order for determinism regardless of caller order.
    candidates = [name for name in allowed if name in candidates]

    max_count = max(0, min(request.max_observations, _HARD_MAX_OBSERVATIONS))
    if len(candidates) > max_count:
        overflow = candidates[max_count:]
        candidates = candidates[:max_count]
        omitted.extend(overflow)
        warnings.extend(f"{_OVER_BUDGET_WARNING_PREFIX}:{name}" for name in overflow)

    return candidates, omitted, warnings


def build_specialist_observations(
    request: SpecialistObservationRequest,
    *,
    agent_context_pack: Any | None = None,
    registry: SpecialistObservationRegistry | None = None,
) -> SpecialistObservationBundle:
    """Deterministically build a bounded, sanitized observation bundle.

    Never raises: an individual observation that can't be built degrades to
    `status="missing"` (source data unavailable) or `status="failed"` (an
    unexpected error while building it); the bundle itself always returns.
    """
    reg = registry or build_default_observation_registry()
    allowed = reg.allowed_observations_for_specialist(request.specialist_agent_name)

    names_to_build, omitted, warnings = _resolve_requested_names(request, allowed=allowed)

    observations: list[SpecialistObservation] = []
    for name in names_to_build:
        descriptor = reg.get(name)
        builder = _OBSERVATION_BUILDERS.get(name)
        if descriptor is None or builder is None:
            omitted.append(name)
            warnings.append(f"{_UNKNOWN_WARNING_PREFIX}:{name}")
            continue

        try:
            raw_summary, source = builder(request, agent_context_pack, descriptor)
        except Exception:  # noqa: BLE001 -- a single observation must never break the bundle
            logger.exception("specialist_observation_build_failed", extra={"observationName": name})
            observations.append(
                SpecialistObservation(
                    name=name,
                    status="failed",
                    source=descriptor.source,
                    summary={},
                    warnings=[_BUILD_FAILED_WARNING],
                    confidence=0.0,
                )
            )
            continue

        if raw_summary is None:
            observations.append(
                SpecialistObservation(
                    name=name,
                    status="missing",
                    source=descriptor.source,
                    summary={},
                    warnings=[_MISSING_SOURCE_WARNING],
                    confidence=0.0,
                )
            )
            continue

        sanitized_summary, sanitize_warnings = sanitize_observation_payload(
            raw_summary, extra_forbidden_keys=descriptor.forbidden_keys
        )
        observations.append(
            SpecialistObservation(
                name=name,
                status="available",
                source=source,  # type: ignore[arg-type]
                summary=sanitized_summary,
                warnings=sanitize_warnings,
                confidence=1.0 if not sanitize_warnings else 0.8,
            )
        )

    return SpecialistObservationBundle(
        specialist_agent_name=request.specialist_agent_name,
        subtask_id=request.subtask_id,
        observations=observations,
        warnings=warnings,
        omitted_observations=sorted(set(omitted)),
    )


__all__ = ["build_specialist_observations"]
