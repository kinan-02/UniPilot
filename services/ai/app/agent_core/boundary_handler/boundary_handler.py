"""Boundary Handler layer (docs/agent/AGENT_VISION.md): receives out-of-scope 
or impossible administrative requests from the Request Understanding layer and
composes a polite, helpful, and appropriately formatted decline message.

Its own concrete `BaseReasoningBlock` shape: single-shot, zero tools.
"""

from __future__ import annotations

import json
import logging
from typing import Any

from app.agent_core.reasoning.llm_adapter import LLMAdapter
from app.agent_core.reasoning.prompt_registry import PromptContract, PromptRegistry, build_default_prompt_registry
from app.agent_core.reasoning_blocks.base import BaseReasoningBlock, RunTelemetry
from app.agent_core.reasoning_blocks.schemas import BaseReasoningBlockInput, BaseReasoningBlockOutput, LLMCallParameters

logger = logging.getLogger(__name__)

BOUNDARY_HANDLER_V1 = "boundary_handler_v1"
BOUNDARY_HANDLER_OUTPUT_SCHEMA_NAME = "boundary_handler_output_v1"

BOUNDARY_HANDLER_OUTPUT_SCHEMA: dict[str, Any] = {
    "type": "object",
    "properties": {
        "answer_text": {"type": "string"},
        "confidence": {"type": "number", "minimum": 0.0, "maximum": 1.0},
    },
    "required": ["answer_text", "confidence"],
    "additionalProperties": False,
}

_MAX_SCHEMA_REPAIR_ATTEMPTS = 2
_TIMEOUT_SECONDS = 30.0

class BoundaryHandlerInput(BaseReasoningBlockInput):
    original_user_message: str
    decline_reason: str


class BoundaryHandlerOutput(BaseReasoningBlockOutput):
    answer_text: str


def _boundary_handler_contract() -> PromptContract:
    return PromptContract(
        name=BOUNDARY_HANDLER_V1,
        version="1.0.0",
        role_prompt=(
            "You are the empathetic Boundary Handler for the UniPilot Agent, a Technion "
            "academic advising assistant. A user has made a request that our triage layer "
            "determined is either entirely out of scope (e.g., non-academic) or impossible "
            "because it requires administrative capabilities we do not possess (e.g., granting "
            "waivers or registering for courses). Your job is to compose a helpful, polite, "
            "and beautifully formatted response to the user."
        ),
        instructions=[
            "Read the original_user_message and the internal decline_reason.",
            "Write a polite, professional, and empathetic response explaining why the agent cannot fulfill the request.",
            "If the request is for administrative action (like granting a waiver), kindly explain that you are an AI advisor and lack the authority or system access to change official records.",
            "If the request is entirely non-academic (e.g., financial aid, housing), explain that you only handle academic advising.",
            "Use Markdown formatting if appropriate, but keep the message concise and direct.",
            "Never fabricate a solution or hallucinate capabilities.",
            "Do NOT mention internal terms like 'decline_reason', 'Request Understanding layer', or 'in_scope'."
        ],
        allowed_context_fields=None,
        output_schema_name=BOUNDARY_HANDLER_OUTPUT_SCHEMA_NAME,
        default_risk_level="low",
        default_min_iterations=1,
        default_max_iterations=1,
        default_temperature=0.3,
        safety_rules=[
            "Do not expose chain-of-thought, hidden reasoning, or private notes.",
            "Do not give false hope or pretend you can forward the request to a human.",
        ],
    )


def build_boundary_handler_prompt_registry() -> PromptRegistry:
    registry = build_default_prompt_registry()
    registry.register(_boundary_handler_contract())
    return registry


def _build_system_prompt(contract: PromptContract) -> str:
    lines = [contract.role_prompt]
    if contract.instructions:
        lines.append("")
        lines.append("INSTRUCTIONS:")
        lines.extend(f"- {item}" for item in contract.instructions)
    if contract.safety_rules:
        lines.append("")
        lines.append("SAFETY RULES:")
        lines.extend(f"- {item}" for item in contract.safety_rules)
    return "\n".join(lines).strip()


def _build_user_prompt(block_input: BoundaryHandlerInput) -> str:
    payload = {
        "original_user_message": block_input.original_user_message,
        "decline_reason": block_input.decline_reason,
    }
    return json.dumps(payload, ensure_ascii=False, indent=2)


class BoundaryHandlingReasoningBlock(BaseReasoningBlock):
    def __init__(self, *, llm_adapter: LLMAdapter, prompt_registry: PromptRegistry | None = None, **kwargs: Any) -> None:
        super().__init__(
            llm_adapter=llm_adapter,
            prompt_registry=prompt_registry or build_boundary_handler_prompt_registry(),
            **kwargs,
        )

    async def _run_internal(
        self, block_input: BoundaryHandlerInput, telemetry: RunTelemetry
    ) -> BoundaryHandlerOutput:
        contract = self._resolve_prompt_contract(block_input.prompt_contract_name or BOUNDARY_HANDLER_V1)
        params = self._resolve_llm_call_parameters(block_input.llm_call_parameters, contract)
        user_prompt = _build_user_prompt(block_input)

        call_result = await self._invoke_llm(
            system_prompt=_build_system_prompt(contract),
            user_prompt=user_prompt,
            params=params,
            response_schema=block_input.output_schema,
            phase="pass1_of_1",
            block_input=block_input,
            telemetry=telemetry,
        )

        normalized = self._normalize_result(call_result.parsed, output_schema=block_input.output_schema)
        validation = self._validate_schema(normalized, block_input.output_schema)
        if not validation.valid:
            repair_outcome = await self._repair_schema(
                initial_result=normalized,
                initial_errors=validation.errors,
                output_schema=block_input.output_schema,
                max_attempts=_MAX_SCHEMA_REPAIR_ATTEMPTS,
                block_input=block_input,
                telemetry=telemetry,
            )
            if not repair_outcome.valid:
                return self._fallback_output(block_input, extra_warning="schema_validation_failed")
            normalized = repair_outcome.result

        return self._to_output(normalized, block_input)

    def _to_output(
        self, normalized: dict[str, Any], block_input: BoundaryHandlerInput
    ) -> BoundaryHandlerOutput:
        answer_text = str(normalized.get("answer_text") or "")
        try:
            confidence = float(normalized.get("confidence", 0.9))
        except (TypeError, ValueError):
            confidence = 0.9
        confidence = max(0.0, min(1.0, confidence))

        if not answer_text.strip():
            return self._fallback_output(block_input, extra_warning="empty_answer_text")

        return BoundaryHandlerOutput(
            status="completed",
            schema_valid=True,
            result=normalized,
            confidence=confidence,
            answer_text=answer_text,
        )

    def _fallback_output(
        self, block_input: BoundaryHandlerInput, *, extra_warning: str | None = None
    ) -> BoundaryHandlerOutput:
        warnings = ["boundary_handler_fallback_used"]
        if extra_warning:
            warnings.append(extra_warning)
        return BoundaryHandlerOutput(
            status="completed",
            schema_valid=False,
            result=None,
            confidence=0.0,
            warnings=warnings,
            answer_text="I'm sorry, but I am unable to assist with that request as it falls outside my capabilities as an academic advisor.",
        )

    def _failed_output(
        self, block_input: BaseReasoningBlockInput, *, reason: str
    ) -> BoundaryHandlerOutput:
        assert isinstance(block_input, BoundaryHandlerInput)
        return self._fallback_output(block_input, extra_warning=f"reasoning_block_failed: {reason}")


async def run_boundary_handler(
    *,
    original_user_message: str,
    decline_reason: str,
    llm_adapter: LLMAdapter,
    block_id: str,
) -> BoundaryHandlerOutput:
    block = BoundaryHandlingReasoningBlock(llm_adapter=llm_adapter)
    block_input = BoundaryHandlerInput(
        block_id=block_id,
        agent_name="boundary_handler",
        objective="Compose a helpful decline message for an out-of-scope or unfulfillable request.",
        original_user_message=original_user_message,
        decline_reason=decline_reason,
        output_schema_name=BOUNDARY_HANDLER_OUTPUT_SCHEMA_NAME,
        output_schema=BOUNDARY_HANDLER_OUTPUT_SCHEMA,
        prompt_contract_name=BOUNDARY_HANDLER_V1,
        llm_call_parameters=LLMCallParameters(timeout=_TIMEOUT_SECONDS),
    )
    return await block.run(block_input)
