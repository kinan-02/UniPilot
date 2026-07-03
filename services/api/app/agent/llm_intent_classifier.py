"""LLM fallback for ambiguous intent classification (spec §8)."""

from __future__ import annotations

import logging

from app.agent.intent_router import classify_intent
from app.agent.llm_client import agent_llm_available, build_chat_llm
from app.agent.llm_json import parse_llm_json_content
from app.agent.llm_prompts import build_intent_classifier_human, build_intent_classifier_system
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
    if not agent_llm_available(settings=cfg):
        return rules_result

    llm_result = await _classify_with_llm(
        message,
        settings=cfg,
        rules_intent=rules_result.intent,
        rules_confidence=rules_result.confidence,
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
) -> IntentClassification | None:
    llm = build_chat_llm(settings=settings, temperature=0.0)
    if llm is None:
        return None

    try:
        from langchain_core.messages import HumanMessage, SystemMessage
    except ImportError:
        return None

    system = build_intent_classifier_system(valid_intents=sorted(_VALID_INTENTS))
    human = build_intent_classifier_human(
        message,
        rules_intent=rules_intent,
        rules_confidence=rules_confidence,
    )
    try:
        response = await llm.ainvoke(
            [SystemMessage(content=system), HumanMessage(content=human)]
        )
        payload = parse_llm_json_content(str(getattr(response, "content", "") or ""))
    except Exception:
        logger.exception("agent_llm_intent_classification_failed")
        return None

    if not payload:
        return None

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
