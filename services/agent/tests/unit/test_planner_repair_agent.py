"""Unit tests for optional planner repair agent (Phase 19)."""

from __future__ import annotations

from typing import Any

import pytest

from app.agent.planner.repair_agent import run_plan_repair, run_plan_repair_with_llm
from app.agent.planner.repair_schemas import PlanRepairRequest, PlanSnapshot
from app.agent.reasoning.prompt_registry import PLANNER_REPAIR_V1
from app.agent.reasoning.schemas import ReasoningBlockInput, ReasoningBlockOutput
from app.config import Settings


class FakeReasoningBlock:
    def __init__(self, output: ReasoningBlockOutput | None = None) -> None:
        self.output = output
        self.calls: list[ReasoningBlockInput] = []

    async def run(self, input: ReasoningBlockInput) -> ReasoningBlockOutput:
        self.calls.append(input)
        assert self.output is not None
        return self.output


def _completed_output(result: dict[str, Any], **overrides: Any) -> ReasoningBlockOutput:
    defaults: dict[str, Any] = dict(
        status="completed",
        result=result,
        decision_summary="repaired",
        confidence=0.8,
        schema_valid=True,
        iterations_used=2,
        repair_attempts_used=0,
    )
    defaults.update(overrides)
    return ReasoningBlockOutput(**defaults)


def _request() -> PlanRepairRequest:
    return PlanRepairRequest(
        request_id="req-llm",
        user_goal="Plan next semester",
        prior_plan=PlanSnapshot(plan_id="plan-1", user_goal="Plan next semester"),
        deltas=[],
    )


@pytest.mark.asyncio
async def test_skipped_when_use_llm_false() -> None:
    cfg = Settings(AGENT_PLAN_REPAIR_USE_LLM=False)
    output = await run_plan_repair_with_llm(_request(), settings=cfg, reasoning_block=FakeReasoningBlock())
    assert output.status == "skipped"


@pytest.mark.asyncio
async def test_uses_planner_repair_v1_when_enabled() -> None:
    cfg = Settings(AGENT_PLAN_REPAIR_USE_LLM=True, OPENAI_API_KEY="test-key")
    fake = FakeReasoningBlock(
        _completed_output(
            {
                "status": "repaired",
                "mode_used": "repair",
                "plan_id": "plan-1",
                "decision_summary": "Repaired plan.",
                "confidence": 0.8,
                "safe_to_use": False,
            }
        )
    )
    await run_plan_repair_with_llm(_request(), settings=cfg, reasoning_block=fake)
    assert fake.calls
    assert fake.calls[0].prompt_contract_name == PLANNER_REPAIR_V1


@pytest.mark.asyncio
async def test_invalid_llm_output_falls_back_to_deterministic_repair() -> None:
    cfg = Settings(AGENT_PLAN_REPAIR_USE_LLM=True, OPENAI_API_KEY="test-key")
    fake = FakeReasoningBlock(
        ReasoningBlockOutput(
            status="completed",
            result={"bad": True},
            decision_summary="bad",
            confidence=0.0,
            schema_valid=False,
            iterations_used=1,
            repair_attempts_used=0,
        )
    )
    output = await run_plan_repair_with_llm(_request(), settings=cfg, reasoning_block=fake)
    assert output.status in {"repaired", "continued", "regenerated", "clarification_needed", "aborted_safely"}
    assert "llm_repair_schema_fallback" in output.warnings or output.mode_used == "continue"


@pytest.mark.asyncio
async def test_no_direct_llm_calls_in_repair_path() -> None:
    cfg = Settings(AGENT_PLAN_REPAIR_USE_LLM=False)
    output = await run_plan_repair(_request(), settings=cfg)
    assert output.status in {"continued", "skipped", "repaired"}


@pytest.mark.asyncio
async def test_llm_plan_id_preserved_when_no_prior_plan() -> None:
    cfg = Settings(AGENT_PLAN_REPAIR_USE_LLM=True, OPENAI_API_KEY="test-key")
    request = PlanRepairRequest(request_id="req-llm", user_goal="Plan next semester", prior_plan=None, deltas=[])
    fake = FakeReasoningBlock(
        _completed_output(
            {
                "status": "regenerated",
                "mode_used": "regenerate",
                "plan_id": "plan-from-llm",
                "decision_summary": "Regenerated plan.",
                "confidence": 0.8,
                "safe_to_use": False,
            }
        )
    )
    output = await run_plan_repair_with_llm(request, settings=cfg, reasoning_block=fake)
    assert output.plan_id == "plan-from-llm"


@pytest.mark.asyncio
async def test_no_proposed_actions_in_output() -> None:
    cfg = Settings(AGENT_PLAN_REPAIR_USE_LLM=True, OPENAI_API_KEY="test-key")
    fake = FakeReasoningBlock(
        _completed_output(
            {
                "status": "repaired",
                "mode_used": "repair",
                "plan_id": "plan-1",
                "repaired_plan": {"proposed_actions": [{"type": "bad"}]},
                "decision_summary": "bad",
                "confidence": 0.5,
                "safe_to_use": False,
            }
        )
    )
    output = await run_plan_repair_with_llm(_request(), settings=cfg, reasoning_block=fake)
    assert "proposed_actions" not in (output.repaired_plan or {})
