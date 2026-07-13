"""Tests for `app.agent_core.orchestrator.task_handler`.

Isolates `task_handler.py`'s own orchestration logic (classify -> dispatch ->
check -> aggregate; the private mini-orchestrator's round loop; the
depth-cap invariant) by monkeypatching its own module-level references to
`classify_step`, `check_success_criteria`, `_dispatch_single_specialist`, and
`build_next_plan_steps` -- the underlying specialist-dispatch chain
(step_prep -> context_builder -> run_subagent) is already covered end-to-end
by `test_skeleton_end_to_end.py`, and the classifier/success-check
primitives have their own dedicated test files. Duplicating that whole
canned-multi-pass-LLM-response choreography here would test the same thing
twice for no added confidence.
"""

from __future__ import annotations

import inspect
from datetime import datetime, timezone
from types import SimpleNamespace

from app.agent_core.orchestrator import task_handler as task_handler_module
from app.agent_core.orchestrator.task_handler import run_task_handler
from app.agent_core.planning.schemas import PlanGraph, PlannerInvocationOutput, PlanStep
from app.agent_core.planning.state import CertaintyTag, PlanExecutionState, StateEntry
from app.agent_core.roles.roster import build_default_role_roster
from app.agent_core.subagents.schemas import SubagentResult, StepPrepOutput, StepInstructionFields, ReasoningParamsOverride
from app.agent_core.tools.default_registry import build_default_tool_registry

ROLE_ROSTER = build_default_role_roster()
TOOL_REGISTRY = build_default_tool_registry()


def _step(step_id="1a", depends_on=None, success_criteria=None, assumptions=None) -> PlanStep:
    return PlanStep(
        step_id=step_id,
        objective="do the thing",
        depends_on=depends_on or [],
        success_criteria=success_criteria if success_criteria is not None else ["thing done"],
        assumptions_to_verify=assumptions or [],
    )


def _entry(step_id: str, confidence: float = 0.9) -> StateEntry:
    return StateEntry(
        entry_id=f"{step_id}-0",
        step_id=step_id,
        role="retrieval",
        status="succeeded",
        output_schema_name="generic_step_output_v1",
        data={},
        certainty=CertaintyTag(basis="wiki_derived", confidence=confidence),
        produced_at=datetime.now(timezone.utc),
    )


def _classifier(atomic: bool, role: str | None):
    return SimpleNamespace(atomic=atomic, role_if_atomic=role)

def _dummy_step_prep_output():
    return StepPrepOutput(
        instruction_fields=StepInstructionFields(goal="g", description="d", specific_instructions=[]),
        context_requirements=[],
        reasoning_params=ReasoningParamsOverride(),
        output_schema_name="generic_step_output_v1",
        output_schema={"type": "object"},
        tool_grant_override=None
    )


def _subagent_result(status="succeeded", data=None, confidence=0.9, basis="wiki_derived", warnings=None):
    return SubagentResult(
        status=status,
        result=data or {},
        certainty=CertaintyTag(basis=basis, confidence=confidence),
        assumptions=[],
        warnings=warnings or [],
        tool_audit_trail=[],
    )


async def _run(
    monkeypatch,
    step,
    *,
    state=None,
    top_classify=None,
    top_dispatch=None,
    top_check=None,
    sub_classify=None,
    sub_dispatch=None,
    sub_check=None,
    planner_queue=None,
    max_rounds=None,
):
    """Drives `run_task_handler`, faking its four collaborators. The TOP-level
    step's own classify/dispatch/check are answered from the `top_*` args
    (exactly one call each, unambiguous); any NESTED sub-step's calls are
    answered by step-id lookup in the `sub_*` dicts, so concurrent dispatch
    within one execution layer never depends on call ordering."""
    state = state if state is not None else PlanExecutionState(plan_id="p1")
    sub_classify = sub_classify or {}
    sub_dispatch = {k: list(v) for k, v in (sub_dispatch or {}).items()}
    sub_check = {k: list(v) for k, v in (sub_check or {}).items()}
    planner_queue = list(planner_queue or [])
    planner_inputs: list = []
    top_step_id = step.step_id
    top_classify_dependency_contexts: list = []
    top_calls_used = {"classify": False, "dispatch": False, "check": False}

    async def fake_classify_and_prep(*, step, dependency_context, llm_adapter, block_id, user_id):
        if step.step_id == top_step_id and not top_calls_used["classify"]:
            top_calls_used["classify"] = True
            top_classify_dependency_contexts.append(dependency_context)
            return top_classify, "dummy_prep"
        return sub_classify[step.step_id], "dummy_prep"

    async def fake_dispatch(
        *,
        step,
        step_prep_output,
        role,
        state,
        tool_registry,
        llm_adapter,
        block_id,
        user_id,
        streaming_queue=None,
        tool_call_cache=None,
        unresolvable_registry=None,
        reasoning_config=None,
    ):
        if step.step_id == top_step_id and not top_calls_used["dispatch"]:
            top_calls_used["dispatch"] = True
            return top_dispatch
        return sub_dispatch[step.step_id].pop(0)

    async def fake_check(*, step, result, llm_adapter, block_id):
        # check_success_criteria now returns SuccessCheckResult(bool,
        # list[str]) -- tests here only care about the bool half, so wrap
        # it with an empty unmet_criteria list rather than threading a
        # third fixture arg through every call site.
        if step.step_id == top_step_id and not top_calls_used["check"]:
            top_calls_used["check"] = True
            return top_check, []
        return sub_check[step.step_id].pop(0), []

    async def fake_build_next_plan_steps(*, planner_input, llm_adapter, block_id, invocation, prompt_contract_name, thinking_enabled=None, reasoning_effort=None, timeout=None):
        planner_inputs.append(planner_input)
        return planner_queue.pop(0)

    monkeypatch.setattr(task_handler_module, "classify_and_prep_step", fake_classify_and_prep)
    monkeypatch.setattr(task_handler_module, "check_success_criteria", fake_check)
    monkeypatch.setattr(task_handler_module, "_dispatch_single_specialist", fake_dispatch)
    monkeypatch.setattr(task_handler_module, "build_next_plan_steps", fake_build_next_plan_steps)

    kwargs = {}
    if max_rounds is not None:
        kwargs["max_rounds"] = max_rounds

    entry = await run_task_handler(
        step=step,
        state=state,
        role_roster=ROLE_ROSTER,
        tool_registry=TOOL_REGISTRY,
        llm_adapter=object(),
        original_user_message="hello",
        user_id="test-user-1",
        plan_id="p1",
        **kwargs,
    )
    return entry, planner_inputs, top_classify_dependency_contexts


async def test_atomic_fast_path_succeeds(monkeypatch):
    step = _step()

    entry, _, _ = await _run(
        monkeypatch,
        step,
        top_classify=_classifier(True, "retrieval"),
        top_dispatch=_subagent_result(data={"answer": 42}, confidence=0.85, basis="official_record"),
        top_check=True,
    )

    assert entry.nested_trace is None
    assert entry.certainty.confidence == 0.85
    assert entry.certainty.basis == "official_record"
    assert entry.status == "succeeded"
    assert entry.data == {"answer": 42}


async def test_fast_path_inadequate_triggers_fallback(monkeypatch):
    step = _step()
    sub_step = _step(step_id="1a1")
    plan_output = PlannerInvocationOutput(
        plan_status="complete",
        next_steps=[sub_step],
        plan_summary="",
        clarification_question=None,
        plan_graph=PlanGraph(forward={"1a1": []}, dependents={}, execution_layers=[["1a1"]]),
    )

    entry, _, _ = await _run(
        monkeypatch,
        step,
        top_classify=_classifier(True, "retrieval"),
        top_dispatch=_subagent_result(status="succeeded"),
        top_check=False,  # fast path is inadequate -- must fall back
        sub_classify={"1a1": _classifier(True, "retrieval")},
        sub_dispatch={"1a1": [_subagent_result(data={"x": 1})]},
        sub_check={"1a1": [True]},
        planner_queue=[plan_output],
    )

    assert entry.nested_trace is not None
    assert "fast_path_inadequate" in entry.warnings
    assert entry.status == "succeeded"


async def test_classified_non_atomic_skips_atomic_attempt_entirely(monkeypatch):
    step = _step()
    sub_step = _step(step_id="1a1")
    plan_output = PlannerInvocationOutput(
        plan_status="complete",
        next_steps=[sub_step],
        plan_summary="",
        clarification_question=None,
        plan_graph=PlanGraph(forward={"1a1": []}, dependents={}, execution_layers=[["1a1"]]),
    )

    # top_dispatch/top_check are left None -- if the atomic path were ever
    # attempted for the top-level step, fake_dispatch/fake_check would fall
    # through to a dict lookup keyed by "1a" in sub_dispatch/sub_check,
    # which isn't populated, raising KeyError and failing the test loudly.
    entry, _, _ = await _run(
        monkeypatch,
        step,
        top_classify=_classifier(False, None),
        sub_classify={"1a1": _classifier(True, "composition")},
        sub_dispatch={"1a1": [_subagent_result(data={"answer_text": "done"})]},
        sub_check={"1a1": [True]},
        planner_queue=[plan_output],
    )

    assert entry.status == "succeeded"
    assert entry.role == "composition"
    # Regression guard: routes/advise.py's final-answer extraction and
    # loop.py's own composition short-circuit both do a flat
    # `data.get("answer_text")` on any StateEntry whose role is
    # "composition" -- wrapping it under `sub_results` (every other role's
    # shape) silently produced a blank final answer even though the agent
    # composed a correct one internally (found live: the real answer ended
    # up at data["sub_results"]["1a1"]["answer_text"] instead of
    # data["answer_text"]).
    assert entry.data == {"answer_text": "done"}


async def test_round_cap_exhaustion_never_fabricates_success(monkeypatch):
    step = _step()
    sub_step = _step(step_id="1a1")
    plan_output = PlannerInvocationOutput(
        plan_status="in_progress",
        next_steps=[sub_step],
        plan_summary="",
        clarification_question=None,
        plan_graph=PlanGraph(forward={"1a1": []}, dependents={}, execution_layers=[["1a1"]]),
    )

    entry, planner_inputs, _ = await _run(
        monkeypatch,
        step,
        top_classify=_classifier(False, None),
        sub_classify={"1a1": _classifier(True, "retrieval")},
        sub_dispatch={"1a1": [_subagent_result(status="succeeded")] * 2},
        sub_check={"1a1": [False, False]},  # never satisfies criteria -- keeps failing every round
        planner_queue=[plan_output, plan_output],
        max_rounds=2,
    )

    assert len(planner_inputs) == 2
    assert "task_handler_round_budget_exhausted" in entry.warnings
    assert entry.status in ("partial", "failed")
    assert entry.status != "succeeded"


async def test_blocked_needs_clarification_translates_upward_not_dropped(monkeypatch):
    step = _step()
    plan_output = PlannerInvocationOutput(
        plan_status="blocked_needs_clarification",
        next_steps=[],
        plan_summary="",
        clarification_question="Which semester do you mean?",
        plan_graph=PlanGraph(),
    )

    entry, _, _ = await _run(
        monkeypatch,
        step,
        top_classify=_classifier(False, None),
        planner_queue=[plan_output],
    )

    assert entry.status == "partial"
    assert any("Which semester do you mean?" in warning for warning in entry.warnings)


def test_depth_cap_is_structurally_impossible_to_violate():
    source = inspect.getsource(task_handler_module)
    assert source.count("run_task_handler(") == 1


async def test_monitor_flags_thread_a_round_1_failure_into_round_2(monkeypatch):
    step = _step()
    sub_step = _step(step_id="1a1")
    plan_output = PlannerInvocationOutput(
        plan_status="in_progress",
        next_steps=[sub_step],
        plan_summary="",
        clarification_question=None,
        plan_graph=PlanGraph(forward={"1a1": []}, dependents={}, execution_layers=[["1a1"]]),
    )

    _, planner_inputs, _ = await _run(
        monkeypatch,
        step,
        top_classify=_classifier(False, None),
        sub_classify={"1a1": _classifier(True, "retrieval")},
        sub_dispatch={"1a1": [_subagent_result(status="succeeded")] * 2},
        sub_check={"1a1": [False, True]},  # fails round 1, then succeeds round 2
        planner_queue=[plan_output, plan_output],
        max_rounds=2,
    )

    assert planner_inputs[0].monitor_flags == []
    assert planner_inputs[0].replan_reason is None
    assert any("1a1" in flag for flag in planner_inputs[1].monitor_flags)
    assert planner_inputs[1].replan_reason is not None
    assert "1a1" in planner_inputs[1].replan_reason


async def test_certainty_aggregates_via_min_confidence_across_sub_steps(monkeypatch):
    step = _step()
    sub1 = _step(step_id="1a1")
    sub2 = _step(step_id="1a2")
    plan_output = PlannerInvocationOutput(
        plan_status="complete",
        next_steps=[sub1, sub2],
        plan_summary="",
        clarification_question=None,
        plan_graph=PlanGraph(forward={"1a1": [], "1a2": []}, dependents={}, execution_layers=[["1a1", "1a2"]]),
    )

    entry, _, _ = await _run(
        monkeypatch,
        step,
        top_classify=_classifier(False, None),
        sub_classify={"1a1": _classifier(True, "retrieval"), "1a2": _classifier(True, "interpretation")},
        sub_dispatch={
            "1a1": [_subagent_result(confidence=0.9, basis="official_record")],
            "1a2": [_subagent_result(confidence=0.6, basis="wiki_derived")],
        },
        sub_check={"1a1": [True], "1a2": [True]},
        planner_queue=[plan_output],
    )

    assert entry.certainty.confidence == 0.6
    assert entry.certainty.basis == "wiki_derived"
    # Both sub-steps' entries land in the nested trace -- proves the
    # execution-layer parallel dispatch wiring actually ran both, not just one.
    assert {trace.step_id for trace in entry.nested_trace.entries} == {"1a1", "1a2"}


async def test_nested_audit_trail_stays_auxiliary_only(monkeypatch):
    step = _step()
    sub_step = _step(step_id="1a1")
    plan_output = PlannerInvocationOutput(
        plan_status="complete",
        next_steps=[sub_step],
        plan_summary="",
        clarification_question=None,
        plan_graph=PlanGraph(forward={"1a1": []}, dependents={}, execution_layers=[["1a1"]]),
    )

    entry, _, _ = await _run(
        monkeypatch,
        step,
        top_classify=_classifier(False, None),
        sub_classify={"1a1": _classifier(True, "retrieval")},
        sub_dispatch={"1a1": [_subagent_result(data={"fact": "value"})]},
        sub_check={"1a1": [True]},
        planner_queue=[plan_output],
    )

    assert entry.data == {"sub_results": {"1a1": {"fact": "value"}}}
    assert entry.nested_trace.entries[0].step_id == "1a1"
    assert entry.nested_trace.private_plan_id == "p1:1a"


async def test_dependency_slice_scoping_excludes_unrelated_entries(monkeypatch):
    state = PlanExecutionState(plan_id="p1")
    state.append(_entry("dep1"))
    state.append(_entry("unrelated"))
    step = _step(depends_on=["dep1"])

    _, _, top_classify_dependency_contexts = await _run(
        monkeypatch,
        step,
        state=state,
        top_classify=_classifier(True, "retrieval"),
        top_dispatch=_subagent_result(),
        top_check=True,
    )

    assert [entry.step_id for entry in top_classify_dependency_contexts[0]] == ["dep1"]


async def test_run_task_handler_never_mutates_parent_state_directly(monkeypatch):
    state = PlanExecutionState(plan_id="p1")
    state.append(_entry("dep1"))
    step = _step(depends_on=["dep1"])

    await _run(
        monkeypatch,
        step,
        state=state,
        top_classify=_classifier(True, "retrieval"),
        top_dispatch=_subagent_result(),
        top_check=True,
    )

    # Only the pre-existing dependency entry -- run_task_handler must never
    # append to the shared state itself; that's still the caller's job.
    assert len(state.entries) == 1
    assert state.entries[0].step_id == "dep1"


async def test_known_global_ids_seeding_preserves_parent_dependency_reference(monkeypatch, fake_llm_adapter_factory):
    """A real regression guard for the pre-seeding fix in `_run_nested_subplan`:
    uses the REAL `build_next_plan_steps` (not faked) so `rewrite_step_ids`'s
    actual dangling-dependency-stripping logic runs for real."""
    step = _step(step_id="1a", depends_on=["s1"])
    parent_state = PlanExecutionState(plan_id="p1")
    parent_state.append(_entry("s1"))

    captured_sub_steps: list[PlanStep] = []

    async def fake_dispatch_nested_sub_step(
        *,
        sub_step,
        private_state,
        role_roster,
        tool_registry,
        llm_adapter,
        plan_id,
        step,
        user_id,
        tool_call_cache=None,
        unresolvable_registry=None,
        reasoning_config=None,
    ):
        captured_sub_steps.append(sub_step)
        return StateEntry(
            entry_id=f"{sub_step.step_id}-0",
            step_id=sub_step.step_id,
            role="retrieval",
            status="succeeded",
            output_schema_name="generic_step_output_v1",
            data={},
            certainty=CertaintyTag(basis="wiki_derived", confidence=0.9),
            produced_at=datetime.now(timezone.utc),
        )

    monkeypatch.setattr(task_handler_module, "_dispatch_nested_sub_step", fake_dispatch_nested_sub_step)

    adapter = fake_llm_adapter_factory(
        [
            {
                "plan_status": "complete",
                "next_steps": [
                    {
                        "step_id": "A",
                        "objective": "use s1's result",
                        "depends_on": ["s1"],
                        "success_criteria": [],
                        "assumptions_to_verify": [],
                    }
                ],
                "plan_summary": "",
                "clarification_question": None,
            }
        ]
    )

    await task_handler_module._run_nested_subplan(
        step=step,
        parent_state=parent_state,
        role_roster=ROLE_ROSTER,
        tool_registry=TOOL_REGISTRY,
        llm_adapter=adapter,
        original_user_message="hello",
        user_id="test-user-1",
        plan_id="p1",
        max_rounds=1,
    )

    assert len(captured_sub_steps) == 1
    assert captured_sub_steps[0].depends_on == ["s1"]


async def test_nested_subplan_seeds_parent_dependency_data_not_just_graph_shape(
    monkeypatch, fake_llm_adapter_factory
):
    """Regression guard: `_run_nested_subplan` used to pre-seed only
    `plan_graph.forward` for a parent dependency (enough to stop
    `rewrite_step_ids` stripping it as dangling) without copying the actual
    parent `StateEntry` -- so a nested sub-step depending on a parent id got
    an EMPTY `private_state.slice(...)`, and e.g. `calculation_validation`
    failed with "ref not found in facts (available: [])" no matter how many
    rounds it got (found via a live-eval run against an undeclared-major
    student). Confirms the parent's real data is now visible to the nested
    sub-plan from the start."""
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

    async def fake_dispatch_nested_sub_step(
        *,
        sub_step,
        private_state,
        role_roster,
        tool_registry,
        llm_adapter,
        plan_id,
        step,
        user_id,
        tool_call_cache=None,
        unresolvable_registry=None,
        reasoning_config=None,
    ):
        captured_states.append(private_state)
        return StateEntry(
            entry_id=f"{sub_step.step_id}-0",
            step_id=sub_step.step_id,
            role="retrieval",
            status="succeeded",
            output_schema_name="generic_step_output_v1",
            data={},
            certainty=CertaintyTag(basis="wiki_derived", confidence=0.9),
            produced_at=datetime.now(timezone.utc),
        )

    monkeypatch.setattr(task_handler_module, "_dispatch_nested_sub_step", fake_dispatch_nested_sub_step)

    adapter = fake_llm_adapter_factory(
        [
            {
                "plan_status": "complete",
                "next_steps": [
                    {
                        "step_id": "A",
                        "objective": "use s1's result",
                        "depends_on": ["s1"],
                        "success_criteria": [],
                        "assumptions_to_verify": [],
                    }
                ],
                "plan_summary": "",
                "clarification_question": None,
            }
        ]
    )

    await task_handler_module._run_nested_subplan(
        step=step,
        parent_state=parent_state,
        role_roster=ROLE_ROSTER,
        tool_registry=TOOL_REGISTRY,
        llm_adapter=adapter,
        original_user_message="hello",
        user_id="test-user-1",
        plan_id="p1",
        max_rounds=1,
    )

    assert len(captured_states) == 1
    sliced = captured_states[0].slice(["s1"])
    assert len(sliced) == 1
    assert sliced[0].data == {"completed_courses": [{"courseNumber": "104166", "grade": 78}]}


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
        tool_registry=TOOL_REGISTRY,
        llm_adapter=adapter,
        block_id="p1-1a",
        user_id="test-user-1",
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

    monkeypatch.setattr(
        task_handler_module, "run_retrieval_subagent", fake_retrieval_subagent
    )
    monkeypatch.setattr(task_handler_module, "run_subagent", fake_run_subagent)

    step = _step(step_id="1a")
    state = PlanExecutionState(plan_id="p1")
    adapter = fake_llm_adapter_factory([])

    result = await task_handler_module._dispatch_single_specialist(
        step=step,
        step_prep_output=_dummy_step_prep_output(),
        role=ROLE_ROSTER["retrieval"],
        state=state,
        tool_registry=TOOL_REGISTRY,
        llm_adapter=adapter,
        block_id="p1-1a",
        user_id="test-user-1",
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

    monkeypatch.setattr(
        task_handler_module, "run_interpretation_subagent", fake_interpretation_subagent
    )
    monkeypatch.setattr(task_handler_module, "run_subagent", fake_run_subagent)

    step = _step(step_id="1a")
    state = PlanExecutionState(plan_id="p1")
    adapter = fake_llm_adapter_factory([])

    result = await task_handler_module._dispatch_single_specialist(
        step=step,
        step_prep_output=_dummy_step_prep_output(),
        role=ROLE_ROSTER["interpretation"],
        state=state,
        tool_registry=TOOL_REGISTRY,
        llm_adapter=adapter,
        block_id="p1-1a",
        user_id="test-user-1",
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

    monkeypatch.setattr(
        task_handler_module, "run_simulation_planning_subagent", fake_simulation_planning_subagent
    )
    monkeypatch.setattr(task_handler_module, "run_subagent", fake_run_subagent)

    step = _step(step_id="1a")
    state = PlanExecutionState(plan_id="p1")
    adapter = fake_llm_adapter_factory([])

    result = await task_handler_module._dispatch_single_specialist(
        step=step,
        step_prep_output=_dummy_step_prep_output(),
        role=ROLE_ROSTER["simulation_planning"],
        state=state,
        tool_registry=TOOL_REGISTRY,
        llm_adapter=adapter,
        block_id="p1-1a",
        user_id="test-user-1",
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

    monkeypatch.setattr(
        task_handler_module, "run_composition_subagent", fake_composition_subagent
    )
    monkeypatch.setattr(task_handler_module, "run_subagent", fake_run_subagent)

    step = _step(step_id="1a")
    state = PlanExecutionState(plan_id="p1")
    adapter = fake_llm_adapter_factory([])

    result = await task_handler_module._dispatch_single_specialist(
        step=step,
        step_prep_output=_dummy_step_prep_output(),
        role=ROLE_ROSTER["composition"],
        state=state,
        tool_registry=TOOL_REGISTRY,
        llm_adapter=adapter,
        block_id="p1-1a",
        user_id="test-user-1",
    )

    assert calls == {"composition": 1, "generic": 0}
    assert result.status == "succeeded"


async def test_role_aggregation_uses_last_successful_entrys_role(monkeypatch):
    step = _step()
    sub1 = _step(step_id="1a1")
    sub2 = _step(step_id="1a2")
    plan_output = PlannerInvocationOutput(
        plan_status="complete",
        next_steps=[sub1, sub2],
        plan_summary="",
        clarification_question=None,
        plan_graph=PlanGraph(
            forward={"1a1": [], "1a2": ["1a1"]}, dependents={"1a1": ["1a2"]}, execution_layers=[["1a1"], ["1a2"]]
        ),
    )

    entry, _, _ = await _run(
        monkeypatch,
        step,
        top_classify=_classifier(False, None),
        sub_classify={"1a1": _classifier(True, "retrieval"), "1a2": _classifier(True, "composition")},
        sub_dispatch={"1a1": [_subagent_result()], "1a2": [_subagent_result(data={"answer_text": "done"})]},
        sub_check={"1a1": [True], "1a2": [True]},
        planner_queue=[plan_output],
    )

    assert entry.role == "composition"


async def test_role_aggregation_falls_back_to_retrieval_when_nothing_succeeded(monkeypatch):
    step = _step()
    sub_step = _step(step_id="1a1")
    plan_output = PlannerInvocationOutput(
        plan_status="in_progress",
        next_steps=[sub_step],
        plan_summary="",
        clarification_question=None,
        plan_graph=PlanGraph(forward={"1a1": []}, dependents={}, execution_layers=[["1a1"]]),
    )

    entry, _, _ = await _run(
        monkeypatch,
        step,
        top_classify=_classifier(False, None),
        sub_classify={"1a1": _classifier(False, None)},
        planner_queue=[plan_output],
        max_rounds=1,
    )

    assert entry.role == "retrieval"
    assert entry.status == "failed"
