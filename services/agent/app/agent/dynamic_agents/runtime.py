"""Shadow-only dynamic agent runtime (Phase 15).

`DynamicAgentInstance.run` executes a fixed block sequence assembled by
`AgentBuilder`. Reasoning goes exclusively through `ReasoningBlock` — never
direct LLM calls. Dynamic agents never affect final user-facing answers.
"""

from __future__ import annotations

import logging
import uuid
from typing import TYPE_CHECKING, Any, Callable, Awaitable

from pydantic import ValidationError

from app.agent.dynamic_agents.block_library import (
    COMPACT_OUTPUT_SUMMARIZATION_BLOCK,
    COMPARISON_SYNTHESIS_BLOCK,
    CONTEXT_FILTER_BLOCK,
    OUTPUT_SCHEMA_VALIDATION_BLOCK,
    SAFETY_VALIDATION_BLOCK,
    SINGLE_PASS_REASONING_BLOCK,
    TOOL_OBSERVATION_LOOP_BLOCK,
    BlockLibrary,
)
from app.agent.dynamic_agents.output_summarizer import summarize_dynamic_agent_output
from app.agent.dynamic_agents.prompt_contracts import DYNAMIC_AGENT_OUTPUT_SCHEMA_NAME, DYNAMIC_AGENT_V1
from app.agent.dynamic_agents.safety import enforce_runtime_safety, sanitize_reasoning_result, validate_output_policy
from app.agent.dynamic_agents.schemas import (
    AgentSpec,
    BlockDescriptor,
    DynamicAgentRunInput,
    DynamicAgentRunOutput,
)
from app.agent.reasoning.llm_adapter import ChatLLMAdapter
from app.agent.reasoning.reasoning_block import ReasoningBlock
from app.agent.reasoning.schema_validator import validate_against_schema
from app.agent.reasoning.schemas import ReasoningBlockInput, ReasoningBlockOutput, ReasoningRiskLevel
from app.agent.reasoning.task_schemas import DYNAMIC_AGENT_OUTPUT_SCHEMA
from app.config import Settings, get_settings

if TYPE_CHECKING:
    # Deferred to function scope below (not just type position) — `app.agent.specialists`
    # imports `app.agent.supervisor`, which imports `app.agent.planner`, which imports
    # `app.agent.dynamic_agents` (this package) to build Planner-emitted specs. Importing
    # these at module level here closes that cycle and makes collection order-dependent
    # (whichever package partially-initializes first "wins"); importing them where they're
    # actually used breaks it, since by call time every module involved has finished loading.
    from app.agent.specialists.schemas import SpecialistToolObservation
    from app.agent.specialists.tools.registry import SpecialistObservationRegistry, build_default_observation_registry
    from app.agent.specialists.tools.tool_loop import run_specialist_tool_loop

logger = logging.getLogger(__name__)

_FALLBACK_DECISION_SUMMARY = "Dynamic agent reasoning unavailable; skipped in shadow mode."
_FALLBACK_WARNING = "dynamic_agent_reasoning_unavailable_or_failed"
_VALID_STATUSES = ("completed", "needs_more_context", "unsupported", "failed", "skipped")


def _clamp01(value: Any) -> float:
    try:
        number = float(value)
    except (TypeError, ValueError):
        return 0.0
    return max(0.0, min(1.0, number))


def _str_list(raw: dict[str, Any], key: str) -> list[str]:
    values = raw.get(key)
    if not isinstance(values, list):
        return []
    return [str(value) for value in values if str(value).strip()]


def _dict_list(raw: dict[str, Any], key: str) -> list[dict[str, Any]]:
    values = raw.get(key)
    if not isinstance(values, list):
        return []
    return [item for item in values if isinstance(item, dict)]


def fallback_output(*, spec: AgentSpec, extra_warnings: list[str] | None = None) -> DynamicAgentRunOutput:
    return DynamicAgentRunOutput(
        status="skipped",
        spec_id=spec.spec_id,
        agent_name=spec.agent_name,
        decision_summary=_FALLBACK_DECISION_SUMMARY,
        warnings=[_FALLBACK_WARNING, *(extra_warnings or [])],
        confidence=0.0,
    )


def filter_context(
    compiled_context: dict[str, Any],
    *,
    spec: AgentSpec,
) -> tuple[dict[str, Any], list[str], list[str]]:
    """Apply the AgentSpec context contract — deterministic, read-only."""
    contract = spec.context_contract
    forbidden = set(contract.forbidden_context_keys)
    filtered = {
        key: value
        for key, value in compiled_context.items()
        if key not in forbidden
    }

    missing: list[str] = []
    warnings: list[str] = []

    if contract.allowed_context_sections:
        allowed = set(contract.allowed_context_sections)
        filtered = {key: value for key, value in filtered.items() if key in allowed}

    for required in contract.required_context_sections:
        if required not in filtered:
            missing.append(required)

    return filtered, missing, warnings


def build_task_context(
    *,
    spec: AgentSpec,
    task_brief: Any,
    filtered_context: dict[str, Any],
    observations: list[dict[str, Any]],
    dependency_outputs: dict[str, Any],
) -> dict[str, Any]:
    return {
        "spec_id": spec.spec_id,
        "agent_name": spec.agent_name,
        "role": spec.role,
        "objective": spec.objective,
        "task_brief": task_brief.model_dump(),
        "compiled_context": filtered_context,
        "deterministic_observations": observations,
        "dependency_outputs": dependency_outputs,
        "allowed_observations": list(spec.allowed_observations),
        "allowed_capabilities": list(spec.allowed_capabilities),
        "boundaries": list(spec.boundaries),
        "success_criteria": list(spec.success_criteria or task_brief.success_criteria),
        "assumptions": list(spec.assumptions),
    }


def build_reasoning_input(
    *,
    spec: AgentSpec,
    task_brief: Any,
    filtered_context: dict[str, Any],
    observations: list[dict[str, Any]],
    dependency_outputs: dict[str, Any],
) -> ReasoningBlockInput:
    constraints = [
        *spec.boundaries,
        "shadow_only_execution",
        "no_writes",
        "no_proposed_actions",
        "use_only_supplied_context_and_observations",
    ]
    success_criteria = list(spec.success_criteria or task_brief.success_criteria)
    if not success_criteria:
        success_criteria = ["return_valid_structured_json"]

    return ReasoningBlockInput(
        block_id=f"{spec.agent_name}-{uuid.uuid4().hex[:10]}",
        agent_name=spec.agent_name,
        objective=task_brief.objective or spec.objective,
        task_context=build_task_context(
            spec=spec,
            task_brief=task_brief,
            filtered_context=filtered_context,
            observations=observations,
            dependency_outputs=dependency_outputs,
        ),
        constraints=constraints,
        success_criteria=success_criteria,
        output_schema_name=DYNAMIC_AGENT_OUTPUT_SCHEMA_NAME,
        output_schema=DYNAMIC_AGENT_OUTPUT_SCHEMA,
        prompt_contract_name=DYNAMIC_AGENT_V1,
        risk_level=spec.risk_level,  # type: ignore[arg-type]
    )


def build_output_from_result(
    result: dict[str, Any],
    *,
    spec: AgentSpec,
) -> DynamicAgentRunOutput:
    sanitized, strip_warnings = sanitize_reasoning_result(result)
    warnings = _str_list(sanitized, "warnings")
    warnings = [*warnings, *strip_warnings]

    status_raw = str(sanitized.get("status") or "completed").strip().lower()
    status = status_raw if status_raw in _VALID_STATUSES else "completed"

    try:
        return DynamicAgentRunOutput(
            status=status,  # type: ignore[arg-type]
            spec_id=spec.spec_id,
            agent_name=spec.agent_name,
            result=sanitized.get("result") if isinstance(sanitized.get("result"), dict) else {},
            decision_summary=str(sanitized.get("decision_summary") or ""),
            key_findings=_str_list(sanitized, "key_findings"),
            missing_context=_str_list(sanitized, "missing_context"),
            warnings=warnings,
            validation_notes=_str_list(sanitized, "validation_notes"),
            sources=_dict_list(sanitized, "sources"),
            confidence=_clamp01(sanitized.get("confidence", 0.0)),
            proposed_actions=[],
        )
    except ValidationError:
        logger.warning("dynamic_agent_output_shape_invalid", extra={"specId": spec.spec_id})
        return fallback_output(spec=spec, extra_warnings=["dynamic_agent_output_shape_invalid"])


def apply_synthesis(result: dict[str, Any], *, dependency_outputs: dict[str, Any]) -> dict[str, Any]:
    """Conservative compare-and-synthesize merge — no multi-agent orchestration yet."""
    synthesis = dict(result)
    inner = synthesis.get("result")
    if not isinstance(inner, dict):
        inner = {}
    inner = {
        **inner,
        "comparison_synthesis": {
            "dependencyKeyCount": len(dependency_outputs),
            "dependencyKeys": sorted(str(key) for key in dependency_outputs.keys())[:20],
        },
    }
    synthesis["result"] = inner
    return synthesis


class DynamicAgentInstance:
    """Runnable shadow-only dynamic agent assembled from fixed blocks."""

    def __init__(
        self,
        *,
        spec: AgentSpec,
        blocks: list[BlockDescriptor],
        block_library: BlockLibrary | None = None,
        reasoning_block: ReasoningBlock | None = None,
        observation_registry: SpecialistObservationRegistry | None = None,
    ) -> None:
        self.spec = spec
        self.blocks = list(blocks)
        self._block_library = block_library
        self._reasoning_block = reasoning_block
        self._observation_registry = observation_registry

    @property
    def block_count(self) -> int:
        return len(self.blocks)

    async def run(
        self,
        input: DynamicAgentRunInput,
        *,
        settings: Settings | None = None,
        reasoning_block_factory: Callable[[], ReasoningBlock | Awaitable[ReasoningBlock]] | None = None,
    ) -> DynamicAgentRunOutput:
        cfg = settings or get_settings()
        spec = input.spec
        warnings = enforce_runtime_safety(
            spec,
            dry_run=input.dry_run,
            settings_dry_run=cfg.is_agent_dynamic_agents_dry_run(),
        )

        if not cfg.is_agent_dynamic_agents_enabled():
            return fallback_output(spec=spec, extra_warnings=["dynamic_agents_disabled"])

        effective_dry_run = True
        if not input.dry_run or not cfg.is_agent_dynamic_agents_dry_run():
            warnings.append("dynamic_agent_forced_shadow_dry_run")

        filtered_context, missing_required, filter_warnings = filter_context(input.compiled_context, spec=spec)
        warnings.extend(filter_warnings)

        if missing_required and not spec.validation_policy.allow_missing_context:
            return DynamicAgentRunOutput(
                status="needs_more_context",
                spec_id=spec.spec_id,
                agent_name=spec.agent_name,
                decision_summary="Required context sections are missing for this dynamic agent.",
                missing_context=missing_required,
                warnings=warnings,
                confidence=0.0,
            )

        observations = list(input.deterministic_observations)
        dependency_outputs = {
            **input.task_brief.dependency_outputs,
            **input.dependency_outputs,
        }

        block_names = {block.name for block in self.blocks}
        reasoning_result: dict[str, Any] | None = None

        reasoning_output = await self._run_reasoning(
            spec=spec,
            input=input,
            filtered_context=filtered_context,
            observations=observations,
            dependency_outputs=dependency_outputs,
            cfg=cfg,
            reasoning_block_factory=reasoning_block_factory,
        )
        if reasoning_output is None:
            return fallback_output(spec=spec, extra_warnings=warnings)

        if (
            reasoning_output.status == "needs_tool"
            and TOOL_OBSERVATION_LOOP_BLOCK in block_names
            and spec.reasoning_pattern == "tool_observation_loop"
        ):
            observations, loop_warnings = await self._run_observation_loop_from_requests(
                spec=spec,
                input=input,
                filtered_context=filtered_context,
                observations=observations,
                dependency_outputs=dependency_outputs,
                tool_requests=reasoning_output.tool_requests,
                cfg=cfg,
            )
            warnings.extend(loop_warnings)
            reasoning_output = await self._run_reasoning(
                spec=spec,
                input=input,
                filtered_context=filtered_context,
                observations=observations,
                dependency_outputs=dependency_outputs,
                cfg=cfg,
                reasoning_block_factory=reasoning_block_factory,
            )
            if reasoning_output is None:
                return fallback_output(spec=spec, extra_warnings=warnings)

        if reasoning_output.status == "needs_tool":
            rejected = [
                getattr(request, "tool_name", None) or getattr(request, "observation_name", None) or "unknown"
                for request in reasoning_output.tool_requests or []
            ]
            for name in rejected:
                warnings.append(f"dynamic_agent_tool_request_rejected:{name}")
            return DynamicAgentRunOutput(
                status="unsupported",
                spec_id=spec.spec_id,
                agent_name=spec.agent_name,
                decision_summary="Unsupported tool request — only spec-allowed observations are permitted.",
                warnings=warnings,
                confidence=0.0,
            )

        if not isinstance(reasoning_output.result, dict):
            return fallback_output(spec=spec, extra_warnings=[*warnings, "dynamic_agent_missing_result"])

        reasoning_result = dict(reasoning_output.result)

        if reasoning_result is None:
            return fallback_output(spec=spec, extra_warnings=warnings)

        if COMPARISON_SYNTHESIS_BLOCK in block_names and spec.reasoning_pattern == "compare_and_synthesize":
            reasoning_result = apply_synthesis(reasoning_result, dependency_outputs=dependency_outputs)

        if OUTPUT_SCHEMA_VALIDATION_BLOCK in block_names:
            validation = validate_against_schema(reasoning_result, DYNAMIC_AGENT_OUTPUT_SCHEMA)
            if not validation.valid:
                return DynamicAgentRunOutput(
                    status="failed",
                    spec_id=spec.spec_id,
                    agent_name=spec.agent_name,
                    decision_summary="Dynamic agent output failed schema validation.",
                    validation_notes=list(validation.errors[:8]),
                    warnings=warnings,
                    confidence=0.0,
                )

        output = build_output_from_result(reasoning_result, spec=spec)
        output.warnings = [*warnings, *output.warnings]

        if SAFETY_VALIDATION_BLOCK in block_names:
            policy_notes = validate_output_policy(output, spec)
            if policy_notes:
                output.validation_notes = [*output.validation_notes, *policy_notes]
                if "proposed_actions_must_be_empty" in policy_notes:
                    output = output.model_copy(update={"status": "failed"})

        if missing_required and spec.validation_policy.allow_missing_context:
            output = output.model_copy(
                update={
                    "status": "needs_more_context",
                    "missing_context": [*output.missing_context, *missing_required],
                }
            )

        if effective_dry_run and output.status == "completed":
            output = output.model_copy(update={"warnings": [*output.warnings, "dynamic_agent_shadow_only"]})

        return output

    async def _resolve_reasoning_block(
        self,
        reasoning_block_factory: Callable[[], ReasoningBlock | Awaitable[ReasoningBlock]] | None,
        cfg: Settings,
    ) -> ReasoningBlock:
        if self._reasoning_block is not None:
            return self._reasoning_block
        if reasoning_block_factory is not None:
            block = reasoning_block_factory()
            if hasattr(block, "__await__"):
                return await block  # type: ignore[misc]
            return block  # type: ignore[return-value]
        return ReasoningBlock(llm=ChatLLMAdapter(settings=cfg))

    async def _run_reasoning(
        self,
        *,
        spec: AgentSpec,
        input: DynamicAgentRunInput,
        filtered_context: dict[str, Any],
        observations: list[dict[str, Any]],
        dependency_outputs: dict[str, Any],
        cfg: Settings,
        reasoning_block_factory: Callable[[], ReasoningBlock | Awaitable[ReasoningBlock]] | None,
    ) -> ReasoningBlockOutput | None:
        block = await self._resolve_reasoning_block(reasoning_block_factory, cfg)
        reasoning_input = build_reasoning_input(
            spec=spec,
            task_brief=input.task_brief,
            filtered_context=filtered_context,
            observations=observations,
            dependency_outputs=dependency_outputs,
        )
        try:
            return await block.run(reasoning_input)
        except Exception:  # noqa: BLE001 — dynamic agents must never crash callers
            logger.exception("dynamic_agent_reasoning_block_failed", extra={"specId": spec.spec_id})
            return None

    async def _run_observation_loop_from_requests(
        self,
        *,
        spec: AgentSpec,
        input: DynamicAgentRunInput,
        filtered_context: dict[str, Any],
        observations: list[dict[str, Any]],
        dependency_outputs: dict[str, Any],
        tool_requests: Any,
        cfg: Settings,
    ) -> tuple[list[dict[str, Any]], list[str]]:
        from app.agent.specialists.schemas import SpecialistToolObservation
        from app.agent.specialists.tools.registry import build_default_observation_registry
        from app.agent.specialists.tools.tool_loop import run_specialist_tool_loop

        warnings: list[str] = []
        registry = self._observation_registry or build_default_observation_registry()
        allowed = set(spec.allowed_observations)
        filtered_registry = _FilteredObservationRegistry(registry, allowed)

        present_names = {
            str(obs.get("name") or "")
            for obs in observations
            if isinstance(obs, dict) and obs.get("name")
        }
        specialist_observations = [
            SpecialistToolObservation(
                name=str(obs.get("name") or ""),
                status=obs.get("status") or "available",  # type: ignore[arg-type]
                summary=obs.get("summary") if isinstance(obs.get("summary"), dict) else {},
                source=obs.get("source"),
                warnings=list(obs.get("warnings") or []) if isinstance(obs.get("warnings"), list) else [],
            )
            for obs in observations
            if isinstance(obs, dict)
        ]

        max_rounds = min(max(spec.budget.max_tool_rounds, 1), 2)
        current_requests = tool_requests
        for _round in range(max_rounds):
            if not current_requests:
                break
            outcome = run_specialist_tool_loop(
                tool_requests=current_requests,
                specialist_agent_name=spec.agent_name,
                subtask_id=input.task_brief.brief_id,
                objective=input.task_brief.objective,
                user_message=input.task_brief.user_goal,
                compiled_context=filtered_context,
                dependency_outputs=dependency_outputs,
                already_present_observations=present_names,
                max_requests_per_round=min(spec.budget.max_observations, 4),
                registry=filtered_registry,
            )
            warnings.extend(outcome.warnings)
            for rejected in outcome.rejected_observations:
                warnings.append(f"dynamic_agent_observation_rejected:{rejected}")
            for obs in outcome.new_observations:
                present_names.add(obs.name)
                specialist_observations.append(obs)
            observations = [obs.model_dump() for obs in specialist_observations]
            current_requests = None

        return observations, warnings


class _FilteredObservationRegistry:
    """Wrap the default registry, exposing only spec-allowed observation names."""

    def __init__(self, inner: SpecialistObservationRegistry, allowed: set[str]) -> None:
        self._inner = inner
        self._allowed = allowed

    def get(self, name: str):
        if name not in self._allowed:
            return None
        return self._inner.get(name)

    def has(self, name: str) -> bool:
        return name in self._allowed and self._inner.has(name)

    def require(self, name: str):
        if name not in self._allowed:
            raise KeyError(f"observation_not_allowed:{name}")
        return self._inner.require(name)

    def list_names(self) -> list[str]:
        return [name for name in self._inner.list_names() if name in self._allowed]

    def allowed_observations_for_specialist(self, specialist_agent_name: str) -> list[str]:
        del specialist_agent_name
        return sorted(self._allowed)
