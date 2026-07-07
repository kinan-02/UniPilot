"""Supervisor `SubtaskHandler` for read-only specialist agents (Phase 10).

Resolves a specialist agent by capability name (via
`specialists.registry.SpecialistAgentRegistry`), builds a
`SpecialistAgentInput` from the subtask + compiled context + blackboard
dependency outputs, calls the specialist (which only ever calls the LLM
through `ReasoningBlock`), and converts its `SpecialistAgentOutput` into a
`SubtaskResult` — storing only a compact summary
(`output_summarizer.summarize_specialist_output`), never the raw compiled
context, raw prompts, or chain-of-thought.

Hard constraints (enforced by construction):
- Only ever safe to invoke for a capability that independently passes
  `specialists.safety.is_specialist_agent_safe` — checked by this handler
  itself (defense in depth, mirroring
  `workflow_adapters.ReadOnlyWorkflowAdapterHandler`'s reliance on
  `supervisor.safety.can_shadow_execute_capability`), not just by whatever
  registered it in the supervisor's handler registry.
- Always forces `SpecialistAgentInput.dry_run` from
  `AGENT_SPECIALIST_AGENTS_DRY_RUN` (default `True`) — Phase 10 never
  executes anything besides `ReasoningBlock` regardless of this setting; a
  misconfigured `false` only adds a warning (see `specialists.base`).
- Never creates an action proposal or performs a write — enforced at the
  `SpecialistAgentOutput.proposed_actions` model level (always `[]`).
- Never included in any live-turn-affecting path in Phase 10 — this handler
  is only ever reached from the shadow-only supervisor runtime.

Phase 14 addition: an optional `specialist_output_sink` dict lets a caller
(only `supervisor.post_context_runner`, only when a controlled specialist
text-promotion attempt is in play) capture the *full* in-memory
`SpecialistAgentOutput` this handler produced, keyed by agent name — never
included in the `SubtaskResult` this handler returns, never persisted, and
safe to ignore entirely (default `None`, zero behavior change) for every
other caller. Mirrors `workflow_adapters.ReadOnlyWorkflowAdapterHandler`'s
own Phase 9 `candidate_sink` pattern exactly.
"""

from __future__ import annotations

import logging
from typing import Any

from app.agent.capabilities.default_registry import build_default_capability_registry
from app.agent.capabilities.registry import CapabilityRegistry
from app.agent.context_compiler.schemas import CompiledContext
from app.agent.planner.schemas import PlannerSubtask
from app.agent.specialists.context import build_agent_context_pack_summary
from app.agent.specialists.output_summarizer import summarize_specialist_output
from app.agent.specialists.registry import SpecialistAgentRegistry, build_default_specialist_agent_registry
from app.agent.specialists.safety import is_specialist_agent_safe, specialist_agent_unsafe_warning
from app.agent.specialists.schemas import SpecialistAgentInput, SpecialistAgentOutput, SpecialistToolObservation
from app.agent.specialists.tools.observation_builder import build_specialist_observations
from app.agent.specialists.tools.schemas import SpecialistObservationBundle, SpecialistObservationRequest
from app.agent.specialists.tools.tool_loop_diagnostics import build_tool_loop_diagnostics_summary
from app.agent.supervisor.blackboard import SupervisorBlackboard
from app.agent.supervisor.schemas import SubtaskResult, SupervisorRuntimeContext
from app.config import Settings, get_settings

logger = logging.getLogger(__name__)

_SPECIALIST_STATUS_TO_SUBTASK_STATUS: dict[str, str] = {
    "completed": "completed",
    "needs_more_context": "completed",
    "unsupported": "completed",
    "failed": "failed",
    "skipped": "skipped",
}


def _observation_metadata(bundle: SpecialistObservationBundle) -> dict[str, Any]:
    """Phase 12: compact observation metadata only -- see module docstring.

    Never the raw `summary` of any observation, only counts/names/warning
    counts -- safe to fold into `SubtaskResult.output_summary` alongside
    `summarize_specialist_output`'s own compact shape.
    """
    available = [observation for observation in bundle.observations if observation.status == "available"]
    missing = [observation for observation in bundle.observations if observation.status == "missing"]
    warning_count = len(bundle.warnings) + sum(len(observation.warnings) for observation in bundle.observations)
    return {
        "observationCount": len(available),
        "observationNames": [observation.name for observation in available],
        "observationWarningCount": warning_count,
        "missingObservationCount": len(missing),
    }


class SpecialistAgentHandler:
    """Executes a read-only specialist agent for shadow diagnostics only."""

    def __init__(
        self,
        *,
        specialist_registry: SpecialistAgentRegistry | None = None,
        capability_registry: CapabilityRegistry | None = None,
        settings: Settings | None = None,
        specialist_output_sink: dict[str, SpecialistAgentOutput] | None = None,
    ) -> None:
        self._specialist_registry = specialist_registry or build_default_specialist_agent_registry()
        self._capability_registry = capability_registry or build_default_capability_registry()
        self._settings = settings
        self._specialist_output_sink = specialist_output_sink

    def _build_observation_bundle(
        self,
        *,
        cfg: Settings,
        agent_name: str,
        subtask: PlannerSubtask,
        compiled_context: dict[str, Any],
        dependency_outputs: dict[str, Any],
        user_message: str,
        runtime_context: SupervisorRuntimeContext | None,
    ) -> SpecialistObservationBundle | None:
        """Phase 12: deterministic, read-only observation gathering.

        Returns `None` unchanged (Phase 10/11 behavior) when
        `AGENT_SPECIALIST_OBSERVATIONS_ENABLED` is off, or when building
        observations unexpectedly fails -- never raises into `.run()`.
        """
        if not cfg.is_agent_specialist_observations_enabled():
            return None
        try:
            request = SpecialistObservationRequest(
                specialist_agent_name=agent_name,
                subtask_id=subtask.id,
                objective=subtask.objective,
                user_message=user_message,
                compiled_context=compiled_context,
                dependency_outputs=dependency_outputs,
                max_observations=cfg.resolved_agent_specialist_observation_max_count(),
            )
            return build_specialist_observations(
                request,
                agent_context_pack=runtime_context.agent_context_pack if runtime_context is not None else None,
            )
        except Exception:  # noqa: BLE001 — observation gathering must never break a specialist call
            logger.exception(
                "specialist_observation_bundle_failed", extra={"subtaskId": subtask.id, "agentName": agent_name}
            )
            return None

    async def run(
        self,
        *,
        subtask: PlannerSubtask,
        compiled_context: CompiledContext,
        blackboard: SupervisorBlackboard,
        dry_run: bool,
        runtime_context: SupervisorRuntimeContext | None = None,
    ) -> SubtaskResult:
        cfg = self._settings or get_settings()
        agent_name = subtask.capability_name

        capability = self._capability_registry.get(agent_name)
        if capability is None or not is_specialist_agent_safe(capability):
            warning = specialist_agent_unsafe_warning(agent_name)
            return SubtaskResult(
                subtask_id=subtask.id,
                capability_name=agent_name,
                status="skipped",
                output_summary={"agentName": agent_name, "reason": "specialist_agent_not_safe_or_unknown"},
                warnings=[warning],
                confidence=0.0,
            )

        specialist_fn = self._specialist_registry.get(agent_name)
        if specialist_fn is None:
            return SubtaskResult(
                subtask_id=subtask.id,
                capability_name=agent_name,
                status="skipped",
                output_summary={"agentName": agent_name, "reason": "specialist_agent_not_registered"},
                warnings=[f"specialist_agent_not_registered: {agent_name}"],
                confidence=0.0,
            )

        dependency_outputs = blackboard.get_dependency_outputs(subtask.depends_on)
        compiled: dict[str, Any] = dict(compiled_context.context)
        pack_summary = build_agent_context_pack_summary(
            runtime_context.agent_context_pack if runtime_context is not None else None
        )
        if pack_summary:
            compiled = {**compiled, "agent_context_pack_summary": pack_summary}

        observation_bundle = self._build_observation_bundle(
            cfg=cfg,
            agent_name=agent_name,
            subtask=subtask,
            compiled_context=compiled,
            dependency_outputs=dependency_outputs,
            user_message=blackboard.original_user_message,
            runtime_context=runtime_context,
        )
        deterministic_observations = (
            [
                SpecialistToolObservation(
                    name=observation.name,
                    status=observation.status,
                    summary=observation.summary,
                    source=observation.source,
                    warnings=observation.warnings,
                )
                for observation in observation_bundle.observations
                if observation.status != "failed"
            ]
            if observation_bundle is not None
            else []
        )

        specialist_input = SpecialistAgentInput(
            subtask_id=subtask.id,
            agent_name=agent_name,  # type: ignore[arg-type]
            objective=subtask.objective,
            user_message=blackboard.original_user_message,
            compiled_context=compiled,
            dependency_outputs=dependency_outputs,
            deterministic_observations=deterministic_observations,
            success_criteria=list(subtask.success_criteria),
            validation_requirements=list(subtask.validation_requirements),
            dry_run=cfg.is_agent_specialist_agents_dry_run(),
        )

        try:
            output = await specialist_fn(
                specialist_input,
                settings=cfg,
                agent_context_pack=runtime_context.agent_context_pack if runtime_context is not None else None,
            )
        except Exception as exc:  # noqa: BLE001 — a specialist bug must never crash the run
            logger.exception(
                "specialist_agent_handler_failed", extra={"subtaskId": subtask.id, "agentName": agent_name}
            )
            return SubtaskResult(
                subtask_id=subtask.id,
                capability_name=agent_name,
                status="failed",
                error=str(exc),
                confidence=0.0,
            )

        if self._specialist_output_sink is not None:
            # In-memory-only capture (Phase 14) -- never included in the
            # `SubtaskResult` returned below, never persisted.
            self._specialist_output_sink[agent_name] = output

        summary = summarize_specialist_output(output)
        if observation_bundle is not None:
            summary = {**summary, **_observation_metadata(observation_bundle)}
        if output.tool_loop_diagnostics is not None:
            summary = {**summary, **build_tool_loop_diagnostics_summary(output.tool_loop_diagnostics)}
        status = _SPECIALIST_STATUS_TO_SUBTASK_STATUS.get(output.status, "failed")

        return SubtaskResult(
            subtask_id=subtask.id,
            capability_name=agent_name,
            status=status,  # type: ignore[arg-type]
            output_summary=summary,
            warnings=list(output.warnings[:8]),
            confidence=output.confidence,
        )
