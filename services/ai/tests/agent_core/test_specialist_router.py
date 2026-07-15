"""Tests for `app.agent_core.orchestrator.specialist_router`
(docs/planning/SPECIALIST_ROUTER_PLANNER_SPLIT_PLAN.md).

The router takes ONE plan step and returns the pipeline of specialist
subagents that execute it -- atomic is the length-1 case. It is single-shot,
no tools, and fails CLOSED to a single retrieval sub-step (the outer Monitor
still verifies, so a bad route can never silently pass).
"""

from __future__ import annotations

from app.agent_core.orchestrator.specialist_router import route_step
from app.agent_core.planning.schemas import PlanStep


def _step(objective="Determine the student's cumulative GPA.", depends_on=None, success_criteria=None) -> PlanStep:
    return PlanStep(
        step_id="1a",
        objective=objective,
        depends_on=depends_on or [],
        success_criteria=success_criteria if success_criteria is not None else ["GPA determined"],
        assumptions_to_verify=[],
    )


def _pipeline(*sub_steps: dict) -> dict:
    return {"pipeline": list(sub_steps)}


def _sub(sub_step_id, specialist, objective="do it", depends_on=None, success_criteria=None) -> dict:
    return {
        "sub_step_id": sub_step_id,
        "specialist": specialist,
        "objective": objective,
        "depends_on": depends_on or [],
        "success_criteria": success_criteria or ["done"],
    }


async def _route(adapter, step=None):
    return await route_step(
        step=step or _step(),
        dependency_context=[],
        llm_adapter=adapter,
        block_id="blk-1",
        user_id="u1",
    )


async def test_atomic_step_routes_to_a_single_specialist_pipeline(fake_llm_adapter_factory):
    adapter = fake_llm_adapter_factory([_pipeline(_sub("s1", "retrieval", "Fetch prerequisites for course X."))])

    out = await _route(adapter, _step(objective="Find prerequisites for course X."))

    assert len(out.pipeline) == 1
    assert out.pipeline[0].specialist == "retrieval"
    assert out.is_atomic is True


async def test_gpa_step_routes_to_retrieval_then_calculation(fake_llm_adapter_factory):
    adapter = fake_llm_adapter_factory([
        _pipeline(
            _sub("s1", "retrieval", "Fetch the student's completed courses and grades."),
            _sub("s2", "calculation_validation", "Compute cumulative GPA.", depends_on=["s1"]),
        )
    ])

    out = await _route(adapter)

    assert [s.specialist for s in out.pipeline] == ["retrieval", "calculation_validation"]
    assert out.pipeline[1].depends_on == ["s1"]
    assert out.is_atomic is False


async def test_policy_step_routes_to_retrieval_then_interpretation(fake_llm_adapter_factory):
    adapter = fake_llm_adapter_factory([
        _pipeline(
            _sub("s1", "retrieval", "Fetch the reserve-duty policy text."),
            _sub("s2", "interpretation", "Explain its implications for the student.", depends_on=["s1"]),
        )
    ])

    out = await _route(adapter, _step(objective="Explain the reserve-duty accommodation policy."))

    assert [s.specialist for s in out.pipeline] == ["retrieval", "interpretation"]


async def test_malformed_output_fails_closed_to_single_retrieval(fake_llm_adapter_factory):
    # Invalid through every repair attempt -> a single retrieval sub-step that
    # mirrors the parent objective, flagged so the fallback is auditable.
    adapter = fake_llm_adapter_factory([{"not_a_pipeline": True}] * 3)

    out = await _route(adapter, _step(objective="Find prerequisites for course X."))

    assert len(out.pipeline) == 1
    assert out.pipeline[0].specialist == "retrieval"
    assert out.pipeline[0].objective == "Find prerequisites for course X."
    assert out.is_atomic is True
    assert out.schema_valid is False
    assert any("router" in w for w in out.warnings)


async def test_empty_pipeline_fails_closed_to_single_retrieval(fake_llm_adapter_factory):
    adapter = fake_llm_adapter_factory([_pipeline()])

    out = await _route(adapter, _step(objective="Find prerequisites for course X."))

    assert len(out.pipeline) == 1
    assert out.pipeline[0].specialist == "retrieval"


async def test_unknown_specialist_substep_is_dropped_and_fails_closed_if_empty(fake_llm_adapter_factory):
    # Even if a bad specialist name slips past the schema enum via repair, a
    # sub-step naming a non-existent specialist is dropped; an emptied pipeline
    # fails closed rather than dispatching to a specialist that does not exist.
    adapter = fake_llm_adapter_factory([_pipeline(_sub("s1", "wizard", "cast a spell"))] * 3)

    out = await _route(adapter, _step(objective="Find prerequisites for course X."))

    assert [s.specialist for s in out.pipeline] == ["retrieval"]


async def test_null_optional_list_fields_are_accepted_not_dropped(fake_llm_adapter_factory):
    """`_SUB_STEP_SCHEMA` advertises `specific_instructions` and
    `context_requirements` as `{"type": ["array", "null"]}`, so `null` is a
    CORRECT response. `RoutedSubStep` typed them `list[str]`, which rejects
    null -- so a perfectly good route was dropped
    (`specialist_router_dropped_invalid_substep`), the pipeline emptied, and
    `_fail_closed_pipeline` downgraded the step to a blind RETRIEVAL fetch.

    Measured live (2026-07-15, credits_remaining): the router correctly routed
    "Calculate the total credits..." to `calculation_validation` with
    `context_requirements: null`. It was dropped for saying null; retrieval got
    the step instead, did 17-number mental math, returned 63.0 (truth: 62.5),
    and stamped it `certainty_basis="official_record", confidence=1.0`.

    We must accept exactly what we advertise."""
    sub = _sub("1e-0", "calculation_validation", "Sum all creditsEarned values.")
    sub["context_requirements"] = None
    sub["specific_instructions"] = None
    adapter = fake_llm_adapter_factory([_pipeline(sub)])

    output = await _route(adapter)

    assert [s.specialist for s in output.pipeline] == ["calculation_validation"], (
        "a schema-valid null must not be downgraded to the fail-closed retrieval route"
    )
    assert output.pipeline[0].context_requirements == []
    assert output.pipeline[0].specific_instructions == []
    assert "specialist_router_fallback_used" not in output.warnings


async def test_router_uses_cheap_fast_params(fake_llm_adapter_factory):
    adapter = fake_llm_adapter_factory([_pipeline(_sub("s1", "retrieval"))])

    await _route(adapter)

    call = adapter.calls[0]
    assert call["thinking_enabled"] is False
    assert call["timeout"] is not None and call["timeout"] <= 30.0
