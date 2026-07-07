"""Unit tests for the shared `ReasoningBlock` runtime (Phase 1 foundation).

All tests use a fake LLM adapter — no real LLM calls are made.
"""

from __future__ import annotations

import json
from typing import Any

import pytest

from app.agent.reasoning.prompt_registry import (
    GENERIC_REASONING_BLOCK_V1,
    SCHEMA_REPAIR_V1,
    PromptContract,
    PromptContractNotFoundError,
    PromptRegistry,
    build_default_prompt_registry,
)
from app.agent.reasoning.llm_adapter import LLMAdapterError
from app.agent.reasoning.reasoning_block import ReasoningBlock
from app.agent.reasoning.schema_validator import validate_against_schema
from app.agent.reasoning.schemas import (
    ReasoningBlockInput,
    ReasoningBlockOutput,
    ReasoningPassPayload,
    ReasoningTrace,
)

_OUTPUT_SCHEMA: dict[str, Any] = {
    "type": "object",
    "properties": {
        "answer": {"type": "string"},
    },
    "required": ["answer"],
    "additionalProperties": False,
}


class FakeLLMAdapter:
    """Deterministic fake `LLMAdapter` that returns queued responses in order."""

    def __init__(self, responses: list[dict[str, Any]]) -> None:
        self._responses = list(responses)
        self.calls: list[dict[str, Any]] = []

    async def complete_json(
        self,
        *,
        system_prompt: str,
        user_prompt: str,
        temperature: float | None = None,
        response_schema: dict[str, Any] | None = None,
        raw_model_text_out: list[str] | None = None,
    ) -> dict[str, Any]:
        self.calls.append(
            {
                "system_prompt": system_prompt,
                "user_prompt": user_prompt,
                "temperature": temperature,
                "response_schema": response_schema,
            }
        )
        if not self._responses:
            raise AssertionError("FakeLLMAdapter exhausted its queued responses")
        response = self._responses.pop(0)
        if raw_model_text_out is not None:
            raw_model_text_out.append(json.dumps(response))
        return response


def _pass_payload(
    *,
    status: str = "ok",
    summary: str = "pass summary",
    result: dict[str, Any] | None = None,
    tool_requests: list[dict[str, Any]] | None = None,
    missing_context: list[str] | None = None,
    confidence: float | None = 0.7,
) -> dict[str, Any]:
    return {
        "status": status,
        "summary": summary,
        "key_factors": [],
        "missing_context": missing_context or [],
        "validation_notes": [],
        "warnings": [],
        "tool_requests": tool_requests or [],
        "confidence": confidence,
        "result": result,
    }


def _make_input(**overrides: Any) -> ReasoningBlockInput:
    defaults: dict[str, Any] = dict(
        block_id="blk-1",
        agent_name="test_agent",
        objective="Answer a simple test objective.",
        task_context={"foo": "bar"},
        output_schema_name="test_output_v1",
        output_schema=_OUTPUT_SCHEMA,
    )
    defaults.update(overrides)
    return ReasoningBlockInput(**defaults)


# ---------------------------------------------------------------------------
# Iteration count defaults
# ---------------------------------------------------------------------------


async def test_low_risk_task_runs_two_iterations_by_default():
    adapter = FakeLLMAdapter(
        [
            _pass_payload(summary="understood the task"),
            _pass_payload(summary="final answer", result={"answer": "ok"}),
        ]
    )
    block = ReasoningBlock(llm_adapter=adapter)

    output = await block.run(_make_input(risk_level="low"))

    assert len(adapter.calls) == 2
    assert output.iterations_used == 2
    assert output.status == "completed"
    assert output.schema_valid is True
    assert output.result == {"answer": "ok"}


async def test_medium_risk_task_runs_three_iterations_by_default():
    adapter = FakeLLMAdapter(
        [
            _pass_payload(summary="understood"),
            _pass_payload(summary="drafted"),
            _pass_payload(summary="reviewed", result={"answer": "ok"}),
        ]
    )
    block = ReasoningBlock(llm_adapter=adapter)

    output = await block.run(_make_input(risk_level="medium"))

    assert len(adapter.calls) == 3
    assert output.iterations_used == 3
    assert output.status == "completed"


async def test_high_risk_task_runs_three_iterations_by_default():
    adapter = FakeLLMAdapter(
        [
            _pass_payload(summary="understood"),
            _pass_payload(summary="drafted"),
            _pass_payload(summary="reviewed", result={"answer": "ok"}),
        ]
    )
    block = ReasoningBlock(llm_adapter=adapter)

    output = await block.run(_make_input(risk_level="high"))

    assert output.iterations_used == 3


async def test_explicit_min_max_iterations_override_risk_default():
    adapter = FakeLLMAdapter([_pass_payload(summary="only pass", result={"answer": "ok"})])
    block = ReasoningBlock(llm_adapter=adapter)

    output = await block.run(
        _make_input(risk_level="high", min_reasoning_iterations=1, max_reasoning_iterations=1)
    )

    assert output.iterations_used == 1
    assert len(adapter.calls) == 1


# ---------------------------------------------------------------------------
# Per-pass role differentiation end-to-end (via a custom contract + registry)
# ---------------------------------------------------------------------------


def _registry_with_role_differentiated_contract() -> tuple[PromptRegistry, str]:
    registry = build_default_prompt_registry()
    contract = PromptContract(
        name="test_role_differentiated_v1",
        version="1.0.0",
        role_prompt="You are a test agent.",
        output_schema_name="test_output_v1",
        default_min_iterations=3,
        default_max_iterations=3,
        pass_role_instructions={"draft": ["Check the previous pass for errors."]},
    )
    registry.register(contract)
    return registry, contract.name


async def test_role_differentiated_contract_varies_system_prompt_by_pass():
    adapter = FakeLLMAdapter(
        [
            _pass_payload(summary="understood"),
            _pass_payload(summary="drafted"),
            _pass_payload(summary="final", result={"answer": "ok"}),
        ]
    )
    registry, contract_name = _registry_with_role_differentiated_contract()
    block = ReasoningBlock(llm_adapter=adapter, prompt_registry=registry)

    await block.run(_make_input(risk_level="high", prompt_contract_name=contract_name))

    assert len(adapter.calls) == 3
    understand_prompt, draft_prompt, final_prompt = (call["system_prompt"] for call in adapter.calls)
    assert "Check the previous pass for errors." not in understand_prompt
    assert "Check the previous pass for errors." in draft_prompt
    assert "Check the previous pass for errors." not in final_prompt


async def test_contract_without_pass_role_instructions_uses_identical_system_prompt():
    adapter = FakeLLMAdapter(
        [
            _pass_payload(summary="understood"),
            _pass_payload(summary="drafted"),
            _pass_payload(summary="final", result={"answer": "ok"}),
        ]
    )
    block = ReasoningBlock(llm_adapter=adapter)

    await block.run(_make_input(risk_level="high"))

    system_prompts = {call["system_prompt"] for call in adapter.calls}
    assert len(system_prompts) == 1


# ---------------------------------------------------------------------------
# Schema validation
# ---------------------------------------------------------------------------


async def test_reasoning_block_validates_a_correct_output_schema():
    adapter = FakeLLMAdapter(
        [
            _pass_payload(summary="understood"),
            _pass_payload(summary="final", result={"answer": "graduation is on track"}),
        ]
    )
    block = ReasoningBlock(llm_adapter=adapter)

    output = await block.run(_make_input(risk_level="low"))

    assert output.schema_valid is True
    assert output.status == "completed"
    assert output.repair_attempts_used == 0


def test_schema_validator_accepts_a_valid_result():
    result = validate_against_schema({"answer": "ok"}, _OUTPUT_SCHEMA)
    assert result.valid is True
    assert result.errors == []


def test_schema_validator_rejects_missing_required_field():
    result = validate_against_schema({}, _OUTPUT_SCHEMA)
    assert result.valid is False
    assert result.errors


def test_schema_validator_rejects_wrong_field_type():
    result = validate_against_schema({"answer": 123}, _OUTPUT_SCHEMA)
    assert result.valid is False


def test_schema_validator_rejects_non_dict_result():
    result = validate_against_schema(["not", "a", "dict"], _OUTPUT_SCHEMA)
    assert result.valid is False
    assert "result_must_be_a_json_object" in result.errors


# ---------------------------------------------------------------------------
# Schema repair loop
# ---------------------------------------------------------------------------


async def test_reasoning_block_repairs_invalid_output_then_succeeds():
    adapter = FakeLLMAdapter(
        [
            _pass_payload(summary="understood"),
            _pass_payload(summary="final", result={"wrong_field": "oops"}),
            {"answer": "fixed"},
        ]
    )
    block = ReasoningBlock(llm_adapter=adapter)

    output = await block.run(_make_input(risk_level="low", max_schema_repair_attempts=2))

    assert len(adapter.calls) == 3
    assert output.status == "completed"
    assert output.schema_valid is True
    assert output.repair_attempts_used == 1
    assert output.result == {"answer": "fixed"}


async def test_reasoning_block_fails_safely_after_repair_budget_exhausted():
    adapter = FakeLLMAdapter(
        [
            _pass_payload(summary="understood"),
            _pass_payload(summary="final", result={"wrong_field": "oops"}),
            {"still_wrong": True},
            {"still_wrong_again": True},
        ]
    )
    block = ReasoningBlock(llm_adapter=adapter)

    output = await block.run(_make_input(risk_level="low", max_schema_repair_attempts=2))

    assert len(adapter.calls) == 4
    assert output.status == "failed"
    assert output.schema_valid is False
    assert output.repair_attempts_used == 2
    assert "schema_validation_failed" in output.warnings


# ---------------------------------------------------------------------------
# Tool requests / missing context short-circuit
# ---------------------------------------------------------------------------


async def test_reasoning_block_returns_needs_tool_when_llm_requests_a_tool():
    adapter = FakeLLMAdapter(
        [
            _pass_payload(
                status="needs_tool",
                summary="need to verify course number",
                tool_requests=[
                    {
                        "tool_name": "catalog_lookup",
                        "purpose": "verify course number",
                        "arguments": {"courseNumber": "234218"},
                    }
                ],
            ),
        ]
    )
    block = ReasoningBlock(llm_adapter=adapter)

    output = await block.run(_make_input(risk_level="medium"))

    assert output.status == "needs_tool"
    assert output.iterations_used == 1
    assert output.result is None
    assert len(output.tool_requests) == 1
    assert output.tool_requests[0].tool_name == "catalog_lookup"
    assert len(adapter.calls) == 1


async def test_reasoning_block_returns_needs_more_context_when_context_is_missing():
    adapter = FakeLLMAdapter(
        [
            _pass_payload(
                status="needs_more_context",
                summary="student profile is missing",
                missing_context=["student_profile"],
            ),
        ]
    )
    block = ReasoningBlock(llm_adapter=adapter)

    output = await block.run(_make_input(risk_level="high"))

    assert output.status == "needs_more_context"
    assert "student_profile" in output.missing_context
    assert output.iterations_used == 1
    assert len(adapter.calls) == 1


# ---------------------------------------------------------------------------
# Adaptive early exit (flag-gated; off by default)
# ---------------------------------------------------------------------------


def _adaptive_settings(*, threshold: float | None = None) -> "Settings":
    from app.config import Settings

    overrides: dict[str, Any] = {"AGENT_REASONING_ADAPTIVE_ITERATIONS_ENABLED": True}
    if threshold is not None:
        overrides["AGENT_REASONING_ADAPTIVE_CONFIDENCE_THRESHOLD"] = threshold
    return Settings(**overrides)


async def test_adaptive_early_exit_disabled_by_default_runs_all_scheduled_passes():
    adapter = FakeLLMAdapter(
        [
            _pass_payload(summary="understood", confidence=0.95, result={"answer": "ok"}),
            _pass_payload(summary="drafted", confidence=0.95, result={"answer": "ok"}),
            _pass_payload(summary="final", confidence=0.95, result={"answer": "ok"}),
        ]
    )
    block = ReasoningBlock(llm_adapter=adapter)

    output = await block.run(_make_input(risk_level="medium"))

    assert len(adapter.calls) == 3
    assert output.iterations_used == 3
    assert "adaptive_early_exit" not in output.warnings


async def test_adaptive_early_exit_stops_after_confident_intermediate_pass():
    adapter = FakeLLMAdapter(
        [
            _pass_payload(summary="understood", confidence=0.95, result={"answer": "ok"}),
            # Passes 2 and 3 would raise (FakeLLMAdapter exhausts) if actually called.
        ]
    )
    block = ReasoningBlock(llm_adapter=adapter, settings=_adaptive_settings())

    output = await block.run(
        _make_input(risk_level="medium", min_reasoning_iterations=1, max_reasoning_iterations=3)
    )

    assert len(adapter.calls) == 1
    assert output.iterations_used == 1
    assert output.status == "completed"
    assert output.schema_valid is True
    assert output.result == {"answer": "ok"}
    assert "adaptive_early_exit" in output.warnings


async def test_adaptive_early_exit_declined_when_confidence_below_threshold():
    adapter = FakeLLMAdapter(
        [
            _pass_payload(summary="understood", confidence=0.4, result={"answer": "tentative"}),
            _pass_payload(summary="final", confidence=0.9, result={"answer": "ok"}),
        ]
    )
    block = ReasoningBlock(
        llm_adapter=adapter, settings=_adaptive_settings(threshold=0.75)
    )

    output = await block.run(
        _make_input(risk_level="medium", min_reasoning_iterations=1, max_reasoning_iterations=2)
    )

    assert len(adapter.calls) == 2
    assert output.result == {"answer": "ok"}


async def test_adaptive_early_exit_declined_when_missing_context_present():
    adapter = FakeLLMAdapter(
        [
            _pass_payload(
                summary="understood",
                confidence=0.95,
                result={"answer": "ok"},
                missing_context=["student_profile"],
            ),
            _pass_payload(summary="final", confidence=0.95, result={"answer": "ok"}),
        ]
    )
    block = ReasoningBlock(
        llm_adapter=adapter, settings=_adaptive_settings()
    )

    output = await block.run(
        _make_input(risk_level="medium", min_reasoning_iterations=1, max_reasoning_iterations=2)
    )

    assert len(adapter.calls) == 2


async def test_adaptive_early_exit_respects_explicit_min_iterations_floor():
    adapter = FakeLLMAdapter(
        [
            _pass_payload(summary="understood", confidence=0.99, result={"answer": "ok"}),
            _pass_payload(summary="final", confidence=0.99, result={"answer": "ok"}),
        ]
    )
    block = ReasoningBlock(llm_adapter=adapter, settings=_adaptive_settings())

    # min_reasoning_iterations=2 means pass 1 must never early-exit, even at
    # maximal confidence with a populated result.
    output = await block.run(
        _make_input(risk_level="medium", min_reasoning_iterations=2, max_reasoning_iterations=2)
    )

    assert len(adapter.calls) == 2
    assert output.iterations_used == 2


# ---------------------------------------------------------------------------
# Privacy: no chain-of-thought fields anywhere
# ---------------------------------------------------------------------------


def test_no_output_model_includes_chain_of_thought_fields():
    banned = {
        "chain_of_thought",
        "chainofthought",
        "hidden_reasoning",
        "private_reasoning",
        "raw_reasoning",
        "internal_reasoning",
        "reasoning_text",
    }
    for model in (ReasoningBlockInput, ReasoningBlockOutput, ReasoningPassPayload, ReasoningTrace):
        field_names = {name.lower() for name in model.model_fields}
        leaked = field_names & banned
        assert not leaked, f"{model.__name__} exposes banned field(s): {leaked}"


# ---------------------------------------------------------------------------
# Safe fallback when LLM is unavailable
# ---------------------------------------------------------------------------


async def test_missing_llm_configuration_fails_safely_without_crashing():
    from app.agent.reasoning.llm_adapter import ChatLLMAdapter
    from app.config import Settings

    # Explicit settings (not env/.env-derived) guarantee no API key is configured,
    # regardless of what a developer's local .env happens to contain. The field
    # uses a validation_alias, so it must be set via that alias to take effect.
    unconfigured_settings = Settings(**{"OPENAI_API_KEY": None})
    block = ReasoningBlock(llm_adapter=ChatLLMAdapter(settings=unconfigured_settings))

    output = await block.run(_make_input(risk_level="low"))

    assert output.status == "failed"
    assert output.schema_valid is False
    assert output.iterations_used == 0
    assert any("llm_adapter_error" in warning for warning in output.warnings)


# ---------------------------------------------------------------------------
# Prompt registry
# ---------------------------------------------------------------------------


# ---------------------------------------------------------------------------
# Debug observer / eval LLM tracker fire once per actual LLM call
# ---------------------------------------------------------------------------


class FakeDebugObserver:
    """Records every `on_llm_call` invocation (mirrors `ReasoningBlockDebugObserver`)."""

    def __init__(self) -> None:
        self.events: list[dict[str, Any]] = []

    def on_llm_call(self, **kwargs: Any) -> None:
        self.events.append(kwargs)


async def test_debug_observer_fires_once_per_pass_for_multi_pass_run():
    adapter = FakeLLMAdapter(
        [
            _pass_payload(summary="understood"),
            _pass_payload(summary="drafted"),
            _pass_payload(summary="reviewed", result={"answer": "ok"}),
        ]
    )
    observer = FakeDebugObserver()
    block = ReasoningBlock(
        llm_adapter=adapter,
        debug_observer=observer,
        debug_case_id="case-1",
        debug_phase="test_phase",
    )

    output = await block.run(_make_input(risk_level="medium"))

    assert output.status == "completed"
    assert len(adapter.calls) == 3
    # Previously only the terminal pass emitted — now every real LLM call does.
    assert len(observer.events) == 3
    assert [event["phase"] for event in observer.events] == [
        "test_phase:pass1_understand",
        "test_phase:pass2_draft",
        "test_phase:pass3_final",
    ]


async def test_debug_observer_fires_on_early_exit_needs_more_context():
    adapter = FakeLLMAdapter(
        [
            _pass_payload(
                status="needs_more_context",
                summary="student profile is missing",
                missing_context=["student_profile"],
            ),
        ]
    )
    observer = FakeDebugObserver()
    block = ReasoningBlock(
        llm_adapter=adapter,
        debug_observer=observer,
        debug_case_id="case-2",
        debug_phase="test_phase",
    )

    output = await block.run(_make_input(risk_level="high"))

    assert output.status == "needs_more_context"
    assert len(adapter.calls) == 1
    # Previously the early-exit path never emitted at all, regardless of pass index.
    assert len(observer.events) == 1
    assert observer.events[0]["phase"] == "test_phase:pass1_understand"


class FailingAdapter:
    """Fake `LLMAdapter` that always raises `LLMAdapterError`."""

    def __init__(self) -> None:
        self.calls = 0

    async def complete_json(self, **_kwargs: Any) -> dict[str, Any]:
        self.calls += 1
        raise LLMAdapterError("llm_call_failed")


async def test_debug_observer_fires_on_llm_adapter_error_at_any_pass():
    adapter = FailingAdapter()
    observer = FakeDebugObserver()
    block = ReasoningBlock(
        llm_adapter=adapter,
        debug_observer=observer,
        debug_case_id="case-3",
        debug_phase="test_phase",
    )

    output = await block.run(_make_input(risk_level="medium"))

    assert output.status == "failed"
    assert adapter.calls == 1
    assert len(observer.events) == 1
    assert observer.events[0]["phase"] == "test_phase:pass1_understand"


def test_prompt_registry_returns_expected_default_contracts():
    registry = build_default_prompt_registry()

    # Phase 2 adds role-specific contracts to the same registry; assert the
    # Phase 1 foundation contracts are still present rather than pinning the
    # full set (see test_prompt_registry_extensions.py for Phase 2 contracts).
    assert {GENERIC_REASONING_BLOCK_V1, SCHEMA_REPAIR_V1}.issubset(set(registry.names()))

    generic = registry.get(GENERIC_REASONING_BLOCK_V1)
    assert generic.default_min_iterations == 2
    assert generic.default_max_iterations == 3
    assert "JSON" in generic.role_prompt
    assert any("chain-of-thought" in rule.lower() for rule in generic.instructions)
    assert any("needs_more_context" in rule for rule in generic.instructions)

    repair = registry.get(SCHEMA_REPAIR_V1)
    assert "schema" in repair.role_prompt.lower()
    assert repair.default_max_iterations == 1

    with pytest.raises(PromptContractNotFoundError):
        registry.get("does_not_exist_v1")
