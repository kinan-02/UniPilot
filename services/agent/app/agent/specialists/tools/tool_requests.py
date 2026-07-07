"""Deterministic validation for specialist-requested observation "tools" (Phase 13).

Turns a specialist's raw `ReasoningBlockOutput.tool_requests` (Phase 1
foundation -- `status="needs_tool"`) into a bounded, validated list of
approved Phase 12 observation names, plus a full per-request audit trail.
Pure, side-effect-free, and deterministic: this module never calls the
observation builder itself (see `tool_loop.py`), never touches a database
or an internal API, and never calls an LLM.

A request is approved only when *all* of the following hold:
- `observation_name` is a real, registered Phase 12 observation
  (`SpecialistObservationRegistry.get`).
- The observation is allowed for the requesting specialist
  (`SPECIALIST_ALLOWED_OBSERVATIONS`, via `registry.allowed_observations_for_specialist`).
- The observation descriptor is genuinely read-only / no-side-effect
  (`tool_loop_safety.is_requested_observation_safe`) -- defensive, since the
  registry can only ever construct read-only descriptors, but checked
  explicitly anyway.
- The observation name was not already supplied (either already present in
  `deterministic_observations` before this round, or requested more than
  once within the same round) -- the first occurrence wins.
- `arguments` carries no forbidden key at any nesting depth
  (`tool_loop_safety.find_forbidden_argument_keys`).
- The request falls within `max_requests_per_round` (position-based, not
  approval-based -- mirrors `observation_builder._resolve_requested_names`'s
  own slice-then-warn pattern).

Never raises: a malformed/unexpected request (missing name, non-dict
`arguments`, wrong type entirely) degrades to a skipped/`"failed"` result,
never an exception escaping this module.
"""

from __future__ import annotations

from collections.abc import Iterable, Sequence
from typing import Any

from pydantic import BaseModel, Field

from app.agent.reasoning.schemas import ReasoningToolRequest
from app.agent.specialists.tools.registry import SpecialistObservationRegistry
from app.agent.specialists.tools.tool_loop_safety import (
    find_forbidden_argument_keys,
    is_requested_observation_safe,
)
from app.agent.specialists.tools.tool_loop_schemas import (
    SpecialistObservationToolRequest,
    SpecialistObservationToolResult,
)

_UNKNOWN_WARNING_PREFIX = "tool_request_unknown_observation"
_NOT_ALLOWED_WARNING_PREFIX = "tool_request_not_allowed_for_specialist"
_DUPLICATE_WARNING_PREFIX = "tool_request_duplicate_observation"
_FORBIDDEN_ARGS_WARNING_PREFIX = "tool_request_forbidden_arguments"
_BUDGET_EXCEEDED_WARNING = "tool_request_budget_exceeded"
_VALIDATION_FAILED_WARNING = "tool_request_validation_failed"


class SpecialistToolRequestValidationOutcome(BaseModel):
    """Result of validating one round's worth of tool requests.

    `results` always has exactly one entry per non-empty coerced request
    (including budget-rejected ones); malformed/empty requests are dropped
    silently before this point, exactly like `reasoning_block._extract_pass_payload`
    already drops malformed `tool_requests` entries.
    """

    results: list[SpecialistObservationToolResult] = Field(default_factory=list)
    approved_observation_names: list[str] = Field(default_factory=list)
    warnings: list[str] = Field(default_factory=list)


def _coerce_tool_requests(
    requests: Sequence[ReasoningToolRequest | SpecialistObservationToolRequest | dict[str, Any]] | None,
) -> list[SpecialistObservationToolRequest]:
    """Defensively coerce raw tool requests into `SpecialistObservationToolRequest`s.

    Accepts a `ReasoningToolRequest` (the real runtime shape), an
    already-built `SpecialistObservationToolRequest` (test convenience), or a
    raw dict (`tool_name`/`observation_name`/`name` + `purpose` + `arguments`)
    -- anything else, or anything that raises while being read, is dropped
    silently. Never raises.
    """
    coerced: list[SpecialistObservationToolRequest] = []
    for raw in requests or []:
        try:
            if isinstance(raw, SpecialistObservationToolRequest):
                if raw.observation_name.strip():
                    coerced.append(raw)
                continue
            if isinstance(raw, ReasoningToolRequest):
                name = raw.tool_name
                purpose = raw.purpose
                arguments = raw.arguments
            elif isinstance(raw, dict):
                name = raw.get("observation_name") or raw.get("tool_name") or raw.get("name") or ""
                purpose = raw.get("purpose") or ""
                arguments = raw.get("arguments")
            else:
                continue

            name = str(name or "").strip()
            if not name:
                continue
            arguments = arguments if isinstance(arguments, dict) else {}
            coerced.append(
                SpecialistObservationToolRequest(observation_name=name, purpose=str(purpose or ""), arguments=arguments)
            )
        except Exception:  # noqa: BLE001 -- one malformed request must never break the batch
            continue
    return coerced


def _validate_single_request(
    request: SpecialistObservationToolRequest,
    *,
    specialist_agent_name: str,
    registry: SpecialistObservationRegistry,
    allowed_names: set[str],
    already_present: set[str],
    seen_this_round: set[str],
) -> SpecialistObservationToolResult:
    name = request.observation_name
    try:
        if name in already_present or name in seen_this_round:
            return SpecialistObservationToolResult(
                observation_name=name, status="rejected", warnings=[f"{_DUPLICATE_WARNING_PREFIX}:{name}"]
            )

        descriptor = registry.get(name)
        if descriptor is None:
            return SpecialistObservationToolResult(
                observation_name=name, status="unavailable", warnings=[f"{_UNKNOWN_WARNING_PREFIX}:{name}"]
            )

        if name not in allowed_names or specialist_agent_name not in descriptor.allowed_specialists:
            return SpecialistObservationToolResult(
                observation_name=name, status="rejected", warnings=[f"{_NOT_ALLOWED_WARNING_PREFIX}:{name}"]
            )

        if not is_requested_observation_safe(descriptor):
            return SpecialistObservationToolResult(
                observation_name=name, status="rejected", warnings=[f"{_NOT_ALLOWED_WARNING_PREFIX}:{name}"]
            )

        forbidden_keys = find_forbidden_argument_keys(request.arguments)
        if forbidden_keys:
            return SpecialistObservationToolResult(
                observation_name=name,
                status="rejected",
                warnings=[f"{_FORBIDDEN_ARGS_WARNING_PREFIX}:{key}" for key in forbidden_keys],
            )

        return SpecialistObservationToolResult(observation_name=name, status="approved")
    except Exception:  # noqa: BLE001 -- a single malformed request must never raise
        return SpecialistObservationToolResult(
            observation_name=name or "unknown", status="failed", warnings=[_VALIDATION_FAILED_WARNING]
        )


def validate_tool_requests(
    requests: Sequence[ReasoningToolRequest | SpecialistObservationToolRequest | dict[str, Any]] | None,
    *,
    specialist_agent_name: str,
    already_present_observations: Iterable[str] = (),
    registry: SpecialistObservationRegistry,
    max_requests_per_round: int,
) -> SpecialistToolRequestValidationOutcome:
    """Validate one round's worth of specialist-requested observation "tools".

    Never raises. `max_requests_per_round` is applied positionally (the
    first `max_requests_per_round` coerced requests are validated normally;
    any beyond that are rejected outright with `tool_request_budget_exceeded`),
    mirroring `observation_builder`'s own slice-then-warn budget pattern.
    """
    coerced = _coerce_tool_requests(requests)
    budget = max(0, int(max_requests_per_round))
    within_budget, over_budget = coerced[:budget], coerced[budget:]

    already_present = {str(name) for name in already_present_observations}
    allowed_names = set(registry.allowed_observations_for_specialist(specialist_agent_name))
    seen_this_round: set[str] = set()

    results: list[SpecialistObservationToolResult] = []
    approved: list[str] = []
    for request in within_budget:
        result = _validate_single_request(
            request,
            specialist_agent_name=specialist_agent_name,
            registry=registry,
            allowed_names=allowed_names,
            already_present=already_present,
            seen_this_round=seen_this_round,
        )
        results.append(result)
        if result.status == "approved":
            approved.append(result.observation_name)
            seen_this_round.add(result.observation_name)

    for request in over_budget:
        results.append(
            SpecialistObservationToolResult(
                observation_name=request.observation_name, status="rejected", warnings=[_BUDGET_EXCEEDED_WARNING]
            )
        )

    warnings: list[str] = []
    for result in results:
        for warning in result.warnings:
            if warning not in warnings:
                warnings.append(warning)

    return SpecialistToolRequestValidationOutcome(results=results, approved_observation_names=approved, warnings=warnings)


__all__ = [
    "SpecialistToolRequestValidationOutcome",
    "validate_tool_requests",
]
