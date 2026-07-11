"""Tests for `app.agent_core.orchestrator.task_handler_classifier`."""

from __future__ import annotations

from app.agent_core.orchestrator.task_handler_classifier import classify_step
from app.agent_core.planning.schemas import PlanStep
from app.agent_core.reasoning.llm_adapter import LLMAdapterError

_STEP = PlanStep(
    step_id="1a",
    objective="Retrieve the student's completed courses.",
    depends_on=[],
    success_criteria=["completed courses returned"],
    assumptions_to_verify=[],
)


async def test_atomic_verdict_returns_the_role(fake_llm_adapter_factory):
    adapter = fake_llm_adapter_factory([{"atomic": True, "role_if_atomic": "retrieval"}])

    output = await classify_step(step=_STEP, dependency_context=[], llm_adapter=adapter, block_id="blk-1")

    assert output.atomic is True
    assert output.role_if_atomic == "retrieval"


async def test_non_atomic_verdict_returns_none_role(fake_llm_adapter_factory):
    adapter = fake_llm_adapter_factory([{"atomic": False, "role_if_atomic": None}])

    output = await classify_step(step=_STEP, dependency_context=[], llm_adapter=adapter, block_id="blk-1")

    assert output.atomic is False
    assert output.role_if_atomic is None


async def test_raising_adapter_fails_closed_to_atomic_false():
    class RaisingAdapter:
        async def complete_json(self, **kwargs):
            raise LLMAdapterError("boom")

    output = await classify_step(step=_STEP, dependency_context=[], llm_adapter=RaisingAdapter(), block_id="blk-1")

    assert output.atomic is False
    assert output.role_if_atomic is None


async def test_hollow_atomic_true_with_null_role_fails_closed(fake_llm_adapter_factory):
    # Schema-valid (role_if_atomic is nullable) but semantically hollow --
    # atomic=true must always carry a real role.
    adapter = fake_llm_adapter_factory([{"atomic": True, "role_if_atomic": None}] * 2)

    output = await classify_step(step=_STEP, dependency_context=[], llm_adapter=adapter, block_id="blk-1")

    assert output.atomic is False
    assert output.role_if_atomic is None
    assert "task_handler_classifier_fallback_used" in output.warnings


async def test_malformed_response_fails_closed(fake_llm_adapter_factory):
    adapter = fake_llm_adapter_factory([{"atomic": "not_a_boolean"}] * 2)

    output = await classify_step(step=_STEP, dependency_context=[], llm_adapter=adapter, block_id="blk-1")

    assert output.atomic is False
    assert output.role_if_atomic is None


async def test_non_atomic_with_a_role_anyway_is_normalized_to_none(fake_llm_adapter_factory):
    adapter = fake_llm_adapter_factory([{"atomic": False, "role_if_atomic": "retrieval"}])

    output = await classify_step(step=_STEP, dependency_context=[], llm_adapter=adapter, block_id="blk-1")

    assert output.atomic is False
    assert output.role_if_atomic is None


async def test_uses_cheap_llm_call_parameters(fake_llm_adapter_factory):
    adapter = fake_llm_adapter_factory([{"atomic": True, "role_if_atomic": "retrieval"}])

    await classify_step(step=_STEP, dependency_context=[], llm_adapter=adapter, block_id="blk-1")

    call = adapter.calls[0]
    assert call["thinking_enabled"] is False
    assert call["reasoning_effort"] == "low"
    assert call["timeout"] == 15.0
    assert call["max_retries"] == 1
