"""Compact ReasoningBlock call summaries for full LLM shadow replay (Phase 26)."""

from __future__ import annotations

from typing import Any, Literal

from pydantic import BaseModel, Field

from app.agent.reasoning.schemas import ReasoningBlockInput, ReasoningBlockOutput

_FORBIDDEN_SUMMARY_KEYS = frozenset(
    {
        "prompt",
        "system_prompt",
        "developer_prompt",
        "raw_response",
        "raw_output",
        "chain_of_thought",
        "hidden_reasoning",
        "task_context",
        "raw_context",
        "candidate_answer_text",
    }
)


class ReasoningContractCallSummary(BaseModel):
    contract_name: str
    status: Literal["completed", "failed", "fallback"]
    reasoning_status: str | None = None
    schema_valid: bool = False
    latency_ms: int | None = None
    input_tokens: int | None = None
    output_tokens: int | None = None
    estimated_cost_usd: float | None = None
    validation_retry_count: int = 0
    output_schema_name: str | None = None
    validation_notes: list[str] = Field(default_factory=list)
    warnings: list[str] = Field(default_factory=list)


_MAX_NOTE_CHARS = 200
_MAX_NOTES = 8
_MAX_WARNINGS = 8


def _sanitize_note_text(value: str) -> str:
    text = " ".join(str(value).split())
    if len(text) > _MAX_NOTE_CHARS:
        return text[:_MAX_NOTE_CHARS] + "…"
    return text


def sanitize_trace_string_list(values: list[str] | None, *, limit: int = _MAX_NOTES) -> list[str]:
    """Compact, safe note/warning strings for reports — no prompts or raw model text."""
    cleaned: list[str] = []
    for item in values or []:
        if not isinstance(item, str):
            continue
        lowered = item.lower()
        if any(forbidden in lowered for forbidden in ("prompt", "raw_response", "chain_of_thought", "task_context")):
            continue
        note = _sanitize_note_text(item)
        if note and note not in cleaned:
            cleaned.append(note)
        if len(cleaned) >= limit:
            break
    return cleaned


def compact_reasoning_call_summary(item: ReasoningContractCallSummary) -> dict[str, Any]:
    return {
        "contractName": item.contract_name,
        "status": item.status,
        "reasoningStatus": item.reasoning_status,
        "schemaValid": item.schema_valid,
        "latencyMs": item.latency_ms,
        "inputTokens": item.input_tokens,
        "outputTokens": item.output_tokens,
        "estimatedCostUsd": item.estimated_cost_usd,
        "validationRetryCount": item.validation_retry_count,
        "outputSchemaName": item.output_schema_name,
        "validationNotes": item.validation_notes,
        "warnings": item.warnings,
    }


class TracedReasoningBlockRunner:
    """Wrap a ReasoningBlock runner and record compact call summaries only."""

    def __init__(self, inner: Any) -> None:
        self._inner = inner
        self.summaries: list[ReasoningContractCallSummary] = []

    async def _record(self, input: ReasoningBlockInput, output: ReasoningBlockOutput, *, latency_ms: int) -> ReasoningBlockOutput:
        contract = input.prompt_contract_name or input.output_schema_name or "unknown"
        status: Literal["completed", "failed", "fallback"]
        if output.status == "completed" and output.schema_valid:
            status = "completed"
        elif output.status == "failed":
            status = "failed"
        else:
            status = "fallback"

        usage = getattr(output, "usage", None)
        input_tokens = None
        output_tokens = None
        estimated_cost = None
        if isinstance(usage, dict):
            input_tokens = usage.get("input_tokens") or usage.get("prompt_tokens")
            output_tokens = usage.get("output_tokens") or usage.get("completion_tokens")
            estimated_cost = usage.get("estimated_cost_usd")

        self.summaries.append(
            ReasoningContractCallSummary(
                contract_name=contract,
                status=status,
                reasoning_status=output.status,
                schema_valid=bool(output.schema_valid),
                latency_ms=latency_ms,
                input_tokens=int(input_tokens) if isinstance(input_tokens, int) else None,
                output_tokens=int(output_tokens) if isinstance(output_tokens, int) else None,
                estimated_cost_usd=float(estimated_cost) if isinstance(estimated_cost, (int, float)) else None,
                validation_retry_count=int(getattr(output, "repair_attempts_used", 0) or 0),
                output_schema_name=input.output_schema_name,
                validation_notes=sanitize_trace_string_list(list(output.validation_notes or [])),
                warnings=sanitize_trace_string_list(list(output.warnings or []), limit=_MAX_WARNINGS),
            )
        )
        return output

    async def run(self, input: ReasoningBlockInput) -> ReasoningBlockOutput:
        import time

        started = time.perf_counter()
        output = await self._inner.run(input)
        latency_ms = int((time.perf_counter() - started) * 1000)
        return await self._record(input, output, latency_ms=latency_ms)

    async def run_via_original(
        self,
        instance: Any,
        input: ReasoningBlockInput,
        original_run: Any,
    ) -> ReasoningBlockOutput:
        """Invoke the unpatched ReasoningBlock.run for real-LLM lab tracing."""
        import time

        started = time.perf_counter()
        output = await original_run(instance, input)
        latency_ms = int((time.perf_counter() - started) * 1000)
        return await self._record(input, output, latency_ms=latency_ms)


def summarize_contract_calls(summaries: list[ReasoningContractCallSummary]) -> dict[str, Any]:
    counts: dict[str, int] = {}
    schema_failures: dict[str, int] = {}
    total_latency = 0
    latency_count = 0
    total_cost = 0.0
    cost_count = 0
    for item in summaries:
        counts[item.contract_name] = counts.get(item.contract_name, 0) + 1
        if item.status != "completed":
            schema_failures[item.contract_name] = schema_failures.get(item.contract_name, 0) + 1
        if item.latency_ms is not None:
            total_latency += item.latency_ms
            latency_count += 1
        if item.estimated_cost_usd is not None:
            total_cost += item.estimated_cost_usd
            cost_count += 1

    compact_summaries = [compact_reasoning_call_summary(item) for item in summaries]
    for entry in compact_summaries:
        for key in list(entry):
            if key in _FORBIDDEN_SUMMARY_KEYS:
                entry.pop(key, None)

    return {
        "totalReasoningCalls": len(summaries),
        "contractCallCounts": counts,
        "schemaValidationFailures": schema_failures,
        "averageLatencyMs": round(total_latency / latency_count, 2) if latency_count else None,
        "totalEstimatedCostUsd": round(total_cost, 6) if cost_count else None,
        "calls": compact_summaries[:50],
    }


def assert_summaries_sanitized(payload: dict[str, Any]) -> None:
    serialized = str(payload).lower()
    for forbidden in _FORBIDDEN_SUMMARY_KEYS:
        if forbidden in serialized and forbidden not in {"task_context"}:
            # task_context key name may appear in docs; reject values with large blobs separately
            if forbidden in {"prompt", "raw_response", "chain_of_thought", "candidate_answer_text"}:
                if forbidden.replace("_", "") in serialized.replace("_", ""):
                    raise ValueError(f"forbidden_summary_content:{forbidden}")
