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
from app.agent_core.planning.state import CertaintyTag, StateEntry

_SLEEP_SECONDS = 0.05


def _entry(step_id: str, *, role: RoleName = "retrieval") -> StateEntry:
    return StateEntry(
        entry_id=f"{step_id}-0",
        step_id=step_id,
        role=role,
        status="succeeded",
        output_schema_name="generic_step_output_v1",
        data={},
        certainty=CertaintyTag(basis="official_record", confidence=0.9),
        produced_at=datetime.now(timezone.utc),
    )


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
        user_goal="test goal",
        original_user_message="test message",
        user_id="test-user-1",
        llm_adapter=None,  # never touched -- build_next_plan_steps is monkeypatched
        role_roster={},  # never touched -- compose_answer's fallback path is short-circuited
        tool_registry=None,  # never touched -- run_task_handler is monkeypatched
        plan_id="test-plan",
    )
    elapsed = event_loop.time() - start

    assert elapsed < _SLEEP_SECONDS * 1.8, (
        f"expected ~{_SLEEP_SECONDS}s for two concurrently-dispatched steps, took {elapsed}s -- "
        "looks like same-layer steps are still being dispatched sequentially"
    )
    assert dispatched_concurrently == ["a", "b"]
    assert {entry.step_id for entry in state.entries} == {"a", "b"}
    assert final_entry is not None and final_entry.step_id == "b"
