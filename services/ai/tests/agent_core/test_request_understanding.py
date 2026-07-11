"""Tests for `RequestUnderstandingReasoningBlock` (docs/agent/AGENT_VISION.md §3, §6.2).

`FakeLLMAdapter` responses here are the raw output-schema dict directly
(`{"in_scope": ..., "sub_asks": [...], ...}`) -- unlike the old `ReasoningBlock`
this block's `_invoke_llm` calls the adapter directly with no "pass payload"
envelope to unwrap. `user_goal` is never part of the queued LLM response --
it's rendered deterministically from `sub_asks` (`_render_user_goal`), never
LLM output, so it can't independently drift from the structured fields.
"""

from __future__ import annotations

from app.agent_core.reasoning.llm_adapter import LLMAdapterError
from app.agent_core.request_understanding.request_understanding import _render_user_goal, understand_request

_MESSAGE = "What am I missing to graduate?"


def _response(**overrides):
    base = {
        "in_scope": True,
        "sub_asks": ["Determine remaining graduation requirements."],
        "constraints": [],
        "open_questions": [],
        "implies_action_request": False,
        "decline_message": None,
        "confidence": 0.9,
    }
    base.update(overrides)
    return base


async def test_single_sub_ask_happy_path(fake_llm_adapter_factory):
    adapter = fake_llm_adapter_factory([_response()])

    output = await understand_request(original_user_message=_MESSAGE, llm_adapter=adapter, block_id="blk-1")

    assert output.in_scope is True
    assert output.sub_asks == ["Determine remaining graduation requirements."]
    assert output.user_goal == "Determine remaining graduation requirements."
    assert output.decline_message is None
    assert output.schema_valid is True
    # Regression guard: the Planner sets its own request-level timeout/
    # max_retries (planning/planner.py) -- RU must never inherit them. RU
    # sets its own independent timeout (request_understanding.py's own
    # _TIMEOUT_SECONDS) and leaves max_retries unset.
    assert adapter.calls[0]["timeout"] == 30.0
    assert adapter.calls[0]["max_retries"] is None


async def test_multiple_sub_asks_render_into_joined_user_goal(fake_llm_adapter_factory):
    adapter = fake_llm_adapter_factory(
        [
            _response(
                sub_asks=[
                    "consequences of failing Data Structures this semester",
                    "feasibility of a Math minor alongside the degree",
                ]
            )
        ]
    )

    output = await understand_request(
        original_user_message="What happens if I fail Data Structures, and can I do a Math minor?",
        llm_adapter=adapter,
        block_id="blk-1",
    )

    assert output.sub_asks == [
        "consequences of failing Data Structures this semester",
        "feasibility of a Math minor alongside the degree",
    ]
    assert output.user_goal == (
        "consequences of failing Data Structures this semester; "
        "feasibility of a Math minor alongside the degree"
    )


async def test_constraints_open_questions_and_implies_action_request_pass_through(fake_llm_adapter_factory):
    adapter = fake_llm_adapter_factory(
        [
            _response(
                constraints=["must graduate within the next year"],
                open_questions=["unclear which semester 'next semester' refers to"],
                implies_action_request=True,
            )
        ]
    )

    output = await understand_request(original_user_message=_MESSAGE, llm_adapter=adapter, block_id="blk-1")

    assert output.constraints == ["must graduate within the next year"]
    assert output.open_questions == ["unclear which semester 'next semester' refers to"]
    assert output.implies_action_request is True


async def test_out_of_scope_path(fake_llm_adapter_factory):
    adapter = fake_llm_adapter_factory(
        [
            _response(
                in_scope=False,
                sub_asks=[],
                decline_message="I can only help with Technion academic advising questions.",
            )
        ]
    )

    output = await understand_request(original_user_message="Write me a poem.", llm_adapter=adapter, block_id="blk-1")

    assert output.in_scope is False
    assert output.user_goal is None
    assert output.sub_asks == []
    assert output.decline_message == "I can only help with Technion academic advising questions."


async def test_falls_back_to_raw_message_when_llm_adapter_raises():
    class RaisingAdapter:
        async def complete_json(self, **_kwargs):
            raise LLMAdapterError("llm_unavailable_test")

    output = await understand_request(original_user_message=_MESSAGE, llm_adapter=RaisingAdapter(), block_id="blk-1")

    assert output.in_scope is True
    assert output.sub_asks == [_MESSAGE]
    assert output.user_goal == _MESSAGE
    assert output.decline_message is None
    assert output.schema_valid is False


async def test_falls_back_when_repair_is_exhausted(fake_llm_adapter_factory):
    # Missing every required key -> schema-invalid; queued for the initial
    # pass plus both schema-repair attempts, so repair never recovers.
    adapter = fake_llm_adapter_factory([{}, {}, {}])

    output = await understand_request(original_user_message=_MESSAGE, llm_adapter=adapter, block_id="blk-1")

    assert output.in_scope is True
    assert output.sub_asks == [_MESSAGE]
    assert output.user_goal == _MESSAGE
    assert output.schema_valid is False
    assert adapter._responses == []


async def test_falls_back_when_in_scope_true_but_sub_asks_empty(fake_llm_adapter_factory):
    # Schema-valid (an empty array is a valid "array of strings") but
    # semantically hollow.
    adapter = fake_llm_adapter_factory([_response(sub_asks=[])])

    output = await understand_request(original_user_message=_MESSAGE, llm_adapter=adapter, block_id="blk-1")

    assert output.in_scope is True
    assert output.sub_asks == [_MESSAGE]
    assert output.user_goal == _MESSAGE
    assert output.schema_valid is False


async def test_falls_back_when_in_scope_false_but_decline_message_missing(fake_llm_adapter_factory):
    adapter = fake_llm_adapter_factory([_response(in_scope=False, sub_asks=[], decline_message=None)])

    output = await understand_request(original_user_message=_MESSAGE, llm_adapter=adapter, block_id="blk-1")

    # A hollow decline falls all the way open rather than surfacing an empty
    # decline -- swallowing a legitimate request behind a blank message would
    # be worse than just letting the Planner see it.
    assert output.in_scope is True
    assert output.sub_asks == [_MESSAGE]
    assert output.user_goal == _MESSAGE
    assert output.schema_valid is False


def test_render_user_goal_empty():
    assert _render_user_goal([]) == ""


def test_render_user_goal_single():
    assert _render_user_goal(["only ask"]) == "only ask"


def test_render_user_goal_multiple():
    assert _render_user_goal(["first ask", "second ask"]) == "first ask; second ask"
