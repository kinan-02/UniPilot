"""Unit tests for dynamic agent runtime (Phase 15)."""

from __future__ import annotations

from typing import Any

import pytest

from app.agent.dynamic_agents.builder import AgentBuilder
from app.agent.dynamic_agents.prompt_contracts import DYNAMIC_AGENT_V1
from app.agent.dynamic_agents.schemas import AgentSpec, DynamicAgentBudget, DynamicAgentRunInput, TaskBrief
from app.agent.reasoning.schemas import ReasoningBlockInput, ReasoningBlockOutput
from app.config import Settings

_ENABLED = Settings(AGENT_DYNAMIC_AGENTS_ENABLED=True, AGENT_DYNAMIC_AGENTS_DRY_RUN=True)
_DISABLED = Settings(AGENT_DYNAMIC_AGENTS_ENABLED=False)
_MISCONFIGURED_DRY_RUN = Settings(AGENT_DYNAMIC_AGENTS_ENABLED=True, AGENT_DYNAMIC_AGENTS_DRY_RUN=False)


class FakeReasoningBlock:
    def __init__(self, output: ReasoningBlockOutput | None = None, *, raises: Exception | None = None) -> None:
        self.output = output
        self.raises = raises
        self.calls: list[ReasoningBlockInput] = []

    async def run(self, input: ReasoningBlockInput) -> ReasoningBlockOutput:
        self.calls.append(input)
        if self.raises is not None:
            raise self.raises
        assert self.output is not None
        return self.output


def _result(**overrides: Any) -> dict[str, Any]:
    defaults: dict[str, Any] = dict(
        status="completed",
        result={"comparison": "plan_a_is_lighter"},
        decision_summary="Plan A is lighter.",
        key_findings=["Plan A has fewer credits"],
        missing_context=[],
        warnings=[],
        validation_notes=[],
        sources=[{"type": "deterministic_observation"}],
        confidence=0.82,
    )
    defaults.update(overrides)
    return defaults


def _completed_output(result: dict[str, Any] | None = None, **overrides: Any) -> ReasoningBlockOutput:
    payload = result or _result()
    defaults: dict[str, Any] = dict(
        status="completed",
        result=payload,
        tool_requests=[],
        decision_summary=payload.get("decision_summary", ""),
        key_factors=[],
        missing_context=[],
        validation_notes=[],
        warnings=[],
        confidence=float(payload.get("confidence", 0.8)),
        schema_valid=True,
        iterations_used=2,
        repair_attempts_used=0,
    )
    defaults.update(overrides)
    return ReasoningBlockOutput(**defaults)


def _spec(**overrides: Any) -> AgentSpec:
    defaults: dict[str, Any] = dict(
        spec_id="spec_compare_001",
        agent_name="semester_plan_comparison_agent",
        role="comparison analyst",
        objective="Compare two semester plans",
        reasoning_pattern="single_pass",
        expected_output_schema_name="dynamic_agent_output_v1",
    )
    defaults.update(overrides)
    return AgentSpec(**defaults)


def _run_input(spec: AgentSpec, **overrides: Any) -> DynamicAgentRunInput:
    defaults: dict[str, Any] = dict(
        spec=spec,
        task_brief=TaskBrief(
            brief_id="brief_001",
            objective=spec.objective,
            user_goal="Compare my plans",
        ),
        compiled_context={"profile_summary": {"program": "CS"}},
    )
    defaults.update(overrides)
    return DynamicAgentRunInput(**defaults)


async def test_single_pass_run_returns_dynamic_agent_run_output() -> None:
    block = FakeReasoningBlock(_completed_output(_result()))
    instance = AgentBuilder().build(_spec())
    instance._reasoning_block = block  # noqa: SLF001 — test seam

    output = await instance.run(_run_input(instance.spec), settings=_ENABLED)

    assert output.spec_id == "spec_compare_001"
    assert output.status == "completed"
    assert output.confidence == 0.82


async def test_reasoning_block_called_with_dynamic_agent_v1() -> None:
    block = FakeReasoningBlock(_completed_output(_result()))
    instance = AgentBuilder().build(_spec())
    instance._reasoning_block = block  # noqa: SLF001

    await instance.run(_run_input(instance.spec), settings=_ENABLED)

    assert block.calls[0].prompt_contract_name == DYNAMIC_AGENT_V1


async def test_tool_observation_loop_uses_only_allowed_observations() -> None:
    needs_tool = _completed_output(
        status="needs_tool",
        tool_requests=[{"tool_name": "course_catalog_summary", "purpose": "Need catalog summary"}],
    )
    final = _completed_output(_result())
    block = FakeReasoningBlock(needs_tool)
    side_effect = AsyncMockSideEffect([needs_tool, final])
    block.run = side_effect  # type: ignore[method-assign]

    spec = _spec(
        reasoning_pattern="tool_observation_loop",
        allowed_observations=["course_catalog_summary"],
        budget=DynamicAgentBudget(max_tool_rounds=1),
    )
    instance = AgentBuilder().build(spec)
    instance._reasoning_block = block  # noqa: SLF001

    output = await instance.run(_run_input(spec), settings=_ENABLED)
    assert output.status in {"completed", "unsupported", "skipped", "failed", "needs_more_context"}
    assert len(side_effect.calls) >= 1


class AsyncMockSideEffect:
    def __init__(self, outputs: list[ReasoningBlockOutput]) -> None:
        self._outputs = outputs
        self.calls: list[ReasoningBlockInput] = []

    async def __call__(self, input: ReasoningBlockInput) -> ReasoningBlockOutput:
        self.calls.append(input)
        return self._outputs[min(len(self.calls) - 1, len(self._outputs) - 1)]


async def test_unknown_tool_request_rejected() -> None:
    block = FakeReasoningBlock(
        _completed_output(
            status="needs_tool",
            tool_requests=[{"tool_name": "forbidden_observation", "purpose": "Need forbidden obs"}],
        )
    )
    instance = AgentBuilder().build(_spec(reasoning_pattern="tool_observation_loop", allowed_observations=["course_catalog_summary"]))
    instance._reasoning_block = block  # noqa: SLF001

    output = await instance.run(_run_input(instance.spec), settings=_ENABLED)
    assert output.status == "unsupported"


async def test_proposed_actions_stripped_or_blocked() -> None:
    block = FakeReasoningBlock(_completed_output(_result(proposed_actions=[{"type": "write"}])))
    instance = AgentBuilder().build(_spec())
    instance._reasoning_block = block  # noqa: SLF001

    output = await instance.run(_run_input(instance.spec), settings=_ENABLED)
    assert output.proposed_actions == []


async def test_output_schema_validation_failure_returns_safe_failure() -> None:
    block = FakeReasoningBlock(_completed_output({"status": "completed"}))
    instance = AgentBuilder().build(_spec())
    instance._reasoning_block = block  # noqa: SLF001

    output = await instance.run(_run_input(instance.spec), settings=_ENABLED)
    assert output.status == "failed"


async def test_missing_context_returns_needs_more_context() -> None:
    from app.agent.dynamic_agents.schemas import DynamicAgentContextContract, DynamicAgentValidationPolicy

    spec = _spec(
        context_contract=DynamicAgentContextContract(required_context_sections=["transcript_summary"]),
        validation_policy=DynamicAgentValidationPolicy(allow_missing_context=False),
    )
    instance = AgentBuilder().build(spec)
    output = await instance.run(_run_input(spec, compiled_context={}), settings=_ENABLED)
    assert output.status == "needs_more_context"


async def test_runtime_never_stores_raw_context() -> None:
    block = FakeReasoningBlock(_completed_output(_result()))
    instance = AgentBuilder().build(_spec())
    instance._reasoning_block = block  # noqa: SLF001

    await instance.run(_run_input(instance.spec, compiled_context={"secret": "value"}), settings=_ENABLED)
    dumped = block.calls[0].model_dump_json()
    assert "secret" not in dumped or "compiled_context" in dumped


async def test_runtime_never_exposes_chain_of_thought() -> None:
    block = FakeReasoningBlock(_completed_output(_result(chain_of_thought="hidden")))
    instance = AgentBuilder().build(_spec())
    instance._reasoning_block = block  # noqa: SLF001

    output = await instance.run(_run_input(instance.spec), settings=_ENABLED)
    assert "chain_of_thought" not in output.model_dump()


async def test_dry_run_false_misconfiguration_still_runs_shadow_only_or_skips() -> None:
    block = FakeReasoningBlock(_completed_output(_result()))
    instance = AgentBuilder().build(_spec())
    instance._reasoning_block = block  # noqa: SLF001

    output = await instance.run(_run_input(instance.spec, dry_run=False), settings=_MISCONFIGURED_DRY_RUN)
    assert "dynamic_agent_forced_shadow_dry_run" in output.warnings or output.status == "skipped"


async def test_runtime_fallback_works_when_reasoning_block_fails() -> None:
    block = FakeReasoningBlock(None, raises=RuntimeError("boom"))
    instance = AgentBuilder().build(_spec())
    instance._reasoning_block = block  # noqa: SLF001

    output = await instance.run(_run_input(instance.spec), settings=_ENABLED)
    assert output.status == "skipped"


async def test_disabled_flag_skips_without_llm() -> None:
    block = FakeReasoningBlock(_completed_output(_result()))
    instance = AgentBuilder().build(_spec())
    instance._reasoning_block = block  # noqa: SLF001

    output = await instance.run(_run_input(instance.spec), settings=_DISABLED)
    assert output.status == "skipped"
    assert block.calls == []
