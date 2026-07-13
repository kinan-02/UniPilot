"""Tests for `app.agent_core.orchestrator.task_handler_classify_and_prep`."""

from __future__ import annotations

import logging

from app.agent_core.orchestrator.task_handler_classify_and_prep import (
    _resolve_context_requirements,
    classify_and_prep_step,
)
from app.agent_core.planning.schemas import PlanStep
from app.agent_core.reasoning.llm_adapter import LLMAdapterError

_STEP = PlanStep(
    step_id="1a",
    objective="Retrieve the student's completed courses.",
    depends_on=[],
    success_criteria=["completed courses returned"],
    assumptions_to_verify=[],
)


async def test_atomic_verdict_returns_the_role_and_prep(fake_llm_adapter_factory):
    # context_requirements=["dep1"] is only trusted when "dep1" is actually
    # one of the step's own declared depends_on -- see the dedicated
    # context_requirements tests below for the mismatch/fallback cases.
    step = _STEP.model_copy(update={"depends_on": ["dep1"]})
    adapter = fake_llm_adapter_factory([{
        "atomic": True,
        "role_if_atomic": "retrieval",
        "goal": "g",
        "description": "d",
        "specific_instructions": ["instr"],
        "context_requirements": ["dep1"]
    }])

    cls_out, prep_out = await classify_and_prep_step(
        step=step, dependency_context=[], llm_adapter=adapter, block_id="blk-1", user_id="u1"
    )

    assert cls_out.atomic is True
    assert cls_out.role_if_atomic == "retrieval"
    assert prep_out.instruction_fields.goal == "g"
    assert prep_out.instruction_fields.description == "d"
    assert "instr" in prep_out.instruction_fields.specific_instructions
    assert any("u1" in i for i in prep_out.instruction_fields.specific_instructions)
    assert prep_out.context_requirements == ["dep1"]


async def test_non_atomic_verdict_returns_none_role_and_deterministic_fallback_prep(fake_llm_adapter_factory):
    adapter = fake_llm_adapter_factory([{"atomic": False, "role_if_atomic": None}])

    cls_out, prep_out = await classify_and_prep_step(
        step=_STEP, dependency_context=[], llm_adapter=adapter, block_id="blk-1", user_id="u1"
    )

    assert cls_out.atomic is False
    assert cls_out.role_if_atomic is None
    assert prep_out.instruction_fields.goal == _STEP.objective


async def test_raising_adapter_fails_closed_to_atomic_false():
    class RaisingAdapter:
        async def complete_json(self, **kwargs):
            raise LLMAdapterError("boom")

    cls_out, prep_out = await classify_and_prep_step(
        step=_STEP, dependency_context=[], llm_adapter=RaisingAdapter(), block_id="blk-1", user_id="u1"
    )

    assert cls_out.atomic is False
    assert cls_out.role_if_atomic is None
    assert prep_out.instruction_fields.goal == _STEP.objective


async def test_hollow_atomic_true_with_null_role_fails_closed(fake_llm_adapter_factory):
    # Schema-valid (role_if_atomic is nullable) but semantically hollow --
    # atomic=true must always carry a real role.
    adapter = fake_llm_adapter_factory([{"atomic": True, "role_if_atomic": None}] * 2)

    cls_out, prep_out = await classify_and_prep_step(
        step=_STEP, dependency_context=[], llm_adapter=adapter, block_id="blk-1", user_id="u1"
    )

    assert cls_out.atomic is False
    assert cls_out.role_if_atomic is None
    assert "task_handler_classify_and_prep_fallback_used" in cls_out.warnings


async def test_malformed_response_fails_closed(fake_llm_adapter_factory):
    adapter = fake_llm_adapter_factory([{"atomic": "not_a_boolean"}] * 2)

    cls_out, prep_out = await classify_and_prep_step(
        step=_STEP, dependency_context=[], llm_adapter=adapter, block_id="blk-1", user_id="u1"
    )

    assert cls_out.atomic is False
    assert cls_out.role_if_atomic is None


async def test_non_atomic_with_a_role_anyway_is_normalized_to_none(fake_llm_adapter_factory):
    adapter = fake_llm_adapter_factory([{"atomic": False, "role_if_atomic": "retrieval"}])

    cls_out, prep_out = await classify_and_prep_step(
        step=_STEP, dependency_context=[], llm_adapter=adapter, block_id="blk-1", user_id="u1"
    )

    assert cls_out.atomic is False
    assert cls_out.role_if_atomic is None


async def test_prose_context_requirements_falls_back_to_depends_on(fake_llm_adapter_factory):
    # Regression guard for a live-eval-found bug: the model reliably filled
    # context_requirements with a descriptive sentence ("Current semester
    # from step 1a.") instead of the exact step_id "1a" -- context_builder.py
    # resolves this list via an EXACT match against known step ids, so a
    # prose "id" never matches anything and the subagent silently receives
    # none of the data it depends on. Since the wrong value is non-empty, a
    # plain `or` fallback never used to catch it; every returned entry must
    # now be a real, known dependency id or the whole list is discarded in
    # favor of the step's own already-correct depends_on.
    step = _STEP.model_copy(update={"depends_on": ["1a", "1c"]})
    adapter = fake_llm_adapter_factory([{
        "atomic": True,
        "role_if_atomic": "calculation_validation",
        "context_requirements": ["Current semester label and year from step 1a."],
    }])

    _, prep_out = await classify_and_prep_step(
        step=step, dependency_context=[], llm_adapter=adapter, block_id="blk-1", user_id="u1"
    )

    assert prep_out.context_requirements == ["1a", "1c"]


async def test_context_requirements_subset_of_depends_on_is_trusted(fake_llm_adapter_factory):
    # A step legitimately needing only SOME of its declared dependencies'
    # data must not be forced back to the full depends_on list.
    step = _STEP.model_copy(update={"depends_on": ["1a", "1c"]})
    adapter = fake_llm_adapter_factory([{
        "atomic": True,
        "role_if_atomic": "calculation_validation",
        "context_requirements": ["1c"],
    }])

    _, prep_out = await classify_and_prep_step(
        step=step, dependency_context=[], llm_adapter=adapter, block_id="blk-1", user_id="u1"
    )

    assert prep_out.context_requirements == ["1c"]


def test_resolve_context_requirements_narrowing_is_honored_but_logged(caplog):
    """The subset is still returned (behavior unchanged), but the previously
    silent narrowing -- the one path that can starve a subagent of a declared
    dependency -- now leaves a diagnosable trace naming exactly what it
    dropped."""
    step = _STEP.model_copy(update={"depends_on": ["1a", "1c"]})
    with caplog.at_level(logging.DEBUG, logger="app.agent_core.orchestrator.task_handler_classify_and_prep"):
        resolved = _resolve_context_requirements(["1c"], step)

    assert resolved == ["1c"]
    record = next(r for r in caplog.records if r.message == "classify_and_prep_context_narrowed_below_depends_on")
    assert record.droppedContext == ["1a"]
    assert record.keptContext == ["1c"]
    assert record.stepId == "1a"


def test_resolve_context_requirements_discard_falls_back_and_logs(caplog):
    step = _STEP.model_copy(update={"depends_on": ["1a", "1c"]})
    with caplog.at_level(logging.DEBUG, logger="app.agent_core.orchestrator.task_handler_classify_and_prep"):
        resolved = _resolve_context_requirements(["prose that is not an id"], step)

    assert resolved == ["1a", "1c"]
    record = next(r for r in caplog.records if r.message == "classify_and_prep_context_discarded_using_depends_on")
    assert record.rejectedContext == ["prose that is not an id"]
    assert record.dependsOn == ["1a", "1c"]


def test_resolve_context_requirements_full_depends_on_does_not_log_a_drop(caplog):
    """Requesting exactly depends_on drops nothing, so it must NOT emit the
    narrowing log -- the trace stays quiet on the common, correct path."""
    step = _STEP.model_copy(update={"depends_on": ["1a", "1c"]})
    with caplog.at_level(logging.DEBUG, logger="app.agent_core.orchestrator.task_handler_classify_and_prep"):
        resolved = _resolve_context_requirements(["1a", "1c"], step)

    assert resolved == ["1a", "1c"]
    assert not [r for r in caplog.records if "narrowed" in r.message or "discarded" in r.message]


async def test_hallucinated_id_not_in_depends_on_falls_back(fake_llm_adapter_factory):
    step = _STEP.model_copy(update={"depends_on": ["1a", "1c"]})
    adapter = fake_llm_adapter_factory([{
        "atomic": True,
        "role_if_atomic": "calculation_validation",
        "context_requirements": ["1a", "not_a_real_step_id"],
    }])

    _, prep_out = await classify_and_prep_step(
        step=step, dependency_context=[], llm_adapter=adapter, block_id="blk-1", user_id="u1"
    )

    assert prep_out.context_requirements == ["1a", "1c"]


async def test_uses_cheap_llm_call_parameters(fake_llm_adapter_factory):
    adapter = fake_llm_adapter_factory([{"atomic": True, "role_if_atomic": "retrieval", "goal": "g", "description": "d"}])

    await classify_and_prep_step(
        step=_STEP, dependency_context=[], llm_adapter=adapter, block_id="blk-1", user_id="u1"
    )

    call = adapter.calls[0]
    assert call["thinking_enabled"] is False
    assert call["reasoning_effort"] == "low"
    assert call["timeout"] == 20.0
    assert call["max_retries"] == 1
