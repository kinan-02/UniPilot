"""Internal /advise route -- the live entry point into `agent_core`.

Protected by the existing internal-service-token dependency (the same one
`services/api`'s `ai_advisor_client.py` already sends
`X-Internal-Service-Token` for), not a user JWT -- `services/api` is the
only intended caller, already authenticated the end user itself.

The response shape matches EXACTLY what `services/api`'s
`advisor_service.py::ask_advisor_for_user` already parses (`response.answer`/
`confidence`/`course_ids`/`wiki_slugs`/`sources`/`contacts`/`eligibility`,
`semester_resolution`, `retrieval_agent.status`) -- that mapping logic and
the frontend's `AdvisorReply` type are unchanged by this route (§11).

V2: the request runs through the single thinking-ON agent loop
(`app.agent_core.loop.run_agent_loop`). `course_ids`/`sources` stay derived in
code from the loop's tool audit trail, never model-authored.
"""

from __future__ import annotations

import asyncio
import json
from typing import Any

from fastapi import APIRouter, Depends
from fastapi.responses import StreamingResponse

from app.agent_core.loop import AgentLoopResult, run_agent_loop
from app.agent_core.certainty import ToolInvocationRecord
from app.agent_core.tools.default_registry import build_default_tool_registry
from app.config import get_settings
from app.core.responses import success_response
from app.dependencies.internal_auth import require_internal_service_token
from app.schemas.advise import AdviseRequest

router = APIRouter(dependencies=[Depends(require_internal_service_token)])

_TIMEOUT_MESSAGE = "This question is taking longer than expected to analyze -- please try again or ask something more specific."

# Outcome -> the frontend's retrieval_agent.status vocabulary (kept from V1).
# A declined (out-of-scope) question IS a completed, valid response -- the system
# answered by politely declining -- so it maps to "succeeded", not an error state.
_STATUS_BY_OUTCOME = {
    "answered": "succeeded",
    "clarified": "blocked_needs_clarification",
    "declined": "succeeded",
    "budget_exhausted": "incomplete",
}

_WIKI_SOURCE_ENTITY_TYPES = frozenset({"wiki_page", "track", "program", "minor", "faculty"})


def _confidence_band(result: AgentLoopResult) -> str:
    """A low/medium/high band from the answer's grounding. A non-answer is always
    low; an answer is banded by its weakest grounded fact, so a predicted-pattern
    or interpreted fact honestly pulls the band down from a pure official record."""
    if result.outcome != "answered":
        return "low"
    confidences = [fact.confidence for fact in result.facts.values()]
    lowest = min(confidences) if confidences else 0.8
    if lowest >= 0.9:
        return "high"
    if lowest >= 0.6:
        return "medium"
    return "low"


def _derive_course_ids(audit: list[ToolInvocationRecord]) -> list[str]:
    """Grounded in real tool calls, never LLM-invented: every successful
    `get_entity(entity_type="course", ...)` in the loop's audit, deduplicated."""
    course_ids: set[str] = set()
    for record in audit:
        if (
            record.tool_name == "get_entity"
            and record.output_ok
            and record.arguments.get("entity_type") == "course"
        ):
            entity_id = record.arguments.get("entity_id")
            if entity_id:
                course_ids.add(str(entity_id))
    return sorted(course_ids)


def _derive_sources(audit: list[ToolInvocationRecord]) -> list[str]:
    """Grounded in real tool calls: successful wiki/track/etc. fetches, plus the
    query term of each successful search (a provenance hint -- the audit records
    arguments + status, not the result payload)."""
    sources: set[str] = set()
    for record in audit:
        if record.tool_name == "get_entity" and record.output_ok:
            if record.arguments.get("entity_type") in _WIKI_SOURCE_ENTITY_TYPES:
                entity_id = record.arguments.get("entity_id")
                if entity_id:
                    sources.add(str(entity_id))
        elif record.tool_name == "search_knowledge" and record.output_ok:
            query = record.arguments.get("query") or record.arguments.get("search_query")
            if query:
                sources.add(f"search: {query}")
    return sorted(sources)


def _response_payload(
    *,
    answer: str,
    confidence: str,
    course_ids: list[str],
    retrieval_status: str,
    sources: list[str] | None = None,
) -> dict[str, Any]:
    return {
        "response": {
            "answer": answer,
            "confidence": confidence,
            "course_ids": course_ids,
            # No primitive/entity type grounds these yet -- left honestly empty
            # rather than faked (don't fabricate what the system can't ground).
            "wiki_slugs": [],
            "sources": sources or [],
            "contacts": [],
            "eligibility": None,
        },
        "semester_resolution": None,
        "retrieval_agent": {"status": retrieval_status},
    }


def _build_advise_response(question: str, result: AgentLoopResult) -> dict[str, Any]:
    return {
        "question": question,
        **_response_payload(
            answer=result.answer,
            confidence=_confidence_band(result),
            course_ids=_derive_course_ids(result.audit),
            retrieval_status=_STATUS_BY_OUTCOME.get(result.outcome, "incomplete"),
            sources=_derive_sources(result.audit),
        ),
    }


def _timeout_response(question: str) -> dict[str, Any]:
    return {
        "question": question,
        **_response_payload(
            answer=_TIMEOUT_MESSAGE, confidence="low", course_ids=[], retrieval_status="timeout"
        ),
    }


@router.post("/advise")
async def advise_route(payload: AdviseRequest) -> dict[str, Any]:
    settings = get_settings()
    try:
        result = await asyncio.wait_for(
            run_agent_loop(
                question=payload.question,
                user_id=payload.user_id,
                registry=build_default_tool_registry(),
            ),
            timeout=settings.agent_turn_timeout_seconds,
        )
    except asyncio.TimeoutError:
        # Only a hung provider should reach here. The loop's own wall-clock budget
        # (§7) concludes below this ceiling and degrades into a grounded partial
        # answer, which is strictly better than the canned string below -- see the
        # ordering invariant on `agent_turn_timeout_seconds` in config.py, which
        # this comment previously asserted while the opposite was true.
        return success_response(_timeout_response(payload.question))
    return success_response(_build_advise_response(payload.question, result))


def _to_frontend_advisor_shape(raw: dict[str, Any]) -> dict[str, Any]:
    """Transform the internal AI response shape into the `advisor` shape the
    frontend's SSE handler (`data.data.advisor`) expects -- the same mapping
    `services/api`'s `advisor_service.py` applies on the non-streaming path."""
    response = raw.get("response") if isinstance(raw.get("response"), dict) else {}
    return {
        "advisor": {
            "question": raw.get("question", ""),
            "answer": response.get("answer", ""),
            "confidence": response.get("confidence", "medium"),
            "courseIds": response.get("course_ids", []),
            "wikiSlugs": response.get("wiki_slugs", []),
            "sources": response.get("sources", []),
            "contacts": response.get("contacts", []),
            "eligibility": response.get("eligibility"),
            "semesterResolution": raw.get("semester_resolution"),
            "retrievalStatus": (raw.get("retrieval_agent") or {}).get("status"),
        },
    }


@router.post("/advise/stream")
async def advise_stream_route(payload: AdviseRequest) -> StreamingResponse:
    """Typed-event SSE (§11). The V2 answer is composed deterministically after
    the loop concludes (not token-by-token from the model), so the stream emits
    the finished answer as one `chunk` then a `final` event -- no fragile
    text-backfill reconciliation, which the untyped V1 queue needed."""
    settings = get_settings()

    async def _event_generator():
        try:
            result = await asyncio.wait_for(
                run_agent_loop(
                    question=payload.question,
                    user_id=payload.user_id,
                    registry=build_default_tool_registry(),
                ),
                timeout=settings.agent_turn_timeout_seconds,
            )
            final_payload = _build_advise_response(payload.question, result)
        except asyncio.TimeoutError:
            final_payload = _timeout_response(payload.question)
        except Exception as exc:  # noqa: BLE001 -- surface as a typed error event, never a 500 mid-stream
            yield f"data: {json.dumps({'type': 'error', 'error': str(exc)})}\n\n"
            return

        answer = (final_payload.get("response") or {}).get("answer", "")
        if answer:
            yield f"data: {json.dumps({'type': 'chunk', 'text': answer})}\n\n"
        yield f"data: {json.dumps({'type': 'final', 'data': _to_frontend_advisor_shape(final_payload)})}\n\n"

    return StreamingResponse(_event_generator(), media_type="text/event-stream")


__all__ = ["router"]
