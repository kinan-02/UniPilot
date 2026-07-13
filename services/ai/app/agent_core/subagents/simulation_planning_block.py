"""`SimulationPlanningReasoningBlock` -- a purpose-built, alternate
dispatch target for the `simulation_planning` role
(docs/agent/agent_plans/SIMULATION_PLANNING_REASONING_BLOCK_PLAN.md).

Structurally closer to `RetrievalReasoningBlock`'s shape than
`InterpretationReasoningBlock`'s: neither granted tool (`mutate_state`,
`search_over_state`) is LLM-backed, so there's no nested-reasoning-block
concern -- just a flat bounded tool-round loop using the shared
`subagents.tool_round.execute_tool_round` helper. The "reflect-and-revise"
pattern (AGENT_VISION.md §6.2) needs no new machinery: a failed candidate
just means the next round's tool_requests propose a different
change/constraints, which the existing loop already supports.

One deliberate schema difference from both existing dedicated blocks: the
output schema's `certainty_basis` enum is restricted to exactly
`{hypothetical_simulation, predicted_pattern}` -- `official_record`,
`wiki_derived`, and `llm_interpretation` are structurally excluded. This
turns the role's own guardrail ("Never present a simulated outcome as an
official record") into a schema-level enforcement, not just a prompt
instruction.
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

_SIMULATION_PLANNING_ROUND_V1 = "simulation_planning_round_v1"
_SIMULATION_PLANNING_OUTPUT_SCHEMA_NAME = "simulation_planning_agent_output_v1"

_SIMULATION_PLANNING_OUTPUT_SCHEMA: dict[str, Any] = {
    "type": "object",
    "properties": {
        "certainty_basis": {
            "type": "string",
            "enum": ["hypothetical_simulation", "predicted_pattern"],
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
        "outcome": {"type": "object"},
    },
    "required": ["certainty_basis", "confidence", "outcome"],
}

_MIN_ROUNDS = 2
_MAX_ROUNDS = 4


def _simulation_planning_round_contract() -> PromptContract:
    return PromptContract(
        name=_SIMULATION_PLANNING_ROUND_V1,
        version="1.0.0",
        role_prompt=(
            f"{build_shared_grounding_block()}\n\n"
            "You are the Simulation/Planning Agent. You own mutate_state and "
            "search_over_state, translating loose constraints into the formal objects "
            "those primitives need, and produce projected plans or outcomes, plus "
            "higher-level tools that bundle a whole simulation/comparison/audit chain "
            "into one call. A hypothetical/simulated result must always be tagged as "
            "such, never phrased as an official fact."
        ),
        instructions=[
            "You may decide, interpret, and judge freely, but you may never directly assert a "
            "computed or structural fact in your output without it coming from a tool call result "
            "already present in task_context or requested via tool_requests.",
            "Tag every simulated/projected result with certainty_basis='hypothetical_simulation' or "
            "'predicted_pattern' as appropriate -- never 'official_record'.",
            "When granted, prefer a higher-level tool over assembling the equivalent chain of "
            "mutate_state/search_over_state calls by hand: simulate_course_disruption instead of "
            "mutate_state followed by a before/after search_over_state comparison; "
            "check_eligibility for a single-course snapshot check instead of a full "
            "search_over_state run; audit_graduation_progress instead of manually comparing "
            "completed courses against a track's requirements; compare_plans instead of "
            "hand-diffing two search_over_state results. Each does the same work in one call.",
            "If the first candidate fails a constraint, revise and retry before giving up.",
            "You must call at least one tool (e.g. mutate_state or search_over_state) before "
            "finalizing -- you may never answer status='ready' on the very first round.",
            "Output must be either a tool request (status='need_tools', provide tool_requests) OR "
            "a final result (status='ready', provide result matching the required schema).",
        ],
        allowed_context_fields=None,
        output_schema_name=_SIMULATION_PLANNING_OUTPUT_SCHEMA_NAME,
        default_risk_level="medium",
        default_min_iterations=_MIN_ROUNDS,
        default_max_iterations=_MAX_ROUNDS,
        default_temperature=0.2,
        safety_rules=[
            "Do not expose chain-of-thought, hidden reasoning, or private notes.",
            "Never present a simulated/projected outcome as an official record.",
        ],
    )


def _build_prompt_registry() -> PromptRegistry:
    registry = build_default_prompt_registry()
    registry.register(_simulation_planning_round_contract())
    return registry


def _build_system_prompt(contract: PromptContract) -> str:
    lines = [contract.role_prompt, "", "INSTRUCTIONS:"]
    lines.extend(f"- {item}" for item in contract.instructions)
    lines.append("")
    lines.append("SAFETY RULES:")
    lines.extend(f"- {item}" for item in contract.safety_rules)
    return "\n".join(lines).strip()


class _SimulationPlanningBlockInput(BaseReasoningBlockInput):
    tool_grant: list[str] = Field(default_factory=list)


class _SimulationPlanningBlockOutput(BaseReasoningBlockOutput):
    tool_audit_trail: list[ToolInvocationRecord] = Field(default_factory=list)
    rounds_used: int = 0


class SimulationPlanningReasoningBlock(BaseReasoningBlock):
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
        self, block_input: _SimulationPlanningBlockInput, telemetry: RunTelemetry
    ) -> _SimulationPlanningBlockOutput:
        contract = self._resolve_prompt_contract(block_input.prompt_contract_name or _SIMULATION_PLANNING_ROUND_V1)
        params = self._resolve_llm_call_parameters(block_input.llm_call_parameters, contract)
        system_prompt = _build_system_prompt(contract)

        round_num = 0
        tool_results_so_far: dict[str, dict] = {}
        tool_audit_trail: list[ToolInvocationRecord] = []

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
                "result": _SIMULATION_PLANNING_OUTPUT_SCHEMA,
            },
            "required": ["status"],
        }

        while round_num < _MAX_ROUNDS:
            round_num += 1
            is_final_round = round_num == _MAX_ROUNDS
            below_min_rounds = round_num < _MIN_ROUNDS

            available_tools_with_schemas = []
            for t_name in block_input.tool_grant:
                try:
                    desc = self._tool_registry.get(t_name)
                    available_tools_with_schemas.append(
                        {
                            "name": desc.name,
                            "description": desc.description,
                            "input_schema": desc.input_model.model_json_schema(),
                        }
                    )
                except Exception:
                    available_tools_with_schemas.append({"name": t_name})

            payload = {
                "objective": block_input.objective,
                "task_context": block_input.task_context,
                "tool_results_so_far": tool_results_so_far,
                "available_tools": available_tools_with_schemas,
            }
            if below_min_rounds:
                payload["instruction"] = (
                    "You must call at least one tool this round; a 'ready' status now will be ignored."
                )
            if is_final_round:
                payload["instruction"] = (
                    "NO MORE TOOL CALLS. You must finalize with what you have. "
                    "Return status='ready' and populate the result."
                )

            user_prompt = json.dumps(payload, ensure_ascii=False, indent=2, default=str)

            call_result = await self._invoke_llm(
                system_prompt=system_prompt,
                user_prompt=user_prompt,
                params=params,
                response_schema=round_schema,
                phase=f"simulation_planning_round_{round_num}",
                block_input=block_input,
                telemetry=telemetry,
            )

            parsed = call_result.parsed or {}
            status = parsed.get("status")

            if status == "need_tools" and not is_final_round:
                requests = parsed.get("tool_requests") or []
                requests = await self._repair_tool_requests_if_needed(
                    parsed, requests, round_schema=round_schema, block_input=block_input, telemetry=telemetry
                )
                tool_results_so_far, new_records = await execute_tool_round(
                    tool_requests=requests,
                    tool_grant=block_input.tool_grant,
                    tool_registry=self._tool_registry,
                    tool_results_so_far=tool_results_so_far,
                    log_prefix="simulation_planning",
                    tool_call_cache=self._tool_call_cache,
                    unresolvable_registry=self._unresolvable_registry,
                )
                tool_audit_trail.extend(new_records)
                continue

            if status == "ready" and below_min_rounds:
                # Premature finalize attempt -- never honored. No tools
                # executed this round; just advance (bounded by _MAX_ROUNDS
                # regardless, so no infinite-loop risk).
                continue

            # status == "ready" (round >= _MIN_ROUNDS), OR this was the
            # forced-finalize final round.
            candidate_result = parsed.get("result")
            if candidate_result is None:
                return self._simulation_planning_failed_output(
                    reason="round_budget_exhausted_no_result" if is_final_round else "status_ready_but_no_result",
                    tool_audit_trail=tool_audit_trail,
                    rounds_used=round_num,
                )

            candidate = self._normalize_result(candidate_result, output_schema=_SIMULATION_PLANNING_OUTPUT_SCHEMA)
            validation = self._validate_schema(candidate, _SIMULATION_PLANNING_OUTPUT_SCHEMA)

            if not validation.valid:
                repair_outcome = await self._repair_schema(
                    initial_result=candidate,
                    initial_errors=validation.errors,
                    output_schema=_SIMULATION_PLANNING_OUTPUT_SCHEMA,
                    max_attempts=2,
                    block_input=block_input,
                    telemetry=telemetry,
                )
                if not repair_outcome.valid:
                    return self._simulation_planning_failed_output(
                        reason=f"schema_repair_exhausted: {'; '.join(repair_outcome.errors[:5])}",
                        tool_audit_trail=tool_audit_trail,
                        rounds_used=round_num,
                    )
                candidate = repair_outcome.result

            return _SimulationPlanningBlockOutput(
                status="completed",
                schema_valid=True,
                result=candidate,
                confidence=candidate.get("confidence", 1.0),
                tool_audit_trail=tool_audit_trail,
                rounds_used=round_num,
            )

        # Should never reach here due to the `is_final_round` check, but just in case:
        return self._simulation_planning_failed_output(
            reason="round_budget_exhausted_unexpectedly",
            tool_audit_trail=tool_audit_trail,
            rounds_used=round_num,
        )

    def _simulation_planning_failed_output(
        self, *, reason: str, tool_audit_trail: list[ToolInvocationRecord] | None = None, rounds_used: int = 0
    ) -> _SimulationPlanningBlockOutput:
        return _SimulationPlanningBlockOutput(
            status="failed",
            schema_valid=False,
            result=None,
            confidence=0.0,
            warnings=[f"simulation_planning_failed: {reason}"],
            tool_audit_trail=tool_audit_trail or [],
            rounds_used=rounds_used,
        )

    def _failed_output(
        self, block_input: BaseReasoningBlockInput, *, reason: str
    ) -> _SimulationPlanningBlockOutput:
        return self._simulation_planning_failed_output(reason=f"reasoning_block_failed: {reason}")


async def run_simulation_planning_subagent(
    *,
    context_package: SubagentContextPackage,
    tool_registry: ToolRegistry,
    llm_adapter: LLMAdapter,
    block_id: str,
    tool_call_cache: ToolCallCache | None = None,
    unresolvable_registry: UnresolvableEntityRegistry | None = None,
    llm_call_params: LLMCallParameters | None = None,
) -> SubagentResult:
    block_input = _SimulationPlanningBlockInput(
        block_id=block_id,
        agent_name="simulation_planning",
        objective=context_package.structured_fields.goal,
        task_context={
            "rendered_prompt": context_package.rendered_prompt,
            "structured_fields": context_package.structured_fields.model_dump(),
            "dependency_state": [entry.model_dump() for entry in context_package.dependency_state],
        },
        output_schema_name=_SIMULATION_PLANNING_OUTPUT_SCHEMA_NAME,
        output_schema=_SIMULATION_PLANNING_OUTPUT_SCHEMA,
        tool_grant=list(context_package.tool_grant),
        **({"llm_call_parameters": llm_call_params} if llm_call_params else {}),
    )
    block = SimulationPlanningReasoningBlock(
        llm_adapter=llm_adapter, tool_registry=tool_registry, tool_call_cache=tool_call_cache,
        unresolvable_registry=unresolvable_registry,
    )
    output = await block.run(block_input)

    status: Literal["succeeded", "partial", "failed"] = (
        "succeeded" if output.status == "completed" and output.result is not None else "failed"
    )

    certainty: CertaintyTag
    assumptions: list[str] = []
    if output.result is not None:
        basis = output.result.get("certainty_basis", "hypothetical_simulation")
        confidence = output.result.get("confidence", 1.0)
        source_ref_dict = output.result.get("source_ref")
        certainty = CertaintyTag(basis=basis, confidence=confidence, source_ref=source_ref_dict)
        assumptions = output.result.get("assumptions", [])
    else:
        certainty = CertaintyTag(basis="hypothetical_simulation", confidence=0.0)

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
    "_SIMULATION_PLANNING_ROUND_V1",
    "_SIMULATION_PLANNING_OUTPUT_SCHEMA_NAME",
    "SimulationPlanningReasoningBlock",
    "run_simulation_planning_subagent",
]
