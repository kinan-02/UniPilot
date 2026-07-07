"""Task Understanding Agent (Phase 3).

Produces a richer, structured understanding of a student's request than the
rules-first intent classifier, via the shared `ReasoningBlock` runtime.

Hard constraints (enforced by construction, not just by convention):
- Only calls the LLM through `ReasoningBlock` — never directly.
- Never creates write actions.
- Never retrieves large academic context (catalog, transcript rows, degree
  requirements, wiki snippets) — only the minimal context passed in.
- Never runs workflows.
- Never decides the final answer shown to the student.

In Phase 3 this output is diagnostic/future-planning data only. Nothing in
the live orchestrator uses it to choose a workflow or alter a response.
"""

from __future__ import annotations

import logging
import uuid
from typing import Any, get_args

from pydantic import ValidationError

from app.agent.llm_prompts import intent_catalog_entries
from app.agent.reasoning.llm_adapter import ChatLLMAdapter
from app.agent.reasoning.prompt_registry import TASK_UNDERSTANDING_V1
from app.agent.reasoning.reasoning_block import ReasoningBlock
from app.agent.reasoning.schemas import ReasoningBlockInput
from app.agent.reasoning.task_schemas import TASK_UNDERSTANDING_OUTPUT_SCHEMA
from app.agent.schemas import AgentIntent
from app.agent.task_understanding.normalizer import reconcile_task_understanding_output
from app.agent.task_understanding.schemas import (
    TaskCategory,
    TaskUnderstandingInput,
    TaskUnderstandingOutput,
)
from app.config import Settings, get_settings

logger = logging.getLogger(__name__)

_UNKNOWN_INTENT_VALUE = "unknown_or_unsupported"
_SUPPORTED_INTENTS: frozenset[str] = frozenset(get_args(AgentIntent))

# Kept local to this module rather than added to `workflows/registry.py`:
# these are short human-readable descriptions for the LLM prompt only, not a
# functional registry entry.
_SUPPORTED_WORKFLOWS: dict[str, str] = {
    "graduation_progress_workflow": (
        "Compute graduation/degree progress from completed courses and requirements."
    ),
    "course_question_workflow": (
        "Answer eligibility, prerequisite, or offering questions about a specific course."
    ),
    "transcript_import_workflow": (
        "Parse an uploaded transcript and let the student review/confirm before saving."
    ),
    "semester_planning_workflow": "Generate or modify a semester schedule/plan.",
    "requirement_explanation_workflow": (
        "Explain a degree requirement bucket and what satisfies it."
    ),
    "general_academic_workflow": "General/catalog Q&A and unsupported/unclear requests.",
}

_TASK_CATEGORY_BY_INTENT: dict[str, TaskCategory] = {
    "graduation_progress_check": "academic_analysis",
    "transcript_import": "transcript_processing",
    "completed_courses_update": "transcript_processing",
    "semester_plan_generation": "planning",
    "semester_plan_modification": "planning",
    "course_question": "simple_question",
    "prerequisite_check": "simple_question",
    "requirement_explanation": "requirement_explanation",
    "catalog_search": "simple_question",
    "profile_update": "write_or_update_request",
    "general_academic_question": "simple_question",
    "unknown_or_unsupported": "unsupported",
}


def _clamp01(value: Any) -> float:
    try:
        number = float(value)
    except (TypeError, ValueError):
        return 0.5
    return max(0.0, min(1.0, number))


def _task_category_for_intent(intent: str) -> TaskCategory:
    return _TASK_CATEGORY_BY_INTENT.get(intent, "unsupported")


def _attachment_metadata_only(attachments: list[dict[str, Any]] | None) -> list[dict[str, Any]]:
    """Strip attachment payload contents (e.g. parsed transcript rows) — metadata only."""
    metadata: list[dict[str, Any]] = []
    for item in attachments or []:
        if not isinstance(item, dict):
            continue
        metadata.append(
            {
                "type": item.get("type"),
                "filename": item.get("filename"),
                "contentType": item.get("contentType"),
            }
        )
    return metadata


def _deterministic_fallback(
    *,
    user_message: str,
    deterministic_intent: str | None,
    deterministic_intent_confidence: float | None,
    deterministic_entities: dict[str, Any] | None,
    warning: str,
) -> TaskUnderstandingOutput:
    intent = deterministic_intent if deterministic_intent in _SUPPORTED_INTENTS else _UNKNOWN_INTENT_VALUE
    confidence = (
        _clamp01(deterministic_intent_confidence) if deterministic_intent_confidence is not None else 0.5
    )
    return TaskUnderstandingOutput(
        status="completed",
        user_goal=user_message,
        normalized_request=user_message,
        primary_intent=intent,
        secondary_intents=[],
        task_category=_task_category_for_intent(intent),
        task_complexity="medium",
        recommended_autonomy_level=2,
        suggested_next_layer="deterministic_workflow",
        required_context=[],
        missing_context=[],
        extracted_entities=dict(deterministic_entities or {}),
        assumptions=[],
        requires_user_confirmation=False,
        write_risk="none",
        clarifying_questions=[],
        intent_confidence=confidence,
        overall_confidence=confidence,
        decision_summary=(
            "Used deterministic fallback task understanding because LLM reasoning "
            "was unavailable or failed."
        ),
        warnings=[warning],
        source="deterministic_fallback",
    )


def _str_list(result: dict[str, Any], key: str) -> list[str]:
    values = result.get(key)
    if not isinstance(values, list):
        return []
    return [str(value) for value in values if str(value).strip()]


def _candidate_from_result(result: dict[str, Any]) -> TaskUnderstandingOutput:
    """Lenient construction from a `result` dict that already passed JSON-schema validation."""
    return TaskUnderstandingOutput(
        status=result.get("status", "completed"),
        user_goal=str(result.get("user_goal") or ""),
        normalized_request=str(result.get("normalized_request") or ""),
        primary_intent=str(result.get("primary_intent") or _UNKNOWN_INTENT_VALUE),
        secondary_intents=_str_list(result, "secondary_intents"),
        task_category=result.get("task_category", "unsupported"),
        task_complexity=result.get("task_complexity", "medium"),
        recommended_autonomy_level=result.get("recommended_autonomy_level", 2),
        suggested_next_layer=result.get("suggested_next_layer", "deterministic_workflow"),
        required_context=_str_list(result, "required_context"),
        missing_context=_str_list(result, "missing_context"),
        extracted_entities=dict(result.get("extracted_entities") or {}),
        assumptions=_str_list(result, "assumptions"),
        requires_user_confirmation=bool(result.get("requires_user_confirmation", False)),
        write_risk=result.get("write_risk", "none"),
        clarifying_questions=_str_list(result, "clarifying_questions"),
        intent_confidence=_clamp01(result.get("intent_confidence", 0.5)),
        overall_confidence=_clamp01(result.get("overall_confidence", 0.5)),
        decision_summary=str(result.get("decision_summary") or ""),
        warnings=_str_list(result, "warnings"),
        source="llm_reasoning_block",
    )


def _build_task_context(task_input: TaskUnderstandingInput) -> dict[str, Any]:
    supported_intent_catalog = [
        entry for entry in intent_catalog_entries() if entry["name"] in _SUPPORTED_INTENTS
    ]
    supported_workflow_catalog = [
        {"name": name, "description": description}
        for name, description in sorted(_SUPPORTED_WORKFLOWS.items())
    ]
    return {
        "user_message": task_input.user_message,
        "conversation_summary": task_input.conversation_summary,
        "recent_messages": task_input.recent_messages[-6:],
        "existing_entities": task_input.existing_entities,
        "existing_assumptions": task_input.existing_assumptions,
        "deterministic_intent": task_input.deterministic_intent,
        "deterministic_intent_confidence": task_input.deterministic_intent_confidence,
        "deterministic_entities": task_input.deterministic_entities,
        "user_profile_summary": task_input.user_profile_summary,
        "attachment_metadata": task_input.attachment_metadata,
        "supported_intents": supported_intent_catalog,
        "supported_workflows": supported_workflow_catalog,
        "locale_hint": task_input.locale_hint,
    }


async def understand_user_task(
    *,
    user_message: str,
    deterministic_intent: str | None = None,
    deterministic_intent_confidence: float | None = None,
    deterministic_entities: dict[str, Any] | None = None,
    conversation_summary: str | None = None,
    recent_messages: list[dict[str, Any]] | None = None,
    existing_entities: dict[str, Any] | None = None,
    existing_assumptions: list[str] | None = None,
    user_profile_summary: dict[str, Any] | None = None,
    attachment_metadata: list[dict[str, Any]] | None = None,
    locale_hint: str | None = None,
    reasoning_block: ReasoningBlock | None = None,
    settings: Settings | None = None,
) -> TaskUnderstandingOutput:
    """Produce a structured understanding of the user's task via `ReasoningBlock`.

    Diagnostic only in Phase 3 — the result is not used to select a workflow
    or alter the final response. Falls back to a deterministic result when
    the feature flag is off, the LLM is unavailable, or reasoning fails.
    """
    cfg = settings or get_settings()
    if not cfg.is_agent_task_understanding_enabled():
        return _deterministic_fallback(
            user_message=user_message,
            deterministic_intent=deterministic_intent,
            deterministic_intent_confidence=deterministic_intent_confidence,
            deterministic_entities=deterministic_entities,
            warning="task_understanding_disabled",
        )

    task_input = TaskUnderstandingInput(
        user_message=user_message,
        conversation_summary=conversation_summary,
        recent_messages=list(recent_messages or []),
        existing_entities=dict(existing_entities or {}),
        existing_assumptions=list(existing_assumptions or []),
        deterministic_intent=deterministic_intent,
        deterministic_intent_confidence=deterministic_intent_confidence,
        deterministic_entities=dict(deterministic_entities or {}),
        user_profile_summary=dict(user_profile_summary or {}),
        attachment_metadata=_attachment_metadata_only(attachment_metadata),
        supported_intents=sorted(_SUPPORTED_INTENTS),
        supported_workflows=sorted(_SUPPORTED_WORKFLOWS),
        locale_hint=locale_hint,
    )

    block = reasoning_block or ReasoningBlock(llm_adapter=ChatLLMAdapter(settings=cfg))
    reasoning_input = ReasoningBlockInput(
        block_id=f"task_understanding-{uuid.uuid4().hex[:10]}",
        agent_name="task_understanding_agent",
        objective="Deeply understand the user's academic task before planning or workflow execution.",
        task_context=_build_task_context(task_input),
        constraints=[
            "Only use supported intent values for primary_intent and secondary_intents.",
            "Do not invent academic facts, transcript data, or completed courses.",
            "Do not claim any write action has happened.",
        ],
        success_criteria=[
            "The goal, normalized request, and intents reflect only the supplied context.",
            "Missing context and clarifying questions are populated when genuinely needed.",
        ],
        output_schema_name="task_understanding_output_v1",
        output_schema=TASK_UNDERSTANDING_OUTPUT_SCHEMA,
        prompt_contract_name=TASK_UNDERSTANDING_V1,
        risk_level="medium",
    )

    output = await block.run(reasoning_input)
    if output.status != "completed" or not output.schema_valid or output.result is None:
        if output.warnings:
            logger.warning("task_understanding_incomplete", extra={"warnings": output.warnings})
        return _deterministic_fallback(
            user_message=user_message,
            deterministic_intent=deterministic_intent,
            deterministic_intent_confidence=deterministic_intent_confidence,
            deterministic_entities=deterministic_entities,
            warning="task_understanding_llm_unavailable_or_failed",
        )

    try:
        candidate = _candidate_from_result(output.result)
    except ValidationError:
        logger.warning("task_understanding_result_shape_invalid")
        return _deterministic_fallback(
            user_message=user_message,
            deterministic_intent=deterministic_intent,
            deterministic_intent_confidence=deterministic_intent_confidence,
            deterministic_entities=deterministic_entities,
            warning="task_understanding_result_shape_invalid",
        )

    return reconcile_task_understanding_output(
        candidate,
        user_message=user_message,
        supported_intents=_SUPPORTED_INTENTS,
        deterministic_intent=deterministic_intent,
        deterministic_intent_confidence=deterministic_intent_confidence,
        unknown_intent_value=_UNKNOWN_INTENT_VALUE,
    )
