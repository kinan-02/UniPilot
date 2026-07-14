"""Tests for `run_planner_council` (app.agent_core.planning.planner_council).

Drives the council directly (draft -> parallel critics -> gated synthesis)
with a `FakeLLMAdapter`. Responses are dispatched in call order; each member
is identified in assertions by a distinctive phrase in its system prompt
(the drafter says "You are the Planner", critics say "<X> Critic", the
synthesizer says "Synthesizer").
"""

from __future__ import annotations

from app.agent_core.planning.planner import PLANNER_OUTPUT_SCHEMA, PLANNER_OUTPUT_SCHEMA_NAME
from app.agent_core.planning.planner_council import run_planner_council
from app.agent_core.planning.schemas import PlannerInvocationInput
from app.agent_core.reasoning.llm_adapter import LLMAdapterError

_INPUT = PlannerInvocationInput(
    user_goal="What happens if I fail Data Structures this semester?",
    original_user_message="What happens if I fail Data Structures this semester?",
    sub_asks=["What happens if I fail Data Structures this semester?"],
)


def _plan(step_id: str = "A", objective: str = "Retrieve the student's current academic state.") -> dict:
    return {
        "plan_status": "in_progress",
        "next_steps": [
            {
                "step_id": step_id,
                "objective": objective,
                "depends_on": [],
                "success_criteria": ["state fetched"],
                "assumptions_to_verify": [],
            }
        ],
        "plan_summary": "summary",
        "clarification_question": None,
    }


def _critic(issues: list[str]) -> dict:
    return {"issues": issues}


async def _run(adapter):
    return await run_planner_council(
        planner_input=_INPUT,
        llm_adapter=adapter,
        block_id="blk-1",
        output_schema_name=PLANNER_OUTPUT_SCHEMA_NAME,
        output_schema=PLANNER_OUTPUT_SCHEMA,
    )


def _system_prompts(adapter) -> list[str]:
    return [c["system_prompt"] for c in adapter.calls]


async def test_clean_draft_with_no_findings_returns_draft_and_skips_synth(fake_llm_adapter_factory):
    # Draft is valid; all four critics find nothing -> the draft stands and
    # the synthesizer is never called (the gate saves that call).
    adapter = fake_llm_adapter_factory([_plan(), _critic([]), _critic([]), _critic([]), _critic([])])

    output = await _run(adapter)

    assert [s.step_id for s in output.next_steps] == ["A"]
    assert output.plan_status == "in_progress"
    assert not any("Synthesizer" in sp for sp in _system_prompts(adapter))
    assert "planner_council_synthesized" not in output.warnings


async def test_critic_findings_trigger_synthesis(fake_llm_adapter_factory):
    # One critic flags an issue -> the synthesizer runs and its revised plan
    # is returned (not the draft).
    revised = _plan(step_id="A", objective="Retrieve completed courses AND current standing.")
    adapter = fake_llm_adapter_factory([_plan(), _critic(["step A is missing the standing lookup"]), _critic([]), _critic([]), _critic([]), revised])

    output = await _run(adapter)

    assert any("Synthesizer" in sp for sp in _system_prompts(adapter))
    assert "planner_council_synthesized" in output.warnings
    assert output.next_steps[0].objective == "Retrieve completed courses AND current standing."


async def test_drafter_failure_returns_fallback_without_running_critics(fake_llm_adapter_factory):
    # Draft is malformed through every repair attempt -> the council returns
    # the drafter's own fail-closed output and never invokes a critic.
    adapter = fake_llm_adapter_factory([{"plan_status": "not_a_real_status"}] * 3)

    output = await _run(adapter)

    assert output.plan_status == "blocked_needs_clarification"
    assert output.next_steps == []
    assert not any("Critic" in sp for sp in _system_prompts(adapter))


async def test_synthesizer_failure_falls_back_to_the_vetted_draft(fake_llm_adapter_factory):
    # Critics flag an issue so the synthesizer runs, but the synthesizer's
    # output is malformed (pass + its one repair) -> the already-valid draft
    # is returned rather than a clarification block.
    adapter = fake_llm_adapter_factory(
        [_plan(), _critic(["needs a standing lookup"]), _critic([]), _critic([]), _critic([]),
         {"plan_status": "not_a_real_status"}, {"plan_status": "not_a_real_status"}]
    )

    output = await _run(adapter)

    assert [s.step_id for s in output.next_steps] == ["A"]
    assert output.plan_status == "in_progress"
    assert "planner_council_synth_discarded" in output.warnings


async def test_all_critics_failing_degrades_to_the_draft(fake_llm_adapter_factory):
    # Only the draft response is queued; all four critics exhaust the
    # adapter and fail closed to no findings -> the draft stands, no synth.
    adapter = fake_llm_adapter_factory([_plan()])

    output = await _run(adapter)

    assert [s.step_id for s in output.next_steps] == ["A"]
    assert not any("Synthesizer" in sp for sp in _system_prompts(adapter))
    # draft + four attempted (exhausted) critic calls were recorded.
    assert len(adapter.calls) == 5


async def test_routine_continuation_skips_the_council(fake_llm_adapter_factory):
    # A later invocation with no replan flags is a routine continuation:
    # only the fast drafter runs -- no critics, no synth.
    adapter = fake_llm_adapter_factory([_plan()])

    output = await run_planner_council(
        planner_input=_INPUT,
        llm_adapter=adapter,
        block_id="blk-1",
        invocation=2,
        output_schema_name=PLANNER_OUTPUT_SCHEMA_NAME,
        output_schema=PLANNER_OUTPUT_SCHEMA,
    )

    assert [s.step_id for s in output.next_steps] == ["A"]
    assert "planner_council_draft_only" in output.warnings
    assert len(adapter.calls) == 1  # drafter only -- critics never fired
    assert not any("Critic" in sp for sp in _system_prompts(adapter))


async def test_replan_on_a_later_invocation_still_runs_the_full_council(fake_llm_adapter_factory):
    # Even past the first invocation, a Monitor-flagged replan re-engages the
    # full council -- the previous attempt hit a problem, so plan shape matters.
    replan_input = _INPUT.model_copy(
        update={"monitor_flags": ["step 1a failed"], "replan_reason": "step 1a failed"}
    )
    adapter = fake_llm_adapter_factory([_plan(), _critic([]), _critic([]), _critic([]), _critic([])])

    output = await run_planner_council(
        planner_input=replan_input,
        llm_adapter=adapter,
        block_id="blk-1",
        invocation=3,
        output_schema_name=PLANNER_OUTPUT_SCHEMA_NAME,
        output_schema=PLANNER_OUTPUT_SCHEMA,
    )

    assert any("Critic" in sp for sp in _system_prompts(adapter))
    assert "planner_council_draft_only" not in output.warnings


async def test_drafter_raising_adapter_fails_closed():
    class RaisingAdapter:
        async def complete_json(self, **kwargs):
            raise LLMAdapterError("boom")

    output = await run_planner_council(
        planner_input=_INPUT,
        llm_adapter=RaisingAdapter(),
        block_id="blk-1",
        output_schema_name=PLANNER_OUTPUT_SCHEMA_NAME,
        output_schema=PLANNER_OUTPUT_SCHEMA,
    )

    assert output.plan_status == "blocked_needs_clarification"
    assert output.next_steps == []
