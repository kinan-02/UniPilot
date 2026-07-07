"""Optional dry-run integration point for `TaskUnderstandingAgent` (Phase 3).

Diagnostic only. The summary returned here is never used by the orchestrator
to select a workflow, alter the final response, or change SSE/structured
block behavior — it is only logged and optionally attached to the existing
free-form `agent_runs.retrievalMetadata` field (no schema/migration needed).
"""

from __future__ import annotations

import logging
from typing import Any

from app.agent.task_understanding.agent import understand_user_task
from app.agent.task_understanding.schemas import TaskUnderstandingOutput
from app.config import Settings, get_settings

logger = logging.getLogger(__name__)


def _diagnostic_summary(output: TaskUnderstandingOutput) -> dict[str, Any]:
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


async def run_task_understanding_dry_run(
    *,
    user_message: str,
    deterministic_intent: str | None,
    deterministic_intent_confidence: float | None,
    deterministic_entities: dict[str, Any] | None,
    existing_assumptions: list[str] | None = None,
    attachment_metadata: list[dict[str, Any]] | None = None,
    settings: Settings | None = None,
) -> dict[str, Any] | None:
    """Run `TaskUnderstandingAgent` for diagnostics only.

    Returns a compact summary dict (safe to log or store in
    `agent_runs.retrievalMetadata`), or `None` when the feature flag is off.

    Never raises: `understand_user_task` already fails safely on its own
    (disabled flag / unavailable LLM / invalid output all resolve to a
    deterministic fallback), but this diagnostic call site adds one more
    guard on top — a bug here must never break a live agent turn.
    """
    cfg = settings or get_settings()
    if not cfg.is_agent_task_understanding_enabled():
        return None

    try:
        output = await understand_user_task(
            user_message=user_message,
            deterministic_intent=deterministic_intent,
            deterministic_intent_confidence=deterministic_intent_confidence,
            deterministic_entities=deterministic_entities,
            existing_assumptions=existing_assumptions,
            attachment_metadata=attachment_metadata,
            settings=cfg,
        )
    except Exception:  # noqa: BLE001 — diagnostic-only path, must never break a live turn
        logger.exception("task_understanding_dry_run_failed")
        return None

    summary = _diagnostic_summary(output)
    logger.info("task_understanding_dry_run_result", extra={"taskUnderstanding": summary})
    return summary
