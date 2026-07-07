"""Shared specialist-agent execution helper (Phase 10).

Every specialist agent (`graduation_progress_agent`, `course_catalog_agent`,
`requirement_explanation_agent`) is a thin, agent-specific wrapper around
`run_specialist_reasoning` — the actual `ReasoningBlock` call, output
validation, proposed-action stripping, and fallback behavior all live here
so each specialist module only supplies its own prompt contract name, JSON
schema, constraints, and success criteria.

Hard constraints (enforced by construction):
- Only ever calls the LLM through `ReasoningBlock` — never directly.
- Never creates a write/action proposal (`SpecialistAgentOutput.proposed_actions`
  is forced to `[]` by that model's own field validator; this module strips
  it defensively *before* construction too, adding a
  `specialist_proposed_actions_blocked` warning if the raw LLM result ever
  carried one).
- Never raises: an unavailable/failed `ReasoningBlock` call, a schema-invalid
  result, or an unexpected exception all degrade to the same safe
  `status="skipped"` fallback output instead.
"""

from __future__ import annotations

import logging
import uuid
from typing import Any

from pydantic import ValidationError

from app.agent.reasoning.llm_adapter import ChatLLMAdapter
from app.agent.reasoning.reasoning_block import ReasoningBlock
from app.agent.reasoning.schemas import ReasoningBlockInput, ReasoningBlockOutput, ReasoningRiskLevel
from app.agent.specialists.schemas import SpecialistAgentInput, SpecialistAgentKind, SpecialistAgentOutput
from app.agent.specialists.tools.registry import SpecialistObservationRegistry, build_default_observation_registry
from app.agent.specialists.tools.tool_loop import run_specialist_tool_loop
from app.agent.specialists.tools.tool_loop_schemas import SpecialistToolLoopDiagnostics
from app.config import Settings, get_settings

logger = logging.getLogger(__name__)

_FALLBACK_DECISION_SUMMARY = "Specialist agent reasoning unavailable; skipped in shadow mode."
_FALLBACK_WARNING = "specialist_reasoning_unavailable_or_failed"
_VALID_OUTPUT_STATUSES = ("completed", "needs_more_context", "unsupported", "failed", "skipped")


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


def fallback_output(
    *,
    agent_name: SpecialistAgentKind,
    subtask_id: str,
    extra_warnings: list[str] | None = None,
) -> SpecialistAgentOutput:
    """The deterministic fallback returned whenever real reasoning can't happen.

    Matches the Phase 10 spec's fallback shape exactly:
    `status="skipped"`, the fixed decision summary, `confidence=0.0`, and
    `proposed_actions=[]` (guaranteed by the model itself).
    """
    return SpecialistAgentOutput(
        status="skipped",
        agent_name=agent_name,
        subtask_id=subtask_id,
        decision_summary=_FALLBACK_DECISION_SUMMARY,
        warnings=[_FALLBACK_WARNING, *(extra_warnings or [])],
        confidence=0.0,
    )


def build_output_from_result(
    result: dict[str, Any], *, agent_name: SpecialistAgentKind, subtask_id: str
) -> SpecialistAgentOutput:
    """Build a `SpecialistAgentOutput` from an already schema-validated LLM result dict.

    Defensive even against a schema-valid `result` — schema validation only
    guarantees shape, not safety. If `result` somehow carries a non-empty
    `proposed_actions` key (unreachable via the schema sent to the LLM, which
    has no such property, but checked anyway as defense in depth), it is
    stripped and a `specialist_proposed_actions_blocked` warning is added;
    `SpecialistAgentOutput.proposed_actions`'s own field validator forces it
    to `[]` unconditionally regardless.
    """
    warnings = _str_list(result, "warnings")
    raw_proposed_actions = result.get("proposed_actions")
    if isinstance(raw_proposed_actions, list) and raw_proposed_actions:
        warnings = [*warnings, "specialist_proposed_actions_blocked"]

    status_raw = str(result.get("status") or "completed").strip().lower()
    status = status_raw if status_raw in _VALID_OUTPUT_STATUSES else "completed"

    try:
        return SpecialistAgentOutput(
            status=status,  # type: ignore[arg-type]
            agent_name=agent_name,
            subtask_id=subtask_id,
            result=result.get("result") if isinstance(result.get("result"), dict) else {},
            decision_summary=str(result.get("decision_summary") or ""),
            key_findings=_str_list(result, "key_findings"),
            missing_context=_str_list(result, "missing_context"),
            warnings=warnings,
            validation_notes=_str_list(result, "validation_notes"),
            sources=_dict_list(result, "sources"),
            confidence=_clamp01(result.get("confidence", 0.0)),
            proposed_actions=[],
        )
    except ValidationError:
        logger.warning("specialist_output_shape_invalid", extra={"agentName": agent_name})
        return fallback_output(
            agent_name=agent_name, subtask_id=subtask_id, extra_warnings=["specialist_output_shape_invalid"]
        )


def build_task_context(specialist_input: SpecialistAgentInput) -> dict[str, Any]:
    """The exact `task_context` shape every specialist prompt contract's
    `allowed_context_fields` is built to match (see `reasoning/prompt_registry.py`)."""
    return {
        "objective": specialist_input.objective,
        "user_message": specialist_input.user_message,
        "compiled_context": specialist_input.compiled_context,
        "dependency_outputs": specialist_input.dependency_outputs,
        "deterministic_observations": [obs.model_dump() for obs in specialist_input.deterministic_observations],
        "success_criteria": specialist_input.success_criteria,
        "validation_requirements": specialist_input.validation_requirements,
    }


def _build_reasoning_input(
    specialist_input: SpecialistAgentInput,
    *,
    prompt_contract_name: str,
    output_schema_name: str,
    output_schema: dict[str, Any],
    risk_level: ReasoningRiskLevel,
    constraints: list[str],
    success_criteria: list[str],
) -> ReasoningBlockInput:
    return ReasoningBlockInput(
        block_id=f"{specialist_input.agent_name}-{uuid.uuid4().hex[:10]}",
        agent_name=specialist_input.agent_name,
        objective=specialist_input.objective,
        task_context=build_task_context(specialist_input),
        constraints=constraints,
        success_criteria=success_criteria,
        output_schema_name=output_schema_name,
        output_schema=output_schema,
        prompt_contract_name=prompt_contract_name,
        risk_level=risk_level,
    )


async def _run_reasoning_once(block: ReasoningBlock, reasoning_input: ReasoningBlockInput) -> ReasoningBlockOutput | None:
    """One `ReasoningBlock.run` call; returns `None` (never raises) on failure."""
    try:
        return await block.run(reasoning_input)
    except Exception:  # noqa: BLE001 — a specialist must never crash its caller
        logger.exception("specialist_reasoning_block_raised", extra={"agentName": reasoning_input.agent_name})
        return None


async def _run_specialist_tool_loop_and_final_pass(
    *,
    specialist_input: SpecialistAgentInput,
    initial_output: ReasoningBlockOutput,
    block: ReasoningBlock,
    cfg: Settings,
    prompt_contract_name: str,
    output_schema_name: str,
    output_schema: dict[str, Any],
    risk_level: ReasoningRiskLevel,
    constraints: list[str],
    success_criteria: list[str],
    agent_context_pack: Any | None,
    observation_registry: SpecialistObservationRegistry | None,
) -> tuple[ReasoningBlockOutput, SpecialistToolLoopDiagnostics]:
    """Phase 13: bounded tool-request loop (see `tools/tool_loop.py`).

    Runs up to `Settings.resolved_agent_specialist_tool_loop_max_rounds()`
    rounds (hard-capped at 2): each round validates the specialist's
    requested observation "tools", builds only the approved ones through
    the existing Phase 12 observation builder, appends them to
    `deterministic_observations`, and re-runs `ReasoningBlock` once for a
    (possibly still-`needs_tool`) final pass. Never calls an LLM itself
    beyond delegating to `block.run` via `_run_reasoning_once` — the actual
    tool-request validation/observation-building never touches an LLM.
    """
    registry = observation_registry or build_default_observation_registry()
    max_rounds = cfg.resolved_agent_specialist_tool_loop_max_rounds()
    max_requests = cfg.resolved_agent_specialist_tool_loop_max_requests_per_round()

    observations = list(specialist_input.deterministic_observations)
    current_output = initial_output
    rounds_used = 0
    requested_all: list[str] = []
    approved_all: list[str] = []
    rejected_all: list[str] = []
    missing_all: list[str] = []
    warnings_all: list[str] = []
    loop_failed = False

    while current_output.status == "needs_tool" and rounds_used < max_rounds:
        rounds_used += 1
        outcome = run_specialist_tool_loop(
            tool_requests=current_output.tool_requests,
            specialist_agent_name=specialist_input.agent_name,
            subtask_id=specialist_input.subtask_id,
            objective=specialist_input.objective,
            user_message=specialist_input.user_message,
            compiled_context=specialist_input.compiled_context,
            dependency_outputs=specialist_input.dependency_outputs,
            already_present_observations=[obs.name for obs in observations],
            max_requests_per_round=max_requests,
            agent_context_pack=agent_context_pack,
            registry=registry,
        )
        requested_all.extend(outcome.requested_observations)
        approved_all.extend(outcome.approved_observations)
        rejected_all.extend(outcome.rejected_observations)
        missing_all.extend(outcome.missing_observations)
        for warning in outcome.warnings:
            if warning not in warnings_all:
                warnings_all.append(warning)

        if outcome.new_observations:
            observations = [*observations, *outcome.new_observations]

        augmented_input = specialist_input.model_copy(update={"deterministic_observations": observations})
        reasoning_input = _build_reasoning_input(
            augmented_input,
            prompt_contract_name=prompt_contract_name,
            output_schema_name=output_schema_name,
            output_schema=output_schema,
            risk_level=risk_level,
            constraints=constraints,
            success_criteria=success_criteria,
        )
        next_output = await _run_reasoning_once(block, reasoning_input)
        if next_output is None:
            loop_failed = True
            break
        current_output = next_output

    if loop_failed:
        status = "failed"
        warnings_all.append("specialist_tool_loop_reasoning_failed")
    elif current_output.status == "needs_tool":
        status = "budget_exceeded"
        warnings_all.append("tool_loop_rounds_exhausted")
    elif approved_all:
        status = "completed_with_tools"
    else:
        status = "completed"

    diagnostics = SpecialistToolLoopDiagnostics(
        status=status,  # type: ignore[arg-type]
        rounds_used=rounds_used,
        requested_observations=requested_all,
        approved_observations=approved_all,
        rejected_observations=rejected_all,
        missing_observations=missing_all,
        warnings=warnings_all,
    )
    return current_output, diagnostics


async def run_specialist_reasoning(
    specialist_input: SpecialistAgentInput,
    *,
    prompt_contract_name: str,
    output_schema_name: str,
    output_schema: dict[str, Any],
    risk_level: ReasoningRiskLevel,
    constraints: list[str],
    success_criteria: list[str],
    reasoning_block: ReasoningBlock | None = None,
    settings: Settings | None = None,
    agent_context_pack: Any | None = None,
    observation_registry: SpecialistObservationRegistry | None = None,
) -> SpecialistAgentOutput:
    """Shared specialist-agent execution path — see module docstring.

    Never raises, never calls an LLM directly (only ever through
    `ReasoningBlock`). Returns the deterministic fallback output when
    specialist agents are disabled (`AGENT_SPECIALIST_AGENTS_ENABLED=false`),
    when `ReasoningBlock` fails/is unavailable, or when its result can't be
    normalized into a `SpecialistAgentOutput`.

    Phase 13: when the first `ReasoningBlock` pass returns `status="needs_tool"`
    and `AGENT_SPECIALIST_TOOL_LOOP_ENABLED=true`, runs the bounded
    tool-request loop (`_run_specialist_tool_loop_and_final_pass`) before
    falling through to the same completion/fallback logic as before Phase 13
    existed — when the flag is off (the default), behavior is byte-for-byte
    unchanged from Phase 12.
    """
    agent_name = specialist_input.agent_name
    subtask_id = specialist_input.subtask_id
    extra_warnings: list[str] = []

    if not specialist_input.dry_run:
        # Phase 10 is shadow-only regardless of this flag — surface the
        # misconfiguration loudly instead of silently ignoring it (mirrors
        # Phase 5/6/9's own `*_DRY_RUN=false` handling).
        logger.warning("specialist_dry_run_disabled_but_execution_not_implemented", extra={"agentName": agent_name})
        extra_warnings.append("specialist_dry_run_disabled_but_execution_not_implemented_in_phase10")

    cfg = settings or get_settings()
    if not cfg.is_agent_specialist_agents_enabled():
        return fallback_output(
            agent_name=agent_name, subtask_id=subtask_id, extra_warnings=[*extra_warnings, "specialist_agents_disabled"]
        )

    block = reasoning_block or ReasoningBlock(llm_adapter=ChatLLMAdapter(settings=cfg))
    reasoning_input = _build_reasoning_input(
        specialist_input,
        prompt_contract_name=prompt_contract_name,
        output_schema_name=output_schema_name,
        output_schema=output_schema,
        risk_level=risk_level,
        constraints=constraints,
        success_criteria=success_criteria,
    )

    output = await _run_reasoning_once(block, reasoning_input)
    if output is None:
        return fallback_output(agent_name=agent_name, subtask_id=subtask_id, extra_warnings=extra_warnings)

    tool_loop_diagnostics: SpecialistToolLoopDiagnostics | None = None
    if output.status == "needs_tool" and cfg.is_agent_specialist_tool_loop_enabled():
        output, tool_loop_diagnostics = await _run_specialist_tool_loop_and_final_pass(
            specialist_input=specialist_input,
            initial_output=output,
            block=block,
            cfg=cfg,
            prompt_contract_name=prompt_contract_name,
            output_schema_name=output_schema_name,
            output_schema=output_schema,
            risk_level=risk_level,
            constraints=constraints,
            success_criteria=success_criteria,
            agent_context_pack=agent_context_pack,
            observation_registry=observation_registry,
        )

    if output.status != "completed" or not output.schema_valid or output.result is None:
        if output.warnings:
            logger.warning(
                "specialist_reasoning_incomplete", extra={"agentName": agent_name, "warnings": output.warnings}
            )
        fallback = fallback_output(agent_name=agent_name, subtask_id=subtask_id, extra_warnings=extra_warnings)
        if tool_loop_diagnostics is not None:
            fallback = fallback.model_copy(update={"tool_loop_diagnostics": tool_loop_diagnostics})
        return fallback

    built = build_output_from_result(output.result, agent_name=agent_name, subtask_id=subtask_id)
    if extra_warnings:
        built = built.model_copy(update={"warnings": [*built.warnings, *extra_warnings]})
    if tool_loop_diagnostics is not None:
        built = built.model_copy(update={"tool_loop_diagnostics": tool_loop_diagnostics})
    return built
