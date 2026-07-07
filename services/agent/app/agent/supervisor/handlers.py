"""Phase 6 built-in subtask handlers — safe dry-run/diagnostic handlers only.

None of these execute a real workflow, call a real internal API, write to
Mongo, or create an action proposal — this module only validates that a
capability and its compiled context are usable, and reports a compact,
honest "not executed yet" summary. Real workflow adapter handlers are
`app.agent.supervisor.workflow_adapters.ReadOnlyWorkflowAdapterHandler`
(Phase 7), registered only for capabilities that pass
`app.agent.supervisor.safety.can_shadow_execute_capability`.

Every handler accepts an optional `runtime_context` kwarg (Phase 7) so all
handlers share one `SubtaskHandler` call signature — the three handlers
here simply ignore it, since none of them ever needs a real database
handle or `AgentContextPack`.
"""

from __future__ import annotations

from typing import Protocol, runtime_checkable

from app.agent.context_compiler.schemas import CompiledContext
from app.agent.planner.schemas import PlannerSubtask
from app.agent.supervisor.blackboard import SupervisorBlackboard
from app.agent.supervisor.schemas import SubtaskResult, SupervisorRuntimeContext

_DEFERRED_EXECUTION_MESSAGE = (
    "Capability validated and context preview compiled. "
    "Real execution is deferred to Phase 7."
)


@runtime_checkable
class SubtaskHandler(Protocol):
    """Contract every Phase 6/7 subtask handler must implement."""

    async def run(
        self,
        *,
        subtask: PlannerSubtask,
        compiled_context: CompiledContext,
        blackboard: SupervisorBlackboard,
        dry_run: bool,
        runtime_context: SupervisorRuntimeContext | None = None,
    ) -> SubtaskResult:
        ...


class DryRunCapabilityHandler:
    """Default Phase 6 handler for any resolvable, enabled capability.

    Confirms the capability exists/is enabled and that context compilation
    succeeded, then returns a compact "completed (dry-run)" result — it
    never calls a real workflow, internal API, or Mongo write.
    """

    async def run(
        self,
        *,
        subtask: PlannerSubtask,
        compiled_context: CompiledContext,
        blackboard: SupervisorBlackboard,
        dry_run: bool,
        runtime_context: SupervisorRuntimeContext | None = None,
    ) -> SubtaskResult:
        return SubtaskResult(
            subtask_id=subtask.id,
            capability_name=subtask.capability_name,
            status="completed",
            output_summary={
                "dryRun": True,
                "message": _DEFERRED_EXECUTION_MESSAGE,
                "includedContextSections": compiled_context.included_sections,
            },
            warnings=list(compiled_context.warnings),
            confidence=0.8 if compiled_context.warnings else 1.0,
        )


class ContextPreviewHandler:
    """Handler for context/retrieval-flavored capabilities (`retrieval`, `validator`, `composer`).

    Reports the compiled context preview only — no capability-specific
    "work" is even simulated, since these capability types are inputs to
    other subtasks rather than end results themselves.
    """

    async def run(
        self,
        *,
        subtask: PlannerSubtask,
        compiled_context: CompiledContext,
        blackboard: SupervisorBlackboard,
        dry_run: bool,
        runtime_context: SupervisorRuntimeContext | None = None,
    ) -> SubtaskResult:
        return SubtaskResult(
            subtask_id=subtask.id,
            capability_name=subtask.capability_name,
            status="completed",
            output_summary={
                "dryRun": True,
                "includedSections": compiled_context.included_sections,
                "omittedSections": compiled_context.omitted_sections,
                "estimatedItems": compiled_context.estimated_items,
            },
            warnings=list(compiled_context.warnings),
        )


class UnsupportedCapabilityHandler:
    """Used when a subtask's capability is unknown or disabled in the registry.

    Never raises — always resolves to a safe `"skipped"` result so the
    runtime can move on to (or skip) dependents deterministically.
    """

    async def run(
        self,
        *,
        subtask: PlannerSubtask,
        compiled_context: CompiledContext | None = None,
        blackboard: SupervisorBlackboard,
        dry_run: bool,
        runtime_context: SupervisorRuntimeContext | None = None,
    ) -> SubtaskResult:
        return SubtaskResult(
            subtask_id=subtask.id,
            capability_name=subtask.capability_name,
            status="skipped",
            output_summary={"dryRun": True, "reason": "unsupported_or_unknown_capability"},
            warnings=[f"unsupported_capability: {subtask.capability_name}"],
            confidence=0.0,
        )
