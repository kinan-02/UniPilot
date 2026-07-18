"""Proves `orchestrator/loop.py::run_plan_to_completion` actually dispatches
same-layer top-level steps CONCURRENTLY, not sequentially -- the top-level
parallelism retrofit. Mirrors `test_orchestrator_parallel_dispatch.py`'s own
"two sleeps take ~one sleep, not two" technique, applied at the
`run_plan_to_completion` level rather than the generic `dispatch_layer_concurrently`
utility, since that utility was already proven correct in isolation but
`loop.py` previously never called it at all (steps were dispatched via a
plain sequential `for` loop, ignoring `plan_graph.execution_layers` entirely).

Both `build_next_plan_steps` and `run_task_handler` are monkeypatched at the
`loop` module level -- consistent with this codebase's established
"monkeypatch the collaborator, not the LLM" convention for orchestration-logic
tests (see `test_orchestrator_task_handler.py`)."""

from __future__ import annotations

import asyncio
from datetime import datetime, timezone

import pytest

from app.agent_core.orchestrator import loop as loop_module
from app.agent_core.planning.schemas import PlanGraph, PlannerInvocationOutput, PlanStep, RoleName
from app.agent_core.certainty import CertaintyTag
from app.agent_core.planning.state import StateEntry
from app.agent_core.subagents.schemas import SubagentResult
from app.agent_core.turn_context import TurnContext


def _ctx(**overrides) -> TurnContext:
    """The turn wiring these tests don't exercise.

    `llm`/`tools` are None and `roles` is a stub because every collaborator that
    would touch them (`build_next_plan_steps`, `run_task_handler`, `route_plan`,
    `compose_answer`) is monkeypatched per-test. Pass `replans=` to assert on a
    ledger the test holds a reference to -- otherwise the context makes its own,
    exactly as a real turn does."""
    return TurnContext(
        **{
            "plan_id": "p",
            "user_id": "u",
            "original_user_message": "m",
            "llm": None,
            "tools": None,
            "roles": {"composition": object()},
            **overrides,
        }
    )

_SLEEP_SECONDS = 0.05


def _never_completes(step_id: str = "a") -> PlannerInvocationOutput:
    step = PlanStep(step_id=step_id, objective="resolve X", depends_on=[], success_criteria=[])
    return PlannerInvocationOutput(
        plan_status="in_progress",  # never reaches "complete" -> budget exhausts
        next_steps=[step],
        plan_summary="",
        plan_graph=PlanGraph(forward={step_id: []}, dependents={}, execution_layers=[[step_id]]),
    )


def _fake_composed(answer: str = "best-effort answer from partial state") -> SubagentResult:
    return SubagentResult(
        status="succeeded",
        result={"answer_text": answer},
        certainty=CertaintyTag(basis="llm_interpretation", confidence=0.5),
        assumptions=[],
        warnings=[],
        tool_audit_trail=[],
    )


def _entry(step_id: str, *, role: RoleName = "retrieval", status: str = "succeeded") -> StateEntry:
    return StateEntry(
        entry_id=f"{step_id}-0",
        step_id=step_id,
        role=role,
        status=status,
        output_schema_name="generic_step_output_v1",
        # A composition entry needs a real `answer_text` to be treated as the
        # turn's answer: loop.py's short-circuit now checks that it actually SAID
        # something, after a live run returned an empty composition entry
        # verbatim and the student got a blank reply. A test leaning on that
        # short-circuit as a convenient plan exit has to answer something.
        data={"answer_text": f"answer from {step_id}"} if role == "composition" else {},
        certainty=CertaintyTag(basis="official_record", confidence=0.9),
        produced_at=datetime.now(timezone.utc),
    )


@pytest.fixture(autouse=True)
def _stub_plan_router(monkeypatch: pytest.MonkeyPatch) -> None:
    """`route_plan` is a loop collaborator exactly like `build_next_plan_steps`
    and `run_task_handler`, so it is stubbed for the same reason (see module
    docstring): these tests exercise orchestration LOGIC, and pass
    `llm_adapter=None` precisely because no LLM should be reached.

    Returning `{}` means "nothing precomputed" -- the same best-effort miss
    `route_plan` reports on any failure, and the case the task handler is built
    to fall back from. Without this, most of these tests still passed, but only
    because that fail-open path swallowed a doomed call against a null adapter.
    """

    async def _no_precomputed_routes(**_kwargs: object) -> dict[str, list]:
        return {}

    monkeypatch.setattr(loop_module, "route_plan", _no_precomputed_routes)


@pytest.mark.asyncio
async def test_same_layer_steps_dispatch_concurrently_not_sequentially(monkeypatch: pytest.MonkeyPatch) -> None:
    step_a = PlanStep(step_id="a", objective="fetch A", depends_on=[], success_criteria=[])
    step_b = PlanStep(step_id="b", objective="fetch B", depends_on=[], success_criteria=[])
    # step_b's entry is role="composition" so the plan ends via loop.py's own
    # composition short-circuit -- keeps this test scoped to proving
    # concurrent dispatch, without also having to fake out compose_answer.
    planner_output = PlannerInvocationOutput(
        plan_status="complete",
        next_steps=[step_a, step_b],
        plan_summary="two independent fetches",
        plan_graph=PlanGraph(forward={"a": [], "b": []}, dependents={}, execution_layers=[["a", "b"]]),
    )

    dispatched_concurrently: list[str] = []

    async def fake_build_next_plan_steps(**_kwargs: object) -> PlannerInvocationOutput:
        return planner_output

    async def fake_run_task_handler(*, step: PlanStep, **_kwargs: object) -> StateEntry:
        dispatched_concurrently.append(step.step_id)
        await asyncio.sleep(_SLEEP_SECONDS)
        return _entry(step.step_id, role="composition" if step.step_id == "b" else "retrieval")

    monkeypatch.setattr(loop_module, "build_next_plan_steps", fake_build_next_plan_steps)
    monkeypatch.setattr(loop_module, "run_task_handler", fake_run_task_handler)

    event_loop = asyncio.get_event_loop()
    start = event_loop.time()
    state, final_entry, clarification_question = await loop_module.run_plan_to_completion(
        ctx=_ctx(
            plan_id="test-plan",
            user_id="test-user-1",
            original_user_message="test message",
            llm=None,  # never touched -- build_next_plan_steps is monkeypatched
            roles={},  # never touched -- compose_answer's fallback path is short-circuited
            tools=None,  # never touched -- run_task_handler is monkeypatched
        ),
        user_goal="test goal",
    )
    elapsed = event_loop.time() - start

    assert elapsed < _SLEEP_SECONDS * 1.8, (
        f"expected ~{_SLEEP_SECONDS}s for two concurrently-dispatched steps, took {elapsed}s -- "
        "looks like same-layer steps are still being dispatched sequentially"
    )
    assert dispatched_concurrently == ["a", "b"]
    assert {entry.step_id for entry in state.entries} == {"a", "b"}
    assert final_entry is not None and final_entry.step_id == "b"


@pytest.mark.asyncio
async def test_budget_exhaustion_composes_from_state_instead_of_returning_none(monkeypatch: pytest.MonkeyPatch) -> None:
    """A turn that never reaches plan_status='complete' (e.g. it keeps
    re-trying an unresolvable entity until the invocation budget runs out) must
    still compose a best-effort answer from whatever the plan established --
    never return an empty turn (final_entry=None, no clarification)."""
    async def fake_build_next_plan_steps(**_kwargs: object) -> PlannerInvocationOutput:
        return _never_completes()

    async def fake_run_task_handler(*, step: PlanStep, **_kwargs: object) -> StateEntry:
        return _entry(step.step_id, role="retrieval")

    async def fake_compose_answer(**_kwargs: object) -> SubagentResult:
        return _fake_composed()

    monkeypatch.setattr(loop_module, "build_next_plan_steps", fake_build_next_plan_steps)
    monkeypatch.setattr(loop_module, "run_task_handler", fake_run_task_handler)
    monkeypatch.setattr(loop_module, "compose_answer", fake_compose_answer)

    state, final_entry, clarification_question = await loop_module.run_plan_to_completion(
        ctx=_ctx(),
        user_goal="g",
        max_planner_invocations=2,
    )

    assert clarification_question is None
    assert final_entry is not None, "budget exhaustion must not return an empty turn"
    assert final_entry.data.get("answer_text") == "best-effort answer from partial state"


@pytest.mark.asyncio
async def test_final_round_flag_only_on_the_last_invocation(monkeypatch: pytest.MonkeyPatch) -> None:
    captured_final_round: list[bool] = []
    captured_flags: list[list[str]] = []

    async def fake_build_next_plan_steps(*, planner_input, **_kwargs: object) -> PlannerInvocationOutput:
        captured_final_round.append(planner_input.final_round)
        captured_flags.append(list(planner_input.monitor_flags))
        return _never_completes()

    async def fake_run_task_handler(*, step: PlanStep, **_kwargs: object) -> StateEntry:
        return _entry(step.step_id, role="retrieval")

    async def fake_compose_answer(**_kwargs: object) -> SubagentResult:
        return _fake_composed()

    monkeypatch.setattr(loop_module, "build_next_plan_steps", fake_build_next_plan_steps)
    monkeypatch.setattr(loop_module, "run_task_handler", fake_run_task_handler)
    monkeypatch.setattr(loop_module, "compose_answer", fake_compose_answer)

    await loop_module.run_plan_to_completion(
        ctx=_ctx(),
        user_goal="g",
        max_planner_invocations=3,
    )

    # final_round is set ONLY on the last round -- earlier rounds keep exploring.
    assert captured_final_round == [False, False, True]
    # And it never leaks into monitor_flags (which would trip the council gate).
    assert all(flag == [] for flag in captured_flags)


@pytest.mark.asyncio
async def test_repeatedly_failing_step_becomes_an_exhausted_step(monkeypatch: pytest.MonkeyPatch) -> None:
    """W3a escalation guard: a step whose objective keeps failing is recorded
    in the ReplanLedger; once it has been re-attempted to the threshold, its
    objective is surfaced to the Planner as an `exhausted_step` -- and never
    leaks into `monitor_flags` (which would trip the council gate).

    The ledger under test is the one `TurnContext` makes by default, which is
    the same one a real turn gets -- this used to pass its own instance in."""
    captured_exhausted: list[list[str]] = []
    captured_flags: list[list[str]] = []

    async def fake_build_next_plan_steps(*, planner_input, **_kwargs: object) -> PlannerInvocationOutput:
        captured_exhausted.append(list(planner_input.exhausted_steps))
        captured_flags.append(list(planner_input.monitor_flags))
        return _never_completes()  # re-emits objective "resolve X" every round

    async def fake_run_task_handler(*, step: PlanStep, **_kwargs: object) -> StateEntry:
        return _entry(step.step_id, role="retrieval", status="failed")  # forces a replan each round

    async def fake_compose_answer(**_kwargs: object) -> SubagentResult:
        return _fake_composed()

    monkeypatch.setattr(loop_module, "build_next_plan_steps", fake_build_next_plan_steps)
    monkeypatch.setattr(loop_module, "run_task_handler", fake_run_task_handler)
    monkeypatch.setattr(loop_module, "compose_answer", fake_compose_answer)

    await loop_module.run_plan_to_completion(
        ctx=_ctx(),
        user_goal="g",
        max_planner_invocations=4,
    )

    # Rounds 1 and 2 build the count; by round 3 the objective is exhausted.
    assert captured_exhausted[0] == []
    assert captured_exhausted[1] == []
    assert captured_exhausted[2] == ["resolve X"]
    # The exhausted objective never appears in monitor_flags.
    assert all("resolve X" not in flag for flags in captured_flags for flag in flags)


def _completes_with(step_id: str = "a") -> PlannerInvocationOutput:
    step = PlanStep(step_id=step_id, objective="resolve X", depends_on=[], success_criteria=[])
    return PlannerInvocationOutput(
        plan_status="complete",
        next_steps=[step],
        plan_summary="",
        plan_graph=PlanGraph(forward={step_id: []}, dependents={}, execution_layers=[[step_id]]),
    )


@pytest.mark.asyncio
async def test_partial_step_replans_even_when_the_planner_said_complete(monkeypatch: pytest.MonkeyPatch) -> None:
    """A step that comes back `partial` must re-invoke the Planner, even when
    that round's plan_status was already "complete".

    Regression for a live incident (2026-07-16, ise_correctness
    `offering_pattern`): a composition step returned `partial` with `data={}`
    via the task handler's empty-dependency-context guard -- whose own comment
    says it fails partial "so the Monitor replans, rather than emitting a
    confident wrong answer". No replan came. The Monitor DID return "clarify",
    but that branch recorded the flags and the failed step id without ever
    setting `should_replan`, so "complete" won the round and the unmet criteria
    were collected and then dropped. The student got "".

    The `failed` path was never affected -- only `partial`/`clarify` -- which is
    why this went unnoticed: every test that forced a replan forced it with a
    `failed` status.
    """
    captured_focus: list[object] = []
    captured_flags: list[list[str]] = []

    async def fake_build_next_plan_steps(*, planner_input, **_kwargs: object) -> PlannerInvocationOutput:
        captured_focus.append(planner_input.replan_focus)
        captured_flags.append(list(planner_input.monitor_flags))
        return _completes_with("a")

    async def fake_run_task_handler(*, step: PlanStep, **_kwargs: object) -> StateEntry:
        return _entry(step.step_id, role="retrieval", status="partial")

    async def fake_compose_answer(**_kwargs: object) -> SubagentResult:
        return _fake_composed()

    monkeypatch.setattr(loop_module, "build_next_plan_steps", fake_build_next_plan_steps)
    monkeypatch.setattr(loop_module, "run_task_handler", fake_run_task_handler)
    monkeypatch.setattr(loop_module, "compose_answer", fake_compose_answer)

    await loop_module.run_plan_to_completion(
        ctx=_ctx(),
        user_goal="g",
        max_planner_invocations=2,
    )

    assert len(captured_focus) == 2, (
        "a `partial` step must trigger a replan -- the Planner was only invoked "
        f"{len(captured_focus)}x, so plan_status='complete' ended the turn while a "
        "step was still unsatisfied"
    )
    # The replan is SCOPED to the partial step, exactly as a `failed` one is.
    focus = captured_focus[1]
    assert focus is not None
    assert focus.failed_step_ids == ["a"]
    # ...and the Planner is actually TOLD what fell short, rather than being
    # re-invoked with an empty hand.
    assert captured_flags[1] == ["step a partial or did not fully satisfy its success criteria"]


def _two_independent_steps() -> PlannerInvocationOutput:
    a = PlanStep(step_id="a", objective="resolve X", depends_on=[], success_criteria=[])
    b = PlanStep(step_id="b", objective="fetch Y", depends_on=[], success_criteria=[])
    return PlannerInvocationOutput(
        plan_status="in_progress",
        next_steps=[a, b],
        plan_summary="",
        plan_graph=PlanGraph(forward={"a": [], "b": []}, dependents={}, execution_layers=[["a", "b"]]),
    )


@pytest.mark.asyncio
async def test_replan_focus_scopes_the_next_invocation(monkeypatch: pytest.MonkeyPatch) -> None:
    """W3b scoped replan: when a step fails alongside a step that succeeded, the
    NEXT invocation's `replan_focus` names the failed step and protects the
    completed one, so the Planner repairs only the failed region."""
    captured_focus: list[object] = []

    async def fake_build_next_plan_steps(*, planner_input, **_kwargs: object) -> PlannerInvocationOutput:
        captured_focus.append(planner_input.replan_focus)
        return _two_independent_steps() if len(captured_focus) == 1 else _never_completes()

    async def fake_run_task_handler(*, step: PlanStep, **_kwargs: object) -> StateEntry:
        return _entry(step.step_id, status="failed" if step.step_id == "a" else "succeeded")

    async def fake_compose_answer(**_kwargs: object) -> SubagentResult:
        return _fake_composed()

    monkeypatch.setattr(loop_module, "build_next_plan_steps", fake_build_next_plan_steps)
    monkeypatch.setattr(loop_module, "run_task_handler", fake_run_task_handler)
    monkeypatch.setattr(loop_module, "compose_answer", fake_compose_answer)

    await loop_module.run_plan_to_completion(
        ctx=_ctx(),
        user_goal="g",
        max_planner_invocations=2,
    )

    assert captured_focus[0] is None  # first invocation: nothing failed yet
    focus = captured_focus[1]
    assert focus is not None
    assert focus.failed_step_ids == ["a"]
    assert focus.protected_step_ids == ["b"]
