"""Optional LLM validation of retrieval sufficiency (Agent_spec.md §24.7).

Phase 2: validation now runs through the shared `ReasoningBlock` runtime
instead of calling the chat model directly. The function is now a coroutine
(the old implementation was sync and had to be called via
`asyncio.to_thread`) — see `context_builder.py` for the updated call site.
Return shape, flags, and fallback behavior are unchanged.
"""

from __future__ import annotations

import logging
import uuid
from typing import Any

from app.agent.reasoning.llm_adapter import ChatLLMAdapter
from app.agent.reasoning.prompt_registry import ANSWER_VALIDATOR_V1
from app.agent.reasoning.reasoning_block import ReasoningBlock
from app.agent.reasoning.schemas import ReasoningBlockInput
from app.agent.reasoning.task_schemas import ANSWER_VALIDATOR_OUTPUT_SCHEMA
from app.agent.schemas import AgentContextPack
from app.config import Settings, get_settings

logger = logging.getLogger(__name__)


def _retrieval_summary(pack: AgentContextPack) -> dict[str, Any]:
    wiki_lines = [
        {
            "title": snippet.page_title or snippet.source_file,
            "section": snippet.section_title,
            "score": snippet.score,
        }
        for snippet in pack.retrieved_wiki_context[:8]
    ]
    return {
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
    }


async def validate_retrieval_with_llm(
    pack: AgentContextPack,
    *,
    user_message: str,
    settings: Settings | None = None,
    reasoning_block: ReasoningBlock | None = None,
) -> dict[str, Any] | None:
    """
    Optional second-pass validation using the shared reasoning runtime.

    Returns None when disabled/unavailable. Otherwise:
    {"sufficient": bool, "gaps": list[str], "reasoning": str}
    """
    cfg = settings or get_settings()
    if not cfg.is_agent_llm_validation_enabled():
        return None

    # No `agent_llm_available` pre-check: `ReasoningBlock`/`ChatLLMAdapter` is
    # the single source of truth for LLM availability and fails safely below.
    block = reasoning_block or ReasoningBlock(llm_adapter=ChatLLMAdapter(settings=cfg))
    reasoning_input = ReasoningBlockInput(
        block_id=f"answer_validator-{uuid.uuid4().hex[:10]}",
        agent_name="answer_validator",
        objective="Judge whether the retrieved context is sufficient to safely answer the student's question.",
        task_context={
            "student_question": user_message.strip(),
            "retrieval_summary": _retrieval_summary(pack),
        },
        constraints=[
            "sufficient=true only when structured data or wiki snippets cover the "
            "question without guessing.",
        ],
        success_criteria=[
            "gaps must be actionable (what to retrieve or ask the student), not generic.",
        ],
        output_schema_name="answer_validator_output_v1",
        output_schema=ANSWER_VALIDATOR_OUTPUT_SCHEMA,
        prompt_contract_name=ANSWER_VALIDATOR_V1,
        risk_level="medium",
    )

    output = await block.run(reasoning_input)
    if output.status != "completed" or not output.schema_valid or output.result is None:
        if output.warnings:
            logger.warning("agent_llm_validation_incomplete", extra={"warnings": output.warnings})
        return None

    payload = output.result
    return {
        "sufficient": bool(payload.get("sufficient")),
        "gaps": [str(item) for item in payload.get("gaps") or []],
        "reasoning": str(payload.get("reasoning") or ""),
    }
