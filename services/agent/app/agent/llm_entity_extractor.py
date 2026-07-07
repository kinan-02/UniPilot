"""LLM fallback for entity resolution when regex extraction finds nothing.

Mirrors `llm_intent_classifier.py`'s rules-first/LLM-fallback pattern:
`entity_resolver.resolve_entities` (regex) always runs first and always
wins — this only recovers a core entity regex missed entirely, and never
overrides an already-resolved value. Off by default
(`AGENT_LLM_ENTITY_EXTRACTION_FALLBACK_ENABLED`).
"""

from __future__ import annotations

import logging
import uuid
from typing import Any

from app.agent.reasoning.llm_adapter import ChatLLMAdapter
from app.agent.reasoning.prompt_registry import ENTITY_EXTRACTOR_V1
from app.agent.reasoning.reasoning_block import ReasoningBlock
from app.agent.reasoning.schemas import ReasoningBlockInput
from app.agent.reasoning.task_schemas import ENTITY_EXTRACTOR_OUTPUT_SCHEMA
from app.config import Settings, get_settings

logger = logging.getLogger(__name__)

# Entities the deterministic regex parser (`entity_resolver.resolve_entities`)
# is responsible for. The LLM fallback only ever runs when none of these are
# already present, and only ever fills in whichever of these regex left
# empty — it never adds or overrides any other entity key.
_CORE_ENTITY_KEYS = ("courseNumber", "trackSlug", "programSlug", "wikiSlug")

_MIN_MESSAGE_LENGTH_FOR_FALLBACK = 8


def _needs_llm_fallback(message: str, resolved_entities: dict[str, Any]) -> bool:
    """Only recover a core entity regex missed entirely.

    Never called when regex already found one (nothing to recover), and
    never for messages too short to plausibly name a course/track/program
    (avoids spending an LLM call on "ok" or "thanks").
    """
    if any(resolved_entities.get(key) for key in _CORE_ENTITY_KEYS):
        return False
    return len(message.strip()) >= _MIN_MESSAGE_LENGTH_FOR_FALLBACK


async def resolve_entities_with_llm_fallback(
    user_message: str,
    *,
    resolved_entities: dict[str, Any],
    settings: Settings | None = None,
    reasoning_block: ReasoningBlock | None = None,
) -> dict[str, Any]:
    """Recover a core entity via LLM only when regex extraction found none.

    `resolved_entities` is the output of `entity_resolver.resolve_entities`
    (regex already applied) — this function only ever adds a value for a key
    that's currently empty; it never overwrites anything regex resolved.
    """
    cfg = settings or get_settings()
    if not cfg.is_agent_llm_entity_extraction_fallback_enabled():
        return resolved_entities
    if not _needs_llm_fallback(user_message, resolved_entities):
        return resolved_entities

    # No `agent_llm_available` pre-check: `ReasoningBlock`/`ChatLLMAdapter` is
    # the single source of truth for LLM availability and fails safely below.
    block = reasoning_block or ReasoningBlock(llm_adapter=ChatLLMAdapter(settings=cfg))
    reasoning_input = ReasoningBlockInput(
        block_id=f"entity_extractor-{uuid.uuid4().hex[:10]}",
        agent_name="entity_extractor",
        objective="Recover a course/track/program/wiki reference the deterministic parser missed.",
        task_context={
            "student_message": user_message.strip(),
            "already_detected_entities": resolved_entities,
        },
        constraints=[
            "Populate at most one field — the single entity the message is about.",
            "Never invent a course number, track, or program that isn't stated or clearly implied.",
            "Use null for anything not clearly identifiable.",
        ],
        success_criteria=[
            "Return at most one non-null field, only if confidently identifiable.",
        ],
        output_schema_name="entity_extractor_output_v1",
        output_schema=ENTITY_EXTRACTOR_OUTPUT_SCHEMA,
        prompt_contract_name=ENTITY_EXTRACTOR_V1,
        risk_level="low",
    )

    output = await block.run(reasoning_input)
    if output.status != "completed" or not output.schema_valid or output.result is None:
        if output.warnings:
            logger.warning(
                "agent_llm_entity_extraction_incomplete", extra={"warnings": output.warnings}
            )
        return resolved_entities

    payload = output.result
    merged = dict(resolved_entities)
    for key in _CORE_ENTITY_KEYS:
        if merged.get(key):
            continue  # regex already resolved this — never overwrite
        value = payload.get(key)
        if value:
            merged[key] = str(value)
    return merged
