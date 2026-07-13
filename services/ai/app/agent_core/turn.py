"""Top-level entry point for one full agent turn (docs/agent/AGENT_VISION.md §3):

    User request -> Request Understanding -> Planner -> Orchestrator

the one sub-chain of the architecture confirmed final. Request Understanding
is its own layer in the vision's diagram -- a peer of Planner and
Orchestrator, not nested inside either -- so it gets its own top-level
module rather than a function bolted onto `orchestrator.loop`.
"""

from __future__ import annotations

import asyncio

from app.agent_core.orchestrator.loop import DEFAULT_MAX_PLANNER_INVOCATIONS, run_plan_to_completion
from app.agent_core.planning.schemas import RoleName
from app.agent_core.planning.state import PlanExecutionState, StateEntry
from app.agent_core.reasoning.llm_adapter import LLMAdapter
from app.agent_core.request_understanding.request_understanding import understand_request
from app.agent_core.request_understanding.schemas import RequestUnderstandingReasoningBlockOutput
from app.agent_core.roles.schemas import RoleDefinition
from app.agent_core.tools.call_cache import ToolCallCache
from app.agent_core.tools.registry import ToolRegistry
from app.agent_core.tools.unresolvable_registry import UnresolvableEntityRegistry


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
    Planner never ran -- `state` is empty, `final_entry` and
    `clarification_question` are both `None` -- and the answer is
    `understanding.decline_message`, not anything else in the return value.
    When `in_scope` is `True`, `final_entry`/`clarification_question` are
    `None`/populated under the exact same conditions
    `run_plan_to_completion` already documents (blocked on clarification, or
    the invocation budget ran out).
    """
    understanding = await understand_request(
        original_user_message=original_user_message,
        llm_adapter=llm_adapter,
        block_id=f"{plan_id}-request-understanding",
    )
    if not understanding.in_scope:
        return understanding, PlanExecutionState(plan_id=plan_id), None, None

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
