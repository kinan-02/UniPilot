"""Proves there are no gaps in the confirmed chain (docs/agent/AGENT_VISION.md §3):

    User request -> Request Understanding -> Planner -> Orchestrator

`run_agent_turn` is exercised starting from a **raw user message only** --
no pre-supplied `user_goal` -- reusing the same 9-response plan/subagent
sequence already proven in `test_skeleton_end_to_end.py`, with one Request
Understanding response prepended.
"""

from __future__ import annotations

from app.agent_core.roles.roster import build_default_role_roster
from app.agent_core.tools.default_registry import build_default_tool_registry
from app.agent_core.turn import run_agent_turn
from tests.agent_core.test_skeleton_end_to_end import _RESPONSES

_RAW_MESSAGE = "What course is 234218?"

_REQUEST_UNDERSTANDING_RESPONSE = {
    "in_scope": True,
    "sub_asks": ["Identify course 234218 and describe it."],
    "constraints": [],
    "open_questions": [],
    "implies_action_request": False,
    "decline_message": None,
    "confidence": 0.85,
}

_OUT_OF_SCOPE_RESPONSE = {
    "in_scope": False,
    "sub_asks": [],
    "constraints": [],
    "open_questions": [],
    "implies_action_request": False,
    "decline_message": "I can only help with Technion academic advising questions.",
    "confidence": 0.9,
}


async def test_raw_message_drives_the_full_chain_with_no_gaps(fake_llm_adapter_factory):
    adapter = fake_llm_adapter_factory([_REQUEST_UNDERSTANDING_RESPONSE, *_RESPONSES])
    role_roster = build_default_role_roster()
    tool_registry = build_default_tool_registry()

    understanding, state, final_entry = await run_agent_turn(
        original_user_message=_RAW_MESSAGE,
        llm_adapter=adapter,
        role_roster=role_roster,
        tool_registry=tool_registry,
        plan_id="test-turn-1",
    )

    # Request Understanding actually ran and produced a real derived goal --
    # not the raw message verbatim (which is what the fallback would return).
    assert understanding.sub_asks == ["Identify course 234218 and describe it."]
    assert understanding.user_goal == "Identify course 234218 and describe it."

    # That derived goal is what actually reached the Planner: the very next
    # call the fake adapter recorded is the planner's own call, and its
    # user_prompt embeds task_context (which includes user_goal).
    planner_call = adapter.calls[1]
    assert "Identify course 234218 and describe it." in planner_call["user_prompt"]

    # The structured fields themselves reached the Planner too -- not just
    # the lossily-flattened user_goal string (Option B: PlannerInvocationInput
    # was additively widened so this data isn't lost at the boundary).
    assert '"sub_asks"' in planner_call["user_prompt"]

    # The rest of the chain completes exactly as already proven in
    # test_skeleton_end_to_end.py's own end-to-end test.
    assert len(state.entries) == 2
    assert [e.step_id for e in state.entries] == ["s1", "s2"]
    assert final_entry is not None
    assert final_entry.step_id == "s2"
    assert final_entry.data["answer_text"] == "Course 234218 is Some Course."

    # Every queued response was consumed in order, nothing left over.
    assert adapter._responses == []


async def test_out_of_scope_request_never_reaches_the_planner(fake_llm_adapter_factory):
    # Only one response queued -- if the Planner were invoked, the fake
    # adapter would raise on the second call, failing this test.
    adapter = fake_llm_adapter_factory([_OUT_OF_SCOPE_RESPONSE])
    role_roster = build_default_role_roster()
    tool_registry = build_default_tool_registry()

    understanding, state, final_entry = await run_agent_turn(
        original_user_message="Write me a poem.",
        llm_adapter=adapter,
        role_roster=role_roster,
        tool_registry=tool_registry,
        plan_id="test-turn-2",
    )

    assert understanding.in_scope is False
    assert understanding.decline_message == "I can only help with Technion academic advising questions."
    assert state.entries == []
    assert final_entry is None
    assert len(adapter.calls) == 1
