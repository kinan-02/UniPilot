"""Unit tests for planning swarm sub-agent (no OpenAI calls)."""

from __future__ import annotations

from app.schemas.advisor import UserContextPayload
from app.services.planning_agent import (
    PlanningAgentResult,
    _planning_available,
    run_planning_agent,
)


def test_planning_available_requires_envelope_flag():
    empty = UserContextPayload()
    assert not _planning_available(empty)

    with_envelope = UserContextPayload(planning_context={"available": True, "status": "ok"})
    assert _planning_available(with_envelope)


def test_run_planning_agent_unavailable_without_profile():
    ctx = UserContextPayload(planning_context={"status": "degree_not_selected", "available": False})
    result = run_planning_agent("Am I on track to graduate?", ctx)
    assert isinstance(result, PlanningAgentResult)
    assert result.status == "unavailable"
    assert result.blocks[0]["intent"] == "planning_unavailable"


def test_planning_tools_return_graduation_snapshot_without_llm():
    ctx = UserContextPayload(
        planning_context={
            "available": True,
            "status": "ok",
            "graduation": {
                "completedCredits": 72,
                "totalRequiredCredits": 120,
                "completionPercentage": 60,
            },
            "latest_plan": None,
            "latest_risk": None,
        }
    )

    from app.services.planning_agent import _build_planning_tools

    state: dict = {"blocks": []}
    tools = _build_planning_tools(ctx, state)
    graduation_tool = next(tool for tool in tools if tool.name == "get_graduation_progress_snapshot")
    output = graduation_tool.invoke({})

    assert "72" in output
    assert state["blocks"][0]["intent"] == "graduation_progress"
    assert state["blocks"][0]["facts"]["completedCredits"] == 72
