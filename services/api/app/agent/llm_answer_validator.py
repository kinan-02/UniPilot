"""Optional LLM validation of retrieval sufficiency (Agent_spec.md §24.7)."""

from __future__ import annotations

import json
import logging
from typing import Any

from app.agent.llm_client import agent_llm_available, build_chat_llm
from app.agent.llm_json import parse_llm_json_content
from app.agent.llm_prompts import build_retrieval_validator_human, build_retrieval_validator_system
from app.agent.schemas import AgentContextPack
from app.config import Settings, get_settings

logger = logging.getLogger(__name__)


def _retrieval_summary(pack: AgentContextPack) -> str:
    wiki_lines = [
        {
            "title": snippet.page_title or snippet.source_file,
            "section": snippet.section_title,
            "score": snippet.score,
        }
        for snippet in pack.retrieved_wiki_context[:8]
    ]
    return json.dumps(
        {
            "intent": pack.intent,
            "retrievalProfile": pack.retrieval_profile,
            "wikiSections": wiki_lines,
            "academicContextKeys": sorted(pack.academic_context.keys()),
            "userContextKeys": sorted(pack.user_context.keys()),
            "entityKeys": sorted(pack.entities.keys()),
            "validationStatus": pack.validation.status,
            "validationWarnings": pack.validation.warnings[:8],
            "validationErrors": pack.validation.errors[:8],
            "missingData": pack.missing_data[:6],
            "provenanceCount": len(pack.provenance),
        },
        ensure_ascii=False,
        indent=2,
    )


def validate_retrieval_with_llm(
    pack: AgentContextPack,
    *,
    user_message: str,
    settings: Settings | None = None,
) -> dict[str, Any] | None:
    """
    Optional second-pass validation using the chat LLM.

    Returns None when disabled/unavailable. Otherwise:
    {"sufficient": bool, "gaps": list[str], "reasoning": str}
    """
    cfg = settings or get_settings()
    if not cfg.is_agent_llm_validation_enabled():
        return None
    if not agent_llm_available(settings=cfg):
        return None

    llm = build_chat_llm(settings=cfg, temperature=0.0)
    if llm is None:
        return None

    try:
        from langchain_core.messages import HumanMessage, SystemMessage
    except ImportError:
        logger.warning("agent_llm_validation_unavailable_import")
        return None

    system = build_retrieval_validator_system()
    human = build_retrieval_validator_human(
        user_message=user_message,
        retrieval_summary=_retrieval_summary(pack),
    )
    try:
        response = llm.invoke([SystemMessage(content=system), HumanMessage(content=human)])
        payload = parse_llm_json_content(str(getattr(response, "content", "") or ""))
    except Exception:
        logger.exception("agent_llm_validation_failed")
        return None

    if not payload:
        return None
    return {
        "sufficient": bool(payload.get("sufficient")),
        "gaps": [str(item) for item in payload.get("gaps") or []],
        "reasoning": str(payload.get("reasoning") or ""),
    }
