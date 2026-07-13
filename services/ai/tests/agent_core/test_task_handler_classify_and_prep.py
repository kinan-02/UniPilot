"""Tests for `app.agent_core.orchestrator.task_handler_classify_and_prep`."""

from __future__ import annotations

from app.agent_core.orchestrator.task_handler_classify_and_prep import classify_and_prep_step
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
    adapter = fake_llm_adapter_factory([{
        "atomic": True,
        "role_if_atomic": "retrieval",
        "goal": "g",
        "description": "d",
        "specific_instructions": ["instr"],
        "context_requirements": ["dep1"]
    }])

    cls_out, prep_out = await classify_and_prep_step(
        step=_STEP, dependency_context=[], llm_adapter=adapter, block_id="blk-1", user_id="u1"
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
