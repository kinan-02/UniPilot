"""Planner Agent (Phase 5).

Converts a validated `TaskUnderstandingOutput` into a structured,
capability-aware execution plan via the shared `ReasoningBlock` runtime.

Hard constraints (enforced by construction, not just by convention):
- Only calls the LLM through `ReasoningBlock` — never directly.
- Never executes a subtask, tool, or workflow.
- Never creates a write/action proposal.
- Never answers the user directly.
- Only ever returns subtasks referencing capabilities present and enabled in
  the `CapabilityRegistry` (enforced by `planner.normalizer`).

Diagnostic only in Phase 5: nothing in the live orchestrator executes this
plan, uses it to select a workflow, or changes the final response.
"""

from __future__ import annotations

import logging
import uuid
from typing import Any

from pydantic import ValidationError

from app.agent.capabilities.default_registry import build_default_capability_registry
from app.agent.capabilities.registry import CapabilityRegistry
from app.agent.planner.dynamic_spec_policy import normalize_planner_dynamic_specs
from app.agent.planner.legacy_mapping import legacy_workflow_to_capability_name
from app.agent.planner.normalizer import normalize_planner_output
from app.agent.planner.schemas import PlannerInput, PlannerOutput, PlannerSubtask
from app.agent.reasoning.llm_adapter import ChatLLMAdapter
from app.agent.reasoning.prompt_registry import PLANNER_AGENT_V1
from app.agent.reasoning.reasoning_block import ReasoningBlock
from app.agent.reasoning.schemas import ReasoningBlockInput
from app.agent.reasoning.task_schemas import PLANNER_OUTPUT_SCHEMA
from app.agent.task_understanding.schemas import TaskUnderstandingOutput
from app.config import Settings, get_settings

logger = logging.getLogger(__name__)

_LEGACY_PLAN_ID = "legacy_workflow_plan"
_LEGACY_SUBTASK_ID = "run_legacy_workflow"
_LEGACY_CONTEXT_SECTION = "agent_context_pack_summary"


def _clamp01(value: Any) -> float:
    try:
        number = float(value)
    except (TypeError, ValueError):
        return 0.5
    return max(0.0, min(1.0, number))


def _task_understanding_dict(task_understanding: TaskUnderstandingOutput | dict[str, Any] | None) -> dict[str, Any]:
    if task_understanding is None:
        return {}
    if isinstance(task_understanding, dict):
        return task_understanding
    if hasattr(task_understanding, "model_dump"):
        return task_understanding.model_dump()
    return {}


def _summarize_capabilities(registry: CapabilityRegistry) -> list[dict[str, Any]]:
    """Compact, prompt-sized summary of every *enabled* capability.

    Disabled placeholder capabilities (most Phase 4 future specialist
    agents) are intentionally excluded — the LLM should never be told about
    a capability it isn't allowed to use yet. `planner.normalizer` still
    defends against a hallucinated or disabled capability name regardless.
    """
    return [
        {
            "name": capability.name,
            "type": capability.type,
            "description": capability.description,
            "supported_intents": capability.supported_intents,
            "write_scope": capability.permissions.write_scope,
            "risk_level": capability.risk_level,
        }
        for capability in registry.find_enabled()
    ]


def _deterministic_fallback_plan(
    *,
    user_message: str,
    task_understanding: dict[str, Any],
    deterministic_intent: str | None,
    legacy_workflow_plan: dict[str, Any] | None,
    warning: str,
) -> PlannerOutput:
    """Map the current deterministic `task_planner.py` selection into a single-workflow plan.

    Used whenever the LLM planner is disabled, unavailable, or its output
    could not be normalized into a usable plan.
    """
    plan = legacy_workflow_plan or {}
    workflow_name = str(plan.get("workflow") or "general_academic_workflow")
    capability_name = str(plan.get("capability_name") or legacy_workflow_to_capability_name(workflow_name))
    primary_intent = (
        deterministic_intent
        or task_understanding.get("primaryIntent")
        or task_understanding.get("primary_intent")
        or plan.get("primary_intent")
        or "unknown_or_unsupported"
    )
    requires_confirmation = bool(plan.get("requires_confirmation", False))

    return PlannerOutput(
        status="completed",
        plan_id=_LEGACY_PLAN_ID,
        user_goal=user_message,
        execution_mode="deterministic_workflow",
        recommended_autonomy_level=2,
        primary_intent=str(primary_intent),
        subtasks=[
            PlannerSubtask(
                id=_LEGACY_SUBTASK_ID,
                title="Run existing deterministic workflow",
                kind="analyze",
                capability_name=capability_name,
                objective="Run the existing workflow selected by task_planner.py.",
                depends_on=[],
                required_context_sections=[_LEGACY_CONTEXT_SECTION],
                success_criteria=["Use existing deterministic workflow behavior unchanged."],
                validation_requirements=["Preserve deterministic workflow output."],
                requires_user_confirmation=requires_confirmation,
                risk_level="medium",
            )
        ],
        required_context=[_LEGACY_CONTEXT_SECTION],
        missing_context=[],
        assumptions=[],
        requires_user_confirmation=requires_confirmation,
        write_risk="possible" if requires_confirmation else "none",
        clarification_questions=[],
        validation_strategy=["Preserve deterministic workflow output."],
        fallback_workflow_name=workflow_name,
        decision_summary="Used deterministic fallback planner based on existing task_planner.py output.",
        warnings=[warning],
        confidence=0.6,
        source="deterministic_fallback",
    )


def _str_list(result: dict[str, Any], key: str) -> list[str]:
    values = result.get(key)
    if not isinstance(values, list):
        return []
    return [str(value) for value in values if str(value).strip()]


def _subtask_from_result(item: dict[str, Any]) -> PlannerSubtask | None:
    try:
        raw_spec = item.get("dynamic_agent_spec")
        dynamic_agent_spec = raw_spec if isinstance(raw_spec, dict) else None
        return PlannerSubtask(
            id=str(item.get("id") or ""),
            title=str(item.get("title") or ""),
            kind=item.get("kind", "analyze"),
            capability_name=str(item.get("capability_name") or ""),
            objective=str(item.get("objective") or ""),
            depends_on=_str_list(item, "depends_on"),
            required_context_sections=_str_list(item, "required_context_sections"),
            expected_output_schema_name=item.get("expected_output_schema_name"),
            success_criteria=_str_list(item, "success_criteria"),
            validation_requirements=_str_list(item, "validation_requirements"),
            can_run_in_parallel_group=item.get("can_run_in_parallel_group"),
            requires_user_confirmation=bool(item.get("requires_user_confirmation", False)),
            risk_level=item.get("risk_level", "medium"),
            dynamic_agent_spec=dynamic_agent_spec,
            dynamic_agent_spec_status="generated" if dynamic_agent_spec else None,
        )
    except ValidationError:
        return None


def _candidate_from_result(result: dict[str, Any]) -> PlannerOutput:
    """Lenient construction from a `result` dict that already passed JSON-schema validation."""
    subtasks: list[PlannerSubtask] = []
    for item in result.get("subtasks") or []:
        if not isinstance(item, dict):
            continue
        subtask = _subtask_from_result(item)
        if subtask is not None and subtask.id and subtask.capability_name:
            subtasks.append(subtask)

    return PlannerOutput(
        status=result.get("status", "completed"),
        plan_id=str(result.get("plan_id") or f"plan-{uuid.uuid4().hex[:10]}"),
        user_goal=str(result.get("user_goal") or ""),
        execution_mode=result.get("execution_mode", "unsupported"),
        recommended_autonomy_level=result.get("recommended_autonomy_level", 2),
        primary_intent=str(result.get("primary_intent") or "unknown_or_unsupported"),
        subtasks=subtasks,
        required_context=_str_list(result, "required_context"),
        missing_context=_str_list(result, "missing_context"),
        assumptions=_str_list(result, "assumptions"),
        requires_user_confirmation=bool(result.get("requires_user_confirmation", False)),
        write_risk=result.get("write_risk", "none"),
        clarification_questions=_str_list(result, "clarification_questions"),
        validation_strategy=_str_list(result, "validation_strategy"),
        fallback_workflow_name=result.get("fallback_workflow_name"),
        decision_summary=str(result.get("decision_summary") or ""),
        warnings=_str_list(result, "warnings"),
        confidence=_clamp01(result.get("confidence", 0.5)),
        source="llm_reasoning_block",
    )


def _build_task_context(planner_input: PlannerInput) -> dict[str, Any]:
    return {
        "user_message": planner_input.user_message,
        "task_understanding": planner_input.task_understanding,
        "deterministic_intent": planner_input.deterministic_intent,
        "deterministic_entities": planner_input.deterministic_entities,
        "conversation_entities": planner_input.conversation_entities,
        "conversation_assumptions": planner_input.conversation_assumptions,
        "capability_registry_summary": planner_input.capability_registry_summary,
        "legacy_workflow_plan": planner_input.legacy_workflow_plan,
        "profile_summary": planner_input.profile_summary,
    }


async def build_execution_plan(
    *,
    user_message: str,
    task_understanding: TaskUnderstandingOutput | dict[str, Any] | None = None,
    deterministic_intent: str | None = None,
    deterministic_entities: dict[str, Any] | None = None,
    conversation_entities: dict[str, Any] | None = None,
    conversation_assumptions: list[str] | None = None,
    legacy_workflow_plan: dict[str, Any] | None = None,
    capability_registry: CapabilityRegistry | None = None,
    profile_summary: dict[str, Any] | None = None,
    reasoning_block: ReasoningBlock | None = None,
    settings: Settings | None = None,
) -> PlannerOutput:
    """Produce a structured, capability-aware execution plan via `ReasoningBlock`.

    Diagnostic only — the result is never executed and never used to select
    a workflow or alter the final response. Falls back to a deterministic
    single-workflow plan (mirroring `legacy_workflow_plan`) when the feature
    flag is off, the LLM is unavailable, reasoning fails, or the LLM's plan
    cannot be normalized into something usable.
    """
    cfg = settings or get_settings()
    task_understanding_dict = _task_understanding_dict(task_understanding)
    registry = capability_registry or build_default_capability_registry()

    if not cfg.is_agent_planner_enabled():
        return _deterministic_fallback_plan(
            user_message=user_message,
            task_understanding=task_understanding_dict,
            deterministic_intent=deterministic_intent,
            legacy_workflow_plan=legacy_workflow_plan,
            warning="planner_disabled",
        )

    planner_input = PlannerInput(
        user_message=user_message,
        task_understanding=task_understanding_dict,
        deterministic_intent=deterministic_intent,
        deterministic_entities=dict(deterministic_entities or {}),
        conversation_entities=dict(conversation_entities or {}),
        conversation_assumptions=list(conversation_assumptions or []),
        capability_registry_summary=_summarize_capabilities(registry),
        legacy_workflow_plan=legacy_workflow_plan,
        profile_summary=dict(profile_summary or {}),
        dry_run=True,
    )

    constraints = [
        "Only use capability names present in capability_registry_summary.",
        "Prefer the existing deterministic workflow in legacy_workflow_plan when it already solves the task.",
        "Do not invent academic facts, transcript data, or completed courses.",
        "Do not claim any write action has happened.",
    ]
    if cfg.is_agent_planner_dynamic_specs_enabled():
        constraints.extend(
            [
                "You may attach dynamic_agent_spec only to read-only diagnostic subtasks.",
                "Every dynamic_agent_spec must set shadow_only=true.",
                "Never generate code or executable scripts in dynamic_agent_spec.",
            ]
        )

    block = reasoning_block or ReasoningBlock(llm_adapter=ChatLLMAdapter(settings=cfg))
    reasoning_input = ReasoningBlockInput(
        block_id=f"planner_agent-{uuid.uuid4().hex[:10]}",
        agent_name="planner_agent",
        objective="Convert the task understanding into a capability-aware execution plan.",
        task_context=_build_task_context(planner_input),
        constraints=constraints,
        success_criteria=[
            "Every subtask.capability_name exists in capability_registry_summary.",
            "Dependencies form a valid, acyclic graph over subtask ids.",
            "Explicit write/save/import subtasks require user confirmation.",
        ],
        output_schema_name="planner_output_v1",
        output_schema=PLANNER_OUTPUT_SCHEMA,
        prompt_contract_name=PLANNER_AGENT_V1,
        risk_level="high",
    )

    output = await block.run(reasoning_input)
    if output.status != "completed" or not output.schema_valid or output.result is None:
        if output.warnings:
            logger.warning("planner_agent_incomplete", extra={"warnings": output.warnings})
        return _deterministic_fallback_plan(
            user_message=user_message,
            task_understanding=task_understanding_dict,
            deterministic_intent=deterministic_intent,
            legacy_workflow_plan=legacy_workflow_plan,
            warning="planner_llm_unavailable_or_failed",
        )

    try:
        candidate = _candidate_from_result(output.result)
    except ValidationError:
        logger.warning("planner_result_shape_invalid")
        return _deterministic_fallback_plan(
            user_message=user_message,
            task_understanding=task_understanding_dict,
            deterministic_intent=deterministic_intent,
            legacy_workflow_plan=legacy_workflow_plan,
            warning="planner_result_shape_invalid",
        )

    normalized = normalize_planner_output(
        candidate,
        registry=registry,
        user_message=user_message,
        deterministic_intent=deterministic_intent,
    )
    if normalized is None:
        return _deterministic_fallback_plan(
            user_message=user_message,
            task_understanding=task_understanding_dict,
            deterministic_intent=deterministic_intent,
            legacy_workflow_plan=legacy_workflow_plan,
            warning="planner_plan_unusable_after_normalization",
        )

    if not cfg.is_agent_planner_dry_run():
        # Phase 5 never executes a plan regardless of this flag — dry-run
        # off only means "the operator expected execution to be live",
        # which isn't implemented yet. Surface that loudly instead of
        # silently ignoring the misconfiguration.
        normalized = normalized.model_copy(
            update={
                "warnings": [
                    *normalized.warnings,
                    "planner_dry_run_disabled_but_execution_not_implemented_in_phase5",
                ]
            }
        )

    normalized, _spec_diagnostics = normalize_planner_dynamic_specs(
        planner_output=normalized,
        settings=cfg,
    )

    return normalized.model_copy(update={"dynamic_spec_diagnostics": _spec_diagnostics})
