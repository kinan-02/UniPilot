"""Internal /advise route -- the live entry point into `agent_core`.

Protected by the existing internal-service-token dependency (the same one
`services/api`'s `ai_advisor_client.py` already sends
`X-Internal-Service-Token` for), not a user JWT -- `services/api` is the
only intended caller, already authenticated the end user itself.

The response shape matches EXACTLY what `services/api`'s
`advisor_service.py::ask_advisor_for_user` already parses (`response.answer`/
`confidence`/`course_ids`/`wiki_slugs`/`sources`/`contacts`/`eligibility`,
`semester_resolution`, `retrieval_agent.status`) -- that mapping logic and
the frontend's `AdvisorReply` type are unchanged by this route.
"""

from __future__ import annotations

import asyncio
import json
from typing import Any
from uuid import uuid4

from fastapi import APIRouter, Depends
from fastapi.responses import StreamingResponse

from app.agent_core.orchestrator.state_index import certainty_band
from app.agent_core.planning.state import PlanExecutionState, StateEntry
from app.agent_core.reasoning.llm_adapter import ChatLLMAdapter
from app.agent_core.reasoning.reasoning_budget import BudgetedLLMAdapter
from app.agent_core.request_understanding.schemas import RequestUnderstandingReasoningBlockOutput
from app.agent_core.roles.roster import build_default_role_roster
from app.agent_core.tools.default_registry import build_default_tool_registry
from app.agent_core.turn import run_agent_turn
from app.config import get_settings
from app.core.responses import success_response
from app.dependencies.internal_auth import require_internal_service_token
from app.schemas.advise import AdviseRequest

router = APIRouter(dependencies=[Depends(require_internal_service_token)])

_FALLBACK_CLARIFICATION_MESSAGE = "I need more information to answer that -- could you clarify your question?"
_TIMEOUT_MESSAGE = "This question is taking longer than expected to analyze -- please try again or ask something more specific."


def _derive_course_ids(state: PlanExecutionState) -> list[str]:
    """Grounded in real tool calls, never LLM-invented: every successful
    `get_entity(entity_type="course", ...)` call recorded anywhere in the
    plan's accumulated state, deduplicated. The composition role's own
    output schema has no `course_ids` field (it's not something the LLM is
    asked to produce), so this is derived in code from the tool audit trail
    instead -- consistent with this codebase's fail-closed, tool-grounded
    philosophy."""
    course_ids: set[str] = set()
    for entry in state.entries:
        for record in entry.tool_audit_trail:
            if (
                record.tool_name == "get_entity"
                and record.output_ok
                and record.arguments.get("entity_type") == "course"
            ):
                entity_id = record.arguments.get("entity_id")
                if entity_id:
                    course_ids.add(str(entity_id))
    return sorted(course_ids)

def _derive_sources(state: PlanExecutionState) -> list[str]:
    """Grounded in real tool calls: every successful get_entity or search_knowledge 
    that returned wiki pages, catalog records, or tracks."""
    sources: set[str] = set()
    for entry in state.entries:
        for record in entry.tool_audit_trail:
            if record.tool_name == "get_entity" and record.output_ok:
                entity_type = record.arguments.get("entity_type")
                if entity_type in ("wiki_page", "track", "program", "minor", "faculty"):
                    entity_id = record.arguments.get("entity_id")
                    if entity_id:
                        sources.add(str(entity_id))
            elif record.tool_name == "search_knowledge" and record.output_ok:
                # ToolInvocationRecord only records arguments + status, not the
                # output payload itself — so we surface the query term as a
                # provenance hint rather than individual result slugs.
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
            # No corresponding primitive/entity type exists anywhere in
            # agent_core yet for these -- left honestly empty rather than
            # faked (docs/agent/TOOL_PRIMITIVES_OPEN_GAPS.md's own
            # discipline: don't fabricate what the system can't ground).
            "wiki_slugs": [],
            "sources": sources or [],
            "contacts": [],
            "eligibility": None,
        },
        "semester_resolution": None,
        "retrieval_agent": {"status": retrieval_status},
    }


def _build_advise_response(
    *,
    question: str,
    understanding: RequestUnderstandingReasoningBlockOutput,
    state: PlanExecutionState,
    final_entry: StateEntry | None,
    clarification_question: str | None,
) -> dict[str, Any]:
    if not understanding.in_scope:
        payload = _response_payload(
            answer=final_entry.data.get("answer_text", "") if final_entry else _FALLBACK_CLARIFICATION_MESSAGE,
            confidence=certainty_band(final_entry.certainty.confidence) if final_entry else "low",
            course_ids=[],
            retrieval_status="out_of_scope",
            sources=[],
        )
    elif final_entry is None:
        payload = _response_payload(
            answer=clarification_question or _FALLBACK_CLARIFICATION_MESSAGE,
            confidence="low",
            course_ids=[],
            retrieval_status="blocked_needs_clarification" if clarification_question else "incomplete",
            sources=_derive_sources(state),
        )
    else:
        payload = _response_payload(
            answer=final_entry.data.get("answer_text", ""),
            confidence=certainty_band(final_entry.certainty.confidence),
            course_ids=_derive_course_ids(state),
            retrieval_status=final_entry.status,
            sources=_derive_sources(state),
        )
    return {"question": question, **payload}


@router.post("/advise")
async def advise_route(payload: AdviseRequest) -> dict[str, Any]:
    plan_id = str(uuid4())
    settings = get_settings()
    llm_adapter = BudgetedLLMAdapter(
        ChatLLMAdapter(), max_calls=settings.agent_reasoning_call_budget_per_turn
    )
    try:
        understanding, state, final_entry, clarification_question = await asyncio.wait_for(
            run_agent_turn(
                original_user_message=payload.question,
                user_id=payload.user_id,
                llm_adapter=llm_adapter,
                role_roster=build_default_role_roster(),
                tool_registry=build_default_tool_registry(),
                plan_id=plan_id,
            ),
            timeout=settings.agent_turn_timeout_seconds,
        )
    except asyncio.TimeoutError:
        # A manual end-to-end smoke test found a real turn hang with no
        # ceiling at all (ReasoningBlock's own complete_json calls never pass
        # a timeout) -- this bounds the worst case so a slow/hung LLM call
        # can never block a worker indefinitely; the student gets an honest
        # "try again" answer instead of the request hanging forever.
        return success_response(
            {
                "question": payload.question,
                **_response_payload(
                    answer=_TIMEOUT_MESSAGE,
                    confidence="low",
                    course_ids=[],
                    retrieval_status="timeout",
                ),
            }
        )
    return success_response(
        _build_advise_response(
            question=payload.question,
            understanding=understanding,
            state=state,
            final_entry=final_entry,
            clarification_question=clarification_question,
        )
    )

def _to_frontend_advisor_shape(raw: dict[str, Any]) -> dict[str, Any]:
    """Transform the internal AI response shape into the `advisor` shape that
    the frontend's SSE handler (`data.data.advisor`) expects.

    The non-streaming path runs through `services/api`'s `advisor_service.py`
    which does this same mapping -- the streaming path bypasses that service,
    so we apply the equivalent transform here."""
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
    plan_id = str(uuid4())
    settings = get_settings()
    llm_adapter = BudgetedLLMAdapter(
        ChatLLMAdapter(), max_calls=settings.agent_reasoning_call_budget_per_turn
    )
    streaming_queue: asyncio.Queue[str | None] = asyncio.Queue()

    async def _run_agent_and_close_queue():
        try:
            understanding, state, final_entry, clarification_question = await asyncio.wait_for(
                run_agent_turn(
                    original_user_message=payload.question,
                    user_id=payload.user_id,
                    llm_adapter=llm_adapter,
                    role_roster=build_default_role_roster(),
                    tool_registry=build_default_tool_registry(),
                    plan_id=plan_id,
                    streaming_queue=streaming_queue,
                ),
                timeout=settings.agent_turn_timeout_seconds,
            )
            final_payload = _build_advise_response(
                question=payload.question,
                understanding=understanding,
                state=state,
                final_entry=final_entry,
                clarification_question=clarification_question,
            )
            # Signal completion and push the final payload
            await streaming_queue.put(json.dumps({"type": "final", "data": _to_frontend_advisor_shape(final_payload)}))
        except asyncio.TimeoutError:
            final_payload = {
                "question": payload.question,
                **_response_payload(
                    answer=_TIMEOUT_MESSAGE,
                    confidence="low",
                    course_ids=[],
                    retrieval_status="timeout",
                    sources=[],
                ),
            }
            await streaming_queue.put(json.dumps({"type": "final", "data": _to_frontend_advisor_shape(final_payload)}))
        except Exception as e:
            await streaming_queue.put(json.dumps({"type": "error", "error": str(e)}))
        finally:
            await streaming_queue.put(None)  # EOF

    async def _event_generator():
        task = asyncio.create_task(_run_agent_and_close_queue())
        streamed_text_parts: list[str] = []
        while True:
            chunk = await streaming_queue.get()
            if chunk is None:
                break
            # Differentiate raw text chunks vs structured JSON events.
            if chunk.startswith('{"type":'):
                # Before yielding the final event, backfill the answer from
                # accumulated streamed text when the composition block
                # streamed a plain-text answer but failed to parse it as
                # JSON (final_entry.data is {} → answer is "").
                if streamed_text_parts and '"type": "final"' in chunk:
                    try:
                        event = json.loads(chunk)
                        advisor = (event.get("data") or {}).get("advisor") or {}
                        if not advisor.get("answer"):
                            streamed_answer = "".join(streamed_text_parts).strip()
                            # The streamed output may be a JSON envelope;
                            # try to unwrap {"answer_text": "..."}.
                            try:
                                parsed = json.loads(streamed_answer)
                                if isinstance(parsed, dict) and "answer_text" in parsed:
                                    streamed_answer = parsed["answer_text"]
                            except (json.JSONDecodeError, TypeError):
                                pass
                            # ONLY the answer. Recovering the answer text says
                            # nothing about whether retrieval succeeded or how
                            # confident the turn should be -- those are the
                            # turn's own verdict on itself, already computed by
                            # `_build_advise_response` from the real state, and
                            # this block has no evidence that would revise
                            # either. It used to rewrite `retrievalStatus`
                            # "failed" -> "succeeded" here, which reported a
                            # genuinely failed turn to the frontend as a clean
                            # success, on the streaming path only.
                            advisor["answer"] = streamed_answer
                            chunk = json.dumps(event)
                    except (json.JSONDecodeError, TypeError):
                        pass
                yield f"data: {chunk}\n\n"
            else:
                streamed_text_parts.append(chunk)
                yield f"data: {json.dumps({'type': 'chunk', 'text': chunk})}\n\n"
        await task

    return StreamingResponse(_event_generator(), media_type="text/event-stream")


__all__ = ["router"]
