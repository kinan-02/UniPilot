"""Live integration point for `TaskUnderstandingAgent`.

`run_task_understanding` is the authoritative request-understanding pass for
every turn — its output feeds `to_intent_classification` (the bridge into
`app.agent.task_planner.build_task_plan`, unchanged since this redesign only
replaces what *produces* the intent/entities it consumes, not the dispatch
mechanism itself) and `extracted_entities` (the entities used for the rest of
the turn). It never returns `None` and never raises: any failure degrades to
the same deterministic fallback `understand_user_task` already falls back to
internally, built from the caller-supplied deterministic intent/entities so a
bug here can never leave the turn without a usable result.
"""

from __future__ import annotations

import logging
from typing import Any

from app.agent.schemas import IntentClassification
from app.agent.task_understanding.agent import (
    build_deterministic_task_understanding_fallback,
    understand_user_task,
)
from app.agent.task_understanding.schemas import TaskUnderstandingOutput
from app.config import Settings, get_settings

logger = logging.getLogger(__name__)


def build_task_understanding_diagnostic_summary(output: TaskUnderstandingOutput) -> dict[str, Any]:
    """Compact, storage-safe summary — no raw context, no chain-of-thought."""
    return {
        "status": output.status,
        "primaryIntent": output.primary_intent,
        "secondaryIntents": output.secondary_intents,
        "taskCategory": output.task_category,
        "taskComplexity": output.task_complexity,
        "recommendedAutonomyLevel": output.recommended_autonomy_level,
        "suggestedNextLayer": output.suggested_next_layer,
        "requiresUserConfirmation": output.requires_user_confirmation,
        "writeRisk": output.write_risk,
        "missingContext": output.missing_context[:8],
        "intentConfidence": output.intent_confidence,
        "overallConfidence": output.overall_confidence,
        "decisionSummary": output.decision_summary,
        "warnings": output.warnings[:8],
        "source": output.source,
    }


def to_intent_classification(
    output: TaskUnderstandingOutput, *, requires_file: bool = False
) -> IntentClassification:
    """Bridge `TaskUnderstandingOutput` into the `IntentClassification` shape
    `app.agent.task_planner.build_task_plan` and its downstream consumers
    (`context_builder`, `retrieval_planner`, `clarification.turn_handler`)
    already expect.

    Safe by construction: `reconcile_task_understanding_output`
    (`task_understanding/normalizer.py`) already guarantees `primary_intent`
    is always a valid `AgentIntent` value before this runs.
    """
    return IntentClassification(
        intent=output.primary_intent,  # type: ignore[arg-type]
        confidence=output.intent_confidence,
        requires_file=requires_file,
        requires_confirmation=output.requires_user_confirmation,
        required_context=output.required_context,
    )


async def run_task_understanding(
    *,
    user_message: str,
    deterministic_intent: str | None,
    deterministic_intent_confidence: float | None,
    deterministic_entities: dict[str, Any] | None,
    existing_entities: dict[str, Any] | None = None,
    existing_assumptions: list[str] | None = None,
    recent_messages: list[dict[str, Any]] | None = None,
    attachment_metadata: list[dict[str, Any]] | None = None,
    settings: Settings | None = None,
) -> TaskUnderstandingOutput:
    """Run `TaskUnderstandingAgent` as the live, authoritative understanding pass.

    Always returns a `TaskUnderstandingOutput`, never `None`, never raises.
    When the feature flag is off, `understand_user_task` itself resolves to
    its internal deterministic fallback — this wrapper does not special-case
    that (unlike the old dry-run version, which short-circuited to `None`
    before ever calling it).
    """
    cfg = settings or get_settings()

    try:
        output = await understand_user_task(
            user_message=user_message,
            deterministic_intent=deterministic_intent,
            deterministic_intent_confidence=deterministic_intent_confidence,
            deterministic_entities=deterministic_entities,
            existing_entities=existing_entities,
            existing_assumptions=existing_assumptions,
            recent_messages=recent_messages,
            attachment_metadata=attachment_metadata,
            settings=cfg,
        )
    except Exception:  # noqa: BLE001 — this is load-bearing for every turn; must never raise
        logger.exception("task_understanding_unexpected_error")
        output = build_deterministic_task_understanding_fallback(
            user_message=user_message,
            deterministic_intent=deterministic_intent,
            deterministic_intent_confidence=deterministic_intent_confidence,
            deterministic_entities=deterministic_entities,
            warning="task_understanding_integration_unexpected_error",
        )

    logger.info(
        "task_understanding_result",
        extra={"taskUnderstanding": build_task_understanding_diagnostic_summary(output)},
    )
    return output
