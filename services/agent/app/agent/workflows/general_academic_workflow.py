"""General academic and catalog workflows with grounded LLM answers (spec §24.1)."""

from __future__ import annotations

import uuid
from collections.abc import AsyncIterator

from motor.motor_asyncio import AsyncIOMotorDatabase

from app.agent.explanation_enricher import build_wiki_explanation_context
from app.agent.llm_prompts import explanation_style_guide, language_instruction
from app.agent.llm_response_composer import build_general_academic_response
from app.agent.reasoning.llm_adapter import ChatLLMAdapter
from app.agent.reasoning.prompt_registry import RESPONSE_COMPOSER_V1
from app.agent.reasoning.reasoning_block import ReasoningBlock
from app.agent.reasoning.schemas import ReasoningBlockInput
from app.agent.reasoning.task_schemas import RESPONSE_COMPOSER_OUTPUT_SCHEMA
from app.agent.response_composer import compose_response
from app.agent.schemas import AgentContextPack, AgentResponse, StreamEvent, StructuredBlock


class GeneralAcademicWorkflow:
    name = "general_academic_workflow"

    async def run(
        self,
        database: AsyncIOMotorDatabase,
        *,
        context: AgentContextPack,
        user_message: str,
    ) -> AsyncIterator[StreamEvent | AgentResponse]:
        yield StreamEvent(
            type="agent.step.started",
            label="Preparing response",
            run_id=context.run_id,
        )

        if context.intent == "profile_update":
            text, blocks = _profile_update_guidance(context)
        elif context.intent == "catalog_search":
            text, blocks = await _catalog_search_response(context, user_message)
        elif context.intent == "unknown_or_unsupported":
            text, blocks = _unsupported_guidance(context)
        else:
            text, blocks = await _general_academic_response(context, user_message)

        used_sources = list(context.provenance)
        for block in blocks:
            if block.type != "SourceSummaryBlock":
                continue
            for item in block.data.get("provenance") or []:
                if item not in used_sources:
                    used_sources.append(item)

        yield StreamEvent(
            type="agent.step.completed",
            label="Preparing response",
            run_id=context.run_id,
        )

        for block in blocks:
            yield StreamEvent(type="structured_output", block=block, run_id=context.run_id)

        yield compose_response(
            conversation_id=context.conversation_id,
            message_id="",
            run_id=context.run_id,
            text=text,
            blocks=blocks,
            warnings=list(context.validation.warnings),
            suggested_prompts=_suggested_prompts(context),
            assumptions=list(context.assumptions),
            used_sources=used_sources,
        )


def _profile_update_guidance(context: AgentContextPack) -> tuple[str, list[StructuredBlock]]:
    text = (
        "Profile changes must be confirmed before they become official. "
        "Open your student profile to update degree program, track, catalog year, "
        "or semester preferences. I can explain what each field affects, but I cannot "
        "silently change your profile from chat."
    )
    blocks = [
        StructuredBlock(
            type="WarningBlock",
            data={"message": "Profile updates require explicit confirmation in the profile UI."},
        ),
        StructuredBlock(
            type="SourceSummaryBlock",
            data={"provenance": context.provenance},
        ),
    ]
    return text, blocks


def _unsupported_guidance(context: AgentContextPack) -> tuple[str, list[StructuredBlock]]:
    text = (
        "I could not classify that request yet. "
        "Try asking about graduation progress, a specific course, semester planning, "
        "or uploading a transcript."
    )
    return text, [
        StructuredBlock(
            type="WarningBlock",
            data={"message": "Intent not recognized with sufficient confidence."},
        )
    ]


async def _catalog_search_response(
    context: AgentContextPack,
    user_message: str,
) -> tuple[str, list[StructuredBlock]]:
    wiki_summary = build_wiki_explanation_context(context.retrieved_wiki_context)
    if wiki_summary:
        baseline = f"Catalog search results for your query:\n{wiki_summary[:1800]}"
    else:
        baseline = "I could not find matching catalog pages for that search."
    llm_text = await _grounded_llm_answer(context, user_message, baseline)
    return build_general_academic_response(context=context, user_message=user_message, llm_text=llm_text)


async def _general_academic_response(
    context: AgentContextPack,
    user_message: str,
) -> tuple[str, list[StructuredBlock]]:
    from app.services.academic_lookup_service import try_compose_deterministic_answer

    deterministic = try_compose_deterministic_answer(user_message, entities=context.entities)
    if deterministic:
        text, sources = deterministic
        provenance = list(context.provenance)
        for source in sources:
            label = f"Loaded catalog wiki page [{source}]"
            if label not in provenance:
                provenance.append(label)
        blocks = [
            StructuredBlock(
                type="SourceSummaryBlock",
                data={
                    "provenance": provenance,
                    "wikiSections": [{"title": source, "section": "deterministic_lookup"} for source in sources],
                },
            )
        ]
        return text, blocks

    wiki_summary = build_wiki_explanation_context(context.retrieved_wiki_context)
    regulation_context = (context.academic_context or {}).get("regulationSynthesisContext")
    baseline_parts = [
        f"Intent: {context.intent.replace('_', ' ')}.",
    ]
    profile = context.user_context.get("profile") or {}
    if profile.get("degreeProgram"):
        baseline_parts.append(f"Student program: {profile.get('degreeProgram')}.")
    if regulation_context:
        baseline_parts.append(str(regulation_context))
    if wiki_summary:
        baseline_parts.append(f"Retrieved catalog notes:\n{wiki_summary[:1600]}")
    baseline = "\n".join(baseline_parts)
    llm_text = await _grounded_llm_answer(context, user_message, baseline)
    return build_general_academic_response(context=context, user_message=user_message, llm_text=llm_text)


async def _grounded_llm_answer(
    context: AgentContextPack,
    user_message: str,
    baseline: str,
    *,
    reasoning_block: ReasoningBlock | None = None,
) -> str:
    """Grounded free-text answer for general/catalog questions.

    Phase 2: runs through the shared `ReasoningBlock` runtime (reusing the
    `response_composer_v1` contract — same "rewrite text only, ground in
    supplied context" task) instead of calling the chat model directly.

    Note (pre-existing behavior, unchanged): unlike the other LLM features,
    this path is not gated by any `AGENT_LLM_*_ENABLED` flag — it always
    attempts reasoning and relies on `ReasoningBlock`/`ChatLLMAdapter` (the
    single source of truth for LLM availability) to fail safely back to
    `baseline` when no LLM is configured. That inconsistency (no dedicated
    flag) predates this migration; flagged here as a Phase 3+ follow-up
    rather than changed now, since Phase 2 is a behavior-preserving migration.
    """
    wiki_summary = build_wiki_explanation_context(context.retrieved_wiki_context)
    profile = context.user_context.get("profile") or {}
    block = reasoning_block or ReasoningBlock(llm_adapter=ChatLLMAdapter())
    reasoning_input = ReasoningBlockInput(
        block_id=f"general_academic_answer-{uuid.uuid4().hex[:10]}",
        agent_name="response_composer",
        objective="Answer the student's general/catalog academic question using only the supplied context.",
        task_context={
            "workflow_intent": context.intent,
            "baseline_answer": baseline[:2000],
            "profile_summary": {
                "degreeProgram": profile.get("degreeProgram"),
                "track": profile.get("track"),
                "catalogYear": profile.get("catalogYear"),
                "currentSemesterCode": profile.get("currentSemesterCode"),
            },
            "warnings": context.validation.warnings[:6],
            "assumptions": context.assumptions[:8],
            "used_sources": context.provenance[:8],
            "validation_status": context.validation.status,
            "wiki_context": (wiki_summary or baseline).strip()[:2400] or None,
            "style_guidance": explanation_style_guide(context.intent),
            "language_instruction": language_instruction(user_message),
        },
        constraints=["Answer using only the provided context; do not invent academic facts."],
        success_criteria=["Directly answer the student's question in their own language."],
        output_schema_name="response_composer_output_v1",
        output_schema=RESPONSE_COMPOSER_OUTPUT_SCHEMA,
        prompt_contract_name=RESPONSE_COMPOSER_V1,
        risk_level="low",
    )

    output = await block.run(reasoning_input)
    if output.status != "completed" or not output.schema_valid or output.result is None:
        return baseline[:2000]

    text = str(output.result.get("text") or "").strip()
    return text or baseline[:2000]


def _suggested_prompts(context: AgentContextPack) -> list[str]:
    if context.intent == "profile_update":
        return ["What am I missing to graduate?", "Build a semester plan for next semester"]
    return [
        "What am I missing to graduate?",
        "Can I take 234218 next semester?",
        "Explain my missing electives",
    ]
