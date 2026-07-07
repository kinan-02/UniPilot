"""Optional diagnostic integration: Supervisor Orchestrator Runtime (Phase 6/7).

Diagnostic only, mirroring `app.agent.task_understanding.integration`,
`app.agent.capabilities.diagnostics`, and `app.agent.planner.diagnostics`.
Runs the (already shadow-only) Supervisor Runtime against a Phase 5
`PlannerOutput` and produces a small, compact summary meant to be attached
to `agent_runs.retrievalMetadata.supervisorDiagnostics`.

Hard constraints:
- Never selects a workflow or performs a write/creates an action proposal.
- Never changes the final response or emits new SSE events.
- Never raises into a live turn — any failure degrades to `None`.
- No raw compiled context, raw workflow response, raw LLM prompts, or
  chain-of-thought is ever included in the returned summary.
"""

from __future__ import annotations

import logging
from typing import Any

from app.agent.supervisor.runtime import run_supervisor_shadow
from app.agent.supervisor.schemas import (
    ExecutionBudget,
    SupervisorRunInput,
    SupervisorRunOutput,
    SupervisorRuntimeContext,
)
from app.config import Settings, get_settings

logger = logging.getLogger(__name__)

_MAX_WARNINGS_LOGGED = 8
_MAX_ERRORS_LOGGED = 8
_MAX_SUBTASK_IDS_LOGGED = 20


def _diagnostic_summary(run_output: SupervisorRunOutput, *, budget: ExecutionBudget) -> dict[str, Any]:
    capabilities = sorted(
        {record.capability_name for record in run_output.subtask_records}
    )
    return {
        "status": run_output.status,
        "planId": run_output.plan_id,
        "executionMode": run_output.execution_mode,
        "subtaskCount": len(run_output.subtask_records),
        "completedSubtasks": run_output.completed_subtasks[:_MAX_SUBTASK_IDS_LOGGED],
        "failedSubtasks": run_output.failed_subtasks[:_MAX_SUBTASK_IDS_LOGGED],
        "skippedSubtasks": run_output.skipped_subtasks[:_MAX_SUBTASK_IDS_LOGGED],
        "capabilities": capabilities,
        "warnings": run_output.warnings[:_MAX_WARNINGS_LOGGED],
        "errors": run_output.errors[:_MAX_ERRORS_LOGGED],
        "budget": {
            "maxSubtasks": budget.max_subtasks,
            "maxRetriesPerSubtask": budget.max_retries_per_subtask,
        },
        "contextPreviewCount": run_output.diagnostics.get("budget", {}).get("contextPreviewsCompiled", 0),
    }


async def run_supervisor_dry_run(
    *,
    user_message: str,
    planner_diagnostics: dict[str, Any] | None,
    planner_output: dict[str, Any] | None,
    task_understanding_summary: dict[str, Any] | None = None,
    deterministic_intent: str | None = None,
    deterministic_entities: dict[str, Any] | None = None,
    conversation_entities: dict[str, Any] | None = None,
    conversation_assumptions: list[str] | None = None,
    profile_summary: dict[str, Any] | None = None,
    runtime_context: SupervisorRuntimeContext | None = None,
    settings: Settings | None = None,
) -> dict[str, Any] | None:
    """Run the Supervisor Runtime for diagnostics only.

    Returns a compact summary dict (safe to log or store in
    `agent_runs.retrievalMetadata`), or `None` when the feature flag is off,
    planner diagnostics were unavailable (nothing to run the graph on), or
    the diagnostic run itself fails.

    `runtime_context` is `None` by default — the live orchestrator's own
    call site does not currently supply one (see
    `docs/agent/CURRENT_STATE.md` Phase 7 section for why), so real Phase 7
    handlers never execute automatically from a live turn yet; passing one
    explicitly (as tests do) lets real read-only workflow adapters run.

    Never raises: `run_supervisor_shadow` already fails safely on its own
    (invalid plan / dependency cycle all resolve to a `status="failed"`
    output), but this diagnostic call site adds one more guard on top — a
    bug here must never break a live agent turn.
    """
    cfg = settings or get_settings()
    if not cfg.is_agent_supervisor_enabled():
        return None
    if planner_diagnostics is None or planner_output is None:
        # Mirrors the spec: only run supervisor shadow once planner
        # diagnostics exist — there is no subtask graph to run otherwise.
        return None

    try:
        budget = ExecutionBudget()
        run_input = SupervisorRunInput(
            user_id=None,
            conversation_id=None,
            user_message=user_message,
            planner_output=planner_output,
            task_understanding=task_understanding_summary,
            deterministic_intent=deterministic_intent,
            deterministic_entities=dict(deterministic_entities or {}),
            conversation_entities=dict(conversation_entities or {}),
            conversation_assumptions=list(conversation_assumptions or []),
            profile_summary=dict(profile_summary or {}),
            # Phase 6 never executes anything besides safe dry-run handlers
            # regardless of this setting -- passing it through (rather than
            # hardcoding `True`) lets `run_supervisor_shadow` itself surface
            # a loud warning if an operator sets `AGENT_SUPERVISOR_DRY_RUN=false`
            # by mistake, instead of the misconfiguration being silently lost.
            dry_run=cfg.is_agent_supervisor_dry_run(),
            budget=budget,
        )
        run_output = await run_supervisor_shadow(
            input=run_input, runtime_context=runtime_context, settings=cfg
        )
        summary = _diagnostic_summary(run_output, budget=budget)
    except Exception:  # noqa: BLE001 — diagnostic-only path, must never break a live turn
        logger.exception("supervisor_dry_run_failed")
        return None

    logger.info("supervisor_dry_run_result", extra={"supervisorDiagnostics": summary})
    return summary
