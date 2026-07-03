"""Central agent controller (spec §7)."""

from __future__ import annotations

from collections.abc import AsyncIterator
from typing import Any

from motor.motor_asyncio import AsyncIOMotorDatabase

from app.agent.context_builder import build_agent_context_pack
from app.agent.conversation_memory import load_conversation_memory
from app.agent.entity_resolver import resolve_entities
from app.agent.llm_intent_classifier import classify_intent_with_llm_fallback
from app.agent.llm_response_composer import enhance_response_with_llm
from app.agent.response_composer import compose_response
from app.agent.schemas import AgentContextPack, AgentResponse, StreamEvent, StructuredBlock
from app.agent.task_planner import build_task_plan
from app.agent.workflows.registry import get_workflow
from app.config import Settings, get_settings
from app.repositories.agent_conversation_repository import (
    append_conversation_assumptions,
    append_conversation_entities,
    find_conversation_by_id_and_user,
)
from app.repositories.agent_message_repository import create_agent_message
from app.repositories.agent_run_repository import (
    complete_agent_run,
    create_agent_run,
    create_agent_step,
    fail_agent_run,
    update_agent_step,
)
from app.repositories.agent_tool_call_repository import (
    complete_agent_tool_call,
    create_agent_tool_call,
)


async def run_agent_turn(
    database: AsyncIOMotorDatabase,
    *,
    user_id: str,
    conversation_id: str,
    user_message: str,
    trigger_message_id: str,
    message_attachments: list[dict[str, Any]] | None = None,
    settings: Settings | None = None,
) -> AsyncIterator[StreamEvent]:
    """Execute one agent turn and yield streaming events."""
    cfg = settings or get_settings()
    conversation = await find_conversation_by_id_and_user(database, conversation_id, user_id)
    if conversation is None:
        yield StreamEvent(type="run.failed", error="Conversation not found")
        return

    run = await create_agent_run(
        database,
        user_id=user_id,
        conversation_id=conversation_id,
        trigger_message_id=trigger_message_id,
        intent="unknown_or_unsupported",
        settings=cfg,
    )
    run_id = str(run["id"])
    tool_call_count = 0
    workflow_step_count = 0

    try:
        classification = await classify_intent_with_llm_fallback(user_message, settings=cfg)
        await complete_agent_run(
            database,
            run_id=run_id,
            user_id=user_id,
            status="running",
            intent=classification.intent,
            settings=cfg,
        )

        entities = resolve_entities(
            user_message,
            conversation_entities=conversation.get("entities") or {},
        )
        if entities:
            await append_conversation_entities(
                database,
                conversation_id=conversation_id,
                user_id=user_id,
                entities=entities,
                settings=cfg,
            )

        memory = await load_conversation_memory(
            database,
            conversation_id=conversation_id,
            user_id=user_id,
            stored_assumptions=conversation.get("assumptions") or [],
            entities=entities,
        )
        if memory.get("assumptions"):
            await append_conversation_assumptions(
                database,
                conversation_id=conversation_id,
                user_id=user_id,
                assumptions=list(memory["assumptions"]),
                settings=cfg,
            )

        task_plan = build_task_plan(classification)

        for label in ("Understanding your request", "Planning next steps"):
            if workflow_step_count >= cfg.agent_max_workflow_steps:
                break
            workflow_step_count += 1
            step = await create_agent_step(database, run_id=run_id, label=label, settings=cfg)
            yield StreamEvent(type="agent.step.started", label=label, run_id=run_id)
            await update_agent_step(
                database,
                step_id=str(step["id"]),
                status="completed",
                summary=f"intent={classification.intent}; workflow={task_plan.workflow}",
                settings=cfg,
            )
            yield StreamEvent(type="agent.step.completed", label=label, run_id=run_id)

        retrieval_label = "Gathering academic context"
        if workflow_step_count < cfg.agent_max_workflow_steps:
            workflow_step_count += 1
            retrieval_step = await create_agent_step(
                database,
                run_id=run_id,
                label=retrieval_label,
                settings=cfg,
            )
            yield StreamEvent(type="agent.step.started", label=retrieval_label, run_id=run_id)

            tool_call = await _record_tool_call(
                database,
                run_id=run_id,
                user_id=user_id,
                conversation_id=conversation_id,
                tool_name="context_builder",
                input_summary=f"intent={classification.intent}",
                settings=cfg,
            )
            tool_call_count += 1
            if tool_call is not None:
                yield StreamEvent(type="tool.started", label="context_builder", run_id=run_id)

            context = await build_agent_context_pack(
                database,
                conversation_id=conversation_id,
                run_id=run_id,
                user_id=user_id,
                intent=classification.intent,
                entities=entities,
                classification=classification,
                task_plan=task_plan,
                user_message=user_message,
                message_attachments=message_attachments,
                assumptions=list(memory.get("assumptions") or []),
                settings=cfg,
            )

            if tool_call is not None:
                await complete_agent_tool_call(
                    database,
                    tool_call_id=tool_call["id"],
                    output_summary=(
                        f"validation={context.validation.status}; "
                        f"wikiSnippets={len(context.retrieved_wiki_context)}"
                    ),
                    settings=cfg,
                )
                yield StreamEvent(type="tool.completed", label="context_builder", run_id=run_id)

            await update_agent_step(
                database,
                step_id=str(retrieval_step["id"]),
                status="completed",
                summary=(
                    f"validation={context.validation.status}; "
                    f"profile={context.retrieval_profile or 'none'}; "
                    f"wikiSnippets={len(context.retrieved_wiki_context)}; "
                    f"provenance={len(context.provenance)}"
                ),
                settings=cfg,
            )
            yield StreamEvent(type="agent.step.completed", label=retrieval_label, run_id=run_id)
        else:
            context = AgentContextPack(
                conversation_id=conversation_id,
                run_id=run_id,
                user_id=user_id,
                intent=classification.intent,
                entities=entities,
                assumptions=list(memory.get("assumptions") or []),
            )

        if tool_call_count >= cfg.agent_max_tool_calls_per_run:
            yield StreamEvent(
                type="agent.step.failed",
                label="Tool budget exceeded",
                run_id=run_id,
                error="Maximum tool calls reached for this run.",
            )

        if context.validation.errors and context.validation.status == "partial":
            clarification = _clarification_response(context)
            if clarification is not None:
                final_response = await _finalize_response(
                    clarification,
                    context=context,
                    user_message=user_message,
                    cfg=cfg,
                )
                message_id = await _persist_assistant_message(
                    database,
                    conversation_id=conversation_id,
                    user_id=user_id,
                    response=final_response,
                    run_id=run_id,
                    settings=cfg,
                )
                final_response = final_response.model_copy(update={"message_id": message_id})
                async for event in _emit_final_response_events(final_response, run_id=run_id):
                    yield event
                await complete_agent_run(
                    database,
                    run_id=run_id,
                    user_id=user_id,
                    status="completed",
                    intent=classification.intent,
                    retrieval_profile=context.retrieval_profile,
                    retrieval_metadata=context.retrieval_metadata,
                    settings=cfg,
                )
                yield StreamEvent(type="run.completed", run_id=run_id, message_id=message_id)
                return

        workflow = get_workflow(task_plan.workflow)
        final_response: AgentResponse | None = None

        async for item in workflow.run(database, context=context, user_message=user_message):
            if isinstance(item, AgentResponse):
                final_response = item
                continue
            if item.type in {"agent.step.started", "agent.step.completed", "agent.step.failed"}:
                workflow_step_count += 1
                if workflow_step_count > cfg.agent_max_workflow_steps:
                    yield StreamEvent(
                        type="agent.step.failed",
                        label=item.label,
                        run_id=run_id,
                        error="Maximum workflow steps reached.",
                    )
                    break
            yield item

        if final_response is None:
            final_response = compose_response(
                conversation_id=conversation_id,
                message_id="",
                run_id=run_id,
                text="I could not produce a response for this request.",
                warnings=["Workflow returned no response."],
            )

        final_response = await _finalize_response(
            final_response,
            context=context,
            user_message=user_message,
            cfg=cfg,
        )

        message_id = await _persist_assistant_message(
            database,
            conversation_id=conversation_id,
            user_id=user_id,
            response=final_response,
            run_id=run_id,
            settings=cfg,
        )
        final_response = final_response.model_copy(update={"message_id": message_id})

        async for event in _emit_final_response_events(final_response, run_id=run_id):
            yield event

        run_status = "completed"
        if final_response.proposed_actions:
            run_status = "requires_user_confirmation"

        await complete_agent_run(
            database,
            run_id=run_id,
            user_id=user_id,
            status=run_status,
            intent=classification.intent,
            retrieval_profile=context.retrieval_profile,
            retrieval_metadata=context.retrieval_metadata,
            settings=cfg,
        )
        yield StreamEvent(type="run.completed", run_id=run_id, message_id=message_id)

    except Exception as exc:  # noqa: BLE001
        await fail_agent_run(
            database,
            run_id=run_id,
            user_id=user_id,
            error=str(exc),
            settings=cfg,
        )
        yield StreamEvent(type="run.failed", run_id=run_id, error=str(exc))


async def _finalize_response(
    response: AgentResponse,
    *,
    context: AgentContextPack,
    user_message: str,
    cfg: Settings,
) -> AgentResponse:
    deltas: list[str] = []

    async def on_delta(token: str) -> None:
        deltas.append(token)

    enhanced = await enhance_response_with_llm(
        response,
        context=context,
        user_message=user_message,
        settings=cfg,
        on_delta=on_delta,
    )
    return enhanced


async def _emit_final_response_events(
    response: AgentResponse,
    *,
    run_id: str,
) -> AsyncIterator[StreamEvent]:
    if response.text and len(response.text) > 120:
        chunk_size = 48
        for index in range(0, len(response.text), chunk_size):
            yield StreamEvent(
                type="message.delta",
                text=response.text[index : index + chunk_size],
                run_id=run_id,
            )
    for block in response.blocks:
        yield StreamEvent(type="structured_output", block=block, run_id=run_id)
    for action in response.proposed_actions:
        yield StreamEvent(type="action.proposed", action=action, run_id=run_id)
    yield StreamEvent(
        type="message.completed",
        text=response.text,
        message_id=response.message_id,
        run_id=run_id,
    )


async def _persist_assistant_message(
    database: AsyncIOMotorDatabase,
    *,
    conversation_id: str,
    user_id: str,
    response: AgentResponse,
    run_id: str,
    settings: Settings,
) -> str:
    assistant_message = await create_agent_message(
        database,
        conversation_id=conversation_id,
        user_id=user_id,
        role="assistant",
        content=response.text,
        structured_blocks=[block.model_dump() for block in response.blocks],
        run_id=run_id,
        warnings=response.warnings,
        suggested_prompts=response.suggested_prompts,
        proposed_actions=[action.model_dump() for action in response.proposed_actions],
        assumptions=response.assumptions,
        used_sources=response.used_sources,
        settings=settings,
    )
    return str(assistant_message["id"])


async def _record_tool_call(
    database: AsyncIOMotorDatabase,
    *,
    run_id: str,
    user_id: str,
    conversation_id: str,
    tool_name: str,
    input_summary: str | None,
    settings: Settings,
) -> dict[str, Any] | None:
    try:
        return await create_agent_tool_call(
            database,
            run_id=run_id,
            user_id=user_id,
            conversation_id=conversation_id,
            tool_name=tool_name,
            input_summary=input_summary,
            settings=settings,
        )
    except Exception:
        return None


def _clarification_response(context: AgentContextPack) -> AgentResponse | None:
    blocking = [error for error in context.validation.errors if error]
    if not blocking:
        return None

    if any("profile" in error.lower() for error in blocking):
        text = (
            "I need your student profile before I can answer this accurately. "
            "Please complete your degree program, track, and catalog year on your profile."
        )
    elif any("course number" in error.lower() for error in blocking):
        text = "Which course number are you asking about? Please provide the Technion course number."
    elif any("transcript" in error.lower() or "upload" in error.lower() for error in blocking):
        text = (
            "Please upload your official transcript PDF with your message. "
            "I will parse it and show a review table before saving any courses."
        )
    elif any("semester" in error.lower() for error in blocking):
        text = (
            "Which semester should I plan for? Say 'next semester' or provide a semester code like 2025-2."
        )
    else:
        text = "I need a bit more information before I can continue: " + "; ".join(blocking)

    warning_block = StructuredBlock(
        type="WarningBlock",
        data={"messages": blocking, "validationStatus": context.validation.status},
    )
    source_block = StructuredBlock(
        type="SourceSummaryBlock",
        data={"provenance": context.provenance, "usedSources": context.provenance[:5]},
    )
    return compose_response(
        conversation_id=context.conversation_id,
        message_id="",
        run_id=context.run_id,
        text=text,
        blocks=[warning_block, source_block],
        warnings=list(context.validation.warnings),
        assumptions=list(context.missing_data),
        used_sources=list(context.provenance),
    )
