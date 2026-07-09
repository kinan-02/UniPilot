"""Shared reasoning runtime (Phase 1 foundation).

`ReasoningBlock` is the single place future LLM-powered agent components will
call into instead of issuing one-shot LLM calls directly. It runs a small
number of structured reasoning passes, validates the final result against a
task-specific JSON schema, repairs the structure when needed, and always
returns a fully typed `ReasoningBlockOutput` — never raw model text and never
chain-of-thought.

This module does not change any existing production call path in Phase 1.
"""

from __future__ import annotations

import json
import logging
import time
from typing import Any

from app.agent_core.reasoning.llm_adapter import ChatLLMAdapter, LLMAdapter, LLMAdapterError
from app.agent_core.reasoning.prompt_registry import (
    GENERIC_REASONING_BLOCK_V1,
    SCHEMA_REPAIR_V1,
    PromptContract,
    PromptRegistry,
    build_default_prompt_registry,
)
from app.agent_core.reasoning.result_normalizer import normalize_structured_result
from app.agent_core.reasoning.schema_repair import run_schema_repair_loop
from app.agent_core.reasoning.schema_validator import validate_against_schema
from app.agent_core.reasoning.schemas import (
    ReasoningBlockInput,
    ReasoningBlockOutput,
    ReasoningPassPayload,
    ReasoningRiskLevel,
    ReasoningStatus,
    ReasoningTrace,
)
from app.agent_core.reasoning.tracing import log_reasoning_trace
from app.agent_core.reasoning.debug_observer import ReasoningBlockDebugObserver, current_eval_debug_context
from app.config import Settings, get_settings

logger = logging.getLogger(__name__)

_RISK_ITERATION_DEFAULTS: dict[ReasoningRiskLevel, int] = {
    "low": 2,
    "medium": 3,
    "high": 3,
}


def _resolve_min_iterations(input: ReasoningBlockInput, contract: PromptContract) -> int:
    min_iterations = (
        input.min_reasoning_iterations
        if input.min_reasoning_iterations is not None
        else contract.default_min_iterations
    )
    return max(1, min_iterations)


def _resolve_iteration_count(input: ReasoningBlockInput, contract: PromptContract) -> int:
    """Pick how many reasoning passes to run for this task.

    Risk level sets the default (low=2, medium/high=3); explicit
    `min_reasoning_iterations` / `max_reasoning_iterations` on the input
    clamp or override that default. This is the *target* pass count for
    contracts/inputs that don't opt into adaptive early exit — with it
    enabled, `run()` may still stop earlier once `_resolve_min_iterations`
    passes have run and a pass is confidently complete.
    """
    base = _RISK_ITERATION_DEFAULTS.get(input.risk_level, contract.default_max_iterations)
    min_iterations = _resolve_min_iterations(input, contract)
    max_iterations = (
        input.max_reasoning_iterations
        if input.max_reasoning_iterations is not None
        else contract.default_max_iterations
    )
    max_iterations = max(min_iterations, max_iterations)
    return min(max(base, min_iterations), max_iterations)


def _eligible_for_adaptive_early_exit(
    payload: ReasoningPassPayload,
    *,
    pass_index: int,
    min_iterations: int,
    confidence_threshold: float,
) -> bool:
    """Whether an intermediate `"ok"` pass is confident/complete enough to
    finalize now instead of continuing to the next scheduled pass.

    Callers must already have gated this on the adaptive-iterations setting
    being enabled and `pass_index < total_passes` — this function only checks
    the pass's own content, not any feature flag.
    """
    if pass_index < min_iterations:
        return False
    if payload.result is None:
        return False
    if payload.confidence is None or payload.confidence < confidence_threshold:
        return False
    if payload.missing_context or payload.validation_notes:
        return False
    return True


def _pass_label(pass_index: int, total_passes: int) -> str:
    if pass_index == total_passes:
        return "final"
    if pass_index == 1:
        return "understand"
    return "draft"


def _build_system_prompt(
    contract: PromptContract, input: ReasoningBlockInput, *, pass_label: str | None = None
) -> str:
    lines = [contract.role_prompt, "", f"AGENT: {input.agent_name}"]
    if contract.instructions:
        lines.append("")
        lines.append("INSTRUCTIONS:")
        lines.extend(f"- {item}" for item in contract.instructions)
    pass_instructions = (contract.pass_role_instructions or {}).get(pass_label or "")
    if pass_instructions:
        lines.append("")
        lines.append(f"THIS PASS ({(pass_label or '').upper()}):")
        lines.extend(f"- {item}" for item in pass_instructions)
    if contract.safety_rules:
        lines.append("")
        lines.append("SAFETY RULES:")
        lines.extend(f"- {item}" for item in contract.safety_rules)
    return "\n".join(lines).strip()


def _filtered_task_context(
    task_context: dict[str, Any], allowed_context_fields: list[str] | None
) -> dict[str, Any]:
    """Trim `task_context` to a contract's declared allowlist, when it has one.

    Keeps context minimal/task-specific per the shared reasoning contract; a
    contract with `allowed_context_fields=None` places no restriction.
    """
    if allowed_context_fields is None:
        return task_context
    allowed = set(allowed_context_fields)
    return {key: value for key, value in task_context.items() if key in allowed}


def _build_user_prompt(
    input: ReasoningBlockInput,
    contract: PromptContract,
    *,
    pass_label: str,
    pass_index: int,
    total_passes: int,
    previous_passes: list[dict[str, Any]],
    allow_early_finalize: bool = False,
) -> str:
    if allow_early_finalize:
        result_instruction = (
            "Populate ONLY when status is 'ok' and you are confident the task is fully "
            "complete — this may happen before the final scheduled pass. Must match "
            "output_schema exactly and set confidence accordingly. Otherwise null."
        )
    else:
        result_instruction = (
            "Populate ONLY on the final pass, and ONLY when status is 'ok'. "
            "Must match output_schema exactly. Otherwise null."
        )
    payload = {
        "objective": input.objective,
        "pass": {"label": pass_label, "index": pass_index, "of": total_passes},
        "task_context": _filtered_task_context(input.task_context, contract.allowed_context_fields),
        "available_tools": [tool.model_dump() for tool in input.available_tools],
        "constraints": input.constraints,
        "success_criteria": input.success_criteria,
        "output_schema_name": input.output_schema_name,
        "output_schema": input.output_schema,
        "previous_passes": previous_passes,
        "response_shape": {
            "status": "ok | needs_tool | needs_more_context",
            "summary": "short human-readable summary of this pass' conclusion (no private reasoning)",
            "key_factors": ["..."],
            "missing_context": ["..."],
            "validation_notes": ["..."],
            "warnings": ["..."],
            "tool_requests": [{"tool_name": "...", "purpose": "...", "arguments": {}}],
            "confidence": 0.0,
            "result": result_instruction,
        },
    }
    return json.dumps(payload, ensure_ascii=False, indent=2)


def _unwrap_repair_candidate(candidate: dict[str, Any]) -> dict[str, Any]:
    nested = candidate.get("result")
    if isinstance(nested, dict) and not any(key in candidate for key in ("plan_id", "primary_intent", "user_goal")):
        return nested
    return candidate


def _extract_pass_payload(raw: dict[str, Any]) -> ReasoningPassPayload:
    """Defensively coerce a raw LLM JSON dict into a `ReasoningPassPayload`.

    LLM output is untrusted; this never raises on malformed shapes.
    """
    status_raw = str(raw.get("status") or "ok").strip().lower()
    status = status_raw if status_raw in {"ok", "needs_tool", "needs_more_context"} else "ok"

    tool_requests = []
    for item in raw.get("tool_requests") or []:
        if not isinstance(item, dict):
            continue
        tool_name = str(item.get("tool_name") or item.get("name") or "").strip()
        if not tool_name:
            continue
        arguments = item.get("arguments")
        tool_requests.append(
            {
                "tool_name": tool_name,
                "purpose": str(item.get("purpose") or ""),
                "arguments": arguments if isinstance(arguments, dict) else {},
            }
        )

    confidence_raw = raw.get("confidence")
    try:
        confidence = float(confidence_raw) if confidence_raw is not None else None
    except (TypeError, ValueError):
        confidence = None

    result = raw.get("result")
    result = result if isinstance(result, dict) else None

    def _str_list(key: str) -> list[str]:
        values = raw.get(key) or []
        if not isinstance(values, list):
            return []
        return [str(v) for v in values if str(v).strip()]

    return ReasoningPassPayload(
        status=status,  # type: ignore[arg-type]
        summary=str(raw.get("summary") or ""),
        key_factors=_str_list("key_factors"),
        missing_context=_str_list("missing_context"),
        validation_notes=_str_list("validation_notes"),
        warnings=_str_list("warnings"),
        tool_requests=tool_requests,  # type: ignore[arg-type]
        confidence=confidence,
        result=result,
    )


def _fallback_output(*, iterations_used: int, reason: str) -> ReasoningBlockOutput:
    return ReasoningBlockOutput(
        status="failed",
        result=None,
        tool_requests=[],
        decision_summary="Reasoning could not be completed because the LLM was unavailable or failed.",
        key_factors=[],
        missing_context=[],
        validation_notes=[],
        warnings=[f"llm_adapter_error: {reason}"],
        confidence=0.0,
        schema_valid=False,
        iterations_used=iterations_used,
        repair_attempts_used=0,
    )


def _early_exit_output(
    payload: ReasoningPassPayload, *, status: ReasoningStatus, iterations_used: int
) -> ReasoningBlockOutput:
    return ReasoningBlockOutput(
        status=status,
        result=None,
        tool_requests=payload.tool_requests,
        decision_summary=payload.summary or f"Reasoning stopped early: {status}.",
        key_factors=payload.key_factors,
        missing_context=payload.missing_context,
        validation_notes=payload.validation_notes,
        warnings=payload.warnings,
        confidence=payload.confidence if payload.confidence is not None else 0.0,
        schema_valid=False,
        iterations_used=iterations_used,
        repair_attempts_used=0,
    )


def _candidate_output(payload: ReasoningPassPayload, *, iterations_used: int) -> ReasoningBlockOutput:
    return ReasoningBlockOutput(
        status="completed",
        result=payload.result,
        tool_requests=payload.tool_requests,
        decision_summary=payload.summary or "Reasoning completed.",
        key_factors=payload.key_factors,
        missing_context=payload.missing_context,
        validation_notes=payload.validation_notes,
        warnings=payload.warnings,
        confidence=payload.confidence if payload.confidence is not None else 0.5,
        schema_valid=False,
        iterations_used=iterations_used,
        repair_attempts_used=0,
    )


class ReasoningBlock:
    """Shared runtime for structured, multi-pass LLM reasoning.

    Future agent components should call `ReasoningBlock.run` instead of
    issuing direct one-shot LLM calls. This class owns: prompt assembly from
    the `PromptRegistry`, the multi-pass reasoning loop, schema validation,
    the schema repair loop, and safe fallback behavior when the LLM is
    unavailable.
    """

    def __init__(
        self,
        llm_adapter: LLMAdapter | None = None,
        prompt_registry: PromptRegistry | None = None,
        *,
        settings: Settings | None = None,
        debug_observer: ReasoningBlockDebugObserver | None = None,
        debug_case_id: str | None = None,
        debug_phase: str | None = None,
    ) -> None:
        self._llm_adapter: LLMAdapter = llm_adapter or ChatLLMAdapter(settings=settings)
        self._settings = settings or get_settings()
        self._prompt_registry = prompt_registry or build_default_prompt_registry()
        self._debug_observer = debug_observer
        self._debug_case_id = debug_case_id
        self._debug_phase = debug_phase

    def _emit_debug_observer(
        self,
        *,
        contract: PromptContract,
        input: ReasoningBlockInput,
        system_prompt: str,
        user_prompt: str,
        raw_model_output: str,
        output: ReasoningBlockOutput,
        started_at: float | None = None,
        pass_label: str | None = None,
        pass_index: int | None = None,
    ) -> None:
        """Emit one debug/tracker event for a single actual LLM call.

        Called once per `complete_json` invocation in `run()` — not just on
        the terminal pass — so `EvalLlmCallTracker.call_count` reflects real
        LLM round-trips for multi-pass reasoning. `pass_label`/`pass_index`
        are folded into `phase` (rather than added as new kwargs) so the
        `ReasoningBlockDebugObserver` protocol and its two implementers don't
        need to change shape.
        """
        ctx = current_eval_debug_context()
        observer = self._debug_observer
        case_id = self._debug_case_id or ""
        phase = self._debug_phase or input.agent_name
        if ctx is not None:
            observer = observer or ctx[0]
            case_id = case_id or ctx[1]
            phase = phase or ctx[2]
        if observer is None or not case_id:
            return

        # Deferred: this eval-harness tracker doesn't exist in services/ai
        # (it's `services/agent`-specific eval tooling, out of this port's
        # scope) -- only imported if a debug_observer/eval context is
        # actually configured, which the skeleton never does today.
        try:
            from app.agent.evaluation.eval_llm_tracker import current_eval_llm_tracker
        except ModuleNotFoundError:
            current_eval_llm_tracker = None  # type: ignore[assignment]
        if pass_label is not None and pass_index is not None:
            phase = f"{phase}:pass{pass_index}_{pass_label}"
        preview = output.result if isinstance(output.result, dict) else None
        duration_ms = (time.monotonic() - started_at) * 1000.0 if started_at is not None else None
        payload = {
            "case_id": case_id,
            "phase": phase,
            "contract_name": contract.name,
            "contract_version": contract.version,
            "prompt_text": f"SYSTEM:\n{system_prompt}\n\nUSER:\n{user_prompt}",
            "raw_model_output": raw_model_output,
            "parsed_json_preview": preview,
            "schema_valid": bool(output.schema_valid),
            "status": output.status,
            "repair_attempted": bool(output.repair_attempts_used),
            "repair_succeeded": bool(output.schema_valid and output.repair_attempts_used),
            "fallback_used": any("fallback_used" in warning for warning in output.warnings),
            "warnings": list(output.warnings)[:20],
            "duration_ms": duration_ms,
        }
        observer.on_llm_call(**payload)
        tracker = current_eval_llm_tracker() if current_eval_llm_tracker is not None else None
        if tracker is not None and tracker is not observer:
            tracker.on_llm_call(**payload)

    async def run(self, input: ReasoningBlockInput) -> ReasoningBlockOutput:
        """Run the reasoning loop for one task and return a typed output.

        Never raises for LLM unavailability/failure or invalid model output —
        those become a `status="failed"` `ReasoningBlockOutput` instead.
        """
        started_at = time.monotonic()
        contract = self._prompt_registry.get(input.prompt_contract_name or GENERIC_REASONING_BLOCK_V1)
        total_passes = _resolve_iteration_count(input, contract)
        min_iterations = _resolve_min_iterations(input, contract)
        temperature = input.temperature if input.temperature is not None else contract.default_temperature
        adaptive_early_exit_enabled = self._settings.is_agent_reasoning_adaptive_iterations_enabled()
        adaptive_confidence_threshold = self._settings.resolved_agent_reasoning_adaptive_confidence_threshold()

        previous_passes: list[dict[str, Any]] = []
        output: ReasoningBlockOutput

        for pass_index in range(1, total_passes + 1):
            pass_label = _pass_label(pass_index, total_passes)
            # Built per-pass (not hoisted before the loop) so a contract can
            # opt into `pass_role_instructions`; for every contract that
            # leaves it unset this produces the exact same string every pass.
            system_prompt = _build_system_prompt(contract, input, pass_label=pass_label)
            user_prompt = _build_user_prompt(
                input,
                contract,
                pass_label=pass_label,
                pass_index=pass_index,
                total_passes=total_passes,
                previous_passes=previous_passes,
                allow_early_finalize=adaptive_early_exit_enabled,
            )
            try:
                raw_text_holder: list[str] = []
                raw = await self._llm_adapter.complete_json(
                    system_prompt=system_prompt,
                    user_prompt=user_prompt,
                    temperature=temperature,
                    response_schema=(
                        input.output_schema
                        if pass_index == total_passes or adaptive_early_exit_enabled
                        else None
                    ),
                    raw_model_text_out=raw_text_holder,
                )
            except LLMAdapterError as exc:
                reason = str(exc)
                output = _fallback_output(iterations_used=pass_index - 1, reason=reason)
                if "fallback_used" not in output.warnings:
                    output = output.model_copy(update={"warnings": [*output.warnings, "fallback_used"]})
                self._trace(input, output, started_at)
                self._emit_debug_observer(
                    contract=contract,
                    input=input,
                    system_prompt=system_prompt,
                    user_prompt=user_prompt,
                    raw_model_output=raw_text_holder[0] if raw_text_holder else "",
                    output=output,
                    started_at=started_at,
                    pass_label=pass_label,
                    pass_index=pass_index,
                )
                return output

            payload = _extract_pass_payload(raw)

            if payload.status in ("needs_tool", "needs_more_context"):
                output = _early_exit_output(payload, status=payload.status, iterations_used=pass_index)
                self._trace(input, output, started_at)
                self._emit_debug_observer(
                    contract=contract,
                    input=input,
                    system_prompt=system_prompt,
                    user_prompt=user_prompt,
                    raw_model_output=raw_text_holder[0] if raw_text_holder else "",
                    output=output,
                    started_at=started_at,
                    pass_label=pass_label,
                    pass_index=pass_index,
                )
                return output

            early_exit_now = adaptive_early_exit_enabled and _eligible_for_adaptive_early_exit(
                payload,
                pass_index=pass_index,
                min_iterations=min_iterations,
                confidence_threshold=adaptive_confidence_threshold,
            )

            if pass_index < total_passes and not early_exit_now:
                # This pass made a real LLM call too — emit its own debug/tracker
                # event now rather than silently folding it into the next pass's
                # accounting (previously only the terminal pass ever emitted).
                self._emit_debug_observer(
                    contract=contract,
                    input=input,
                    system_prompt=system_prompt,
                    user_prompt=user_prompt,
                    raw_model_output=raw_text_holder[0] if raw_text_holder else "",
                    output=_candidate_output(payload, iterations_used=pass_index),
                    started_at=started_at,
                    pass_label=pass_label,
                    pass_index=pass_index,
                )
                previous_passes.append(
                    {
                        "label": pass_label,
                        "summary": payload.summary,
                        "key_factors": payload.key_factors,
                        "missing_context": payload.missing_context,
                    }
                )
                continue

            # Either the true final pass, or (when adaptive early exit is
            # enabled) an earlier pass that was already confident/complete —
            # both go through the same schema-validation/repair path.
            output = await self._finalize(input, payload, iterations_used=pass_index)
            if early_exit_now and pass_index < total_passes:
                output = output.model_copy(
                    update={"warnings": [*output.warnings, "adaptive_early_exit"]}
                )
            self._trace(input, output, started_at)
            self._emit_debug_observer(
                contract=contract,
                input=input,
                system_prompt=system_prompt,
                user_prompt=user_prompt,
                raw_model_output=raw_text_holder[0] if raw_text_holder else "",
                output=output,
                started_at=started_at,
                pass_label=pass_label,
                pass_index=pass_index,
            )
            return output

        # Defensive: total_passes is always >= 1, so the loop above always returns.
        output = _fallback_output(iterations_used=0, reason="no_passes_executed")
        self._trace(input, output, started_at)
        return output

    async def _finalize(
        self, input: ReasoningBlockInput, payload: ReasoningPassPayload, *, iterations_used: int
    ) -> ReasoningBlockOutput:
        candidate = _candidate_output(payload, iterations_used=iterations_used)
        normalized_result = normalize_structured_result(
            candidate.result,
            output_schema=input.output_schema,
        )
        candidate = candidate.model_copy(update={"result": normalized_result})
        validation = validate_against_schema(normalized_result, input.output_schema)
        if validation.valid:
            return candidate.model_copy(update={"schema_valid": True})

        repair_contract = self._prompt_registry.get(SCHEMA_REPAIR_V1)
        repair_outcome = await run_schema_repair_loop(
            llm_adapter=self._llm_adapter,
            contract=repair_contract,
            initial_result=normalized_result,
            output_schema=input.output_schema,
            initial_errors=validation.errors,
            max_attempts=input.max_schema_repair_attempts,
        )
        if repair_outcome.valid:
            return candidate.model_copy(
                update={
                    "result": repair_outcome.result,
                    "schema_valid": True,
                    "repair_attempts_used": repair_outcome.attempts_used,
                    "warnings": [
                        *candidate.warnings,
                        "repair_attempted",
                        "repair_succeeded",
                    ],
                }
            )

        return candidate.model_copy(
            update={
                "status": "failed",
                "schema_valid": False,
                "repair_attempts_used": repair_outcome.attempts_used,
                "warnings": [
                    *candidate.warnings,
                    "repair_attempted",
                    "schema_validation_failed",
                    "status_not_completed",
                    *repair_outcome.errors[:5],
                ],
            }
        )

    def _trace(self, input: ReasoningBlockInput, output: ReasoningBlockOutput, started_at: float) -> None:
        duration_ms = (time.monotonic() - started_at) * 1000
        trace = ReasoningTrace(
            block_id=input.block_id,
            agent_name=input.agent_name,
            objective=input.objective,
            iterations_used=output.iterations_used,
            repair_attempts_used=output.repair_attempts_used,
            status=output.status,
            schema_valid=output.schema_valid,
            decision_summary=output.decision_summary,
            warnings=output.warnings,
            duration_ms=duration_ms,
        )
        log_reasoning_trace(trace)
