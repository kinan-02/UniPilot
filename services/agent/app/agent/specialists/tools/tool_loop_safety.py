"""Deterministic safety checks for the Specialist Tool-Request Loop (Phase 13).

Pure functions only -- no I/O, no LLM calls, no database access. Reuses
`specialists.tools.safety.FORBIDDEN_OBSERVATION_KEYS` (itself the shared
`FORBIDDEN_DIAGNOSTIC_KEYS` tuple) rather than keeping a third, divergent
forbidden-key list, and `specialists.tools.safety.is_observation_descriptor_safe`
to verify a requested observation is genuinely `read_only`/`side_effect_level
== "none"` before it can ever be approved.
"""

from __future__ import annotations

from typing import Any

from app.agent.specialists.tools.registry import ObservationDescriptor
from app.agent.specialists.tools.safety import FORBIDDEN_OBSERVATION_KEYS, is_observation_descriptor_safe

# Re-exported so `tool_requests.py` (and its tests) can import a single,
# tool-loop-specific name without needing to know it is shared with the
# Phase 12 observation-payload safety layer.
FORBIDDEN_TOOL_REQUEST_ARGUMENT_KEYS = FORBIDDEN_OBSERVATION_KEYS

# Fail-closed ceiling on how many top-level argument keys a single tool
# request may carry -- independent of the forbidden-key scan below, this
# keeps a hostile/malformed `arguments` payload from doing meaningful work
# (e.g. an unbounded nested structure) even before it is scanned.
MAX_TOOL_REQUEST_ARGUMENT_KEYS = 20


def find_forbidden_argument_keys(arguments: Any) -> list[str]:
    """Recursively find forbidden key names inside `arguments` (any depth).

    Returns the distinct forbidden key *names* found, in first-seen order --
    never full paths, never the associated values. Never raises: a
    malformed/unexpected `arguments` payload degrades to `[]`.
    """
    found: list[str] = []

    def _walk(value: Any) -> None:
        if isinstance(value, dict):
            for key, item in value.items():
                key_str = str(key)
                if key_str in FORBIDDEN_TOOL_REQUEST_ARGUMENT_KEYS and key_str not in found:
                    found.append(key_str)
                _walk(item)
        elif isinstance(value, (list, tuple, set)):
            for item in value:
                _walk(item)

    try:
        _walk(arguments)
    except Exception:  # noqa: BLE001 -- a scan bug must never break a caller
        return []
    return found


def has_too_many_argument_keys(arguments: Any) -> bool:
    """`True` only when `arguments` is a dict with more than
    `MAX_TOOL_REQUEST_ARGUMENT_KEYS` top-level keys -- defensive only, since
    every real observation request needs zero or very few keys."""
    if not isinstance(arguments, dict):
        return False
    return len(arguments) > MAX_TOOL_REQUEST_ARGUMENT_KEYS


def is_requested_observation_safe(descriptor: ObservationDescriptor) -> bool:
    """`True` only when `descriptor` is genuinely read-only/no-side-effect.

    Thin, tool-loop-specific wrapper over `tools.safety.is_observation_descriptor_safe`
    -- kept as its own function so the tool-request validator never needs to
    import the Phase 12 safety module's name directly.
    """
    return is_observation_descriptor_safe(descriptor)


__all__ = [
    "FORBIDDEN_TOOL_REQUEST_ARGUMENT_KEYS",
    "MAX_TOOL_REQUEST_ARGUMENT_KEYS",
    "find_forbidden_argument_keys",
    "has_too_many_argument_keys",
    "is_requested_observation_safe",
]
