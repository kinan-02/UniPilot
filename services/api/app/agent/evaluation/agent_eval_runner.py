"""Execute one agent benchmark case and collect turn output."""

from __future__ import annotations

import time
from typing import Any

from motor.motor_asyncio import AsyncIOMotorDatabase

from app.agent.evaluation.agent_eval_scorer import AgentTurnResult, ScoreOutcome, score_agent_turn
from app.agent.evaluation.agent_setup import SetupResult, setup_eval_user
from app.agent.orchestrator import run_agent_turn
from app.agent.schemas import StreamEvent
from app.repositories.agent_message_repository import (
    create_agent_message,
    list_messages_for_conversation,
)
from app.repositories.agent_conversation_repository import update_conversation_preview


async def _collect_agent_turn(
    database: AsyncIOMotorDatabase,
    *,
    user_id: str,
    conversation_id: str,
    message: str,
) -> AgentTurnResult:
    started = time.perf_counter()
    events: list[dict[str, Any]] = []
    final_text = ""
    run_failed = False
    run_error: str | None = None

    user_message = await create_agent_message(
        database,
        conversation_id=conversation_id,
        user_id=user_id,
        role="user",
        content=message.strip(),
    )
    await update_conversation_preview(
        database,
        conversation_id=conversation_id,
        user_id=user_id,
        preview=message.strip(),
    )

    async for event in run_agent_turn(
        database,
        user_id=user_id,
        conversation_id=conversation_id,
        user_message=message.strip(),
        trigger_message_id=str(user_message["id"]),
    ):
        payload = _event_to_dict(event)
        events.append(payload)
        if payload.get("type") == "message.completed":
            final_text = str(payload.get("text") or final_text)
        if payload.get("type") == "run.failed":
            run_failed = True
            run_error = str(payload.get("error") or "Agent run failed")

    latency_ms = (time.perf_counter() - started) * 1000.0
    events = _append_persisted_blocks(
        events,
        await list_messages_for_conversation(
            database,
            conversation_id=conversation_id,
            user_id=user_id,
        ),
    )
    return AgentTurnResult(
        text=final_text,
        events=events,
        run_failed=run_failed,
        run_error=run_error,
        latency_ms=latency_ms,
    )


def _event_to_dict(event: StreamEvent | dict[str, Any]) -> dict[str, Any]:
    if isinstance(event, StreamEvent):
        return event.to_sse_payload()
    return dict(event)


def _append_persisted_blocks(
    events: list[dict[str, Any]],
    messages: list[dict[str, Any]],
) -> list[dict[str, Any]]:
    """Clarification turns persist blocks without streaming structured_output events."""
    existing_types = {
        (event.get("block") or {}).get("type")
        for event in events
        if event.get("type") == "structured_output"
    }
    augmented = list(events)
    for message in reversed(messages):
        if message.get("role") != "assistant":
            continue
        for block in message.get("structuredBlocks") or []:
            block_type = block.get("type")
            if block_type in existing_types:
                continue
            augmented.append({"type": "structured_output", "block": block})
            if block_type:
                existing_types.add(block_type)
        break
    return augmented


async def run_agent_benchmark_case(
    database: AsyncIOMotorDatabase,
    case: dict[str, Any],
) -> dict[str, Any]:
    """Run setup, agent turn, and scoring for one benchmark case."""
    case_id = str(case.get("id") or "unknown")
    message = str(case.get("message") or "").strip()
    setup = dict(case.get("setup") or {})
    expect = dict(case.get("expect") or {})

    if not message:
        return {
            "id": case_id,
            "category": case.get("category"),
            "status": "skip",
            "reason": "empty message",
        }

    setup_result: SetupResult = await setup_eval_user(
        database,
        case_id=case_id,
        setup=setup,
    )
    if not setup_result.ok or setup_result.context is None:
        return {
            "id": case_id,
            "category": case.get("category"),
            "status": "skip",
            "reason": setup_result.skip_reason or "setup failed",
        }

    context = setup_result.context
    try:
        turn = await _collect_agent_turn(
            database,
            user_id=context.user_id,
            conversation_id=context.conversation_id,
            message=message,
        )
    except Exception as exc:  # noqa: BLE001
        return {
            "id": case_id,
            "category": case.get("category"),
            "status": "fail",
            "reason": f"exception: {exc}",
            "message": message,
        }

    score: ScoreOutcome = score_agent_turn(message=message, result=turn, expect=expect)
    status = "pass" if score.passed else "fail"

    return {
        "id": case_id,
        "category": case.get("category"),
        "status": status,
        "message": message,
        "textPreview": turn.text[:240],
        "failures": score.failures,
        "warnings": score.warnings,
        "observed": score.observed,
        "latencyMs": round(turn.latency_ms, 1),
    }
