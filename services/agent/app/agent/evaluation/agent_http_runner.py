"""Execute agent benchmark cases through HTTP API routes."""

from __future__ import annotations

import time
from typing import Any

import httpx

from app.agent.evaluation.agent_eval_scorer import AgentTurnResult, score_agent_turn
from app.agent.evaluation.agent_http_setup import (
    DEFAULT_TIMEOUT_SEC,
    _auth_headers,
    _request_with_retry,
    setup_http_eval_user,
)


def _append_persisted_blocks(
    events: list[dict[str, Any]],
    messages: list[dict[str, Any]],
) -> list[dict[str, Any]]:
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


async def _send_agent_message(
    client: httpx.AsyncClient,
    *,
    base_url: str,
    access_token: str,
    conversation_id: str,
    message: str,
) -> tuple[AgentTurnResult, str | None]:
    started = time.perf_counter()
    headers = _auth_headers(access_token)

    response = await _request_with_retry(
        client,
        "POST",
        f"{base_url}/agent/conversations/{conversation_id}/messages",
        headers=headers,
        json={"content": message.strip()},
    )
    latency_ms = (time.perf_counter() - started) * 1000.0

    if response.status_code != 200:
        return (
            AgentTurnResult(
                run_failed=True,
                run_error=f"HTTP {response.status_code}: {response.text[:200]}",
                latency_ms=latency_ms,
            ),
            f"message request failed: HTTP {response.status_code}",
        )

    envelope = response.json()
    if not envelope.get("success"):
        error = str(envelope.get("error") or "API returned success=false")
        return (
            AgentTurnResult(run_failed=True, run_error=error, latency_ms=latency_ms),
            error,
        )

    data = envelope.get("data") or {}
    events = list(data.get("events") or [])
    final_text = str(data.get("text") or "")
    run_failed = any(event.get("type") == "run.failed" for event in events)
    run_error = None
    if run_failed:
        failed = next(event for event in events if event.get("type") == "run.failed")
        run_error = str(failed.get("error") or "run.failed")

    detail_response = await _request_with_retry(
        client,
        "GET",
        f"{base_url}/agent/conversations/{conversation_id}",
        headers=headers,
    )
    if detail_response.status_code == 200:
        messages = detail_response.json()["data"].get("messages") or []
        events = _append_persisted_blocks(events, messages)

    return (
        AgentTurnResult(
            text=final_text,
            events=events,
            run_failed=run_failed,
            run_error=run_error,
            latency_ms=latency_ms,
        ),
        None,
    )


async def run_agent_http_benchmark_case(
    client: httpx.AsyncClient,
    *,
    base_url: str,
    case: dict[str, Any],
) -> dict[str, Any]:
    """Run one benchmark case end-to-end via HTTP."""
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

    setup_result = await setup_http_eval_user(
        client,
        base_url=base_url,
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
    turn, transport_error = await _send_agent_message(
        client,
        base_url=base_url,
        access_token=context.access_token,
        conversation_id=context.conversation_id,
        message=message,
    )
    if transport_error and turn.run_failed:
        return {
            "id": case_id,
            "category": case.get("category"),
            "status": "fail",
            "reason": transport_error,
            "message": message,
            "httpStatus": "error",
        }

    score = score_agent_turn(message=message, result=turn, expect=expect)
    return {
        "id": case_id,
        "category": case.get("category"),
        "status": "pass" if score.passed else "fail",
        "message": message,
        "textPreview": turn.text[:240],
        "failures": score.failures,
        "warnings": score.warnings,
        "observed": score.observed,
        "latencyMs": round(turn.latency_ms, 1),
        "transport": "http",
        "conversationId": context.conversation_id,
    }


def build_http_client(*, timeout_sec: float = DEFAULT_TIMEOUT_SEC) -> httpx.AsyncClient:
    return httpx.AsyncClient(timeout=httpx.Timeout(timeout_sec))
