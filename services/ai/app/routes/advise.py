"""Internal /advise route -- the live entry point into the agent.

Protected by the existing internal-service-token dependency (the same one
`services/api`'s `ai_advisor_client.py` already sends
`X-Internal-Service-Token` for), not a user JWT -- `services/api` is the only
intended caller, already authenticated the end user itself.

The response shape matches EXACTLY what `services/api`'s
`advisor_service.py::ask_advisor_for_user` already parses (`response.answer`/
`confidence`/`course_ids`/`wiki_slugs`/`sources`/`contacts`/`eligibility`,
`semester_resolution`, `retrieval_agent.status`) -- that mapping and the
frontend's `AdvisorReply` type are unchanged by this route.

The request runs through the fact/tool loop (`app.agent_core.facts`). Everything
the response needs -- the answer, its confidence band, the course codes it
grounded, the outcome status -- is derived from the loop's own result by
`facts.service`, never model-authored: the loop's working set is the only
channel through which data is admitted, so a number that reached the prose
without a fact behind it is filtered back out.
"""

from __future__ import annotations

import asyncio
import json
import logging
import time
from collections.abc import AsyncIterator
from typing import Any

from fastapi import APIRouter, Depends
from fastapi.responses import StreamingResponse

from app.agent_core.facts.loop import LoopResult
from app.agent_core.facts.service import Advice, course_references, run_advice, to_advice
from app.config import get_settings
from app.core.responses import success_response
from app.dependencies.internal_auth import require_internal_service_token
from app.schemas.advise import AdviseRequest

logger = logging.getLogger(__name__)

router = APIRouter(dependencies=[Depends(require_internal_service_token)])

_TIMEOUT_MESSAGE = "This question is taking longer than expected to analyze -- please try again or ask something more specific."


def _response_payload(advice: Advice) -> dict[str, Any]:
    return {
        "response": {
            "answer": advice.answer,
            "confidence": advice.confidence,
            "course_ids": advice.course_ids,
            # The same ids carrying their display name, so the UI can label a
            # citation "E-Commerce Models" instead of "00960211". Looked up in
            # code like every name; never model-authored.
            "courses": course_references(advice.course_ids),
            # No primitive grounds these yet -- left honestly empty rather than
            # faked.
            "wiki_slugs": [],
            "sources": advice.sources,
            "contacts": [],
            "eligibility": None,
        },
        "semester_resolution": None,
        "retrieval_agent": {"status": advice.status},
    }


def _timeout_payload() -> dict[str, Any]:
    return _response_payload(
        Advice(
            answer=_TIMEOUT_MESSAGE,
            confidence="low",
            course_ids=[],
            status="timeout",
            sources=[],
            outcome="timeout",
        )
    )


def _log_outcome(result: LoopResult, advice: Advice) -> None:
    """What the run cost and how it ended.

    The answer text carries grades and course history, so it is logged only
    outside production. The metrics are safe everywhere and are what turn "it
    felt slow" into a number.
    """
    logger.info(
        "advise_outcome outcome=%s status=%s turns=%d facts=%d confidence=%s answer_chars=%d",
        result.outcome,
        advice.status,
        result.turns,
        len(result.facts),
        advice.confidence,
        len(advice.answer),
    )
    if get_settings().environment != "production":
        logger.info("advise_answer %s", json.dumps(advice.answer, ensure_ascii=False))


def _build_advise_response(question: str, result: LoopResult) -> dict[str, Any]:
    advice = to_advice(result)
    _log_outcome(result, advice)
    return {"question": question, **_response_payload(advice)}


def _timeout_response(question: str) -> dict[str, Any]:
    return {"question": question, **_timeout_payload()}


@router.post("/advise")
async def advise_route(payload: AdviseRequest) -> dict[str, Any]:
    settings = get_settings()
    try:
        result = await asyncio.wait_for(
            run_advice(
                question=payload.question,
                user_id=payload.user_id,
                settings=settings,
                conversation_id=payload.conversation_id,
            ),
            timeout=settings.agent_turn_timeout_seconds,
        )
    except asyncio.TimeoutError:
        # Only a hung provider should reach here -- the loop's own turn budget
        # concludes below this ceiling.
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
            "courses": response.get("courses", []),
            "wikiSlugs": response.get("wiki_slugs", []),
            "sources": response.get("sources", []),
            "contacts": response.get("contacts", []),
            "eligibility": response.get("eligibility"),
            "semesterResolution": raw.get("semester_resolution"),
            "retrievalStatus": (raw.get("retrieval_agent") or {}).get("status"),
        },
    }


async def _drain_until_done(
    progress: asyncio.Queue[str],
    loop_task: asyncio.Task[LoopResult],
    timeout: float,
) -> AsyncIterator[str]:
    """Yield queued progress phrases until the loop task finishes.

    The whole-request ceiling is enforced here rather than by wrapping the loop
    in `asyncio.wait_for`, because the generator has to stay awake forwarding
    progress for as long as the loop runs.
    """
    deadline = time.monotonic() + timeout
    while True:
        remaining = deadline - time.monotonic()
        if remaining <= 0:
            raise asyncio.TimeoutError
        getter: asyncio.Task[str] = asyncio.ensure_future(progress.get())
        done, _ = await asyncio.wait(
            {getter, loop_task}, timeout=remaining, return_when=asyncio.FIRST_COMPLETED
        )
        if getter in done:
            yield getter.result()
            continue
        getter.cancel()
        if loop_task not in done:
            raise asyncio.TimeoutError
        # Anything the last turn queued still belongs to the student.
        while not progress.empty():
            yield progress.get_nowait()
        loop_task.result()  # re-raise whatever the loop failed with, if anything
        return


@router.post("/advise/stream")
async def advise_stream_route(payload: AdviseRequest) -> StreamingResponse:
    """Typed-event SSE. The answer is assembled after the loop concludes (not
    token-by-token from the model), so the stream emits the finished answer as
    one `chunk` then a `final` event. While the loop runs, it forwards one short
    progress phrase per turn so a long request is not silent."""
    settings = get_settings()

    async def _event_generator():
        progress: asyncio.Queue[str] = asyncio.Queue()
        loop_task = asyncio.create_task(
            run_advice(
                question=payload.question,
                user_id=payload.user_id,
                settings=settings,
                on_progress=progress.put_nowait,
                conversation_id=payload.conversation_id,
            )
        )

        try:
            async for phrase in _drain_until_done(progress, loop_task, settings.agent_turn_timeout_seconds):
                yield f"data: {json.dumps({'type': 'progress', 'text': phrase})}\n\n"
            final_payload = _build_advise_response(payload.question, loop_task.result())
        except asyncio.TimeoutError:
            final_payload = _timeout_response(payload.question)
        except Exception as exc:  # noqa: BLE001 -- surface as a typed error event, never a 500 mid-stream
            yield f"data: {json.dumps({'type': 'error', 'error': str(exc)})}\n\n"
            return
        finally:
            # A timed-out or failed generator must not leave the loop running and
            # burning provider calls for an answer nobody will read.
            if not loop_task.done():
                loop_task.cancel()

        answer = (final_payload.get("response") or {}).get("answer", "")
        if answer:
            yield f"data: {json.dumps({'type': 'chunk', 'text': answer})}\n\n"
        yield f"data: {json.dumps({'type': 'final', 'data': _to_frontend_advisor_shape(final_payload)})}\n\n"

    return StreamingResponse(_event_generator(), media_type="text/event-stream")


__all__ = ["router"]
