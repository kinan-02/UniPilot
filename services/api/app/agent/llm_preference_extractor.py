"""LLM extraction of semester planning preferences (spec §31.2 call 1)."""

from __future__ import annotations

import logging
from typing import Any

from app.agent.llm_client import agent_llm_available, build_chat_llm
from app.agent.llm_json import parse_llm_json_content
from app.agent.llm_prompts import build_preference_extractor_human, build_preference_extractor_system
from app.config import Settings, get_settings

logger = logging.getLogger(__name__)


async def extract_planning_preferences(
    user_message: str,
    *,
    existing_entities: dict[str, Any] | None = None,
    settings: Settings | None = None,
) -> dict[str, Any]:
    """
    Merge regex-resolved entities with LLM-extracted planning constraints.
    Returns entity updates only — never overwrites explicit regex matches.
    """
    cfg = settings or get_settings()
    base = dict(existing_entities or {})
    if not cfg.is_agent_llm_preference_extraction_enabled():
        return base
    if not agent_llm_available(settings=cfg):
        return base

    llm = build_chat_llm(settings=cfg, temperature=0.0)
    if llm is None:
        return base

    try:
        from langchain_core.messages import HumanMessage, SystemMessage
    except ImportError:
        return base

    system = build_preference_extractor_system()
    human = build_preference_extractor_human(user_message, already_detected=base)
    try:
        response = await llm.ainvoke(
            [SystemMessage(content=system), HumanMessage(content=human)]
        )
        payload = parse_llm_json_content(str(getattr(response, "content", "") or ""))
    except Exception:
        logger.exception("agent_llm_preference_extraction_failed")
        return base

    if not payload:
        return base

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
