"""LLM fallback for ambiguous intent classification (spec §8).

Phase 2: the LLM fallback now runs through the shared `ReasoningBlock`
runtime (`app.agent.reasoning`) instead of calling the chat model directly.
Public function names, flags, and fallback behavior are unchanged.
"""

from __future__ import annotations

import logging
import uuid

from app.agent.intent_router import classify_intent
from app.agent.llm_prompts import intent_catalog_entries
from app.agent.reasoning.llm_adapter import ChatLLMAdapter
from app.agent.reasoning.prompt_registry import INTENT_CLASSIFIER_V1
from app.agent.reasoning.reasoning_block import ReasoningBlock
from app.agent.reasoning.schemas import ReasoningBlockInput
from app.agent.reasoning.task_schemas import INTENT_CLASSIFIER_OUTPUT_SCHEMA
from app.agent.schemas import IntentClassification
from app.config import Settings, get_settings

logger = logging.getLogger(__name__)

_LLM_FALLBACK_THRESHOLD = 0.78

_VALID_INTENTS: frozenset[str] = frozenset(
    {
        "graduation_progress_check",
        "transcript_import",
        "semester_plan_generation",
        "semester_plan_modification",
        "course_question",
        "requirement_explanation",
        "prerequisite_check",
        "catalog_search",
        "completed_courses_update",
        "profile_update",
        "general_academic_question",
        "unknown_or_unsupported",
    }
)


def classify_intent_rules(message: str) -> IntentClassification:
    """Rules-only classification (backward compatible)."""
    return classify_intent(message)


async def classify_intent_with_llm_fallback(
    message: str,
    *,
    settings: Settings | None = None,
    reasoning_block: ReasoningBlock | None = None,
) -> IntentClassification:
    """
    Rules first; optional LLM classification when confidence is low (spec §8).
    """
    rules_result = classify_intent(message)
    cfg = settings or get_settings()
    if not cfg.is_agent_llm_intent_fallback_enabled():
        return rules_result
    if rules_result.confidence >= _LLM_FALLBACK_THRESHOLD:
        return rules_result

    # No `agent_llm_available` pre-check here: `ReasoningBlock.run` (via
    # `ChatLLMAdapter`) is the single place that knows whether an LLM is
    # actually configured, and fails safely (status="failed") when it isn't —
    # `_classify_with_llm` already treats that the same as "no result".
    llm_result = await _classify_with_llm(
        message,
        settings=cfg,
        rules_intent=rules_result.intent,
        rules_confidence=rules_result.confidence,
        reasoning_block=reasoning_block,
    )
    if llm_result is None:
        return rules_result
    if llm_result.confidence >= rules_result.confidence:
        return llm_result
    return rules_result


async def _classify_with_llm(
    message: str,
    *,
    settings: Settings,
    rules_intent: str | None = None,
    rules_confidence: float | None = None,
    reasoning_block: ReasoningBlock | None = None,
) -> IntentClassification | None:
    block = reasoning_block or ReasoningBlock(llm_adapter=ChatLLMAdapter(settings=settings))

    reasoning_input = ReasoningBlockInput(
        block_id=f"intent_classifier-{uuid.uuid4().hex[:10]}",
        agent_name="intent_classifier",
        objective="Classify the student's academic intent into exactly one allowed intent.",
        task_context={
            "student_message": message.strip(),
            "rules_guess": (
                {"intent": rules_intent, "confidence": rules_confidence}
                if rules_intent is not None
                else None
            ),
            "valid_intents": intent_catalog_entries(),
        },
        constraints=[
            "Pick exactly one intent from valid_intents.",
            "Override rules_guess only if it is clearly wrong.",
        ],
        success_criteria=[
            "Return an intent value from valid_intents with a calibrated confidence.",
        ],
        output_schema_name="intent_classifier_output_v1",
        output_schema=INTENT_CLASSIFIER_OUTPUT_SCHEMA,
        prompt_contract_name=INTENT_CLASSIFIER_V1,
        risk_level="medium",
    )

    # `ReasoningBlock.run` never raises for LLM unavailability/failure — it
    # returns a `status="failed"` output instead, so we only need to branch
    # on the result here (no broad exception handling needed).
    output = await block.run(reasoning_input)
    if output.status != "completed" or not output.schema_valid or output.result is None:
        if output.warnings:
            logger.warning("agent_llm_intent_classification_incomplete", extra={"warnings": output.warnings})
        return None

    payload = output.result
    intent = str(payload.get("intent") or "general_academic_question")
    if intent not in _VALID_INTENTS:
        intent = "general_academic_question"

    required_context = [
        str(item) for item in (payload.get("requiredContext") or []) if str(item).strip()
    ]
    return IntentClassification(
        intent=intent,  # type: ignore[arg-type]
        confidence=float(payload.get("confidence") or 0.82),
        requires_file=bool(payload.get("requiresFile")),
        requires_confirmation=bool(payload.get("requiresConfirmation")),
        required_context=required_context,
    )
