"""Tests for `run_planner_council` (app.agent_core.planning.planner_council).

Drives the council directly (draft -> validate -> select -> parallel critics ->
gated synthesis) with a `FakeLLMAdapter`. Responses are dispatched in call
order; each member is identified in assertions by a distinctive phrase in its
system prompt (the drafter says "You are the Planner", critics say "<X>
Critic", the synthesizer says "Synthesizer").

The critic SELECTION policy is exhaustively tested in `test_critic_selector.py`.
Here, orchestration tests monkeypatch `select_critics` to a fixed subset so
they exercise the draft/critic/synth wiring independent of heuristic tuning;
a few tests at the end drive the REAL selector end-to-end.
"""

from __future__ import annotations

import app.agent_core.planning.planner_council as pc
from app.agent_core.planning.planner import PLANNER_OUTPUT_SCHEMA, PLANNER_OUTPUT_SCHEMA_NAME
from app.agent_core.planning.planner_council import COVERAGE_CRITIC_V1, run_planner_council
from app.agent_core.planning.schemas import PlannerInvocationInput, StateEntrySummary
from app.agent_core.reasoning.llm_adapter import LLMAdapterError

_INPUT = PlannerInvocationInput(
    user_goal="What happens if I fail Data Structures this semester?",
    original_user_message="What happens if I fail Data Structures this semester?",
    sub_asks=["What happens if I fail Data Structures this semester?"],
)


def test_council_prompts_include_within_turn_memory():
    """Fix B regression: the synthesizer (which revises the draft into the
    FINAL plan) and the critics historically saw only the request -- not the
    accumulated state -- so a refinement pass re-scheduled retrieval for data
    already in state_index, and the efficiency critic could not see the
    completed work it is told to flag. Both prompts must now carry the same
    within-turn memory the main planner already gets."""
    memory = StateEntrySummary(
        entry_id="1a-0",
        step_id="1a",
        role="retrieval",
        summary="succeeded: completedCourses already fetched",
        certainty_band="high",
    )
    planner_input = PlannerInvocationInput(
        user_goal="List completed courses.",
        original_user_message="List completed courses.",
        sub_asks=["List completed courses."],
        state_index=[memory],
        exhausted_steps=["some-dead-end-objective"],
        unresolvable_entities=["Nonexistent Course"],
    )
    base = dict(
        block_id="b",
        agent_name="council",
        objective="o",
        output_schema_name=PLANNER_OUTPUT_SCHEMA_NAME,
        output_schema=PLANNER_OUTPUT_SCHEMA,
    )
    critic_prompt = pc._critic_user_prompt(
        pc._CriticInput(planner_input=planner_input, draft_steps=[], plan_summary="", **base)
    )
    synth_prompt = pc._synth_user_prompt(
        pc._SynthesizerInput(
            planner_input=planner_input, draft_steps=[], draft_plan_status="in_progress", issues=[], **base
        )
    )

    for prompt in (critic_prompt, synth_prompt):
        assert "state_index" in prompt
        assert "completedCourses already fetched" in prompt
        assert "exhausted_steps" in prompt
        assert "Nonexistent Course" in prompt


def _force_selection(monkeypatch, critics: list[str]) -> None:
    """Pin the council's critic selection to a fixed subset, so orchestration
    tests don't depend on the selector's heuristics."""
    monkeypatch.setattr(pc, "select_critics", lambda **_kwargs: tuple(critics))


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


def _multi_plan(steps: list[tuple[str, list[str]]]) -> dict:
    """A plan of several steps, each `(step_id, depends_on)` -- so a test can
    state a DAG's SHAPE (its parallel width and serial depth) directly."""
    return {
        "plan_status": "in_progress",
        "next_steps": [
            {
                "step_id": step_id,
                "objective": f"Do {step_id}.",
                "depends_on": depends_on,
                "success_criteria": ["ok"],
                "assumptions_to_verify": [],
            }
            for step_id, depends_on in steps
        ],
        "plan_summary": "summary",
        "clarification_question": None,
    }


def _step_ids(output) -> list[str]:
    return [step.step_id for step in output.next_steps]


def _critic(issues: list[str]) -> dict:
    return {"issues": issues}


async def _run(adapter, planner_input: PlannerInvocationInput = _INPUT, **kwargs):
    return await run_planner_council(
        planner_input=planner_input,
        llm_adapter=adapter,
        block_id="blk-1",
        output_schema_name=PLANNER_OUTPUT_SCHEMA_NAME,
        output_schema=PLANNER_OUTPUT_SCHEMA,
        **kwargs,
    )


def _system_prompts(adapter) -> list[str]:
    return [c["system_prompt"] for c in adapter.calls]


# ── Synthesis depth gate ─────────────────────────────────────────────────────
#
# Measured on the 2026-07-15 ise_correctness live run: the council never once
# shrank a plan (7->8, 4->5, 6->6 steps), and on `credits_remaining` the
# synthesizer took a draft whose depth was 5 and returned one of depth 7 --
# serializing a branch that had been parallel (E: depends_on B -> B,D) and
# splitting one calculation into two chained steps. That case then spent 39
# LLM calls and 177s to deliver a non-answer.
#
# The gate is on critical-path DEPTH rather than step COUNT deliberately: the
# coverage critic's whole job is to add a genuinely missing step, and adding a
# PARALLEL one costs no wall-clock. Depth is what turns into latency (each
# serial hop is one blocking LLM round-trip), so depth is what synthesis may
# not inflate.


async def test_synthesis_that_deepens_the_critical_path_is_discarded(fake_llm_adapter_factory, monkeypatch):
    _force_selection(monkeypatch, [COVERAGE_CRITIC_V1])
    draft = _multi_plan([("A", []), ("B", ["A"])])  # depth 2
    deeper = _multi_plan([("A", []), ("B", ["A"]), ("C", ["B"])])  # depth 3
    adapter = fake_llm_adapter_factory([draft, _critic(["something is missing"]), deeper])

    output = await _run(adapter)

    assert _step_ids(output) == ["A", "B"]
    assert "planner_council_synth_discarded_deeper_plan" in output.warnings


async def test_synthesis_adding_a_parallel_step_is_kept(fake_llm_adapter_factory, monkeypatch):
    # The coverage critic's legitimate case: a genuinely missing step that
    # depends on nothing runs alongside the others and costs no extra hop.
    # Gating on step count would wrongly reject this; gating on depth keeps it.
    _force_selection(monkeypatch, [COVERAGE_CRITIC_V1])
    draft = _multi_plan([("A", []), ("B", ["A"])])  # depth 2
    wider = _multi_plan([("A", []), ("B", ["A"]), ("C", [])])  # depth 2, wider

    adapter = fake_llm_adapter_factory([draft, _critic(["you never fetch C"]), wider])

    output = await _run(adapter)

    assert _step_ids(output) == ["A", "B", "C"]
    assert "planner_council_synthesized" in output.warnings


async def test_synthesis_serializing_a_parallel_branch_is_discarded(fake_llm_adapter_factory, monkeypatch):
    # The exact `credits_remaining` regression: same step count, but a branch
    # that could run in parallel is made to wait on another.
    _force_selection(monkeypatch, [COVERAGE_CRITIC_V1])
    draft = _multi_plan([("A", []), ("B", [])])  # depth 1, both parallel
    serialized = _multi_plan([("A", []), ("B", ["A"])])  # depth 2, same count

    adapter = fake_llm_adapter_factory([draft, _critic(["B should follow A"]), serialized])

    output = await _run(adapter)

    assert _step_ids(output) == ["A", "B"]
    assert "planner_council_synth_discarded_deeper_plan" in output.warnings


async def test_synthesis_that_flattens_the_plan_is_kept(fake_llm_adapter_factory, monkeypatch):
    _force_selection(monkeypatch, [COVERAGE_CRITIC_V1])
    draft = _multi_plan([("A", []), ("B", ["A"]), ("C", ["B"])])  # depth 3
    flatter = _multi_plan([("A", []), ("B", ["A"]), ("C", ["A"])])  # depth 2

    adapter = fake_llm_adapter_factory([draft, _critic(["C need not wait on B"]), flatter])

    output = await _run(adapter)

    assert _step_ids(output) == ["A", "B", "C"]
    assert "planner_council_synthesized" in output.warnings


# ── Orchestration (selection monkeypatched to one critic) ────────────────────


async def test_clean_draft_with_no_findings_returns_draft_and_skips_synth(fake_llm_adapter_factory, monkeypatch):
    # The one selected critic finds nothing -> the draft stands and the
    # synthesizer is never called (the gate saves that call).
    _force_selection(monkeypatch, [COVERAGE_CRITIC_V1])
    adapter = fake_llm_adapter_factory([_plan(), _critic([])])

    output = await _run(adapter)

    assert [s.step_id for s in output.next_steps] == ["A"]
    assert output.plan_status == "in_progress"
    assert not any("Synthesizer" in sp for sp in _system_prompts(adapter))
    assert "planner_council_synthesized" not in output.warnings


async def test_critic_findings_trigger_synthesis(fake_llm_adapter_factory, monkeypatch):
    # A selected critic flags an issue -> the synthesizer runs and its revised
    # plan is returned (not the draft).
    _force_selection(monkeypatch, [COVERAGE_CRITIC_V1])
    revised = _plan(step_id="A", objective="Retrieve completed courses AND current standing.")
    adapter = fake_llm_adapter_factory([_plan(), _critic(["step A is missing the standing lookup"]), revised])

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


async def test_synthesizer_failure_falls_back_to_the_vetted_draft(fake_llm_adapter_factory, monkeypatch):
    # A critic flags an issue so the synthesizer runs, but the synthesizer's
    # output is malformed (pass + its one repair) -> the already-valid draft
    # is returned rather than a clarification block.
    _force_selection(monkeypatch, [COVERAGE_CRITIC_V1])
    adapter = fake_llm_adapter_factory(
        [_plan(), _critic(["needs a standing lookup"]),
         {"plan_status": "not_a_real_status"}, {"plan_status": "not_a_real_status"}]
    )

    output = await _run(adapter)

    assert [s.step_id for s in output.next_steps] == ["A"]
    assert output.plan_status == "in_progress"
    assert "planner_council_synth_discarded" in output.warnings


async def test_selected_critic_failing_degrades_to_the_draft(fake_llm_adapter_factory, monkeypatch):
    # Only the draft response is queued; the one selected critic exhausts the
    # adapter and fails closed to no findings -> the draft stands, no synth.
    _force_selection(monkeypatch, [COVERAGE_CRITIC_V1])
    adapter = fake_llm_adapter_factory([_plan()])

    output = await _run(adapter)

    assert [s.step_id for s in output.next_steps] == ["A"]
    assert not any("Synthesizer" in sp for sp in _system_prompts(adapter))
    assert len(adapter.calls) == 2  # draft + one attempted (exhausted) critic call


async def test_routine_continuation_skips_the_council(fake_llm_adapter_factory):
    # A later invocation with no replan flags is a routine continuation:
    # only the fast drafter runs -- no validator, no critics, no synth.
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


async def test_replan_on_a_later_invocation_still_reviews(fake_llm_adapter_factory, monkeypatch):
    # Even past the first invocation, a Monitor-flagged replan re-engages the
    # review path -- the previous attempt hit a problem, so plan shape matters.
    _force_selection(monkeypatch, [COVERAGE_CRITIC_V1])
    replan_input = _INPUT.model_copy(
        update={"monitor_flags": ["step 1a failed"], "replan_reason": "step 1a failed"}
    )
    adapter = fake_llm_adapter_factory([_plan(), _critic([])])

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


# ── Real selector, end-to-end ────────────────────────────────────────────────


async def test_clean_first_invocation_runs_only_the_floor_critics(fake_llm_adapter_factory):
    # A clean, high-confidence draft with neutral signals falls to the floor:
    # coverage + parsimony (two critics), NOT all six. Only the draft response
    # is queued, so both floor critics exhaust and fail closed.
    neutral = PlannerInvocationInput(
        user_goal="say hello to the person", original_user_message="say hello", confidence=0.95
    )
    adapter = fake_llm_adapter_factory([_plan(objective="greet the person warmly")])

    await _run(adapter, neutral)

    assert len(adapter.calls) == 3  # draft + exactly two floor critics
    prompts = _system_prompts(adapter)
    assert any("Coverage Critic" in sp for sp in prompts)
    assert any("Parsimony Critic" in sp for sp in prompts)


async def test_domain_signal_selects_the_domain_critic(fake_llm_adapter_factory):
    # A prerequisite/eligibility question routes the domain critic in.
    pi = PlannerInvocationInput(
        user_goal="Am I eligible? check the prerequisite rules",
        original_user_message="Am I eligible?",
        confidence=0.95,
    )
    adapter = fake_llm_adapter_factory([_plan(objective="evaluate prerequisite eligibility for the course")])

    await _run(adapter, pi)

    assert any("Domain Critic" in sp for sp in _system_prompts(adapter))
