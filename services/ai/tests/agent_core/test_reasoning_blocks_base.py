"""Tests for `BaseReasoningBlock` (AGENT_VISION.md §6.2).

Exercised via `_EchoReasoningBlock`, a minimal single-shot concrete shape
defined only in this test file -- `BaseReasoningBlock` is abstract and has
no production subclass yet (Request Understanding's own concrete shape is
separate, later work). This proves the base's own mechanics: the
"never raises" guarantee, `_invoke_llm`'s parsed+raw-text return shape,
`_repair_schema` composed from the other helpers, `total_llm_calls_used`
counting, and `LLMCallParameters` override-vs-contract-default resolution.
"""

from __future__ import annotations

from typing import Any

from app.agent_core.reasoning.llm_adapter import LLMAdapterError
from app.agent_core.reasoning.prompt_registry import build_default_prompt_registry
from app.agent_core.reasoning_blocks.base import BaseReasoningBlock, RunTelemetry
from app.agent_core.reasoning_blocks.schemas import (
    BaseReasoningBlockInput,
    BaseReasoningBlockOutput,
    LLMCallParameters,
)

_TEST_SCHEMA_NAME = "echo_test_output_v1"
_TEST_OUTPUT_SCHEMA: dict[str, Any] = {
    "type": "object",
    "properties": {"answer": {"type": "string"}},
    "required": ["answer"],
    "additionalProperties": False,
}


def _make_block_input(**overrides: Any) -> BaseReasoningBlockInput:
    defaults: dict[str, Any] = dict(
        block_id="test-block-1",
        agent_name="echo_test",
        objective="Say hello.",
        output_schema_name=_TEST_SCHEMA_NAME,
        output_schema=_TEST_OUTPUT_SCHEMA,
    )
    defaults.update(overrides)
    return BaseReasoningBlockInput(**defaults)


class _EchoReasoningBlock(BaseReasoningBlock):
    """Test-only single-shot shape: one `_invoke_llm` call, normalize +
    validate, repair once if invalid."""

    def __init__(self, *, llm_adapter: Any, **kwargs: Any) -> None:
        super().__init__(
            llm_adapter=llm_adapter,
            prompt_registry=kwargs.pop("prompt_registry", None) or build_default_prompt_registry(),
            **kwargs,
        )

    async def _run_internal(
        self, block_input: BaseReasoningBlockInput, telemetry: RunTelemetry
    ) -> BaseReasoningBlockOutput:
        contract = self._resolve_prompt_contract(block_input.prompt_contract_name)
        params = self._resolve_llm_call_parameters(block_input.llm_call_parameters, contract)
        call_result = await self._invoke_llm(
            system_prompt=contract.role_prompt,
            user_prompt=block_input.objective,
            params=params,
            response_schema=block_input.output_schema,
            phase="pass1_of_1",
            block_input=block_input,
            telemetry=telemetry,
        )
        normalized = self._normalize_result(call_result.parsed, output_schema=block_input.output_schema)
        validation = self._validate_schema(normalized, block_input.output_schema)
        if validation.valid:
            return BaseReasoningBlockOutput(status="completed", schema_valid=True, result=normalized, confidence=0.9)

        repair_outcome = await self._repair_schema(
            initial_result=normalized,
            initial_errors=validation.errors,
            output_schema=block_input.output_schema,
            max_attempts=2,
            block_input=block_input,
            telemetry=telemetry,
        )
        if repair_outcome.valid:
            return BaseReasoningBlockOutput(
                status="completed",
                schema_valid=True,
                result=repair_outcome.result,
                confidence=0.7,
                warnings=["repair_succeeded"],
            )
        return BaseReasoningBlockOutput(
            status="failed",
            schema_valid=False,
            result=None,
            confidence=0.0,
            warnings=["schema_validation_failed", *repair_outcome.errors[:5]],
        )


class _RaisingRunInternalBlock(BaseReasoningBlock):
    """Test-only shape whose `_run_internal` always raises a plain
    exception -- proves `run()`'s outer safety net, independent of any
    LLM-adapter-specific error path."""

    async def _run_internal(self, block_input: BaseReasoningBlockInput, telemetry: RunTelemetry) -> Any:
        raise ValueError("boom_from_run_internal")


class _RaisingLLMAdapter:
    async def complete_json(self, **_kwargs: Any) -> dict[str, Any]:
        raise LLMAdapterError("llm_unavailable_test")


async def test_run_never_raises_when_run_internal_raises(fake_llm_adapter_factory):
    block = _RaisingRunInternalBlock(llm_adapter=fake_llm_adapter_factory([]), prompt_registry=build_default_prompt_registry())

    output = await block.run(_make_block_input())

    assert output.status == "failed"
    assert output.schema_valid is False
    assert output.result is None


async def test_invoke_llm_error_propagates_and_run_returns_failed_status():
    block = _EchoReasoningBlock(llm_adapter=_RaisingLLMAdapter())

    output = await block.run(_make_block_input())

    assert output.status == "failed"
    # "llm_unavailable_test" is a hard failure, not a parse failure -- one call,
    # no retry.
    assert output.total_llm_calls_used == 1


class _ParseFailingThenSucceedingAdapter:
    """Raises `json_parse_failed` for the first `fail_times` calls, then returns
    a valid payload -- models the transient parse flake seen in live-eval runs."""

    def __init__(self, *, fail_times: int, payload: dict[str, Any] | None = None) -> None:
        self._fail_times = fail_times
        self._payload = payload if payload is not None else {"answer": "hello"}
        self.calls = 0

    async def complete_json(self, **_kwargs: Any) -> dict[str, Any]:
        self.calls += 1
        if self.calls <= self._fail_times:
            raise LLMAdapterError("json_parse_failed")
        return dict(self._payload)


class _HardFailingAdapter:
    """Always raises a NON-parse (hard) failure -- must never be retried."""

    def __init__(self) -> None:
        self.calls = 0

    async def complete_json(self, **_kwargs: Any) -> dict[str, Any]:
        self.calls += 1
        raise LLMAdapterError("llm_unavailable")


async def test_invoke_llm_retries_transient_parse_failure_then_succeeds():
    adapter = _ParseFailingThenSucceedingAdapter(fail_times=1)
    block = _EchoReasoningBlock(llm_adapter=adapter)

    output = await block.run(_make_block_input())

    assert output.status == "completed"
    assert output.result == {"answer": "hello"}
    assert adapter.calls == 2  # first call flaked, the retry recovered it
    assert output.total_llm_calls_used == 2


async def test_invoke_llm_gives_up_after_parse_failure_retries_exhausted():
    adapter = _ParseFailingThenSucceedingAdapter(fail_times=99)  # never recovers
    block = _EchoReasoningBlock(llm_adapter=adapter)

    output = await block.run(_make_block_input())

    assert output.status == "failed"
    assert adapter.calls == 2  # one initial attempt + one bounded retry, then give up
    assert output.total_llm_calls_used == 2


async def test_invoke_llm_does_not_retry_a_hard_failure():
    adapter = _HardFailingAdapter()
    block = _EchoReasoningBlock(llm_adapter=adapter)

    output = await block.run(_make_block_input())

    assert output.status == "failed"
    assert adapter.calls == 1  # a non-parse failure will not fix itself; no retry


async def test_repair_schema_recovers_initially_invalid_result_and_counts_calls(fake_llm_adapter_factory):
    adapter = fake_llm_adapter_factory(
        [
            {},  # missing required "answer" -> schema-invalid
            {"answer": "hello"},  # repair attempt succeeds
        ]
    )
    block = _EchoReasoningBlock(llm_adapter=adapter)

    output = await block.run(_make_block_input())

    assert output.status == "completed"
    assert output.schema_valid is True
    assert output.result == {"answer": "hello"}
    assert "repair_succeeded" in output.warnings
    assert output.total_llm_calls_used == 2


async def test_successful_single_pass_completes_without_repair(fake_llm_adapter_factory):
    adapter = fake_llm_adapter_factory([{"answer": "hello"}])
    block = _EchoReasoningBlock(llm_adapter=adapter)

    output = await block.run(_make_block_input())

    assert output.status == "completed"
    assert output.result == {"answer": "hello"}
    assert output.total_llm_calls_used == 1


def test_resolve_llm_call_parameters_override_wins_and_falls_back_to_contract_default(fake_llm_adapter_factory):
    block = _EchoReasoningBlock(llm_adapter=fake_llm_adapter_factory([]))
    registry = build_default_prompt_registry()
    contract = registry.get("generic_reasoning_block_v1")

    explicit = block._resolve_llm_call_parameters(LLMCallParameters(temperature=0.9), contract)
    assert explicit.temperature == 0.9

    fallback = block._resolve_llm_call_parameters(LLMCallParameters(), contract)
    assert fallback.temperature == contract.default_temperature


async def test_llm_call_parameters_actually_reach_the_adapter(fake_llm_adapter_factory):
    adapter = fake_llm_adapter_factory([{"answer": "hello"}])
    block = _EchoReasoningBlock(llm_adapter=adapter)

    await block.run(
        _make_block_input(llm_call_parameters=LLMCallParameters(model="gpt-4o", temperature=0.0))
    )

    assert adapter.calls[0]["model"] == "gpt-4o"
    assert adapter.calls[0]["temperature"] == 0.0


_ROUND_SCHEMA: dict[str, Any] = {
    "type": "object",
    "properties": {
        "status": {"type": "string", "enum": ["ready", "need_tools"]},
        "tool_requests": {
            "type": "array",
            "items": {
                "type": "object",
                "properties": {"tool_name": {"type": "string"}, "arguments": {"type": "object"}},
                "required": ["tool_name", "arguments"],
            },
        },
    },
    "required": ["status"],
}


async def test_repair_tool_requests_returns_unchanged_when_already_valid(fake_llm_adapter_factory):
    # No repair call should be spent when the round output is already
    # well-formed -- `_repair_tool_requests_if_needed` must not add cost to
    # the already-happy path.
    adapter = fake_llm_adapter_factory([])
    block = _EchoReasoningBlock(llm_adapter=adapter)
    parsed = {
        "status": "need_tools",
        "tool_requests": [{"tool_name": "get_entity", "arguments": {"entity_id": "1"}}],
    }

    result = await block._repair_tool_requests_if_needed(
        parsed,
        parsed["tool_requests"],
        round_schema=_ROUND_SCHEMA,
        block_input=_make_block_input(),
        telemetry=RunTelemetry(),
    )

    assert result == parsed["tool_requests"]
    assert len(adapter.calls) == 0


async def test_repair_tool_requests_backfills_missing_arguments_without_an_llm_call(fake_llm_adapter_factory):
    # A request that names a tool but omits `arguments` (the common shape for
    # zero-arg tools) is fixed deterministically to {} -- no repair call.
    adapter = fake_llm_adapter_factory([])
    block = _EchoReasoningBlock(llm_adapter=adapter)
    parsed = {
        "status": "need_tools",
        "tool_requests": [{"tool_name": "get_current_semester"}, {"tool_name": "get_entity", "arguments": None}],
    }

    result = await block._repair_tool_requests_if_needed(
        parsed,
        parsed["tool_requests"],
        round_schema=_ROUND_SCHEMA,
        block_input=_make_block_input(),
        telemetry=RunTelemetry(),
    )

    assert result == [
        {"tool_name": "get_current_semester", "arguments": {}},
        {"tool_name": "get_entity", "arguments": {}},
    ]
    assert len(adapter.calls) == 0


async def test_repair_tool_requests_fixes_wrong_keys_via_one_repair_call(fake_llm_adapter_factory):
    adapter = fake_llm_adapter_factory(
        [
            {
                "status": "need_tools",
                "tool_requests": [{"tool_name": "get_entity", "arguments": {"entity_id": "1"}}],
            }
        ]
    )
    block = _EchoReasoningBlock(llm_adapter=adapter)
    parsed = {
        "status": "need_tools",
        "tool_requests": [{"name": "get_entity", "params": {"entity_id": "1"}}],
    }

    result = await block._repair_tool_requests_if_needed(
        parsed,
        parsed["tool_requests"],
        round_schema=_ROUND_SCHEMA,
        block_input=_make_block_input(),
        telemetry=RunTelemetry(),
    )

    assert result == [{"tool_name": "get_entity", "arguments": {"entity_id": "1"}}]
    assert len(adapter.calls) == 1


async def test_repair_tool_requests_falls_back_to_original_when_repair_fails():
    # Never worse than the old behavior: if the repair attempt itself
    # doesn't produce a valid result, the original (still-malformed)
    # requests are returned unchanged rather than raising or losing data.
    class _NeverRepairsAdapter:
        async def complete_json(self, **_kwargs: Any) -> dict[str, Any]:
            return {}  # missing required "status" -> stays invalid

    block = _EchoReasoningBlock(llm_adapter=_NeverRepairsAdapter())
    original_requests = [{"name": "get_entity", "params": {"entity_id": "1"}}]
    parsed = {"status": "need_tools", "tool_requests": original_requests}

    result = await block._repair_tool_requests_if_needed(
        parsed,
        original_requests,
        round_schema=_ROUND_SCHEMA,
        block_input=_make_block_input(),
        telemetry=RunTelemetry(),
    )

    assert result == original_requests
