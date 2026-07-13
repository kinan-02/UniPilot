"""Top-level entry point for one full agent turn (docs/agent/AGENT_VISION.md §3):

    User request -> Request Understanding -> Planner -> Orchestrator

the one sub-chain of the architecture confirmed final. Request Understanding
is its own layer in the vision's diagram -- a peer of Planner and
Orchestrator, not nested inside either -- so it gets its own top-level
module rather than a function bolted onto `orchestrator.loop`.
"""

from __future__ import annotations

import asyncio
from datetime import datetime, timezone

from app.agent_core.orchestrator.loop import DEFAULT_MAX_PLANNER_INVOCATIONS, run_plan_to_completion
from app.agent_core.planning.schemas import RoleName
from app.agent_core.planning.state import CertaintyTag, PlanExecutionState, StateEntry
from app.agent_core.reasoning.llm_adapter import LLMAdapter
from app.agent_core.request_understanding.request_understanding import understand_request
from app.agent_core.request_understanding.schemas import RequestUnderstandingReasoningBlockOutput
from app.agent_core.roles.schemas import RoleDefinition
from app.agent_core.tools.call_cache import ToolCallCache
from app.agent_core.tools.registry import ToolRegistry
from app.agent_core.tools.unresolvable_registry import UnresolvableEntityRegistry
from app.agent_core.boundary_handler.boundary_handler import run_boundary_handler
from app.agent_core.complexity_classifier.complexity_classifier import classify_complexity
from app.agent_core.reasoning_effort import build_reasoning_config


async def run_agent_turn(
    *,
    original_user_message: str,
    user_id: str,
    llm_adapter: LLMAdapter,
    role_roster: dict[RoleName, RoleDefinition],
    tool_registry: ToolRegistry,
    plan_id: str,
    max_planner_invocations: int = DEFAULT_MAX_PLANNER_INVOCATIONS,
    streaming_queue: asyncio.Queue[str] | None = None,
) -> tuple[RequestUnderstandingReasoningBlockOutput, PlanExecutionState, StateEntry | None, str | None]:
    """Drives the full confirmed chain: raw message in, final answer out.

    Returns `(understanding, state, final_entry, clarification_question)`.
    Callers must check `understanding.in_scope` first: when `False`, the
    Planner never ran, but `final_entry` contains the Boundary Handler's
    polite rejection. When `in_scope` is `True`, `final_entry`/`clarification_question`
    are populated under the exact same conditions
    `run_plan_to_completion` already documents (blocked on clarification, or
    the invocation budget ran out).
    """
    understanding = await understand_request(
        original_user_message=original_user_message,
        llm_adapter=llm_adapter,
        block_id=f"{plan_id}-request-understanding",
    )
    if not understanding.in_scope:
        boundary_output = await run_boundary_handler(
            original_user_message=original_user_message,
            decline_reason=understanding.decline_reason or "Out of scope",
            llm_adapter=llm_adapter,
            block_id=f"{plan_id}-boundary-handler",
        )
        final_entry = StateEntry(
            entry_id=f"{plan_id}-boundary-entry",
            step_id="boundary_handling",
            role="composition",
            status="succeeded",
            output_schema_name="boundary_handler_output_v1",
            data={"answer_text": boundary_output.answer_text},
            certainty=CertaintyTag(basis="llm_interpretation", confidence=boundary_output.confidence),
            produced_at=datetime.now(timezone.utc),
        )
        return understanding, PlanExecutionState(plan_id=plan_id), final_entry, None

    # ── Complexity Classification ──────────────────────────────────────
    # Lightweight LLM call (~1-1.5s) that maps the structured RU output
    # into a cognitive_complexity tier, which drives how much thinking
    # the Planner and select subagents get for this turn.
    cognitive_complexity = await classify_complexity(
        sub_asks=understanding.sub_asks,
        constraints=understanding.constraints,
        open_questions=understanding.open_questions,
        implies_action_request=understanding.implies_action_request,
        confidence=understanding.confidence,
        llm_adapter=llm_adapter,
        block_id=f"{plan_id}-complexity-classifier",
    )
    reasoning_config = build_reasoning_config(cognitive_complexity)

    # One cache per turn, never a module-level global or caller-supplied
    # value -- created fresh here so concurrent turns/requests can never
    # see each other's cached tool results.
    tool_call_cache = ToolCallCache()
    # One registry per turn -- when a get_entity/search_knowledge call
    # comes back conclusively empty, the term is recorded as a dead end
    # and surfaced as a structured field on PlannerInvocationInput so the
    # Planner never re-schedules the same search.
    unresolvable_registry = UnresolvableEntityRegistry()
    state, final_entry, clarification_question = await run_plan_to_completion(
        user_goal=understanding.user_goal or original_user_message,
        original_user_message=original_user_message,
        user_id=user_id,
        llm_adapter=llm_adapter,
        role_roster=role_roster,
        tool_registry=tool_registry,
        plan_id=plan_id,
        max_planner_invocations=max_planner_invocations,
        reasoning_config=reasoning_config,
        sub_asks=understanding.sub_asks,
        constraints=understanding.constraints,
        open_questions=understanding.open_questions,
        implies_action_request=understanding.implies_action_request,
        streaming_queue=streaming_queue,
        tool_call_cache=tool_call_cache,
        unresolvable_registry=unresolvable_registry,
    )
    return understanding, state, final_entry, clarification_question


__all__ = ["run_agent_turn"]
