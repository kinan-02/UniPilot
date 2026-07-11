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

from typing import Any
from uuid import uuid4

from fastapi import APIRouter, Depends

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


def _response_payload(
    *,
    answer: str,
    confidence: str,
    course_ids: list[str],
    retrieval_status: str,
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
            "sources": [],
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
            answer=understanding.decline_message or _FALLBACK_CLARIFICATION_MESSAGE,
            confidence="low",
            course_ids=[],
            retrieval_status="out_of_scope",
        )
    elif final_entry is None:
        payload = _response_payload(
            answer=clarification_question or _FALLBACK_CLARIFICATION_MESSAGE,
            confidence="low",
            course_ids=[],
            retrieval_status="blocked_needs_clarification" if clarification_question else "incomplete",
        )
    else:
        payload = _response_payload(
            answer=final_entry.data.get("answer_text", ""),
            confidence=certainty_band(final_entry.certainty.confidence),
            course_ids=_derive_course_ids(state),
            retrieval_status=final_entry.status,
        )
    return {"question": question, **payload}


@router.post("/advise")
async def advise_route(payload: AdviseRequest) -> dict[str, Any]:
    plan_id = str(uuid4())
    llm_adapter = BudgetedLLMAdapter(
        ChatLLMAdapter(), max_calls=get_settings().agent_reasoning_call_budget_per_turn
    )
    understanding, state, final_entry, clarification_question = await run_agent_turn(
        original_user_message=payload.question,
        user_id=payload.user_id,
        llm_adapter=llm_adapter,
        role_roster=build_default_role_roster(),
        tool_registry=build_default_tool_registry(),
        plan_id=plan_id,
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


__all__ = ["router"]
