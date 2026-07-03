"""General academic and catalog workflows with grounded LLM answers (spec §24.1)."""

from __future__ import annotations

from collections.abc import AsyncIterator

from motor.motor_asyncio import AsyncIOMotorDatabase

from app.agent.explanation_enricher import build_wiki_explanation_context
from app.agent.llm_client import agent_llm_available, build_chat_llm
from app.agent.llm_prompts import build_general_academic_human, build_general_academic_system
from app.agent.llm_response_composer import build_general_academic_response
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
            used_sources=list(context.provenance),
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
    wiki_summary = build_wiki_explanation_context(context.retrieved_wiki_context)
    profile = context.user_context.get("profile") or {}
    baseline_parts = [
        f"Intent: {context.intent.replace('_', ' ')}.",
    ]
    if profile.get("degreeProgram"):
        baseline_parts.append(f"Student program: {profile.get('degreeProgram')}.")
    if wiki_summary:
        baseline_parts.append(f"Retrieved catalog notes:\n{wiki_summary[:1600]}")
    baseline = "\n".join(baseline_parts)
    llm_text = await _grounded_llm_answer(context, user_message, baseline)
    return build_general_academic_response(context=context, user_message=user_message, llm_text=llm_text)


async def _grounded_llm_answer(
    context: AgentContextPack,
    user_message: str,
    baseline: str,
) -> str:
    if not agent_llm_available():
        return baseline[:2000]

    llm = build_chat_llm(temperature=0.1)
    if llm is None:
        return baseline[:2000]

    try:
        from langchain_core.messages import HumanMessage, SystemMessage
    except ImportError:
        return baseline[:2000]

    wiki_summary = build_wiki_explanation_context(context.retrieved_wiki_context)
    system = build_general_academic_system(intent=context.intent, user_message=user_message)
    human = build_general_academic_human(
        user_message=user_message,
        context=context,
        wiki_context=wiki_summary or baseline,
    )
    try:
        response = await llm.ainvoke(
            [SystemMessage(content=system), HumanMessage(content=human)]
        )
        text = str(getattr(response, "content", "") or "").strip()
        return text or baseline[:2000]
    except Exception:
        return baseline[:2000]


def _suggested_prompts(context: AgentContextPack) -> list[str]:
    if context.intent == "profile_update":
        return ["What am I missing to graduate?", "Build a semester plan for next semester"]
    return [
        "What am I missing to graduate?",
        "Can I take 234218 next semester?",
        "Explain my missing electives",
    ]
