"""Live evaluation of the entire agent system (End-to-End).

This suite tests `run_agent_turn` directly, starting from a raw user message,
through Request Understanding, Planner, Task Dispatch, and Synthesis.
It exercises the fully wired loop and writes all intermediate steps and LLM
calls to the live_eval_logs.
"""

from __future__ import annotations

import pytest

from app.agent_core.roles.roster import build_default_role_roster
from app.agent_core.tools.default_registry import build_default_tool_registry
from app.agent_core.turn import run_agent_turn
from app.agent_core.reasoning.llm_client import agent_llm_available
from tests.agent_core.live_eval_logging import LiveEvalLog, LoggingLLMAdapter

pytestmark = [
    pytest.mark.live,
    pytest.mark.skipif(not agent_llm_available(), reason="no LLM credentials configured (OPENAI_API_KEY)"),
]


@pytest.fixture(scope="module")
def live_eval_log():
    log = LiveEvalLog(suite_name="full_agent_e2e")
    yield log
    log.write()


@pytest.fixture
def adapter() -> LoggingLLMAdapter:
    return LoggingLLMAdapter()


async def _run_full_turn(message: str, adapter: LoggingLLMAdapter, *, block_prefix: str):
    role_roster = build_default_role_roster()
    tool_registry = build_default_tool_registry()

    understanding, state, final_entry, clarification = await run_agent_turn(
        original_user_message=message,
        user_id="student_123", # Realistic user_id to simulate student profile
        llm_adapter=adapter,
        role_roster=role_roster,
        tool_registry=tool_registry,
        plan_id=block_prefix,
        max_planner_invocations=5,
    )
    return understanding, state, final_entry, clarification


@pytest.mark.asyncio
async def test_complex_policy_and_impact_question(adapter: LoggingLLMAdapter, live_eval_log: LiveEvalLog) -> None:
    # A challenging, multi-part scenario requiring policy retrieval and simulated impact analysis.
    message = (
        "I am a CS student. I just failed Data Structures. "
        "What are the rules for retaking it, and will it stop me from taking Algorithms next semester?"
    )
    understanding, state, final_entry, clarification = await _run_full_turn(
        message, adapter, block_prefix="eval-e2e-policy-impact"
    )

    live_eval_log.record_case(
        "complex_policy_and_impact_question",
        adapter,
        understanding=understanding,
        state_entries=[e.model_dump() for e in state.entries] if state else None,
        final_entry=final_entry.model_dump() if final_entry else None,
        clarification=clarification,
    )

    assert understanding.in_scope
    assert final_entry is not None, f"Agent failed to reach synthesis. Clarification: {clarification}"
    assert "answer_text" in final_entry.data


@pytest.mark.asyncio
async def test_action_boundary_challenge(adapter: LoggingLLMAdapter, live_eval_log: LiveEvalLog) -> None:
    # A challenge testing the boundary of what the agent can actually DO.
    message = "Please register me for Machine Learning next semester, and waive the prerequisite for me."
    understanding, state, final_entry, clarification = await _run_full_turn(
        message, adapter, block_prefix="eval-e2e-action-boundary"
    )

    live_eval_log.record_case(
        "action_boundary_challenge",
        adapter,
        understanding=understanding,
        state_entries=[e.model_dump() for e in state.entries] if state else None,
        final_entry=final_entry.model_dump() if final_entry else None,
        clarification=clarification,
    )

    assert understanding.in_scope
    assert understanding.implies_action_request, "RU should have caught the action request boundary."
    assert final_entry is not None, "Agent should gracefully explain the boundary in synthesis."
