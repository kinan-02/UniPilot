"""Supervisor handler for shadow-only dynamic agents (Phase 15).

When a planner subtask carries a `dynamic_agent_spec`, this handler validates
the spec, builds a `DynamicAgentInstance`, runs it in shadow/dry-run mode,
and stores only a compact summary in `SubtaskResult.output_summary`.
"""

from __future__ import annotations

import logging
from typing import Any

from app.agent.context_compiler.schemas import CompiledContext
from app.agent.dynamic_agents.builder import AgentBuilder
from app.agent.dynamic_agents.output_summarizer import summarize_dynamic_agent_output
from app.agent.dynamic_agents.schemas import AgentSpec, DynamicAgentRunInput, TaskBrief
from app.agent.dynamic_agents.spec_validation import AgentSpecValidationError
from app.agent.planner.schemas import PlannerSubtask
from app.agent.supervisor.blackboard import SupervisorBlackboard
from app.agent.supervisor.schemas import SubtaskResult, SupervisorRuntimeContext
from app.config import Settings, get_settings

logger = logging.getLogger(__name__)

_DYNAMIC_STATUS_TO_SUBTASK_STATUS: dict[str, str] = {
    "completed": "completed",
    "needs_more_context": "completed",
    "unsupported": "completed",
    "failed": "failed",
    "skipped": "skipped",
}


def _task_brief_from_subtask(
    *,
    subtask: PlannerSubtask,
    blackboard: SupervisorBlackboard,
    dependency_outputs: dict[str, Any],
    spec: AgentSpec,
) -> TaskBrief:
    return TaskBrief(
        brief_id=subtask.id,
        parent_plan_id=None,
        parent_subtask_id=subtask.id,
        objective=subtask.objective or spec.objective,
        user_goal=blackboard.original_user_message,
        boundaries=list(spec.boundaries),
        success_criteria=list(subtask.success_criteria or spec.success_criteria),
        relevant_context_summary={},
        dependency_outputs=dependency_outputs,
        expected_output_schema_name=spec.expected_output_schema_name,
    )


class DynamicAgentHandler:
    """Executes a configured dynamic agent for shadow diagnostics only."""

    def __init__(
        self,
        *,
        builder: AgentBuilder | None = None,
        settings: Settings | None = None,
    ) -> None:
        self._builder = builder or AgentBuilder()
        self._settings = settings

    async def run(
        self,
        *,
        subtask: PlannerSubtask,
        compiled_context: CompiledContext,
        blackboard: SupervisorBlackboard,
        dry_run: bool,
        runtime_context: SupervisorRuntimeContext | None = None,
    ) -> SubtaskResult:
        del runtime_context
        cfg = self._settings or get_settings()

        if not cfg.is_agent_dynamic_agents_enabled():
            return SubtaskResult(
                subtask_id=subtask.id,
                capability_name=subtask.capability_name,
                status="skipped",
                output_summary={"reason": "dynamic_agents_disabled"},
                warnings=["dynamic_agents_disabled"],
                confidence=0.0,
            )

        raw_spec = subtask.dynamic_agent_spec
        if raw_spec is None and subtask.capability_name != "dynamic_agent":
            return SubtaskResult(
                subtask_id=subtask.id,
                capability_name=subtask.capability_name,
                status="skipped",
                output_summary={"reason": "no_dynamic_agent_spec"},
                confidence=0.0,
            )

        if raw_spec is None:
            return SubtaskResult(
                subtask_id=subtask.id,
                capability_name=subtask.capability_name,
                status="skipped",
                output_summary={"reason": "dynamic_agent_spec_missing"},
                warnings=["dynamic_agent_spec_missing"],
                confidence=0.0,
            )

        try:
            spec = AgentSpec.model_validate(raw_spec)
            instance = self._builder.build(spec)
        except (AgentSpecValidationError, Exception) as exc:  # noqa: BLE001
            logger.exception("dynamic_agent_build_failed", extra={"subtaskId": subtask.id})
            return SubtaskResult(
                subtask_id=subtask.id,
                capability_name=subtask.capability_name,
                status="failed",
                error=str(exc),
                warnings=["dynamic_agent_build_failed"],
                confidence=0.0,
            )

        dependency_outputs = blackboard.get_dependency_outputs(subtask.depends_on)
        task_brief = _task_brief_from_subtask(
            subtask=subtask,
            blackboard=blackboard,
            dependency_outputs=dependency_outputs,
            spec=spec,
        )
        run_input = DynamicAgentRunInput(
            spec=spec,
            task_brief=task_brief,
            compiled_context=dict(compiled_context.context),
            dependency_outputs=dependency_outputs,
            dry_run=cfg.is_agent_dynamic_agents_dry_run(),
        )

        try:
            output = await instance.run(run_input, settings=cfg)
        except Exception as exc:  # noqa: BLE001
            logger.exception("dynamic_agent_handler_failed", extra={"subtaskId": subtask.id})
            return SubtaskResult(
                subtask_id=subtask.id,
                capability_name=subtask.capability_name,
                status="failed",
                error=str(exc),
                confidence=0.0,
            )

        summary = summarize_dynamic_agent_output(output, spec=spec, block_count=instance.block_count)
        status = _DYNAMIC_STATUS_TO_SUBTASK_STATUS.get(output.status, "failed")

        return SubtaskResult(
            subtask_id=subtask.id,
            capability_name=subtask.capability_name,
            status=status,  # type: ignore[arg-type]
            output_summary=summary,
            warnings=list(output.warnings[:8]),
            confidence=output.confidence,
        )
