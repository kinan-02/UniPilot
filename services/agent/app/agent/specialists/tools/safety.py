"""Deterministic safety filtering for specialist tool observations (Phase 12).

Pure functions only -- no I/O, no LLM calls, no database access. Applied to
every `SpecialistObservation.summary` inside `observation_builder.py`
before it is ever attached to a `SpecialistAgentInput`, regardless of which
adapter/summarizer produced the raw fragment.

Reuses the shared `FORBIDDEN_DIAGNOSTIC_KEYS` tuple
(`app.agent.supervisor.validation_schemas`) rather than keeping a second,
divergent forbidden-key list -- exactly the same pattern Phase 11's
`specialists.validation_schemas.FORBIDDEN_SPECIALIST_KEYS` already
established. That shared list already matches the Phase 12 spec's forbidden
key list verbatim (same keys, different order).
"""

from __future__ import annotations

from typing import Any

from app.agent.specialists.tools.registry import ObservationDescriptor
from app.agent.supervisor.validation_schemas import FORBIDDEN_DIAGNOSTIC_KEYS

FORBIDDEN_OBSERVATION_KEYS: frozenset[str] = frozenset(FORBIDDEN_DIAGNOSTIC_KEYS)

_FORBIDDEN_WARNING_PREFIX = "forbidden_observation_payload_omitted"


def _sanitize(value: Any, *, forbidden_keys: frozenset[str], warnings: list[str]) -> Any:
    if isinstance(value, dict):
        sanitized: dict[str, Any] = {}
        for key, item in value.items():
            key_str = str(key)
            if key_str in forbidden_keys:
                warnings.append(f"{_FORBIDDEN_WARNING_PREFIX}:{key_str}")
                continue
            sanitized[key_str] = _sanitize(item, forbidden_keys=forbidden_keys, warnings=warnings)
        return sanitized
    if isinstance(value, list | tuple | set):
        return [_sanitize(item, forbidden_keys=forbidden_keys, warnings=warnings) for item in value]
    return value


def sanitize_observation_payload(
    payload: dict[str, Any], *, extra_forbidden_keys: frozenset[str] | None = None
) -> tuple[dict[str, Any], list[str]]:
    """Recursively strip forbidden keys from `payload` (at any nesting depth).

    Returns `(sanitized_payload, warnings)` -- one
    `forbidden_observation_payload_omitted:<key>` warning per omitted key
    occurrence, including nested occurrences inside lists/dicts. Never
    raises: a malformed/unexpected `payload` degrades to `({}, [])` rather
    than an exception escaping this function.
    """
    forbidden = FORBIDDEN_OBSERVATION_KEYS | (extra_forbidden_keys or frozenset())
    try:
        warnings: list[str] = []
        sanitized = _sanitize(payload, forbidden_keys=forbidden, warnings=warnings)
    except Exception:  # noqa: BLE001 -- sanitization must never raise into a caller
        return {}, []
    if not isinstance(sanitized, dict):
        return {}, warnings
    return sanitized, warnings


def is_observation_descriptor_safe(descriptor: ObservationDescriptor) -> bool:
    """`True` only when `descriptor` declares itself read-only with no side effects."""
    return bool(descriptor.read_only) and descriptor.side_effect_level == "none"


__all__ = [
    "FORBIDDEN_OBSERVATION_KEYS",
    "is_observation_descriptor_safe",
    "sanitize_observation_payload",
]
