"""`RetrievalReasoningBlock` -- a purpose-built, alternate
dispatch target for the `retrieval` role
(docs/agent/agent_plans/RETRIEVAL_REASONING_BLOCK_PLAN.md).

Extends `BaseReasoningBlock` to implement a bounded tool-observation loop
instead of two independent nested loops.
"""

from __future__ import annotations

import json
import logging
from typing import Any, Literal

from pydantic import Field

from app.agent_core.planning.state import CertaintyTag, ToolInvocationRecord
from app.agent_core.reasoning.grounding import build_shared_grounding_block
from app.agent_core.reasoning.llm_adapter import LLMAdapter
from app.agent_core.reasoning.prompt_registry import PromptContract, PromptRegistry, build_default_prompt_registry
from app.agent_core.reasoning_blocks.base import BaseReasoningBlock, RunTelemetry
from app.agent_core.reasoning_blocks.schemas import BaseReasoningBlockInput, BaseReasoningBlockOutput, LLMCallParameters
from app.agent_core.subagents.schemas import SubagentContextPackage, SubagentResult
from app.agent_core.subagents.tool_round import execute_tool_round
from app.agent_core.tools.call_cache import ToolCallCache
from app.agent_core.tools.registry import ToolRegistry
from app.agent_core.tools.unresolvable_registry import UnresolvableEntityRegistry

logger = logging.getLogger(__name__)

_RETRIEVAL_ROUND_V1 = "retrieval_round_v1"
_RETRIEVAL_OUTPUT_SCHEMA_NAME = "retrieval_agent_output_v1"

_RETRIEVAL_OUTPUT_SCHEMA: dict[str, Any] = {
    "type": "object",
    "properties": {
        "certainty_basis": {
            "type": "string",
            "enum": [
                "official_record",
                "wiki_derived",
                "predicted_pattern",
                "llm_interpretation",
                "hypothetical_simulation",
            ],
        },
        "confidence": {"type": "number", "minimum": 0, "maximum": 1},
        "source_ref": {
            "type": ["object", "null"],
            "properties": {
                "page": {"type": "string"},
                "section": {"type": ["string", "null"]},
                "reasoning_path": {"type": ["string", "null"]},
            },
            "required": ["page"],
        },
        "assumptions": {"type": "array", "items": {"type": "string"}},
        "facts": {"type": "object"},
    },
    "required": ["certainty_basis", "confidence", "facts"],
}

_MAX_ROUNDS = 3


def _retrieval_round_contract() -> PromptContract:
    return PromptContract(
        name=_RETRIEVAL_ROUND_V1,
        version="1.0.0",
        role_prompt=(
            f"{build_shared_grounding_block()}\n\n"
            "You are the Retrieval Agent. You resolve and fetch facts using get_entity, "
            "search_knowledge, and traverse_relationship, plus higher-level tools that bundle "
            "several of those into one call. You may iterate if what you find is ambiguous. "
            "You return facts plus their source and confidence -- never commentary or "
            "explanation prose."
        ),
        instructions=[
            "You may decide, interpret, and judge freely, but you may never directly assert a "
            "computed or structural fact in your output without it coming from a tool call result "
            "already present in task_context or requested via tool_requests.",
            "Return facts with their source and confidence, never bare prose.",
            "If a granted tool's own name/description already bundles the multi-step chain you'd "
            "otherwise assemble by hand (e.g. get_course_profile instead of get_entity followed by "
            "several traverse_relationship calls; get_track_requirements instead of get_entity "
            "followed by traverse_relationship; get_policy_answer instead of search_knowledge "
            "followed by an interpretation step), call that one tool instead -- it does the same "
            "work in one round instead of several.",
            "If a search is ambiguous, request another tool call round rather than guessing.",
            "A record that was fetched successfully but has a field that is null/unset (e.g. a "
            "student profile with no declared program) is a CONFIDENT, fully resolved fact -- 'this "
            "field is genuinely absent' -- not an ambiguous or incomplete search. Finalize with that "
            "null value and high confidence rather than spending another round re-fetching the same "
            "record or searching elsewhere for a value the source has already confirmed does not "
            "exist.",
            "Output must be either a tool request (status='need_tools', provide tool_requests) OR "
            "a final result (status='ready', provide result matching the required schema).",
        ],
        allowed_context_fields=None,
        output_schema_name=_RETRIEVAL_OUTPUT_SCHEMA_NAME,
        default_risk_level="low",
        default_min_iterations=1,
        default_max_iterations=_MAX_ROUNDS,
        default_temperature=0.1,
        safety_rules=[
            "Do not expose chain-of-thought, hidden reasoning, or private notes.",
            "Do not fabricate a fact that no tool call actually returned.",
        ],
    )


def _build_prompt_registry() -> PromptRegistry:
    registry = build_default_prompt_registry()
    registry.register(_retrieval_round_contract())
    return registry


def _build_system_prompt(contract: PromptContract) -> str:
    lines = [contract.role_prompt, "", "INSTRUCTIONS:"]
    lines.extend(f"- {item}" for item in contract.instructions)
    lines.append("")
    lines.append("SAFETY RULES:")
    lines.extend(f"- {item}" for item in contract.safety_rules)
    return "\n".join(lines).strip()


class _RetrievalBlockInput(BaseReasoningBlockInput):
    tool_grant: list[str] = Field(default_factory=list)


class _RetrievalBlockOutput(BaseReasoningBlockOutput):
    tool_audit_trail: list[ToolInvocationRecord] = Field(default_factory=list)
    rounds_used: int = 0


class RetrievalReasoningBlock(BaseReasoningBlock):
    def __init__(
        self,
        *,
        llm_adapter: LLMAdapter,
        tool_registry: ToolRegistry,
        tool_call_cache: ToolCallCache | None = None,
        unresolvable_registry: UnresolvableEntityRegistry | None = None,
        prompt_registry: PromptRegistry | None = None,
        **kwargs: Any,
    ) -> None:
        super().__init__(
            llm_adapter=llm_adapter, prompt_registry=prompt_registry or _build_prompt_registry(), **kwargs
        )
        self._tool_registry = tool_registry
        self._tool_call_cache = tool_call_cache
        self._unresolvable_registry = unresolvable_registry

    async def _run_internal(
        self, block_input: _RetrievalBlockInput, telemetry: RunTelemetry
    ) -> _RetrievalBlockOutput:
        contract = self._resolve_prompt_contract(block_input.prompt_contract_name or _RETRIEVAL_ROUND_V1)
        params = self._resolve_llm_call_parameters(block_input.llm_call_parameters, contract)
        system_prompt = _build_system_prompt(contract)

        round_num = 0
        tool_results_so_far: dict[str, dict] = {}
        tool_audit_trail: list[ToolInvocationRecord] = []

        # The schema for the intermediate round calls to decide between status ready/need_tools
        round_schema = {
            "type": "object",
            "properties": {
                "status": {"type": "string", "enum": ["ready", "need_tools"]},
                "tool_requests": {
                    "type": "array",
                    "items": {
                        "type": "object",
                        "properties": {
                            "tool_name": {"type": "string"},
                            "arguments": {"type": "object"},
                        },
                        "required": ["tool_name", "arguments"],
                    },
                },
                "result": _RETRIEVAL_OUTPUT_SCHEMA,
            },
            "required": ["status"],
        }

        while round_num < _MAX_ROUNDS:
            round_num += 1
            is_final_round = round_num == _MAX_ROUNDS

            available_tools_with_schemas = []
            for t_name in block_input.tool_grant:
                try:
                    desc = self._tool_registry.get(t_name)
                    available_tools_with_schemas.append({
                        "name": desc.name,
                        "description": desc.description,
                        "input_schema": desc.input_model.model_json_schema(),
                    })
                except Exception:
                    available_tools_with_schemas.append({"name": t_name})

            payload = {
                "objective": block_input.objective,
                "task_context": block_input.task_context,
                "tool_results_so_far": tool_results_so_far,
                "available_tools": available_tools_with_schemas,
            }
            if is_final_round:
                payload["instruction"] = "NO MORE TOOL CALLS. You must finalize with what you have. Return status='ready' and populate the result."

            user_prompt = json.dumps(payload, ensure_ascii=False, indent=2, default=str)

            call_result = await self._invoke_llm(
                system_prompt=system_prompt,
                user_prompt=user_prompt,
                params=params,
                response_schema=round_schema,
                phase=f"retrieval_round_{round_num}",
                block_input=block_input,
                telemetry=telemetry,
            )

            # Simple fallback normalization if the LLM output is malformed
            parsed = call_result.parsed or {}
            status = parsed.get("status")

            if status == "need_tools" and not is_final_round:
                requests = parsed.get("tool_requests") or []
                tool_results_so_far, new_records = await execute_tool_round(
                    tool_requests=requests,
                    tool_grant=block_input.tool_grant,
                    tool_registry=self._tool_registry,
                    tool_results_so_far=tool_results_so_far,
                    log_prefix="retrieval",
                    tool_call_cache=self._tool_call_cache,
                    unresolvable_registry=self._unresolvable_registry,
                )
                tool_audit_trail.extend(new_records)
                continue

            # status == "ready" OR is_final_round
            candidate_result = parsed.get("result")
            if candidate_result is None:
                return self._retrieval_failed_output(
                    reason="round_budget_exhausted_no_result" if is_final_round else "status_ready_but_no_result",
                    tool_audit_trail=tool_audit_trail,
                    rounds_used=round_num,
                )

            candidate = self._normalize_result(candidate_result, output_schema=_RETRIEVAL_OUTPUT_SCHEMA)
            validation = self._validate_schema(candidate, _RETRIEVAL_OUTPUT_SCHEMA)

            if not validation.valid:
                repair_outcome = await self._repair_schema(
                    initial_result=candidate,
                    initial_errors=validation.errors,
                    output_schema=_RETRIEVAL_OUTPUT_SCHEMA,
                    max_attempts=2,
                    block_input=block_input,
                    telemetry=telemetry,
                )
                if not repair_outcome.valid:
                    return self._retrieval_failed_output(
                        reason=f"schema_repair_exhausted: {'; '.join(repair_outcome.errors[:5])}",
                        tool_audit_trail=tool_audit_trail,
                        rounds_used=round_num,
                    )
                candidate = repair_outcome.result

            return _RetrievalBlockOutput(
                status="completed",
                schema_valid=True,
                result=candidate,
                confidence=candidate.get("confidence", 1.0),
                tool_audit_trail=tool_audit_trail,
                rounds_used=round_num,
            )

        # Should never reach here due to the `is_final_round` check, but just in case:
        return self._retrieval_failed_output(
            reason="round_budget_exhausted_unexpectedly",
            tool_audit_trail=tool_audit_trail,
            rounds_used=round_num,
        )

    def _retrieval_failed_output(
        self, *, reason: str, tool_audit_trail: list[ToolInvocationRecord] | None = None, rounds_used: int = 0
    ) -> _RetrievalBlockOutput:
        return _RetrievalBlockOutput(
            status="failed",
            schema_valid=False,
            result=None,
            confidence=0.0,
            warnings=[f"retrieval_failed: {reason}"],
            tool_audit_trail=tool_audit_trail or [],
            rounds_used=rounds_used,
        )

    def _failed_output(self, block_input: BaseReasoningBlockInput, *, reason: str) -> _RetrievalBlockOutput:
        return self._retrieval_failed_output(reason=f"reasoning_block_failed: {reason}")


async def run_retrieval_subagent(
    *,
    context_package: SubagentContextPackage,
    tool_registry: ToolRegistry,
    llm_adapter: LLMAdapter,
    block_id: str,
    tool_call_cache: ToolCallCache | None = None,
    unresolvable_registry: UnresolvableEntityRegistry | None = None,
    llm_call_params: LLMCallParameters | None = None,
) -> SubagentResult:
    block_input = _RetrievalBlockInput(
        block_id=block_id,
        agent_name="retrieval",
        objective=context_package.structured_fields.goal,
        task_context={
            "rendered_prompt": context_package.rendered_prompt,
            "structured_fields": context_package.structured_fields.model_dump(),
            "dependency_state": [entry.model_dump() for entry in context_package.dependency_state],
        },
        output_schema_name=_RETRIEVAL_OUTPUT_SCHEMA_NAME,
        output_schema=_RETRIEVAL_OUTPUT_SCHEMA,
        tool_grant=list(context_package.tool_grant),
        **({"llm_call_parameters": llm_call_params} if llm_call_params else {}),
    )
    block = RetrievalReasoningBlock(llm_adapter=llm_adapter, tool_registry=tool_registry, tool_call_cache=tool_call_cache, unresolvable_registry=unresolvable_registry)
    output = await block.run(block_input)

    status: Literal["succeeded", "partial", "failed"] = (
        "succeeded" if output.status == "completed" and output.result is not None else "failed"
    )

    certainty = None
    assumptions = []
    if output.result is not None:
        basis = output.result.get("certainty_basis", "wiki_derived")
        confidence = output.result.get("confidence", 1.0)
        source_ref_dict = output.result.get("source_ref")
        
        # Pydantic validation handles this gracefully via CertaintyTag instantiation below.
        certainty = CertaintyTag(
            basis=basis,
            confidence=confidence,
            source_ref=source_ref_dict,
        )
        assumptions = output.result.get("assumptions", [])
    else:
        certainty = CertaintyTag(basis="wiki_derived", confidence=0.0)

    return SubagentResult(
        status=status,
        result=output.result,
        certainty=certainty,
        assumptions=assumptions,
        warnings=list(output.warnings),
        tool_audit_trail=output.tool_audit_trail,
        needs_another_round=False,
    )


__all__ = [
    "_RETRIEVAL_ROUND_V1",
    "_RETRIEVAL_OUTPUT_SCHEMA_NAME",
    "RetrievalReasoningBlock",
    "run_retrieval_subagent",
]
