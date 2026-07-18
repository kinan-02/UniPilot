"""Tests for `app.agent_core.orchestrator.task_handler`
(docs/planning/SPECIALIST_ROUTER_PLANNER_SPLIT_PLAN.md).

Isolates `task_handler.py`'s own orchestration logic (route -> atomic fast
path OR pipeline execution -> success-check -> aggregate; the bounded repair
round loop; the depth-cap invariant) by monkeypatching its own module-level
references to `route_step`, `check_success_criteria`, and
`_dispatch_single_specialist`. The specialist-dispatch chain
(context_builder -> run_subagent) is covered end-to-end by
`test_skeleton_end_to_end.py`; the router and success-check primitives have
their own dedicated test files.
"""

from __future__ import annotations

import inspect
from datetime import datetime, timezone

from app.agent_core.orchestrator import task_handler as task_handler_module
from app.agent_core.orchestrator.specialist_router import RoutedSubStep, SpecialistRouterOutput
from app.agent_core.orchestrator.task_handler import run_task_handler
from app.agent_core.planning.schemas import PlanStep
from app.agent_core.certainty import CertaintyTag
from app.agent_core.planning.state import PlanExecutionState, StateEntry
from app.agent_core.roles.roster import build_default_role_roster
from app.agent_core.subagents.schemas import (
    ReasoningParamsOverride,
    StepInstructionFields,
    StepPrepOutput,
    SubagentResult,
)
from app.agent_core.tools.default_registry import build_default_tool_registry
from app.agent_core.turn_context import TurnContext

ROLE_ROSTER = build_default_role_roster()
TOOL_REGISTRY = build_default_tool_registry()


def _ctx(**overrides) -> TurnContext:
    """The turn wiring these tests don't care about.

    `llm` is a bare object(): every LLM-touching collaborator on this path
    (`route_step`, `check_success_criteria`, `_dispatch_single_specialist`) is
    monkeypatched, so a real adapter would never be called -- and if one ever
    were, `object()` fails loudly rather than quietly doing something."""
    return TurnContext(
        **{
            "plan_id": "p1",
            "user_id": "test-user-1",
            "original_user_message": "hello",
            "llm": object(),
            "tools": TOOL_REGISTRY,
            "roles": ROLE_ROSTER,
            **overrides,
        }
    )


def _step(step_id="1a", depends_on=None, success_criteria=None, assumptions=None) -> PlanStep:
    return PlanStep(
        step_id=step_id,
        objective="do the thing",
        depends_on=depends_on or [],
        success_criteria=success_criteria if success_criteria is not None else ["thing done"],
        assumptions_to_verify=assumptions or [],
    )


def _entry(step_id: str, confidence: float = 0.9, status: str = "succeeded") -> StateEntry:
    return StateEntry(
        entry_id=f"{step_id}-0",
        step_id=step_id,
        role="retrieval",
        status=status,
        output_schema_name="generic_step_output_v1",
        data={},
        certainty=CertaintyTag(basis="wiki_derived", confidence=confidence),
        produced_at=datetime.now(timezone.utc),
    )


def _dummy_step_prep_output(context_requirements: list[str] | None = None) -> StepPrepOutput:
    return StepPrepOutput(
        instruction_fields=StepInstructionFields(goal="g", description="d", specific_instructions=[]),
        context_requirements=context_requirements or [],
        reasoning_params=ReasoningParamsOverride(),
        output_schema_name="generic_step_output_v1",
        output_schema={"type": "object"},
        tool_grant_override=None,
    )


def _subagent_result(status="succeeded", data=None, confidence=0.9, basis="wiki_derived", warnings=None) -> SubagentResult:
    return SubagentResult(
        status=status,
        result=data or {},
        certainty=CertaintyTag(basis=basis, confidence=confidence),
        assumptions=[],
        warnings=warnings or [],
        tool_audit_trail=[],
    )


def _sub(sub_step_id, specialist="retrieval", *, depends_on=None, objective="do it") -> dict:
    return {
        "sub_step_id": sub_step_id,
        "specialist": specialist,
        "objective": objective,
        "depends_on": depends_on or [],
        "success_criteria": ["done"],
    }


async def _run(monkeypatch, step, *, state=None, route, dispatch=None, check=None, precomputed_route=None):
    """Drives `run_task_handler`, faking its three collaborators.

    - `route`: the pipeline (a list of `_sub(...)` dicts) the router returns.
      The task handler routes exactly once per step (no repair loop).
    - `dispatch`: dict step_id -> [SubagentResult] popped per call (keyed by the
      PARENT step_id for the atomic path, by sub_step_ids in a pipeline).
    - `check`: dict step_id -> [bool] popped per success-check call.

    Returns `(entry, route_dependency_contexts)`.
    """
    state = state if state is not None else PlanExecutionState(plan_id="p1")
    dispatch = {k: list(v) for k, v in (dispatch or {}).items()}
    check = {k: list(v) for k, v in (check or {}).items()}
    route_dependency_contexts: list = []

    async def fake_route_step(*, step, dependency_context, llm_adapter, block_id, user_id, role_roster=None, failure_context=None):
        route_dependency_contexts.append(dependency_context)
        pipeline = [RoutedSubStep.model_validate(item) for item in route]
        return SpecialistRouterOutput(status="completed", schema_valid=True, result={}, confidence=1.0, pipeline=pipeline)

    async def fake_dispatch(*, step, **_kwargs):
        return dispatch[step.step_id].pop(0)

    async def fake_check(*, step, **_kwargs):
        met = check[step.step_id].pop(0)
        return met, ([] if met else [f"{step.step_id} unmet"])

    monkeypatch.setattr(task_handler_module, "route_step", fake_route_step)
    monkeypatch.setattr(task_handler_module, "_dispatch_single_specialist", fake_dispatch)
    monkeypatch.setattr(task_handler_module, "check_success_criteria", fake_check)

    entry = await run_task_handler(
        step=step,
        state=state,
        ctx=_ctx(),
        precomputed_route=precomputed_route,
    )
    return entry, route_dependency_contexts


async def test_precomputed_route_is_used_and_skips_the_router_call(monkeypatch):
    """The whole point of batching: a step whose route was computed for the plan
    up front must not pay its own blocking router call. `route_dependency_contexts`
    stays empty because `route_step` was never reached."""
    entry, route_dependency_contexts = await _run(
        monkeypatch,
        _step(),
        route=[_sub("s1", "retrieval")],
        precomputed_route=[RoutedSubStep.model_validate(_sub("s1", "retrieval"))],
        dispatch={"1a": [_subagent_result(data={"answer": 42})]},
        check={"1a": [True]},
    )

    assert route_dependency_contexts == []
    assert entry.status == "succeeded"


async def test_a_failed_dependency_forces_a_fresh_route(monkeypatch):
    """The safety valve. A plan-time route is computed before anything ran, so
    it cannot know a dependency misfired -- and that is the one situation where
    the results genuinely change the right route (measured live 2026-07-15: the
    sole route of 25 that used dependency results was reacting to a failed
    lookup). So a step whose dependencies are not all clean re-routes, precomputed
    route or not."""
    state = PlanExecutionState(plan_id="p1")
    state.append(_entry("dep", status="failed"))

    entry, route_dependency_contexts = await _run(
        monkeypatch,
        _step(depends_on=["dep"]),
        state=state,
        route=[_sub("s1", "retrieval")],
        precomputed_route=[RoutedSubStep.model_validate(_sub("s1", "retrieval"))],
        dispatch={"1a": [_subagent_result(data={"answer": 42})]},
        check={"1a": [True]},
    )

    assert len(route_dependency_contexts) == 1, "a failed dependency must trigger a fresh route"


async def test_a_clean_dependency_still_reuses_the_precomputed_route(monkeypatch):
    """The complement: a succeeded dependency is not a reason to re-route --
    otherwise every dependent step pays the call again and batching buys nothing
    beyond the first layer."""
    state = PlanExecutionState(plan_id="p1")
    state.append(_entry("dep"))

    _, route_dependency_contexts = await _run(
        monkeypatch,
        _step(depends_on=["dep"]),
        state=state,
        route=[_sub("s1", "retrieval")],
        precomputed_route=[RoutedSubStep.model_validate(_sub("s1", "retrieval"))],
        dispatch={"1a": [_subagent_result(data={"answer": 42})]},
        check={"1a": [True]},
    )

    assert route_dependency_contexts == []


async def test_atomic_fast_path_succeeds(monkeypatch):
    entry, _ = await _run(
        monkeypatch,
        _step(),
        route=[_sub("s1", "retrieval")],
        dispatch={"1a": [_subagent_result(data={"answer": 42}, confidence=0.85, basis="official_record")]},
        check={"1a": [True]},
    )

    assert entry.nested_trace is None
    assert entry.certainty.confidence == 0.85
    assert entry.certainty.basis == "official_record"
    assert entry.status == "succeeded"
    assert entry.data == {"answer": 42}


async def test_atomic_fast_path_inadequate_returns_partial_without_rerouting(monkeypatch):
    # A length-1 route whose specialist succeeds but fails the step's own
    # success-check returns a PARTIAL atomic entry (nested_trace None) -- it does
    # NOT re-route locally; the Monitor replans one level up.
    entry, deps = await _run(
        monkeypatch,
        _step(),
        route=[_sub("s1", "retrieval")],
        dispatch={"1a": [_subagent_result(data={"x": 1})]},
        check={"1a": [False]},
    )

    assert entry.nested_trace is None
    assert entry.status == "partial"
    assert "atomic_success_criteria_not_met" in entry.warnings
    assert len(deps) == 1  # routed exactly once, no repair re-route


async def test_multi_specialist_pipeline_executes_without_atomic_attempt(monkeypatch):
    # A length>1 route is complex from the start -- no atomic dispatch is
    # attempted (no "1a" dispatch key exists, so an attempt would KeyError).
    entry, _ = await _run(
        monkeypatch,
        _step(),
        route=[_sub("s1", "retrieval"), _sub("s2", "composition", depends_on=["s1"])],
        dispatch={"s1": [_subagent_result(data={"facts": {}})], "s2": [_subagent_result(data={"answer_text": "done"})]},
        check={"s1": [True], "s2": [True]},
    )

    assert entry.status == "succeeded"
    assert entry.role == "composition"
    # Regression guard: routes/advise.py + loop.py do a flat
    # `data.get("answer_text")` on any composition entry, so a pipeline ending
    # in composition must surface that sub-step's data FLAT, not wrapped under
    # sub_results (found live: the answer got buried at
    # data["sub_results"][...]["answer_text"]).
    assert entry.data == {"answer_text": "done"}


async def test_pipeline_failure_yields_partial_for_the_monitor(monkeypatch):
    # A sub-step that fails its success-check makes the whole step partial/failed
    # (no local repair) -- the Monitor replans one level up.
    entry, deps = await _run(
        monkeypatch,
        _step(),
        route=[_sub("s1", "retrieval"), _sub("s2", "calculation_validation", depends_on=["s1"])],
        dispatch={"s1": [_subagent_result(data={"facts": {}})]},
        check={"s1": [False]},  # s1 fails -> s2's layer never runs
        )

    assert entry.status in ("partial", "failed")
    assert "task_handler_pipeline_incomplete" in entry.warnings
    assert len(deps) == 1  # routed exactly once, no repair re-route


def test_depth_cap_is_structurally_impossible_to_violate():
    source = inspect.getsource(task_handler_module)
    assert source.count("run_task_handler(") == 1


async def test_certainty_aggregates_via_min_confidence_across_sub_steps(monkeypatch):
    entry, _ = await _run(
        monkeypatch,
        _step(),
        route=[_sub("s1", "retrieval"), _sub("s2", "interpretation")],
        dispatch={
            "s1": [_subagent_result(confidence=0.9, basis="official_record")],
            "s2": [_subagent_result(confidence=0.6, basis="wiki_derived")],
        },
        check={"s1": [True], "s2": [True]},
    )

    assert entry.certainty.confidence == 0.6
    assert entry.certainty.basis == "wiki_derived"
    # Both sub-steps' entries land in the nested trace -- proves the
    # execution-layer parallel dispatch actually ran both (they share a layer).
    assert {trace.step_id for trace in entry.nested_trace.entries} == {"s1", "s2"}


async def test_pipeline_wraps_non_composition_results_and_tags_private_plan_id(monkeypatch):
    entry, _ = await _run(
        monkeypatch,
        _step(),
        route=[_sub("s1", "retrieval"), _sub("s2", "retrieval")],
        dispatch={"s1": [_subagent_result(data={"fact": "a"})], "s2": [_subagent_result(data={"fact": "b"})]},
        check={"s1": [True], "s2": [True]},
    )

    assert entry.data == {"sub_results": {"s1": {"fact": "a"}, "s2": {"fact": "b"}}}
    assert entry.nested_trace.private_plan_id == "p1:1a"
    assert {trace.step_id for trace in entry.nested_trace.entries} == {"s1", "s2"}


async def test_dependency_slice_scoping_excludes_unrelated_entries(monkeypatch):
    state = PlanExecutionState(plan_id="p1")
    state.append(_entry("dep1"))
    state.append(_entry("unrelated"))
    step = _step(depends_on=["dep1"])

    _, route_contexts = await _run(
        monkeypatch,
        step,
        state=state,
        route=[_sub("s1", "retrieval")],
        dispatch={"1a": [_subagent_result()]},
        check={"1a": [True]},
    )

    # The router only ever sees the step's own declared dependency, never
    # unrelated accumulated state.
    assert [entry.step_id for entry in route_contexts[0]] == ["dep1"]


async def test_run_task_handler_never_mutates_parent_state_directly(monkeypatch):
    state = PlanExecutionState(plan_id="p1")
    state.append(_entry("dep1"))
    step = _step(depends_on=["dep1"])

    await _run(
        monkeypatch,
        step,
        state=state,
        route=[_sub("s1", "retrieval")],
        dispatch={"1a": [_subagent_result()]},
        check={"1a": [True]},
    )

    # run_task_handler must never append to the shared state itself; that's
    # still the caller's job.
    assert len(state.entries) == 1
    assert state.entries[0].step_id == "dep1"


async def test_pipeline_pre_seeds_parent_dependency_data_not_just_graph_shape(monkeypatch):
    """Regression guard: the pipeline executor must copy the parent
    dependency's real `StateEntry` into the private state, not just its
    graph-shape id -- otherwise a sub-step whose context_requirements names a
    parent id gets an EMPTY slice and e.g. calculation_validation fails with
    "ref not found in facts (available: [])" (found via a live-eval run against
    an undeclared-major student)."""
    step = _step(step_id="1a", depends_on=["s1"])
    parent_state = PlanExecutionState(plan_id="p1")
    parent_state.append(
        StateEntry(
            entry_id="s1-0",
            step_id="s1",
            role="retrieval",
            status="succeeded",
            output_schema_name="generic_step_output_v1",
            data={"completed_courses": [{"courseNumber": "104166", "grade": 78}]},
            certainty=CertaintyTag(basis="official_record", confidence=0.95),
            produced_at=datetime.now(timezone.utc),
        )
    )

    captured_states: list[PlanExecutionState] = []

    async def fake_dispatch_pipeline_sub_step(*, sub, private_state, **_kwargs):
        captured_states.append(private_state)
        return StateEntry(
            entry_id=f"{sub.sub_step_id}-0",
            step_id=sub.sub_step_id,
            role="retrieval",
            status="succeeded",
            output_schema_name="generic_step_output_v1",
            data={},
            certainty=CertaintyTag(basis="wiki_derived", confidence=0.9),
            produced_at=datetime.now(timezone.utc),
        )

    monkeypatch.setattr(task_handler_module, "_dispatch_pipeline_sub_step", fake_dispatch_pipeline_sub_step)

    private_state = task_handler_module._new_private_state(step=step, parent_state=parent_state)
    await task_handler_module._execute_pipeline_once(
        step=step,
        pipeline=[
            RoutedSubStep(sub_step_id="s2", specialist="retrieval", objective="use s1", depends_on=["s1"], success_criteria=[])
        ],
        private_state=private_state,
        ctx=_ctx(),
    )

    assert len(captured_states) == 1
    sliced = captured_states[0].slice(["s1"])
    assert len(sliced) == 1
    assert sliced[0].data == {"completed_courses": [{"courseNumber": "104166", "grade": 78}]}


async def test_role_aggregation_uses_last_successful_entrys_role(monkeypatch):
    entry, _ = await _run(
        monkeypatch,
        _step(),
        route=[_sub("s1", "retrieval"), _sub("s2", "composition", depends_on=["s1"])],
        dispatch={"s1": [_subagent_result()], "s2": [_subagent_result(data={"answer_text": "done"})]},
        check={"s1": [True], "s2": [True]},
    )

    assert entry.role == "composition"


async def test_role_aggregation_falls_back_to_retrieval_when_nothing_succeeded(monkeypatch):
    entry, _ = await _run(
        monkeypatch,
        _step(),
        route=[_sub("s1", "interpretation"), _sub("s2", "interpretation", depends_on=["s1"])],
        dispatch={"s1": [_subagent_result()]},
        check={"s1": [False]},  # nothing succeeds -> s2's layer never runs
    )

    assert entry.role == "retrieval"
    assert entry.status == "failed"


async def test_dispatch_single_specialist_routes_calculation_validation_role_to_dedicated_block(
    monkeypatch, fake_llm_adapter_factory
):
    """`docs/agent/CALCULATION_VALIDATION_REASONING_BLOCK_PLAN.md` Part 2.5 --
    the `calculation_validation` role dispatches through the dedicated
    `run_calculation_validation_subagent`, never the generic `run_subagent`."""
    calls = {"calculation_validation": 0, "generic": 0}

    async def fake_calculation_validation_subagent(*, context_package, tool_registry, llm_adapter, block_id, llm_call_params=None):
        calls["calculation_validation"] += 1
        return _subagent_result(status="succeeded", data={"type": "expression", "result": 5})

    async def fake_run_subagent(*, role, context_package, tool_registry, llm_adapter, block_id):
        calls["generic"] += 1
        return _subagent_result(status="succeeded")

    monkeypatch.setattr(
        task_handler_module, "run_calculation_validation_subagent", fake_calculation_validation_subagent
    )
    monkeypatch.setattr(task_handler_module, "run_subagent", fake_run_subagent)

    step = _step(step_id="1a")
    state = PlanExecutionState(plan_id="p1")
    adapter = fake_llm_adapter_factory([])  # step_prep falls back deterministically -- never queried

    result = await task_handler_module._dispatch_single_specialist(
        step=step,
        step_prep_output=_dummy_step_prep_output(),
        role=ROLE_ROSTER["calculation_validation"],
        state=state,
        ctx=_ctx(llm=adapter),
        block_id="p1-1a",
    )

    assert calls == {"calculation_validation": 1, "generic": 0}
    assert result.status == "succeeded"


async def test_dispatch_single_specialist_routes_retrieval_role_to_dedicated_block(
    monkeypatch, fake_llm_adapter_factory
):
    """`docs/agent/agent_plans/RETRIEVAL_REASONING_BLOCK_PLAN.md` --
    the `retrieval` role dispatches through the dedicated
    `run_retrieval_subagent`, never the generic `run_subagent`."""
    calls = {"retrieval": 0, "generic": 0}

    async def fake_retrieval_subagent(
        *, context_package, tool_registry, llm_adapter, block_id, tool_call_cache=None, unresolvable_registry=None, llm_call_params=None
    ):
        calls["retrieval"] += 1
        return _subagent_result(status="succeeded", data={"facts": {"foo": "bar"}})

    async def fake_run_subagent(*, role, context_package, tool_registry, llm_adapter, block_id):
        calls["generic"] += 1
        return _subagent_result(status="succeeded")

    monkeypatch.setattr(task_handler_module, "run_retrieval_subagent", fake_retrieval_subagent)
    monkeypatch.setattr(task_handler_module, "run_subagent", fake_run_subagent)

    step = _step(step_id="1a")
    state = PlanExecutionState(plan_id="p1")
    adapter = fake_llm_adapter_factory([])

    result = await task_handler_module._dispatch_single_specialist(
        step=step,
        step_prep_output=_dummy_step_prep_output(),
        role=ROLE_ROSTER["retrieval"],
        state=state,
        ctx=_ctx(llm=adapter),
        block_id="p1-1a",
    )

    assert calls == {"retrieval": 1, "generic": 0}
    assert result.status == "succeeded"


async def test_dispatch_single_specialist_routes_interpretation_role_to_dedicated_block(
    monkeypatch, fake_llm_adapter_factory
):
    """`docs/agent/agent_plans/INTERPRETATION_REASONING_BLOCK_PLAN.md` --
    the `interpretation` role dispatches through the dedicated
    `run_interpretation_subagent`, never the generic `run_subagent`."""
    calls = {"interpretation": 0, "generic": 0}

    async def fake_interpretation_subagent(
        *, context_package, tool_registry, llm_adapter, block_id, tool_call_cache=None, unresolvable_registry=None, llm_call_params=None
    ):
        calls["interpretation"] += 1
        return _subagent_result(status="succeeded", data={"answer": "Up to 2 retakes allowed."})

    async def fake_run_subagent(*, role, context_package, tool_registry, llm_adapter, block_id):
        calls["generic"] += 1
        return _subagent_result(status="succeeded")

    monkeypatch.setattr(task_handler_module, "run_interpretation_subagent", fake_interpretation_subagent)
    monkeypatch.setattr(task_handler_module, "run_subagent", fake_run_subagent)

    step = _step(step_id="1a")
    state = PlanExecutionState(plan_id="p1")
    adapter = fake_llm_adapter_factory([])

    result = await task_handler_module._dispatch_single_specialist(
        step=step,
        step_prep_output=_dummy_step_prep_output(),
        role=ROLE_ROSTER["interpretation"],
        state=state,
        ctx=_ctx(llm=adapter),
        block_id="p1-1a",
    )

    assert calls == {"interpretation": 1, "generic": 0}
    assert result.status == "succeeded"


async def test_dispatch_single_specialist_routes_simulation_planning_role_to_dedicated_block(
    monkeypatch, fake_llm_adapter_factory
):
    """`docs/agent/agent_plans/SIMULATION_PLANNING_REASONING_BLOCK_PLAN.md` --
    the `simulation_planning` role dispatches through the dedicated
    `run_simulation_planning_subagent`, never the generic `run_subagent`."""
    calls = {"simulation_planning": 0, "generic": 0}

    async def fake_simulation_planning_subagent(
        *, context_package, tool_registry, llm_adapter, block_id, tool_call_cache=None, unresolvable_registry=None, llm_call_params=None
    ):
        calls["simulation_planning"] += 1
        return _subagent_result(status="succeeded", data={"outcome": {"semestersUsed": 1}})

    async def fake_run_subagent(*, role, context_package, tool_registry, llm_adapter, block_id):
        calls["generic"] += 1
        return _subagent_result(status="succeeded")

    monkeypatch.setattr(task_handler_module, "run_simulation_planning_subagent", fake_simulation_planning_subagent)
    monkeypatch.setattr(task_handler_module, "run_subagent", fake_run_subagent)

    step = _step(step_id="1a")
    state = PlanExecutionState(plan_id="p1")
    adapter = fake_llm_adapter_factory([])

    result = await task_handler_module._dispatch_single_specialist(
        step=step,
        step_prep_output=_dummy_step_prep_output(),
        role=ROLE_ROSTER["simulation_planning"],
        state=state,
        ctx=_ctx(llm=adapter),
        block_id="p1-1a",
    )

    assert calls == {"simulation_planning": 1, "generic": 0}
    assert result.status == "succeeded"


async def test_dispatch_single_specialist_routes_composition_role_to_dedicated_block(
    monkeypatch, fake_llm_adapter_factory
):
    """`docs/agent/agent_plans/COMPOSITION_REASONING_BLOCK_PLAN.md` --
    the `composition` role dispatches through the dedicated
    `run_composition_subagent`, never the generic `run_subagent`."""
    calls = {"composition": 0, "generic": 0}

    async def fake_composition_subagent(*, context_package, llm_adapter, block_id, streaming_queue=None, llm_call_params=None):
        calls["composition"] += 1
        return _subagent_result(status="succeeded", data={"answer_text": "done"})

    async def fake_run_subagent(*, role, context_package, tool_registry, llm_adapter, block_id):
        calls["generic"] += 1
        return _subagent_result(status="succeeded")

    monkeypatch.setattr(task_handler_module, "run_composition_subagent", fake_composition_subagent)
    monkeypatch.setattr(task_handler_module, "run_subagent", fake_run_subagent)

    step = _step(step_id="1a")
    state = PlanExecutionState(plan_id="p1")
    # Composition has zero tool access, so it must be handed upstream data --
    # seed a dependency the step_prep references, otherwise the empty-context
    # safety net short-circuits before routing is even exercised.
    state.append(_entry("dep1"))
    adapter = fake_llm_adapter_factory([])

    result = await task_handler_module._dispatch_single_specialist(
        step=step,
        step_prep_output=_dummy_step_prep_output(context_requirements=["dep1"]),
        role=ROLE_ROSTER["composition"],
        state=state,
        ctx=_ctx(llm=adapter),
        block_id="p1-1a",
    )

    assert calls == {"composition": 1, "generic": 0}
    assert result.status == "succeeded"


def _routed_sub(sub_step_id="s1", specialist="composition", depends_on=None, context_requirements=None) -> RoutedSubStep:
    return RoutedSubStep(
        sub_step_id=sub_step_id,
        specialist=specialist,
        objective="do the thing",
        depends_on=depends_on or [],
        success_criteria=["done"],
        specific_instructions=[],
        context_requirements=context_requirements or [],
    )


def test_resolve_sub_step_context_requirements_keeps_exact_matches():
    """A well-formed dependency id that names a real state entry is kept verbatim."""
    state = PlanExecutionState(plan_id="p1")
    state.append(_entry("21a"))
    sub = _routed_sub(context_requirements=["21a"])
    step = _step(step_id="22", depends_on=["21a"])

    resolved = task_handler_module._resolve_sub_step_context_requirements(sub=sub, state=state, step=step)

    assert resolved == ["21a"]


def test_resolve_sub_step_context_requirements_strips_spurious_sub_step_suffix():
    """The live fabrication bug: the router emitted "21a-2" for the seeded
    parent entry "21a". Suffix-tolerant resolution recovers the real id so the
    data reaches the specialist instead of an empty slice."""
    state = PlanExecutionState(plan_id="p1")
    state.append(_entry("21a"))
    state.append(_entry("21b"))
    sub = _routed_sub(context_requirements=["21a-2", "21b-2"])
    step = _step(step_id="22", depends_on=["21a", "21b"])

    resolved = task_handler_module._resolve_sub_step_context_requirements(sub=sub, state=state, step=step)

    assert resolved == ["21a", "21b"]


def test_resolve_sub_step_context_requirements_falls_back_to_parent_depends_on():
    """When no declared id resolves at all, fall back to the parent step's
    authoritative depends_on -- always seeded into the private state -- so a
    fully mis-wired dep list still reaches the specialist with real data."""
    state = PlanExecutionState(plan_id="p1")
    state.append(_entry("21a"))
    sub = _routed_sub(context_requirements=["totally-wrong-id"])
    step = _step(step_id="22", depends_on=["21a"])

    resolved = task_handler_module._resolve_sub_step_context_requirements(sub=sub, state=state, step=step)

    assert resolved == ["21a"]


def test_resolve_sub_step_context_requirements_uses_depends_on_when_context_requirements_empty():
    """The router may leave context_requirements empty and express the data
    handoff only via depends_on; that list is used and resolved the same way."""
    state = PlanExecutionState(plan_id="p1")
    state.append(_entry("21a"))
    sub = _routed_sub(depends_on=["21a-2"], context_requirements=[])
    step = _step(step_id="22", depends_on=["21a"])

    resolved = task_handler_module._resolve_sub_step_context_requirements(sub=sub, state=state, step=step)

    assert resolved == ["21a"]


async def test_dispatch_single_specialist_composition_with_empty_context_returns_partial(
    monkeypatch, fake_llm_adapter_factory
):
    """Safety net: a zero-tool composition handed no upstream data must NOT be
    dispatched (it could only fabricate) -- it returns partial with the marker
    so the Monitor replans, and the composition subagent is never called."""
    called = {"composition": 0}

    async def fake_composition_subagent(*, context_package, llm_adapter, block_id, streaming_queue=None, llm_call_params=None):
        called["composition"] += 1
        return _subagent_result(status="succeeded", data={"answer_text": "fabricated"})

    monkeypatch.setattr(task_handler_module, "run_composition_subagent", fake_composition_subagent)

    step = _step(step_id="1a")
    state = PlanExecutionState(plan_id="p1")  # no entries -> empty dependency_state
    adapter = fake_llm_adapter_factory([])

    result = await task_handler_module._dispatch_single_specialist(
        step=step,
        step_prep_output=_dummy_step_prep_output(context_requirements=["missing"]),
        role=ROLE_ROSTER["composition"],
        state=state,
        ctx=_ctx(llm=adapter),
        block_id="p1-1a",
    )

    assert called["composition"] == 0
    assert result.status == "partial"
    assert task_handler_module._COMPOSITION_EMPTY_CONTEXT_MARKER in result.warnings
