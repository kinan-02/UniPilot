"""LLM final explanation layer over deterministic workflow output (spec §24.8, §31).

Phase 2: the explanation pass now runs through the shared `ReasoningBlock`
runtime instead of calling the chat model directly. `ReasoningBlock` does not
stream in Phase 1/2 (see `app/agent/reasoning/llm_adapter.py`), so token-level
LLM streaming is gone — but this has no effect on real SSE behavior: the
orchestrator's `on_delta` callback here has always just buffered tokens into
a list that was discarded (`_finalize_response` in `orchestrator.py`), while
the actual `message.delta` SSE events are produced separately by chunking the
final response text (see `_emit_final_response_events`). `on_delta` is kept
for signature compatibility and is now invoked once with the final text.

The LLM may only rewrite `response.text`. Structured blocks, proposed
actions, sources, warnings, and assumptions remain deterministic and are
never touched here.
"""

from __future__ import annotations

import logging
import uuid
from collections.abc import AsyncIterator, Awaitable, Callable

from app.agent.explanation_enricher import build_wiki_explanation_context
from app.services.prerequisite_validation_service import ELIGIBILITY_VALIDATION_SOURCE
from app.agent.llm_prompts import explanation_style_guide, language_instruction, summarize_structured_blocks
from app.agent.reasoning.llm_adapter import ChatLLMAdapter
from app.agent.reasoning.prompt_registry import RESPONSE_COMPOSER_V1
from app.agent.reasoning.reasoning_block import ReasoningBlock
from app.agent.reasoning.result_normalizer import GENERIC_BLANK_FIELD_PLACEHOLDER
from app.agent.reasoning.schemas import ReasoningBlockInput
from app.agent.reasoning.task_schemas import RESPONSE_COMPOSER_OUTPUT_SCHEMA
from app.agent.schemas import AgentContextPack, AgentResponse, StructuredBlock
from app.config import Settings, get_settings

logger = logging.getLogger(__name__)

DeltaCallback = Callable[[str], Awaitable[None] | None]

# Marker a workflow can add to `AgentResponse.used_sources` to signal "I
# already composed this text via a real LLM reasoning pass myself -- don't
# re-run `enhance_response_with_llm` on top of it." Today only
# `general_academic_workflow.py`'s LLM-composing branches
# (`_general_academic_response`/`_catalog_search_response`) set this; every
# other workflow uses the plain deterministic `response_composer.compose_response`
# and still relies on this module's own pass for any LLM-composed text.
ALREADY_LLM_COMPOSED_SOURCE = "already-llm-composed:general_academic_workflow"


def _composer_task_context(
    *, context: AgentContextPack, user_message: str, response: AgentResponse, wiki_context: str
) -> dict[str, object]:
    return {
        "workflow_intent": context.intent,
        "baseline_answer": (response.text or "").strip()[:2500],
        "structured_blocks_summary": summarize_structured_blocks(response.blocks),
        "warnings": response.warnings[:10],
        "assumptions": response.assumptions[:10],
        "used_sources": response.used_sources[:12],
        "validation_status": context.validation.status,
        "wiki_context": (wiki_context or "").strip()[:2200] or None,
        "style_guidance": explanation_style_guide(context.intent),
        "language_instruction": language_instruction(user_message),
    }


async def _run_composer_reasoning(
    *,
    response: AgentResponse,
    context: AgentContextPack,
    user_message: str,
    settings: Settings,
    reasoning_block: ReasoningBlock | None,
) -> str | None:
    """Return enhanced text, or None when unavailable/unchanged."""
    wiki_summary = build_wiki_explanation_context(context.retrieved_wiki_context)
    block = reasoning_block or ReasoningBlock(llm_adapter=ChatLLMAdapter(settings=settings))
    reasoning_input = ReasoningBlockInput(
        block_id=f"response_composer-{uuid.uuid4().hex[:10]}",
        agent_name="response_composer",
        objective="Rewrite the deterministic baseline answer into a clear, student-facing reply.",
        task_context=_composer_task_context(
            context=context, user_message=user_message, response=response, wiki_context=wiki_summary
        ),
        constraints=[
            "Only rewrite text. Never invent facts beyond baseline_answer, "
            "structured_blocks_summary, and wiki_context.",
        ],
        success_criteria=[
            "The reply answers the student's question directly and matches their language.",
        ],
        output_schema_name="response_composer_output_v1",
        output_schema=RESPONSE_COMPOSER_OUTPUT_SCHEMA,
        prompt_contract_name=RESPONSE_COMPOSER_V1,
        risk_level="low",
    )

    output = await block.run(reasoning_input)
    if output.status != "completed" or not output.schema_valid or output.result is None:
        if output.warnings:
            logger.warning("agent_llm_explanation_incomplete", extra={"warnings": output.warnings})
        return None

    enhanced = str(output.result.get("text") or "").strip()
    if enhanced == GENERIC_BLANK_FIELD_PLACEHOLDER:
        # The model returned this required field blank; the reasoning block's
        # own schema-repair filled it with this structural placeholder to
        # pass validation -- never real content. Keep the live response's
        # own text exactly like every other "couldn't enhance" case below.
        logger.warning("agent_llm_explanation_placeholder_text", extra={"warnings": output.warnings})
        return None
    return enhanced or None


async def enhance_response_with_llm(
    response: AgentResponse,
    *,
    context: AgentContextPack,
    user_message: str,
    settings: Settings | None = None,
    on_delta: DeltaCallback | None = None,
    reasoning_block: ReasoningBlock | None = None,
) -> AgentResponse:
    """
    Optional single reasoning pass for user-facing explanation (spec §31.1).
    Falls back to the deterministic template text when LLM is disabled/unavailable.

    Rewrites `response.text` only — blocks, actions, sources, warnings, and
    assumptions are returned unchanged.
    """
    cfg = settings or get_settings()
    if not cfg.is_agent_llm_explanation_enabled():
        return response
    if any("Loaded catalog wiki page" in item for item in response.used_sources):
        return response
    if any(ELIGIBILITY_VALIDATION_SOURCE in item for item in response.used_sources):
        return response
    if ALREADY_LLM_COMPOSED_SOURCE in response.used_sources:
        return response
    if not (response.text or "").strip() and not response.blocks:
        return response

    # No `agent_llm_available` pre-check: `ReasoningBlock`/`ChatLLMAdapter` is
    # the single source of truth for LLM availability and fails safely below.

    enhanced = await _run_composer_reasoning(
        response=response,
        context=context,
        user_message=user_message,
        settings=cfg,
        reasoning_block=reasoning_block,
    )
    if not enhanced:
        return response

    if on_delta is not None:
        result = on_delta(enhanced)
        if result is not None:
            await result

    return response.model_copy(update={"text": enhanced})


async def stream_llm_explanation_deltas(
    response: AgentResponse,
    *,
    context: AgentContextPack,
    user_message: str,
    settings: Settings | None = None,
    reasoning_block: ReasoningBlock | None = None,
) -> AsyncIterator[str]:
    """Yield the composed explanation text (single chunk; `ReasoningBlock` does not stream)."""
    enhanced = await enhance_response_with_llm(
        response,
        context=context,
        user_message=user_message,
        settings=settings,
        reasoning_block=reasoning_block,
    )
    if enhanced.text:
        yield enhanced.text


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
