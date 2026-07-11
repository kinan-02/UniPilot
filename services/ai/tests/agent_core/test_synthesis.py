"""Tests for `agent_core.synthesis.synthesis.compose_answer`'s retry-once
behavior on a `result_is_missing` failure -- monkeypatch the collaborator
(`run_subagent`), not the LLM, per this suite's own established convention
(see test_orchestrator_loop_parallelism.py)."""

from __future__ import annotations

import pytest

from app.agent_core.planning.state import CertaintyTag, PlanExecutionState
from app.agent_core.roles.roster import build_default_role_roster
from app.agent_core.subagents.schemas import SubagentResult
from app.agent_core.synthesis import synthesis as synthesis_module


def _result(*, status: str, warnings: list[str], answer_text: str | None = None) -> SubagentResult:
    return SubagentResult(
        status=status,  # type: ignore[arg-type]
        result={"answer_text": answer_text} if answer_text is not None else None,
        certainty=CertaintyTag(basis="llm_interpretation", confidence=0.5),
        warnings=warnings,
    )


@pytest.mark.asyncio
async def test_retries_once_when_result_is_missing_and_returns_the_retry_outcome(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    calls: list[str] = []

    async def fake_run_subagent(*, role, context_package, tool_registry, llm_adapter, block_id, **kwargs):
        calls.append(block_id)
        if len(calls) == 1:
            return _result(status="failed", warnings=["schema_validation_failed", "result_is_missing"])
        return _result(status="succeeded", warnings=[], answer_text="The composed answer.")

    monkeypatch.setattr(synthesis_module, "run_subagent", fake_run_subagent)

    result = await synthesis_module.compose_answer(
        state=PlanExecutionState(plan_id="p1"),
        user_goal="What courses have I completed?",
        composition_role=build_default_role_roster()["composition"],
        tool_registry=None,  # never touched -- run_subagent is monkeypatched
        llm_adapter=None,  # never touched -- run_subagent is monkeypatched
        block_id="p1-synthesis",
    )

    assert calls == ["p1-synthesis", "p1-synthesis-retry"]
    assert result.status == "succeeded"
    assert result.result == {"answer_text": "The composed answer."}


@pytest.mark.asyncio
async def test_does_not_retry_when_the_failure_is_not_result_is_missing(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    calls: list[str] = []

    async def fake_run_subagent(*, role, context_package, tool_registry, llm_adapter, block_id, **kwargs):
        calls.append(block_id)
        return _result(status="failed", warnings=["schema_validation_failed", "answer_text: 123 is not of type 'string'"])

    monkeypatch.setattr(synthesis_module, "run_subagent", fake_run_subagent)

    result = await synthesis_module.compose_answer(
        state=PlanExecutionState(plan_id="p1"),
        user_goal="What courses have I completed?",
        composition_role=build_default_role_roster()["composition"],
        tool_registry=None,
        llm_adapter=None,
        block_id="p1-synthesis",
    )

    assert calls == ["p1-synthesis"]
    assert result.status == "failed"


@pytest.mark.asyncio
async def test_does_not_retry_on_a_successful_result(monkeypatch: pytest.MonkeyPatch) -> None:
    calls: list[str] = []

    async def fake_run_subagent(*, role, context_package, tool_registry, llm_adapter, block_id, **kwargs):
        calls.append(block_id)
        return _result(status="succeeded", warnings=[], answer_text="Fine on the first try.")

    monkeypatch.setattr(synthesis_module, "run_subagent", fake_run_subagent)

    result = await synthesis_module.compose_answer(
        state=PlanExecutionState(plan_id="p1"),
        user_goal="What courses have I completed?",
        composition_role=build_default_role_roster()["composition"],
        tool_registry=None,
        llm_adapter=None,
        block_id="p1-synthesis",
    )

    assert calls == ["p1-synthesis"]
    assert result.status == "succeeded"
