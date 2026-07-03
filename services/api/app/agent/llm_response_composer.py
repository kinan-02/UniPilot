"""LLM final explanation layer over deterministic workflow output (spec §24.8, §31)."""

from __future__ import annotations

import logging
from collections.abc import AsyncIterator, Awaitable, Callable

from app.agent.explanation_enricher import build_wiki_explanation_context
from app.agent.llm_client import agent_llm_available, build_chat_llm
from app.agent.llm_prompts import build_explanation_human, build_explanation_system
from app.agent.schemas import AgentContextPack, AgentResponse, StructuredBlock
from app.config import Settings, get_settings

logger = logging.getLogger(__name__)

DeltaCallback = Callable[[str], Awaitable[None] | None]


async def enhance_response_with_llm(
    response: AgentResponse,
    *,
    context: AgentContextPack,
    user_message: str,
    settings: Settings | None = None,
    on_delta: DeltaCallback | None = None,
) -> AgentResponse:
    """
    Optional single LLM pass for user-facing explanation (spec §31.1).
    Falls back to the deterministic template text when LLM is disabled/unavailable.
    """
    cfg = settings or get_settings()
    if not cfg.is_agent_llm_explanation_enabled():
        return response
    if not agent_llm_available(settings=cfg):
        return response
    if not (response.text or "").strip() and not response.blocks:
        return response

    llm = build_chat_llm(settings=cfg, temperature=0.15)
    if llm is None:
        return response

    wiki_summary = build_wiki_explanation_context(context.retrieved_wiki_context)
    system = build_explanation_system(intent=context.intent, user_message=user_message)
    human = build_explanation_human(
        user_message=user_message,
        response=response,
        context=context,
        wiki_context=wiki_summary,
    )

    try:
        from langchain_core.messages import HumanMessage, SystemMessage
    except ImportError:
        return response

    messages = [SystemMessage(content=system), HumanMessage(content=human)]

    try:
        if on_delta is not None and hasattr(llm, "astream"):
            parts: list[str] = []
            async for chunk in llm.astream(messages):
                token = str(getattr(chunk, "content", "") or "")
                if not token:
                    continue
                parts.append(token)
                result = on_delta(token)
                if result is not None:
                    await result
            enhanced = "".join(parts).strip()
        else:
            result = await llm.ainvoke(messages)
            enhanced = str(getattr(result, "content", "") or "").strip()
    except Exception:
        logger.exception("agent_llm_explanation_failed")
        return response

    if not enhanced:
        return response

    return response.model_copy(update={"text": enhanced})


async def stream_llm_explanation_deltas(
    response: AgentResponse,
    *,
    context: AgentContextPack,
    user_message: str,
    settings: Settings | None = None,
) -> AsyncIterator[str]:
    """Yield text deltas while composing the LLM explanation."""
    cfg = settings or get_settings()
    if not cfg.is_agent_llm_explanation_enabled() or not agent_llm_available(settings=cfg):
        if response.text:
            yield response.text
        return

    llm = build_chat_llm(settings=cfg, temperature=0.15)
    if llm is None:
        if response.text:
            yield response.text
        return

    wiki_summary = build_wiki_explanation_context(context.retrieved_wiki_context)
    system = build_explanation_system(intent=context.intent, user_message=user_message)
    human = build_explanation_human(
        user_message=user_message,
        response=response,
        context=context,
        wiki_context=wiki_summary,
    )

    try:
        from langchain_core.messages import HumanMessage, SystemMessage
    except ImportError:
        if response.text:
            yield response.text
        return

    try:
        async for chunk in llm.astream(
            [SystemMessage(content=system), HumanMessage(content=human)]
        ):
            token = str(getattr(chunk, "content", "") or "")
            if token:
                yield token
    except Exception:
        logger.exception("agent_llm_explanation_stream_failed")
        if response.text:
            yield response.text


def build_general_academic_response(
    *,
    context: AgentContextPack,
    user_message: str,
    llm_text: str,
) -> tuple[str, list[StructuredBlock]]:
    """Compose general/catalog answers grounded in retrieved wiki context."""
    blocks: list[StructuredBlock] = []
    if context.retrieved_wiki_context:
        blocks.append(
            StructuredBlock(
                type="SourceSummaryBlock",
                data={
                    "provenance": context.provenance,
                    "wikiSections": [
                        {
                            "title": snippet.page_title or snippet.source_file,
                            "section": snippet.section_title,
                        }
                        for snippet in context.retrieved_wiki_context[:6]
                    ],
                },
            )
        )
    if context.validation.warnings:
        blocks.append(
            StructuredBlock(
                type="WarningBlock",
                data={"messages": context.validation.warnings[:6]},
            )
        )
    text = llm_text.strip() or (
        "I found some catalog context but could not compose a full answer. "
        "Try asking about graduation progress or a specific course number."
    )
    return text, blocks
