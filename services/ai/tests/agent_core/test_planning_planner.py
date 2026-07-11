"""Tests for `PlannerReasoningBlock` (docs/agent/PLANNER_OUTPUT_DESIGN.md +
follow-on reasoning-block design).

`FakeLLMAdapter` responses here are the raw output-schema dict directly
(`{"plan_status": ..., "next_steps": [...], ...}`) -- mirrors
`test_request_understanding.py`'s own note: `PlannerReasoningBlock`
(`BaseReasoningBlock`) calls the adapter directly with no "pass payload"
envelope to unwrap, unlike the old `ReasoningBlock`.
"""

from __future__ import annotations

from app.agent_core.planning.planner import NESTED_PLANNER_V1, build_next_plan_steps
from app.agent_core.planning.schemas import PlanGraph, PlannerInvocationInput
from app.agent_core.reasoning.llm_adapter import LLMAdapterError

_INPUT = PlannerInvocationInput(
    user_goal="What happens if I fail Data Structures this semester?",
    original_user_message="What happens if I fail Data Structures this semester?",
    sub_asks=["What happens if I fail Data Structures this semester?"],
)


def _response(**overrides):
    base = {
        "plan_status": "in_progress",
        "next_steps": [
            {
                "step_id": "A",
                "objective": "Retrieve the student's current academic state.",
                "depends_on": [],
                "success_criteria": ["state fetched"],
                "assumptions_to_verify": [],
            }
        ],
        "plan_summary": "Establishing current state before projecting impact.",
        "clarification_question": None,
    }
    base.update(overrides)
    return base


async def test_happy_path_rewrites_ids_and_computes_graph(fake_llm_adapter_factory):
    adapter = fake_llm_adapter_factory([_response()])

    output = await build_next_plan_steps(
        planner_input=_INPUT, llm_adapter=adapter, block_id="blk-1", invocation=1
    )

    assert output.plan_status == "in_progress"
    assert [s.step_id for s in output.next_steps] == ["1a"]
    assert output.plan_graph.forward == {"1a": []}
    assert output.plan_graph.execution_layers == [["1a"]]


async def test_sets_its_own_timeout_and_max_retries(fake_llm_adapter_factory):
    # Regression guard: the Planner sets its own request-level timeout/
    # max_retries (planner.py's _TIMEOUT_SECONDS/_MAX_RETRIES) -- must land
    # on the actual complete_json call, not silently stay None.
    adapter = fake_llm_adapter_factory([_response()])

    await build_next_plan_steps(planner_input=_INPUT, llm_adapter=adapter, block_id="blk-1", invocation=1)

    assert adapter.calls[0]["timeout"] == 60.0
    assert adapter.calls[0]["max_retries"] == 2


async def test_two_dependent_steps_resolve_local_labels(fake_llm_adapter_factory):
    adapter = fake_llm_adapter_factory(
        [
            _response(
                next_steps=[
                    {"step_id": "A", "objective": "fetch", "depends_on": [], "success_criteria": [], "assumptions_to_verify": []},
                    {"step_id": "B", "objective": "compose", "depends_on": ["A"], "success_criteria": [], "assumptions_to_verify": []},
                ]
            )
        ]
    )

    output = await build_next_plan_steps(
        planner_input=_INPUT, llm_adapter=adapter, block_id="blk-1", invocation=1
    )

    by_id = {s.step_id: s for s in output.next_steps}
    assert by_id["1b"].depends_on == ["1a"]


async def test_falls_back_closed_when_llm_adapter_raises():
    class RaisingAdapter:
        async def complete_json(self, **kwargs):
            raise LLMAdapterError("boom")

    output = await build_next_plan_steps(
        planner_input=_INPUT, llm_adapter=RaisingAdapter(), block_id="blk-1", invocation=1
    )

    assert output.plan_status == "blocked_needs_clarification"
    assert output.clarification_question
    assert output.next_steps == []


async def test_falls_back_closed_when_repair_is_exhausted(fake_llm_adapter_factory):
    # Two malformed responses: the first pass plus every repair attempt.
    adapter = fake_llm_adapter_factory([{"plan_status": "not_a_real_status"}] * 3)

    output = await build_next_plan_steps(
        planner_input=_INPUT, llm_adapter=adapter, block_id="blk-1", invocation=1
    )

    assert output.plan_status == "blocked_needs_clarification"
    assert output.clarification_question
    assert output.next_steps == []
    # Regression guard: schema-repair attempts must inherit the ORIGINAL
    # request's timeout/max_retries too, not just the first pass -- a fresh,
    # empty LLMCallParameters() would silently drop them for every repair
    # call (reasoning_blocks/base.py's _repair_schema).
    assert len(adapter.calls) == 3
    assert all(call["timeout"] == 60.0 and call["max_retries"] == 2 for call in adapter.calls)


async def test_falls_back_closed_when_next_steps_has_wrong_shape(fake_llm_adapter_factory):
    # next_steps is schema-shaped as an array of objects, but nothing stops
    # a model from emitting something malformed anyway (e.g. a step missing
    # its required objective) -- must fail closed, never crash the block.
    adapter = fake_llm_adapter_factory(
        [_response(next_steps=[{"step_id": "A"}])]  # missing required "objective"
    )

    output = await build_next_plan_steps(
        planner_input=_INPUT, llm_adapter=adapter, block_id="blk-1", invocation=1
    )

    assert output.plan_status == "blocked_needs_clarification"
    assert output.clarification_question
    assert output.next_steps == []


async def test_falls_back_closed_on_hollow_in_progress(fake_llm_adapter_factory):
    adapter = fake_llm_adapter_factory([_response(plan_status="in_progress", next_steps=[])])

    output = await build_next_plan_steps(
        planner_input=_INPUT, llm_adapter=adapter, block_id="blk-1", invocation=1
    )

    assert output.plan_status == "blocked_needs_clarification"
    assert output.clarification_question
    assert output.next_steps == []


async def test_falls_back_closed_on_hollow_blocked_status(fake_llm_adapter_factory):
    adapter = fake_llm_adapter_factory(
        [_response(plan_status="blocked_needs_clarification", clarification_question=None, next_steps=[])]
    )

    output = await build_next_plan_steps(
        planner_input=_INPUT, llm_adapter=adapter, block_id="blk-1", invocation=1
    )

    assert output.plan_status == "blocked_needs_clarification"
    assert output.clarification_question


async def test_complete_status_with_no_new_steps_is_not_hollow(fake_llm_adapter_factory):
    # "complete" legitimately ends with no new steps -- must not be treated
    # as a failure the way an empty in_progress result is.
    adapter = fake_llm_adapter_factory([_response(plan_status="complete", next_steps=[])])

    output = await build_next_plan_steps(
        planner_input=_INPUT, llm_adapter=adapter, block_id="blk-1", invocation=1
    )

    assert output.plan_status == "complete"


async def test_known_global_id_dependency_is_preserved_not_rewritten(fake_llm_adapter_factory):
    adapter = fake_llm_adapter_factory(
        [
            _response(
                next_steps=[
                    {"step_id": "A", "objective": "compose", "depends_on": ["1a"], "success_criteria": [], "assumptions_to_verify": []},
                ]
            )
        ]
    )
    planner_input = PlannerInvocationInput(
        user_goal="goal",
        original_user_message="goal",
        plan_graph_so_far=PlanGraph(forward={"1a": []}, dependents={"1a": []}, execution_layers=[["1a"]]),
    )

    output = await build_next_plan_steps(
        planner_input=planner_input, llm_adapter=adapter, block_id="blk-2", invocation=2
    )

    assert output.next_steps[0].depends_on == ["1a"]


async def test_default_prompt_contract_frames_this_as_the_students_request(fake_llm_adapter_factory):
    adapter = fake_llm_adapter_factory([_response()])

    await build_next_plan_steps(planner_input=_INPUT, llm_adapter=adapter, block_id="blk-1", invocation=1)

    assert "the student's request" in adapter.calls[0]["system_prompt"]


async def test_nested_prompt_contract_produces_a_genuinely_different_system_prompt(fake_llm_adapter_factory):
    adapter = fake_llm_adapter_factory([_response()])

    await build_next_plan_steps(
        planner_input=_INPUT,
        llm_adapter=adapter,
        block_id="blk-1",
        invocation=1,
        prompt_contract_name=NESTED_PLANNER_V1,
    )

    system_prompt = adapter.calls[0]["system_prompt"]
    assert "internal step of a larger plan" in system_prompt
    assert "the student's request" not in system_prompt
