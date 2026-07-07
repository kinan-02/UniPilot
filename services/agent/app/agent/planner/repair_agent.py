"""Optional warm planner repair via ReasoningBlock (Phase 19)."""

from __future__ import annotations

import logging
import uuid
from typing import Any

from pydantic import ValidationError

from app.agent.planner.repair_fallback import deterministic_plan_repair
from app.agent.planner.repair_policy import choose_repair_mode
from app.agent.planner.repair_schemas import PlanRepairOutput, PlanRepairRequest, PlanRepairStatus
from app.agent.reasoning.llm_adapter import ChatLLMAdapter
from app.agent.reasoning.prompt_registry import PLANNER_REPAIR_V1
from app.agent.reasoning.reasoning_block import ReasoningBlock
from app.agent.reasoning.schemas import ReasoningBlockInput, ReasoningBlockOutput
from app.agent.reasoning.task_schemas import PLANNER_REPAIR_OUTPUT_SCHEMA
from app.config import Settings, get_settings

logger = logging.getLogger(__name__)


def _compact_prior_plan(request: PlanRepairRequest) -> dict[str, Any]:
    if request.prior_plan is None:
        return {}
    return {
        "planId": request.prior_plan.plan_id,
        "userGoal": request.prior_plan.user_goal,
        "subtasks": request.prior_plan.subtasks,
        "assumptions": request.prior_plan.assumptions,
        "successCriteria": request.prior_plan.success_criteria,
    }


def _compact_deltas(request: PlanRepairRequest) -> list[dict[str, Any]]:
    return [
        {
            "deltaId": delta.delta_id,
            "source": delta.source,
            "kind": delta.kind,
            "summary": delta.summary,
            "affectedSubtaskIds": delta.affected_subtask_ids,
            "affectedAssumptionIds": delta.affected_assumption_ids,
            "consequence": delta.consequence,
        }
        for delta in request.deltas
    ]


def _normalize_llm_repair_result(result: dict[str, Any], *, request: PlanRepairRequest) -> PlanRepairOutput | None:
    try:
        status = str(result.get("status") or "")
        mode_used = str(result.get("mode_used") or result.get("modeUsed") or choose_repair_mode(request))
        if mode_used not in {"repair", "regenerate", "continue", "clarify_first", "abort_safely"}:
            return None
        if status not in {
            "repaired",
            "regenerated",
            "continued",
            "clarification_needed",
            "aborted_safely",
            "failed",
            "skipped",
        }:
            return None

        repaired_plan = result.get("repaired_plan") or result.get("repairedPlan")
        if isinstance(repaired_plan, dict) and "proposed_actions" in repaired_plan:
            return None

        fallback_plan_id = request.prior_plan.plan_id if request.prior_plan else ""
        return PlanRepairOutput(
            status=status,  # type: ignore[arg-type]
            mode_used=mode_used,  # type: ignore[arg-type]
            plan_id=str(result.get("plan_id") or result.get("planId") or fallback_plan_id),
            repaired_plan=repaired_plan if isinstance(repaired_plan, dict) else None,
            preserved_subtask_ids=list(result.get("preserved_subtask_ids") or result.get("preservedSubtaskIds") or []),
            revised_subtask_ids=list(result.get("revised_subtask_ids") or result.get("revisedSubtaskIds") or []),
            removed_subtask_ids=list(result.get("removed_subtask_ids") or result.get("removedSubtaskIds") or []),
            added_subtask_ids=list(result.get("added_subtask_ids") or result.get("addedSubtaskIds") or []),
            decision_summary=str(result.get("decision_summary") or result.get("decisionSummary") or "")[:500],
            reason_codes=list(result.get("reason_codes") or result.get("reasonCodes") or []),
            warnings=list(result.get("warnings") or [])[:8],
            confidence=float(result.get("confidence") or 0.0),
            safe_to_use=False,
        )
    except (ValidationError, TypeError, ValueError):
        return None


async def run_plan_repair_with_llm(
    request: PlanRepairRequest,
    *,
    settings: Settings | None = None,
    reasoning_block: ReasoningBlock | None = None,
) -> PlanRepairOutput:
    """Run warm planner repair through ReasoningBlock when LLM flag is enabled."""
    cfg = settings or get_settings()
    if not cfg.is_agent_plan_repair_use_llm():
        return PlanRepairOutput(
            status="skipped",
            mode_used=choose_repair_mode(request),
            plan_id=request.prior_plan.plan_id if request.prior_plan else None,
            decision_summary="LLM plan repair disabled — skipped.",
            reason_codes=["llm_repair_disabled"],
            safe_to_use=False,
        )

    block = reasoning_block or ReasoningBlock(llm_adapter=ChatLLMAdapter(settings=cfg), settings=cfg)
    reasoning_input = ReasoningBlockInput(
        block_id=f"planner_repair-{uuid.uuid4().hex[:10]}",
        agent_name="planner_repair",
        objective="Repair or regenerate the prior plan based on execution deltas.",
        task_context={
            "prior_plan_snapshot": _compact_prior_plan(request),
            "execution_deltas": _compact_deltas(request),
            "monitor_decision": request.monitor_decision,
            "confirmed_clarifications": request.confirmed_clarifications,
            "requested_mode_hint": choose_repair_mode(request),
            "dry_run": request.dry_run,
            "user_message": request.current_user_message or request.user_goal,
        },
        constraints=[
            "Preserve still-valid subtasks when repair is sufficient.",
            "Regenerate only when the user goal changed or the old plan is invalid.",
            "Do not invent academic facts, transcript data, or completed courses.",
            "Do not create action proposals or claim writes happened.",
        ],
        success_criteria=[
            "Output matches planner_repair_output_v1 schema.",
            "safe_to_use remains false for Phase 19 diagnostics.",
        ],
        output_schema_name="planner_repair_output_v1",
        output_schema=PLANNER_REPAIR_OUTPUT_SCHEMA,
        prompt_contract_name=PLANNER_REPAIR_V1,
        risk_level="high",
    )

    try:
        output: ReasoningBlockOutput = await block.run(reasoning_input)
    except Exception:  # noqa: BLE001
        logger.exception("planner_repair_llm_failed", extra={"requestId": request.request_id})
        fallback = deterministic_plan_repair(request)
        fallback.warnings = [*fallback.warnings, "llm_repair_failed_fallback"]
        return fallback

    if output.status != "completed" or not output.schema_valid or not isinstance(output.result, dict):
        fallback = deterministic_plan_repair(request)
        fallback.warnings = [*fallback.warnings, "llm_repair_invalid_fallback"]
        return fallback

    normalized = _normalize_llm_repair_result(output.result, request=request)
    if normalized is None:
        fallback = deterministic_plan_repair(request)
        fallback.warnings = [*fallback.warnings, "llm_repair_schema_fallback"]
        return fallback

    normalized.safe_to_use = False
    return normalized


async def run_plan_repair(
    request: PlanRepairRequest,
    *,
    settings: Settings | None = None,
    reasoning_block: ReasoningBlock | None = None,
) -> PlanRepairOutput:
    """Run plan repair — LLM path when enabled, otherwise deterministic fallback."""
    cfg = settings or get_settings()
    if cfg.is_agent_plan_repair_use_llm():
        return await run_plan_repair_with_llm(request, settings=cfg, reasoning_block=reasoning_block)
    return deterministic_plan_repair(request)


def build_plan_repair_request(
    *,
    prior_plan_snapshot: Any,
    user_goal: str,
    deltas: list[Any],
    monitor_decision: dict[str, Any] | None = None,
    confirmed_clarifications: list[dict[str, Any]] | None = None,
    original_user_message: str | None = None,
    current_user_message: str | None = None,
    dry_run: bool = True,
) -> PlanRepairRequest:
    from app.agent.planner.repair_schemas import PlanExecutionDelta, PlanSnapshot

    prior: PlanSnapshot | None
    if isinstance(prior_plan_snapshot, PlanSnapshot):
        prior = prior_plan_snapshot
    elif isinstance(prior_plan_snapshot, dict):
        prior = PlanSnapshot.model_validate(prior_plan_snapshot)
    else:
        prior = None

    parsed_deltas: list[PlanExecutionDelta] = []
    for delta in deltas:
        if isinstance(delta, PlanExecutionDelta):
            parsed_deltas.append(delta)
        elif isinstance(delta, dict):
            try:
                parsed_deltas.append(PlanExecutionDelta.model_validate(delta))
            except ValidationError:
                continue

    return PlanRepairRequest(
        request_id=f"repair-{uuid.uuid4().hex[:12]}",
        prior_plan=prior,
        user_goal=user_goal,
        original_user_message=original_user_message,
        current_user_message=current_user_message,
        deltas=parsed_deltas,
        monitor_decision=dict(monitor_decision or {}),
        confirmed_clarifications=list(confirmed_clarifications or []),
        dry_run=dry_run,
    )
