"""Live evaluation suite for `PlannerReasoningBlock`.

Unlike every other `agent_core` test, this makes REAL calls to a configured
LLM (via `ChatLLMAdapter`) instead of `FakeLLMAdapter` -- costs money, has
real latency, and is non-deterministic. Deselected by default (see
`pytest.ini`'s `-m "not live"`); run explicitly with `pytest -m live`.
Requires `OPENAI_API_KEY` (and friends) to be configured -- skipped entirely
otherwise. Mirrors `test_request_understanding_live_eval.py`'s own pattern.

Every call this file makes goes through `LoggingLLMAdapter`
(`live_eval_logging.py`), so the full prompt/response detail behind each
case is written to `tests/agent_core/live_eval_logs/` on teardown, not just
visible transiently in terminal output.

These cases are a starting set, not battle-tested the way RU's 15 are yet --
this is exactly what a live-eval harness is for: run it, see what the
contract's instructions actually produce against real cases, and tighten or
loosen assertions (and the contract's own instructions in `planner.py`)
based on real signal, not more guessing. Assertions are property-based, not
exact-match, since LLM output varies run to run.
"""

from __future__ import annotations

import pytest

from app.agent_core.planning.planner import build_next_plan_steps
from app.agent_core.planning.schemas import PlanGraph, PlannerInvocationInput, PlannerInvocationOutput, StateEntrySummary
from app.agent_core.reasoning.llm_client import agent_llm_available
from tests.agent_core.live_eval_logging import LiveEvalLog, LoggingLLMAdapter

pytestmark = [
    pytest.mark.live,
    pytest.mark.skipif(not agent_llm_available(), reason="no LLM credentials configured (OPENAI_API_KEY)"),
]


@pytest.fixture(scope="module")
def live_eval_log():
    log = LiveEvalLog(suite_name="planner_only")
    yield log
    log.write()


@pytest.fixture
def adapter() -> LoggingLLMAdapter:
    return LoggingLLMAdapter()


def _assert_graph_is_internally_consistent(output: PlannerInvocationOutput) -> None:
    """Structural invariants any well-formed output must satisfy, regardless
    of what the LLM actually decided to plan."""
    step_ids = {step.step_id for step in output.next_steps}
    assert step_ids == set(output.plan_graph.forward.keys())
    layered_ids = {step_id for layer in output.plan_graph.execution_layers for step_id in layer}
    assert layered_ids == step_ids
    for step in output.next_steps:
        assert step.step_id.startswith("1")


async def test_worked_example_produces_well_formed_independent_steps(
    adapter: LoggingLLMAdapter, live_eval_log: LiveEvalLog
) -> None:
    """PLANNER_OUTPUT_DESIGN.md §7's own worked example. First real run
    (2025) produced a well-formed but more conservative 2-step batch
    (course record + failure policy) than the doc's illustrative 6-step
    example, and neither real run fetched the student's own current state --
    which the doc's own reasoning says belongs in round 1 regardless of what
    the other facts turn out to say (added to the contract's instructions).
    Exact step count/shape isn't pinned here -- that varies run to run and
    across models -- this checks structural well-formedness only."""
    planner_input = PlannerInvocationInput(
        user_goal="What happens if I fail Data Structures this semester?",
        original_user_message="What happens if I fail Data Structures this semester?",
        sub_asks=["What are the consequences if I fail the Data Structures course this semester?"],
        confidence=0.95,
    )
    output = await build_next_plan_steps(
        planner_input=planner_input, llm_adapter=adapter, block_id="eval-worked-example", invocation=1
    )
    live_eval_log.record_case("worked_example", adapter, planner_input=planner_input, output=output)

    assert output.plan_status in ("in_progress", "complete")
    assert len(output.next_steps) >= 2
    _assert_graph_is_internally_consistent(output)


async def test_simple_request_can_reach_complete_in_one_invocation(
    adapter: LoggingLLMAdapter, live_eval_log: LiveEvalLog
) -> None:
    planner_input = PlannerInvocationInput(
        user_goal="What is the credit value of course 234218?",
        original_user_message="What is the credit value of course 234218?",
        sub_asks=["What is the credit value of course 234218?"],
        confidence=0.95,
    )
    output = await build_next_plan_steps(
        planner_input=planner_input, llm_adapter=adapter, block_id="eval-simple-request", invocation=1
    )
    live_eval_log.record_case("simple_request", adapter, planner_input=planner_input, output=output)

    assert output.plan_status in ("complete", "in_progress")
    assert output.next_steps
    _assert_graph_is_internally_consistent(output)


async def test_genuine_ambiguity_blocks_for_clarification(
    adapter: LoggingLLMAdapter, live_eval_log: LiveEvalLog
) -> None:
    planner_input = PlannerInvocationInput(
        user_goal="Is it worth it compared to the other one?",
        original_user_message="Is it worth it compared to the other one?",
        sub_asks=["Is it worth it compared to the other one?"],
        open_questions=["'The other one' has no established referent in this conversation."],
        confidence=0.4,
    )
    output = await build_next_plan_steps(
        planner_input=planner_input, llm_adapter=adapter, block_id="eval-genuine-ambiguity", invocation=1
    )
    live_eval_log.record_case("genuine_ambiguity", adapter, planner_input=planner_input, output=output)

    assert output.plan_status == "blocked_needs_clarification"
    assert output.clarification_question


async def test_action_request_does_not_conclude_already_done(
    adapter: LoggingLLMAdapter, live_eval_log: LiveEvalLog
) -> None:
    planner_input = PlannerInvocationInput(
        user_goal="Register me for course 234218 this semester.",
        original_user_message="Register me for course 234218 this semester.",
        sub_asks=["Register the student for course 234218 this semester."],
        implies_action_request=True,
        confidence=0.9,
    )
    output = await build_next_plan_steps(
        planner_input=planner_input, llm_adapter=adapter, block_id="eval-action-request", invocation=1
    )
    live_eval_log.record_case("action_request", adapter, planner_input=planner_input, output=output)

    # Regression guard: a state-changing request must never be treated as
    # already fulfilled with zero steps -- some work (at minimum, a proposal
    # step) is always required. plan_status may legitimately be "complete"
    # if a single proposal step is the entire plan -- "complete" doesn't
    # mean the action itself was performed, only that the plan (which ends
    # in a proposal) is fully specified.
    assert output.plan_status in ("in_progress", "complete")
    assert output.next_steps
    _assert_graph_is_internally_consistent(output)


async def test_two_sub_asks_produce_a_reasonably_scoped_batch(
    adapter: LoggingLLMAdapter, live_eval_log: LiveEvalLog
) -> None:
    """Two sub_asks that partially overlap in what they need (both need the
    student's completed-course record; each also needs its own distinct
    fact). After the contract's same-round-synthesis instruction was added,
    a real run correctly produced a full multi-layer plan (fact-gathering
    steps, then steps that compute/compare across them, then a final
    synthesis step) rather than stopping at fact-gathering alone -- the real
    regression to guard against is runaway duplication, not a specific step
    count (which depends on how many facts and derived comparisons the
    request genuinely needs, not something this test can know in advance)."""
    planner_input = PlannerInvocationInput(
        user_goal=(
            "What courses do I still need for my degree, and separately, am I on track to "
            "graduate on time?"
        ),
        original_user_message=(
            "What courses do I still need for my degree, and separately, am I on track to "
            "graduate on time?"
        ),
        sub_asks=[
            "What courses does the student still need to complete their degree?",
            "Is the student on track to graduate on time?",
        ],
        confidence=0.9,
    )
    output = await build_next_plan_steps(
        planner_input=planner_input, llm_adapter=adapter, block_id="eval-shared-fact", invocation=1
    )
    live_eval_log.record_case("two_sub_asks", adapter, planner_input=planner_input, output=output)

    assert output.next_steps
    # Sanity ceiling against genuine runaway duplication -- not a judgment
    # about how many steps legitimate, fully-elaborated work needs. A
    # correctly aggressive plan for this case (per the contract's
    # instruction to include same-round compute/synthesis steps once their
    # shape is known) can reasonably reach a full multi-layer chain in one
    # round. Under the council architecture the coverage critic pushes the
    # drafter toward covering BOTH sub-asks fully in one batch, so a
    # legitimately elaborated, non-duplicated plan was observed at 11 steps
    # across a 5-layer graph (profile/completed/calendar fact-gathering ->
    # requirement interpretation -> remaining-course + credit + semester
    # computations -> on-track assessment). The ceiling guards only against
    # true runaway (20+), never this healthy elaboration.
    assert len(output.next_steps) <= 15
    _assert_graph_is_internally_consistent(output)


async def test_existing_completed_step_is_referenced_not_rebuilt(
    adapter: LoggingLLMAdapter, live_eval_log: LiveEvalLog
) -> None:
    """A second invocation, seeded with a prior invocation's already-completed
    step -- regression guard against re-inventing a local label for
    something that already exists in plan_graph_so_far/state_index."""
    planner_input = PlannerInvocationInput(
        user_goal="Now project how this affects my graduation timeline.",
        original_user_message="What happens if I fail Data Structures this semester?",
        sub_asks=["Project how a Data Structures failure affects the student's graduation timeline."],
        state_index=[
            StateEntrySummary(
                entry_id="1a-0",
                step_id="1a",
                role="retrieval",
                summary="succeeded (generic_step_output_v1)",
                certainty_band="high",
            )
        ],
        plan_graph_so_far=PlanGraph(forward={"1a": []}, dependents={"1a": []}, execution_layers=[["1a"]]),
        confidence=0.9,
    )
    output = await build_next_plan_steps(
        planner_input=planner_input, llm_adapter=adapter, block_id="eval-existing-state", invocation=2
    )
    live_eval_log.record_case("existing_state", adapter, planner_input=planner_input, output=output)

    assert output.next_steps
    all_deps = {dep for step in output.next_steps for dep in step.depends_on}
    # If the new steps need the prior step's result at all, they must
    # reference it by its real id -- never a fresh, unresolved local label
    # that happens to collide/duplicate the same fact.
    assert all(dep == "1a" or dep.startswith("2") for dep in all_deps)
