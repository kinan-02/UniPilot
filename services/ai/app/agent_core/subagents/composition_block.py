"""Composition block (docs/agent/agent_plans/COMPOSITION_REASONING_BLOCK_PLAN.md).

Single-shot, zero-tool reasoning block for the 'composition' role.
"""

from __future__ import annotations

import asyncio
import json
from typing import Any

from app.agent_core.reasoning.llm_adapter import LLMAdapter
from app.agent_core.reasoning.prompt_registry import PromptContract, PromptRegistry
from app.agent_core.reasoning.result_normalizer import GENERIC_BLANK_FIELD_PLACEHOLDER
from app.agent_core.reasoning_blocks.base import BaseReasoningBlock, RunTelemetry
from app.agent_core.reasoning_blocks.schemas import BaseReasoningBlockInput, BaseReasoningBlockOutput, LLMCallParameters
from app.agent_core.roles.prompts import COMPOSITION_AGENT_V1, build_prompt_registry_with_roles
from app.agent_core.subagents.schemas import SubagentContextPackage, SubagentResult
from app.agent_core.planning.state import CertaintyTag

_COMPOSITION_OUTPUT_SCHEMA_NAME = "composition_agent_output_v1"

_COMPOSITION_OUTPUT_SCHEMA: dict[str, Any] = {
    "type": "object",
    "properties": {"answer_text": {"type": "string"}},
    "required": ["answer_text"],
    "additionalProperties": False,
}

_MAX_SCHEMA_REPAIR_ATTEMPTS = 2


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


def _build_user_prompt(block_input: BaseReasoningBlockInput) -> str:
    payload = {
        "objective": block_input.objective,
        "task_context": block_input.task_context,
        "output_schema_name": block_input.output_schema_name,
        "output_schema": block_input.output_schema,
    }
    return json.dumps(payload, ensure_ascii=False, indent=2, default=str)


class CompositionReasoningBlock(BaseReasoningBlock):
    """Single-shot, no tools. Translates accumulated state into grounded prose."""

    def __init__(self, *, llm_adapter: LLMAdapter, prompt_registry: PromptRegistry | None = None, **kwargs: Any) -> None:
        super().__init__(
            llm_adapter=llm_adapter, prompt_registry=prompt_registry or build_prompt_registry_with_roles(), **kwargs
        )

    async def _run_internal(
        self, block_input: BaseReasoningBlockInput, telemetry: RunTelemetry
    ) -> BaseReasoningBlockOutput:
        contract = self._resolve_prompt_contract(block_input.prompt_contract_name or COMPOSITION_AGENT_V1)
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
            # Composition's payload is a single free-text field, so a prose
            # response IS the answer. Live, the model twice answered correctly
            # in prose and the block discarded it, leaving the student with an
            # empty string -- salvage rather than lose a correct answer.
            salvage_text_field="answer_text",
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
                return self._composition_failed_output(reason="schema_validation_failed")
            normalized = repair_outcome.result

        answer_text = normalized.get("answer_text")
        if (
            not (isinstance(answer_text, str) and answer_text.strip())
            or answer_text == GENERIC_BLANK_FIELD_PLACEHOLDER
        ):
            return self._composition_failed_output(reason="empty_answer_text")

        return BaseReasoningBlockOutput(
            status="completed",
            schema_valid=True,
            result=normalized,
            confidence=1.0,
            # A salvaged answer is recovered, not clean -- surface it so the
            # model's failure to honour the JSON contract stays visible rather
            # than being silently absorbed.
            warnings=(["composition_salvaged_prose_answer"] if call_result.salvaged else []),
        )

    def _composition_failed_output(self, *, reason: str) -> BaseReasoningBlockOutput:
        return BaseReasoningBlockOutput(
            status="failed",
            schema_valid=False,
            result=None,
            confidence=0.0,
            warnings=[f"composition_failed: {reason}"],
        )

async def run_composition_subagent(
    *,
    context_package: SubagentContextPackage,
    llm_adapter: LLMAdapter,
    block_id: str,
    streaming_queue: asyncio.Queue[str] | None = None,
    llm_call_params: LLMCallParameters | None = None,
) -> SubagentResult:
    """Wrapper that executes CompositionReasoningBlock.
    
    Includes a retry-on-missing-result policy absorbed from synthesis.py.
    No tool_registry is needed for this wrapper.
    """
    block_input = BaseReasoningBlockInput(
        block_id=block_id,
        agent_name="composition",
        objective=context_package.structured_fields.goal,
        task_context={
            "instruction_fields": context_package.structured_fields.model_dump(),
            "dependency_state": [entry.to_dependency_view() for entry in context_package.dependency_state],
            "guardrails": context_package.guardrails,
            "rendered_prompt": context_package.rendered_prompt,
        },
        output_schema_name=_COMPOSITION_OUTPUT_SCHEMA_NAME,
        output_schema=_COMPOSITION_OUTPUT_SCHEMA,
        prompt_contract_name=COMPOSITION_AGENT_V1,
        **({"llm_call_parameters": llm_call_params} if llm_call_params else {}),
    )

    block = CompositionReasoningBlock(llm_adapter=llm_adapter, streaming_queue=streaming_queue)
    
    output = await block.run(block_input=block_input)
    
    # Retry on missing result logic: if it fails with empty text, we retry once
    if output.status == "failed" and any("empty_answer_text" in w or "result_is_missing" in w for w in output.warnings):
        retry_input = block_input.model_copy(update={"block_id": f"{block_id}-retry"})
        output = await block.run(block_input=retry_input)

    status = "succeeded" if output.status == "completed" else "failed"

    # Default certainty for a subagent result.
    # We map 1.0 confidence to an llm_interpretation certainty tag, 
    # as the subagent itself doesn't possess inherent certainty basis logic beyond its own text output.
    certainty = CertaintyTag(basis="llm_interpretation", confidence=output.confidence)

    return SubagentResult(
        status=status,
        result=output.result,
        certainty=certainty,
        assumptions=[],
        warnings=output.warnings,
        tool_audit_trail=[],
        needs_another_round=False,
    )
