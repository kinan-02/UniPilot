"""Bounded Specialist Tool-Request Loop -- observation execution (Phase 13).

`run_specialist_tool_loop` handles exactly one round: it validates a
specialist's requested observation "tools" (`tool_requests.validate_tool_requests`)
and, for every approved name, builds the observation through the existing
Phase 12 `observation_builder.build_specialist_observations` -- the single,
already-audited entry point for turning an observation name into a
sanitized `SpecialistObservation`. No second observation system is created
here, and this module never calls an LLM/reasoning runtime itself; the
caller (`specialists/base.py`) is responsible for the subsequent reasoning
re-run once this function returns.

Hard constraints (enforced by construction):
- Only ever calls `observation_builder.build_specialist_observations` --
  never a database, never an internal API, never a rebuilt context.
- Never raises: a failed/empty observation build degrades that round to
  "no new observations", never an exception escaping this function.
- Never returns raw observation `summary` content in its own return value
  beyond what is needed to append to `deterministic_observations` for the
  next reasoning pass -- diagnostics-facing counts/names are built
  separately (`tool_loop_diagnostics.py`) from *names* only.
"""

from __future__ import annotations

import logging
from collections.abc import Iterable, Sequence
from dataclasses import dataclass, field
from typing import Any

from app.agent.reasoning.schemas import ReasoningToolRequest
from app.agent.specialists.schemas import SpecialistToolObservation
from app.agent.specialists.tools.observation_builder import build_specialist_observations
from app.agent.specialists.tools.registry import SpecialistObservationRegistry, build_default_observation_registry
from app.agent.specialists.tools.schemas import SpecialistObservationRequest
from app.agent.specialists.tools.tool_loop_schemas import SpecialistObservationToolRequest
from app.agent.specialists.tools.tool_requests import validate_tool_requests

logger = logging.getLogger(__name__)

_BUILD_FAILED_WARNING = "tool_loop_observation_build_failed"


@dataclass(frozen=True)
class SpecialistToolLoopRoundOutcome:
    """Internal, single-round result -- never surfaced to a caller as-is;
    `specialists/base.py` accumulates this across rounds into a
    `SpecialistToolLoopDiagnostics` (names/counts only)."""

    requested_observations: list[str] = field(default_factory=list)
    approved_observations: list[str] = field(default_factory=list)
    rejected_observations: list[str] = field(default_factory=list)
    missing_observations: list[str] = field(default_factory=list)
    new_observations: list[SpecialistToolObservation] = field(default_factory=list)
    warnings: list[str] = field(default_factory=list)


def _requested_names(
    tool_requests: Sequence[ReasoningToolRequest | SpecialistObservationToolRequest | dict[str, Any]] | None,
) -> list[str]:
    names: list[str] = []
    for raw in tool_requests or []:
        try:
            if isinstance(raw, (ReasoningToolRequest, SpecialistObservationToolRequest)):
                name = getattr(raw, "tool_name", None) or getattr(raw, "observation_name", None) or ""
            elif isinstance(raw, dict):
                name = raw.get("tool_name") or raw.get("observation_name") or raw.get("name") or ""
            else:
                continue
            name = str(name or "").strip()
            if name:
                names.append(name)
        except Exception:  # noqa: BLE001 -- diagnostics-only extraction must never raise
            continue
    return names


def run_specialist_tool_loop(
    *,
    tool_requests: Sequence[ReasoningToolRequest | SpecialistObservationToolRequest | dict[str, Any]] | None,
    specialist_agent_name: str,
    subtask_id: str,
    objective: str,
    user_message: str,
    compiled_context: dict[str, Any],
    dependency_outputs: dict[str, Any],
    already_present_observations: Iterable[str] = (),
    max_requests_per_round: int = 4,
    agent_context_pack: Any | None = None,
    registry: SpecialistObservationRegistry | None = None,
) -> SpecialistToolLoopRoundOutcome:
    """Validate + execute one round of specialist-requested observation "tools".

    Never raises. Returns approved-and-built observations (ready to append
    to `SpecialistAgentInput.deterministic_observations`) plus a compact,
    names-only audit trail for `SpecialistToolLoopDiagnostics`.
    """
    reg = registry or build_default_observation_registry()

    validation = validate_tool_requests(
        tool_requests,
        specialist_agent_name=specialist_agent_name,
        already_present_observations=already_present_observations,
        registry=reg,
        max_requests_per_round=max_requests_per_round,
    )

    approved_names = validation.approved_observation_names
    rejected_names = [result.observation_name for result in validation.results if result.status != "approved"]
    new_observations: list[SpecialistToolObservation] = []
    missing_names: list[str] = []
    warnings = list(validation.warnings)

    if approved_names:
        try:
            request = SpecialistObservationRequest(
                specialist_agent_name=specialist_agent_name,
                subtask_id=subtask_id,
                objective=objective,
                user_message=user_message,
                compiled_context=compiled_context,
                dependency_outputs=dependency_outputs,
                allowed_observations=approved_names,
                max_observations=len(approved_names),
            )
            bundle = build_specialist_observations(request, agent_context_pack=agent_context_pack, registry=reg)
        except Exception:  # noqa: BLE001 -- one round must never break the specialist call
            logger.exception(
                "specialist_tool_loop_observation_build_failed",
                extra={"subtaskId": subtask_id, "agentName": specialist_agent_name},
            )
            bundle = None

        if bundle is None:
            missing_names.extend(approved_names)
            warnings.append(_BUILD_FAILED_WARNING)
        else:
            for observation in bundle.observations:
                if observation.status == "available":
                    new_observations.append(
                        SpecialistToolObservation(
                            name=observation.name,
                            status=observation.status,
                            summary=observation.summary,
                            source=observation.source,
                            warnings=observation.warnings,
                        )
                    )
                else:
                    missing_names.append(observation.name)
            for warning in bundle.warnings:
                if warning not in warnings:
                    warnings.append(warning)

    return SpecialistToolLoopRoundOutcome(
        requested_observations=_requested_names(tool_requests),
        approved_observations=approved_names,
        rejected_observations=rejected_names,
        missing_observations=missing_names,
        new_observations=new_observations,
        warnings=warnings,
    )


__all__ = ["SpecialistToolLoopRoundOutcome", "run_specialist_tool_loop"]
