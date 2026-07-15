"""BaseReasoningBlock (AGENT_VISION.md §6.2): the shared floor every
component-specific reasoning-block shape extends.

Nothing existing consumes this yet -- `ReasoningBlock` and its current
callers (Planner, step-prep, subagents, Request Understanding) are
untouched. This is the foundation for future per-component shapes (a single
decisive call, a call-tool-call loop, a self-reflection loop, a
multi-persona debate, ...), each of which owns its own `_run_internal`
freely. Only `run()` -- the "never raises" safety net -- and the composable
helpers below are shared; there is no fixed internal step order, because the
shapes above have genuinely incompatible internal call graphs.
"""

from __future__ import annotations

import asyncio
import json
import logging
import time
from abc import ABC, abstractmethod
from dataclasses import dataclass
from typing import Any

from app.agent_core.reasoning.debug_observer import ReasoningBlockDebugObserver
from app.agent_core.reasoning.llm_adapter import LLMAdapter, LLMAdapterError
from app.agent_core.reasoning.prompt_registry import (
    GENERIC_REASONING_BLOCK_V1,
    SCHEMA_REPAIR_V1,
    PromptContract,
    PromptRegistry,
)
from app.agent_core.reasoning.result_normalizer import normalize_structured_result
from app.agent_core.reasoning.schema_validator import validate_against_schema
from app.agent_core.reasoning.schemas import SchemaRepairOutcome, SchemaValidationResult
from app.agent_core.reasoning_blocks.schemas import (
    BaseReasoningBlockInput,
    BaseReasoningBlockOutput,
    LLMCallParameters,
)

logger = logging.getLogger(__name__)

# A parse-failure code means the model DID answer, but the text wasn't valid
# JSON -- a transient flake a fresh call usually fixes. Distinct from a hard
# failure (no model, import error) that a retry cannot help. Live-eval runs
# showed an un-retried json_parse_failed at the composition/interpretation step
# was the single dominant cause of a turn ending in neither answer nor
# clarification.
_PARSE_FAILURE_CODES = frozenset({"json_parse_failed", "invalid_json_response"})
_MAX_PARSE_FAILURE_RETRIES = 1


@dataclass
class RunTelemetry:
    """Per-`run()`-call mutable state.

    Created fresh inside `run()` and threaded down as a parameter -- never
    stored on `self` -- so it stays correct even if a single block instance
    is reused across concurrent `run()` calls.
    """

    call_count: int = 0


@dataclass
class LlmCallResult:
    """What `_invoke_llm` returns: parsed JSON and raw text together.

    Replaces the mutate-a-list-in-place `raw_model_text_out` output
    parameter the underlying `LLMAdapter.complete_json` protocol still uses
    internally -- callers of this helper never see that pattern.
    """

    parsed: dict[str, Any]
    raw_text: str
    # True when `parsed` was reconstructed from an unparseable prose response
    # rather than returned by the model as JSON -- see `_invoke_llm`'s
    # `salvage_text_field`. Callers surface this as a warning; it is a recovered
    # answer, not a clean one.
    salvaged: bool = False


def _build_repair_user_prompt(
    *,
    invalid_result: dict[str, Any] | None,
    output_schema: dict[str, Any],
    errors: list[str],
) -> str:
    payload = {
        "instruction": (
            "The previous output failed schema validation. Fix only the structure. "
            "Do not add new facts. Do not change the meaning. Return only valid JSON "
            "matching the schema."
        ),
        "output_schema": output_schema,
        "previous_output": invalid_result,
        "validation_errors": errors,
    }
    return json.dumps(payload, ensure_ascii=False, indent=2)


class BaseReasoningBlock(ABC):
    """Identity, LLM/prompt access, and composable helpers -- no fixed
    internal step order. Each concrete shape implements `_run_internal`
    freely, using the helpers below in whatever order/combination it needs;
    `run()` is the one thing every shape gets for free.
    """

    def __init__(
        self,
        *,
        llm_adapter: LLMAdapter,
        prompt_registry: PromptRegistry,
        debug_observer: ReasoningBlockDebugObserver | None = None,
        debug_case_id: str | None = None,
        streaming_queue: asyncio.Queue[str] | None = None,
    ) -> None:
        # Exactly one adapter, one registry -- the honest common minimum.
        # A future shape that genuinely needs more than one (e.g. a
        # multi-persona debate) accepts extras in its own constructor and
        # calls `super().__init__(llm_adapter=<primary>, ...)`; the base
        # doesn't pre-anticipate a shape nothing concrete needs yet.
        self._llm_adapter = llm_adapter
        self._prompt_registry = prompt_registry
        self._debug_observer = debug_observer
        self._debug_case_id = debug_case_id
        self._streaming_queue = streaming_queue

    # ------------------------------------------------------------------
    # The one structural guarantee every shape gets for free: never raises.
    # ------------------------------------------------------------------

    async def run(self, block_input: BaseReasoningBlockInput) -> BaseReasoningBlockOutput:
        """Run this block's own shape for one task.

        Never raises: any exception from `_run_internal` (including one
        propagated up from `_invoke_llm`) is caught here and turned into a
        well-formed `status="failed"` output. Callers only ever need to
        check `output.status` -- never wrap a call to `run()` in their own
        try/except again.
        """
        telemetry = RunTelemetry()
        started_at = time.monotonic()
        try:
            output = await self._run_internal(block_input, telemetry)
        except Exception:
            logger.exception(
                "reasoning_block_run_internal_raised",
                extra={"block_id": block_input.block_id, "agent_name": block_input.agent_name},
            )
            output = self._failed_output(block_input, reason="internal_error")
        output = output.model_copy(update={"total_llm_calls_used": telemetry.call_count})
        self._trace(block_input, output, started_at)
        return output

    @abstractmethod
    async def _run_internal(
        self, block_input: BaseReasoningBlockInput, telemetry: RunTelemetry
    ) -> BaseReasoningBlockOutput:
        """Each concrete shape's own control flow -- single-shot, tool loop,
        self-reflection, multi-persona -- goes here, freely, using the
        helpers below in whatever order it needs. No prescribed sequence.
        """

    def _failed_output(self, block_input: BaseReasoningBlockInput, *, reason: str) -> BaseReasoningBlockOutput:
        """Base default for a hard failure. Subclasses whose own `Output`
        subtype has extra required fields should override this.
        """
        return BaseReasoningBlockOutput(
            status="failed",
            schema_valid=False,
            result=None,
            confidence=0.0,
            warnings=[f"reasoning_block_failed: {reason}"],
        )

    # ------------------------------------------------------------------
    # Shared, composable helpers -- called in whatever order each shape needs.
    # ------------------------------------------------------------------

    def _resolve_prompt_contract(self, name: str | None) -> PromptContract:
        """Registry lookup, falling back to the generic default contract
        when no name is given -- so every subclass doesn't reimplement the
        same `name or GENERIC_REASONING_BLOCK_V1` fallback."""
        return self._prompt_registry.get(name or GENERIC_REASONING_BLOCK_V1)

    def _resolve_llm_call_parameters(
        self, requested: LLMCallParameters, contract: PromptContract
    ) -> LLMCallParameters:
        """Explicit override wins; `temperature` falls back to the
        contract's own default when omitted (generalizing today's inlined
        `temperature = input.temperature if not None else
        contract.default_temperature`). `model`/`thinking_enabled`/
        `reasoning_effort` have no contract-level default yet -- `None`
        passes through to the adapter's own global-settings fallback
        (already wired in `ChatLLMAdapter`/`build_chat_llm`). A future
        per-role contract that wants its own default model can add that
        field to `PromptContract` when a concrete need for it exists.
        """
        return LLMCallParameters(
            model=requested.model,
            temperature=(
                requested.temperature if requested.temperature is not None else contract.default_temperature
            ),
            thinking_enabled=requested.thinking_enabled,
            reasoning_effort=requested.reasoning_effort,
            timeout=requested.timeout,
            max_retries=requested.max_retries,
        )

    def _salvage_prose_response(
        self,
        *,
        error: LLMAdapterError,
        raw_text: str,
        salvage_text_field: str | None,
        block_input: BaseReasoningBlockInput,
        phase: str,
    ) -> LlmCallResult | None:
        """Rebuild a result from a prose response the model refused to wrap in JSON.

        Opt-in (`salvage_text_field`), and only meaningful for a schema whose
        payload is a single free-text field: there, the prose IS the value, so
        discarding it loses a correct answer over its wrapper.

        Found live (2026-07-15): the composition model twice answered
        `"Here is a list of your completed courses... includes 17 courses..."`
        -- fully correct, drawn from real records -- as plain prose. Both
        attempts raised `json_parse_failed` (no `{` at all, so the
        control-character `strict=False` fix cannot help), the block failed, and
        the student received an EMPTY string. Structured output is off by
        default (`agent_reasoning_structured_output_enabled: bool = False`), so
        nothing forces JSON and a retry just re-rolls the same dice.

        Returns None -- letting the original error propagate -- for any
        non-parse failure (a transport error has no usable text), when the
        caller did not opt in, or when the text is blank. A blank salvage would
        manufacture an empty answer, which is worse than a clean failure.
        """
        if salvage_text_field is None or str(error) not in _PARSE_FAILURE_CODES:
            return None
        text = (raw_text or "").strip()
        if not text:
            return None
        logger.warning(
            "reasoning_block_salvaged_prose_response",
            extra={"block_id": block_input.block_id, "phase": phase, "field": salvage_text_field},
        )
        return LlmCallResult(parsed={salvage_text_field: text}, raw_text=raw_text, salvaged=True)

    async def _invoke_llm(
        self,
        *,
        system_prompt: str,
        user_prompt: str,
        params: LLMCallParameters,
        response_schema: dict[str, Any] | None,
        phase: str,
        block_input: BaseReasoningBlockInput,
        telemetry: RunTelemetry,
        salvage_text_field: str | None = None,
    ) -> LlmCallResult:
        """Wraps the actual adapter call with schema support and telemetry.

        A parse-failure code (the model DID respond, but with malformed/
        unparseable JSON) is retried once with a fresh call before giving up:
        `complete_json`'s own `max_retries` only covers transport errors, so a
        successful call that returned bad JSON was never retried -- live-eval
        runs showed that this transient flake at the composition/interpretation
        step was the dominant cause of a turn ending in neither an answer nor a
        clarification. A hard failure (no model, import error) is not retried;
        it cannot fix itself on a second call. On exhaustion the error still
        propagates to `run()`, which turns it into a `status="failed"` output.
        """
        raw_text_out: list[str] = []
        last_error: LLMAdapterError | None = None
        for attempt in range(_MAX_PARSE_FAILURE_RETRIES + 1):
            telemetry.call_count += 1
            raw_text_out.clear()
            try:
                parsed = await self._llm_adapter.complete_json(
                    system_prompt=system_prompt,
                    user_prompt=user_prompt,
                    temperature=params.temperature,
                    model=params.model,
                    thinking_enabled=params.thinking_enabled,
                    reasoning_effort=params.reasoning_effort,
                    response_schema=response_schema,
                    raw_model_text_out=raw_text_out,
                    timeout=params.timeout,
                    max_retries=params.max_retries,
                    streaming_queue=self._streaming_queue,
                )
            except LLMAdapterError as exc:
                last_error = exc
                will_retry = str(exc) in _PARSE_FAILURE_CODES and attempt < _MAX_PARSE_FAILURE_RETRIES
                logger.warning(
                    "reasoning_block_llm_call_failed",
                    extra={
                        "block_id": block_input.block_id,
                        "phase": phase,
                        "attempt": attempt,
                        "will_retry": will_retry,
                    },
                )
                if will_retry:
                    continue
                salvaged = self._salvage_prose_response(
                    error=exc,
                    raw_text=raw_text_out[0] if raw_text_out else "",
                    salvage_text_field=salvage_text_field,
                    block_input=block_input,
                    phase=phase,
                )
                if salvaged is not None:
                    return salvaged
                raise
            raw_text = raw_text_out[0] if raw_text_out else ""
            return LlmCallResult(parsed=parsed, raw_text=raw_text)
        assert last_error is not None  # loop always returns or raises before here
        raise last_error

    async def _invoke_llm_text(
        self,
        *,
        system_prompt: str,
        user_prompt: str,
        params: LLMCallParameters,
        phase: str,
        block_input: BaseReasoningBlockInput,
        telemetry: RunTelemetry,
    ) -> str:
        """Freeform-text sibling of `_invoke_llm`: calls `complete_text`
        instead of `complete_json`, so there is no schema and no JSON-parse
        gate -- this call cannot fail on formatting, only on the LLM call
        itself (unavailable client, provider error). For a shape's first
        stage that generates raw content, paired with a later `_invoke_llm`
        call that structures that content into a schema. Never raises for
        formatting reasons; still re-raises `LLMAdapterError` on a genuine
        call failure, exactly like `_invoke_llm`.
        """
        telemetry.call_count += 1
        try:
            return await self._llm_adapter.complete_text(
                system_prompt=system_prompt,
                user_prompt=user_prompt,
                temperature=params.temperature,
                model=params.model,
                thinking_enabled=params.thinking_enabled,
                reasoning_effort=params.reasoning_effort,
                timeout=params.timeout,
                max_retries=params.max_retries,
            )
        except LLMAdapterError:
            logger.warning(
                "reasoning_block_llm_call_failed",
                extra={"block_id": block_input.block_id, "phase": phase},
            )
            raise

    def _validate_schema(self, result: Any, schema: dict[str, Any]) -> SchemaValidationResult:
        return validate_against_schema(result, schema)

    def _normalize_result(
        self, raw: dict[str, Any] | None, *, output_schema: dict[str, Any] | None
    ) -> dict[str, Any] | None:
        return normalize_structured_result(raw, output_schema=output_schema)

    async def _repair_schema(
        self,
        *,
        initial_result: dict[str, Any] | None,
        initial_errors: list[str],
        output_schema: dict[str, Any],
        max_attempts: int,
        block_input: BaseReasoningBlockInput,
        telemetry: RunTelemetry,
    ) -> SchemaRepairOutcome:
        """Composed from `_invoke_llm` + `_normalize_result` +
        `_validate_schema` in its own bounded retry loop against the shared
        `SCHEMA_REPAIR_V1` contract -- not a monolithic fourth helper.

        If its own underlying LLM call fails, this degrades locally to
        "repair did not succeed" rather than propagating: a repair-attempt
        failure is a distinct, well-defined outcome from a hard `run()`
        -level failure, not something that should blow away the whole
        block.
        """
        contract = self._resolve_prompt_contract(SCHEMA_REPAIR_V1)
        current_result = initial_result
        errors = list(initial_errors)
        attempts_used = 0

        if max_attempts <= 0:
            return SchemaRepairOutcome(result=current_result, valid=False, errors=errors, attempts_used=0)

        for attempt in range(1, max_attempts + 1):
            attempts_used = attempt
            user_prompt = _build_repair_user_prompt(
                invalid_result=current_result,
                output_schema=output_schema,
                errors=errors,
            )
            # The repair pass's own contract (SCHEMA_REPAIR_V1) supplies its
            # own defaults, but the ORIGINAL caller's request-level
            # overrides (timeout, max_retries, thinking_enabled, ...) must
            # still apply here too -- a fresh, empty LLMCallParameters()
            # would silently drop them for every repair attempt, including
            # a caller-set timeout that's supposed to bound every one of
            # that caller's own calls, not just the first.
            params = self._resolve_llm_call_parameters(block_input.llm_call_parameters, contract)
            try:
                call_result = await self._invoke_llm(
                    system_prompt=contract.role_prompt,
                    user_prompt=user_prompt,
                    params=params,
                    response_schema=output_schema,
                    phase=f"schema_repair_attempt{attempt}",
                    block_input=block_input,
                    telemetry=telemetry,
                )
            except LLMAdapterError as exc:
                errors = [f"repair_call_failed: {exc}"]
                break

            current_result = self._normalize_result(call_result.parsed, output_schema=output_schema)
            validation = self._validate_schema(current_result, output_schema)
            errors = validation.errors
            if validation.valid:
                return SchemaRepairOutcome(
                    result=current_result, valid=True, errors=[], attempts_used=attempts_used
                )

        return SchemaRepairOutcome(result=current_result, valid=False, errors=errors, attempts_used=attempts_used)

    def _tool_argument_errors(self, requests: list[Any], tool_registry: Any) -> list[str]:
        """Validate each request's EFFECTIVE arguments against the specific
        tool's own `input_model` -- the check the generic round schema cannot
        do, since it types `arguments` as an opaque `{"type": "object"}`, so an
        empty `{}` (or arguments the model stashed under a non-canonical key)
        is round-schema-valid yet fails the tool the moment it runs.

        Uses `execute_tool_round`'s own key-recovery, so a request whose args
        merely sit under `params`/`tool_input`/... produces NO error here (it
        will be recovered deterministically at execution, for free). Only a
        genuinely missing/malformed argument set is reported -- with the tool's
        own pydantic error -- so the repair pass has a concrete target. Unknown
        tools are skipped (execute_tool_round records those `ok=False`)."""
        from app.agent_core.subagents.tool_round import _extract_tool_arguments

        errors: list[str] = []
        for request in requests:
            if not isinstance(request, dict):
                continue
            tool_name = request.get("tool_name")
            if not isinstance(tool_name, str):
                continue
            try:
                descriptor = tool_registry.get(tool_name)
            except Exception:  # noqa: BLE001 -- unknown tool: not our concern here
                continue
            try:
                descriptor.input_model(**_extract_tool_arguments(request))
            except Exception as exc:  # noqa: BLE001 -- pydantic ValidationError / TypeError
                errors.append(f"tool '{tool_name}' arguments invalid: {exc}")
        return errors

    async def _repair_tool_requests_if_needed(
        self,
        parsed: dict[str, Any],
        requests: list[Any],
        *,
        round_schema: dict[str, Any],
        block_input: BaseReasoningBlockInput,
        telemetry: RunTelemetry,
        tool_registry: Any = None,
    ) -> list[Any]:
        """Best-effort repair for a tool-round's `tool_requests` list.

        `_invoke_llm`'s `response_schema` only shapes the prompt -- it never
        validates or repairs the parsed result against it (that's what
        `_validate_schema`/`_repair_schema` are for, and every caller so far
        only runs those on a block's FINAL result, not on an intermediate
        `need_tools` round). A malformed tool request (wrong keys, e.g.
        `name`/`params` instead of `tool_name`/`arguments`) previously sailed
        straight through to `execute_tool_round`, which skips it gracefully
        -- but "gracefully skipped" means the whole round was wasted: no
        tool actually ran, so the step likely fails its success-check and
        bounces back to the Planner for a full re-plan, costing far more
        LLM calls than one bounded repair attempt here. Never worse than the
        old behavior: returns the original `requests` unchanged if nothing
        needed repair, or if the repair attempt itself didn't produce a
        valid result.

        When a `tool_registry` is supplied, each request's arguments are ALSO
        validated against the specific tool's own `input_model`
        (`_tool_argument_errors`) -- the round schema alone treats `arguments`
        as an opaque object, so an empty/mis-shaped argument set is
        round-valid yet fails at execution. Those errors, too, drive a bounded
        repair (with the tool's own message as the target). A repair is only
        adopted if it actually clears the argument errors, so it can never
        replace requests the deterministic key-recovery could still salvage.
        """
        # Deterministic pre-pass before spending any LLM repair call: the
        # single most common tool-request malformation (a live-eval tally put
        # it among the top schema-repair triggers) is a request that names a
        # tool but omits `arguments` entirely -- overwhelmingly for the
        # zero-argument tools (get_current_date, get_current_semester). An
        # empty arguments object is the correct, unambiguous fix, so backfill
        # it in code; only a genuinely ambiguous malformation should reach the
        # LLM repair below. Mutates the request dicts in place (they are the
        # same objects referenced by `parsed["tool_requests"]`, so the
        # re-validation below sees the fix).
        for request in requests:
            if isinstance(request, dict) and isinstance(request.get("tool_name"), str) and request.get("arguments") is None:
                request["arguments"] = {}

        normalized = self._normalize_result(parsed, output_schema=round_schema)
        validation = self._validate_schema(normalized, round_schema)
        arg_errors = self._tool_argument_errors(requests, tool_registry) if tool_registry is not None else []
        if validation.valid and not arg_errors:
            return requests

        repair_outcome = await self._repair_schema(
            initial_result=normalized,
            initial_errors=[*validation.errors, *arg_errors],
            output_schema=round_schema,
            max_attempts=1,
            block_input=block_input,
            telemetry=telemetry,
        )
        if repair_outcome.valid and repair_outcome.result is not None:
            repaired = repair_outcome.result.get("tool_requests") or requests
            # Adopt the repair only if it actually cleared the argument errors
            # (round-schema validity alone does not guarantee that); otherwise
            # keep the original, which execute_tool_round's key-recovery may
            # still salvage -- never regress.
            if tool_registry is None or not self._tool_argument_errors(repaired, tool_registry):
                return repaired
        return requests

    def _emit_debug_observer(
        self,
        *,
        phase: str,
        contract: PromptContract,
        system_prompt: str,
        user_prompt: str,
        raw_model_output: str,
        schema_valid: bool,
        status: str,
        warnings: list[str],
        parsed_json_preview: dict[str, Any] | None = None,
        repair_attempted: bool = False,
        repair_succeeded: bool = False,
        fallback_used: bool = False,
        duration_ms: float | None = None,
    ) -> None:
        """Emit one optional debug/eval-tracker event for a single actual
        LLM call. `phase` is an opaque label the calling subclass
        constructs itself (e.g. `"pass1_of_1"`, `"round3_tool_call"`) --
        unlike the old `ReasoningBlock`, there is no built-in notion of
        "pass" here. No-op unless a debug observer and case id are both
        configured. Drops the old, always-`ModuleNotFoundError` eval-tracker
        import entanglement -- that module doesn't exist in this service.
        """
        if self._debug_observer is None or not self._debug_case_id:
            return
        self._debug_observer.on_llm_call(
            case_id=self._debug_case_id,
            phase=phase,
            contract_name=contract.name,
            contract_version=contract.version,
            prompt_text=f"SYSTEM:\n{system_prompt}\n\nUSER:\n{user_prompt}",
            raw_model_output=raw_model_output,
            parsed_json_preview=parsed_json_preview,
            schema_valid=schema_valid,
            status=status,
            repair_attempted=repair_attempted,
            repair_succeeded=repair_succeeded,
            fallback_used=fallback_used,
            warnings=warnings[:20],
            duration_ms=duration_ms,
        )

    def _trace(
        self, block_input: BaseReasoningBlockInput, output: BaseReasoningBlockOutput, started_at: float
    ) -> None:
        """Structured, developer-facing trace for one completed `run()`
        call. Only ever references base-level `Output` fields -- never a
        shape-specific one (no `iterations_used`, no persona transcript,
        ...), since this is called generically from `run()` regardless of
        which concrete shape ran.

        The summary is folded directly into the log message (not left in
        `extra` alone) so it's visible under a plain `%(message)s`-style
        formatter -- see `reasoning/tracing.py::log_reasoning_trace` for the
        same fix applied to the other (newer) reasoning-block module; this
        one had the identical bare-message-only bug.
        """
        duration_ms = (time.monotonic() - started_at) * 1000.0
        logger.info(
            "reasoning_block_trace block_id=%s agent=%s status=%s schema_valid=%s "
            "confidence=%.2f llm_calls=%d duration_ms=%.0f",
            block_input.block_id,
            block_input.agent_name,
            output.status,
            output.schema_valid,
            output.confidence,
            output.total_llm_calls_used,
            duration_ms,
            extra={
                "reasoningBlockTrace": {
                    "block_id": block_input.block_id,
                    "agent_name": block_input.agent_name,
                    "objective": block_input.objective,
                    "status": output.status,
                    "schema_valid": output.schema_valid,
                    "confidence": output.confidence,
                    "warnings": output.warnings,
                    "total_llm_calls_used": output.total_llm_calls_used,
                    "duration_ms": duration_ms,
                }
            },
        )


__all__ = ["BaseReasoningBlock", "RunTelemetry", "LlmCallResult"]
