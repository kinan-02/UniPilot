"""LLM extraction of semester planning preferences (spec §31.2 call 1).

Phase 2: extraction now runs through the shared `ReasoningBlock` runtime
instead of calling the chat model directly. Public function name, flags, and
merge semantics (regex-resolved entities always win) are unchanged.
"""

from __future__ import annotations

import logging
import uuid
from typing import Any

from app.agent.reasoning.llm_adapter import ChatLLMAdapter
from app.agent.reasoning.prompt_registry import PREFERENCE_EXTRACTOR_V1
from app.agent.reasoning.reasoning_block import ReasoningBlock
from app.agent.reasoning.schemas import ReasoningBlockInput
from app.agent.reasoning.task_schemas import PREFERENCE_EXTRACTOR_OUTPUT_SCHEMA
from app.config import Settings, get_settings

logger = logging.getLogger(__name__)


async def extract_planning_preferences(
    user_message: str,
    *,
    existing_entities: dict[str, Any] | None = None,
    settings: Settings | None = None,
    reasoning_block: ReasoningBlock | None = None,
) -> dict[str, Any]:
    """
    Merge regex-resolved entities with LLM-extracted planning constraints.
    Returns entity updates only — never overwrites explicit regex matches.
    """
    cfg = settings or get_settings()
    base = dict(existing_entities or {})
    if not cfg.is_agent_llm_preference_extraction_enabled():
        return base

    # No `agent_llm_available` pre-check: `ReasoningBlock`/`ChatLLMAdapter` is
    # the single source of truth for LLM availability and fails safely below.
    block = reasoning_block or ReasoningBlock(llm_adapter=ChatLLMAdapter(settings=cfg))
    reasoning_input = ReasoningBlockInput(
        block_id=f"preference_extractor-{uuid.uuid4().hex[:10]}",
        agent_name="preference_extractor",
        objective="Extract semester-planning preferences/constraints from the student message.",
        task_context={
            "student_message": user_message.strip(),
            "already_detected_entities": base,
        },
        constraints=[
            "Never overwrite a non-empty field already present in already_detected_entities.",
            "Use null for any field that is unknown or not stated.",
        ],
        success_criteria=[
            "Return only preferences clearly stated or clearly implied by the message.",
        ],
        output_schema_name="preference_extractor_output_v1",
        output_schema=PREFERENCE_EXTRACTOR_OUTPUT_SCHEMA,
        prompt_contract_name=PREFERENCE_EXTRACTOR_V1,
        risk_level="low",
    )

    output = await block.run(reasoning_input)
    if output.status != "completed" or not output.schema_valid or output.result is None:
        if output.warnings:
            logger.warning(
                "agent_llm_preference_extraction_incomplete", extra={"warnings": output.warnings}
            )
        return base

    payload = output.result
    merged = dict(base)
    for key in (
        "maxCredits",
        "planningObjective",
        "targetSemester",
        "targetSemesterCode",
        "modificationType",
        "replaceCourseNumber",
        "addCourseNumber",
    ):
        if key in merged and merged[key] not in (None, "", []):
            continue
        value = payload.get(key)
        if value is not None and value != "":
            merged[key] = value

    llm_avoid = [str(day) for day in (payload.get("avoidDays") or []) if day]
    if llm_avoid:
        existing_avoid = [str(day) for day in (merged.get("avoidDays") or []) if day]
        merged["avoidDays"] = list(dict.fromkeys([*existing_avoid, *llm_avoid]))

    return merged
