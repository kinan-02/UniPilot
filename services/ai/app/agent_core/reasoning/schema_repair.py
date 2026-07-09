"""Repair loop invoked when a reasoning pass's `result` fails schema validation."""

from __future__ import annotations

import json
import logging
from typing import Any

from app.agent_core.reasoning.llm_adapter import LLMAdapter, LLMAdapterError
from app.agent_core.reasoning.prompt_registry import PromptContract
from app.agent_core.reasoning.result_normalizer import normalize_structured_result
from app.agent_core.reasoning.schema_validator import validate_against_schema
from app.agent_core.reasoning.schemas import SchemaRepairOutcome

logger = logging.getLogger(__name__)


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


def _unwrap_repair_candidate(candidate: dict[str, Any]) -> dict[str, Any]:
    nested = candidate.get("result")
    if isinstance(nested, dict) and not any(key in candidate for key in ("plan_id", "primary_intent", "user_goal")):
        return nested
    return candidate


async def run_schema_repair_loop(
    *,
    llm_adapter: LLMAdapter,
    contract: PromptContract,
    initial_result: dict[str, Any] | None,
    output_schema: dict[str, Any],
    initial_errors: list[str],
    max_attempts: int,
    temperature: float | None = None,
) -> SchemaRepairOutcome:
    """Repeatedly ask the repair prompt to fix `initial_result` until valid or exhausted."""
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
        try:
            candidate = await llm_adapter.complete_json(
                system_prompt=contract.role_prompt,
                user_prompt=user_prompt,
                temperature=temperature if temperature is not None else contract.default_temperature,
                response_schema=output_schema,
            )
        except LLMAdapterError as exc:
            logger.warning("reasoning_schema_repair_llm_failed", extra={"attempt": attempt})
            errors = [f"repair_call_failed: {exc}"]
            break

        current_result = normalize_structured_result(
            _unwrap_repair_candidate(candidate),
            output_schema=output_schema,
        )
        validation = validate_against_schema(current_result, output_schema)
        errors = validation.errors
        if validation.valid:
            return SchemaRepairOutcome(
                result=current_result,
                valid=True,
                errors=[],
                attempts_used=attempts_used,
            )

    return SchemaRepairOutcome(
        result=current_result,
        valid=False,
        errors=errors,
        attempts_used=attempts_used,
    )
