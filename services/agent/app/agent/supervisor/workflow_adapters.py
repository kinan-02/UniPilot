"""Real, read-only workflow adapter handler for the Supervisor Runtime (Phase 7).

Wraps a selected, provably read-only, already-live deterministic workflow
(looked up via `app.agent.workflows.registry.get_workflow` by default) as
an executable `SubtaskHandler`, for shadow/diagnostic execution only.

Hard constraints (enforced by construction):
- Only ever safe to invoke for a capability that has already passed
  `app.agent.supervisor.safety.can_shadow_execute_capability` *or* (post-
  Phase-9, only when the caller explicitly opted in — see `runtime.py`'s
  `allow_proposal_capable_execution`) `can_execute_capability_for_real_with_proposals`
  — that check happens in `runtime.py` before this handler is ever called;
  this module does not re-derive capability metadata itself.
- Never emits the workflow's internal `StreamEvent`s anywhere — they are
  collected and discarded, never forwarded to any SSE stream.
- Never persists an assistant message.
- Never creates or persists an action proposal itself (that stays entirely
  inside the wrapped workflow's own already-reviewed
  `create_agent_action_proposal` call, never this module). By default,
  treats any `proposed_actions` on the final response as a hard failure
  (defense in depth — should be unreachable given the capability safety
  gate, but a regression in a "read-only" workflow must never be silently
  trusted). `allow_single_proposed_action=True` (post-Phase-9, opt-in per
  instance) narrows that to: 0 or exactly 1 proposed action is tolerated,
  2+ is still always a hard failure.
- Requires a real `database` handle and a real `AgentContextPack` via
  `SupervisorRuntimeContext` — if either is missing, it never attempts to
  reconstruct them and reports a safe `"skipped"` result instead.

Phase 9 addition: an optional `candidate_sink` dict lets a caller (only
`supervisor.post_context_runner`, only when a controlled promotion attempt
is in play) capture the *full* in-memory `AgentResponse` this handler
produced, keyed by capability name — never included in the `SubtaskResult`/
`SupervisorRunOutput` this handler returns, never persisted, and safe to
ignore entirely (default `None`, zero behavior change) for every other
caller.
"""

from __future__ import annotations

import logging
from collections.abc import Callable
from typing import Any

from app.agent.context_compiler.schemas import CompiledContext
from app.agent.planner.schemas import PlannerSubtask
from app.agent.schemas import AgentResponse
from app.agent.supervisor.blackboard import SupervisorBlackboard
from app.agent.supervisor.output_summarizer import summarize_agent_response, unsafe_output_summary
from app.agent.supervisor.schemas import SubtaskResult, SupervisorRuntimeContext

logger = logging.getLogger(__name__)


def _default_workflow_lookup(capability_name: str) -> Any:
    # Imported lazily so importing this module never has a hard, import-time
    # dependency on the full workflow registry (and to keep the static
    # "no direct DB writes" source scan focused on this module's own body).
    from app.agent.workflows.registry import get_workflow

    return get_workflow(capability_name)


class ReadOnlyWorkflowAdapterHandler:
    """Executes a real, read-only workflow for shadow diagnostics only.

    `workflow_lookup` defaults to the real `workflows.registry.get_workflow`;
    tests inject a fake lookup so no real Mongo/audit-client dependency is
    required to exercise this handler in isolation.

    `candidate_sink`, if supplied, receives `{capability_name: AgentResponse}`
    for every capability this handler successfully executes for real (Phase
    9) — a plain in-memory dict, never read back by this class, never
    included in any returned `SubtaskResult`.

    A plan's `ExecutionGraph` only guarantees unique subtask *ids*, not
    unique `capability_name`s, so nothing upstream rules out two subtasks
    for the same capability landing in one run (possibly the same
    concurrently-dispatched wave). Since there is no well-defined single
    "the" candidate for a promotion/compare decision when that happens,
    this handler treats it as a poison condition: the first subtask for a
    given capability name populates `candidate_sink`; any subsequent
    subtask for that same name removes the entry instead of overwriting it
    and permanently blocks that capability name from being populated again
    this run. This is deterministic (independent of asyncio scheduling
    order) and fails closed — an ambiguous candidate is discarded rather
    than nondeterministically kept.
    """

    def __init__(
        self,
        *,
        workflow_lookup: Callable[[str], Any] | None = None,
        candidate_sink: dict[str, AgentResponse] | None = None,
        allow_single_proposed_action: bool = False,
    ) -> None:
        self._workflow_lookup = workflow_lookup or _default_workflow_lookup
        self._candidate_sink = candidate_sink
        self._poisoned_capability_names: set[str] = set()
        self._allow_single_proposed_action = allow_single_proposed_action

    async def run(
        self,
        *,
        subtask: PlannerSubtask,
        compiled_context: CompiledContext,
        blackboard: SupervisorBlackboard,
        dry_run: bool,
        runtime_context: SupervisorRuntimeContext | None = None,
    ) -> SubtaskResult:
        if (
            runtime_context is None
            or runtime_context.database is None
            or runtime_context.agent_context_pack is None
        ):
            return SubtaskResult(
                subtask_id=subtask.id,
                capability_name=subtask.capability_name,
                status="skipped",
                output_summary={
                    "shadowExecuted": False,
                    "reason": "missing_runtime_context_for_real_execution",
                },
                warnings=["real_shadow_execution_requires_runtime_context"],
            )

        workflow = self._workflow_lookup(subtask.capability_name)
        if workflow is None:
            return SubtaskResult(
                subtask_id=subtask.id,
                capability_name=subtask.capability_name,
                status="skipped",
                output_summary=unsafe_output_summary(
                    workflow_name=subtask.capability_name, reason="workflow_not_found"
                ),
                warnings=[f"workflow_adapter_no_workflow_for: {subtask.capability_name}"],
            )

        final_response: AgentResponse | None = None
        try:
            async for item in workflow.run(
                runtime_context.database,
                context=runtime_context.agent_context_pack,
                user_message=runtime_context.user_message,
            ):
                if isinstance(item, AgentResponse):
                    final_response = item
                # Every non-`AgentResponse` item is an internal `StreamEvent`
                # (agent.step.*, tool.*, structured_output, action.proposed)
                # -- deliberately collected and discarded here. Shadow
                # execution never emits anything to a real SSE stream.
        except Exception as exc:  # noqa: BLE001 -- a real workflow bug must never crash the run
            logger.exception("workflow_adapter_execution_failed", extra={"subtaskId": subtask.id})
            return SubtaskResult(
                subtask_id=subtask.id,
                capability_name=subtask.capability_name,
                status="failed",
                error=str(exc),
                confidence=0.0,
            )

        if final_response is None:
            return SubtaskResult(
                subtask_id=subtask.id,
                capability_name=subtask.capability_name,
                status="skipped",
                output_summary=unsafe_output_summary(
                    workflow_name=subtask.capability_name, reason="workflow_produced_no_response"
                ),
                warnings=["workflow_adapter_no_final_response"],
            )

        if final_response.proposed_actions:
            too_many = len(final_response.proposed_actions) > 1
            if not self._allow_single_proposed_action or too_many:
                # Defense in depth: by default only capabilities with
                # `can_create_action_proposals=False` are ever routed here
                # by `runtime.py` -- a real workflow returning proposed
                # actions anyway must never be trusted or surfaced. Even
                # when this instance was explicitly configured to tolerate
                # a single proposed action (post-Phase-9, proposal-capable
                # live execution), 2+ is still an anomaly this workflow has
                # never been reviewed to produce -- still a hard failure.
                logger.warning(
                    "workflow_adapter_unexpected_proposed_actions",
                    extra={"subtaskId": subtask.id, "tooMany": too_many},
                )
                reason = (
                    "unexpected_multiple_proposed_actions"
                    if too_many
                    else "unexpected_proposed_actions_from_supposedly_read_only_workflow"
                )
                return SubtaskResult(
                    subtask_id=subtask.id,
                    capability_name=subtask.capability_name,
                    status="failed",
                    output_summary=unsafe_output_summary(
                        workflow_name=subtask.capability_name,
                        reason=reason,
                    ),
                    warnings=[
                        f"unsafe_workflow_output_discarded: {subtask.capability_name} returned "
                        "proposed_actions not tolerated for this execution"
                    ],
                    confidence=0.0,
                )

        if self._candidate_sink is not None:
            # Only ever reached for a `final_response` that already passed
            # the proposed-actions defense-in-depth check above -- an
            # in-memory-only capture, never serialized into anything
            # returned from this method.
            name = subtask.capability_name
            if name in self._poisoned_capability_names:
                pass
            elif name in self._candidate_sink:
                # Second subtask for the same capability name this run --
                # no well-defined single candidate. Discard both rather
                # than nondeterministically keeping whichever finished
                # first/last under concurrent dispatch.
                del self._candidate_sink[name]
                self._poisoned_capability_names.add(name)
                logger.warning(
                    "workflow_adapter_candidate_sink_collision_discarded", extra={"capabilityName": name}
                )
            else:
                self._candidate_sink[name] = final_response

        summary = summarize_agent_response(
            final_response, workflow_name=subtask.capability_name, shadow_executed=True
        )
        return SubtaskResult(
            subtask_id=subtask.id,
            capability_name=subtask.capability_name,
            status="completed",
            output_summary=summary,
            warnings=list(final_response.warnings[:8]),
            confidence=summary["confidence"],
        )
