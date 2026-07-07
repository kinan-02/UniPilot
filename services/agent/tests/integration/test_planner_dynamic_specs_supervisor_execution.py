"""Integration tests for Phase 20 planner dynamic specs + supervisor shadow execution."""

from __future__ import annotations

import uuid
from typing import Any
from unittest.mock import patch

import pytest
from bson import ObjectId

from app.agent.orchestrator import run_agent_turn
from app.agent.planner.dynamic_spec_policy import normalize_planner_dynamic_specs
from app.agent.planner.schemas import PlannerOutput, PlannerSubtask
from app.agent.reasoning.schemas import ReasoningBlockInput, ReasoningBlockOutput
from app.config import Settings
from app.repositories.agent_conversation_repository import create_agent_conversation
from app.repositories.student_profile_repository import create_student_profile
from app.repositories.user_repository import create_user
from tests.fixtures.graduation_progress_fixtures import seed_graduation_progress_fixtures

_MESSAGE = "Compare my two semester plans"

_BASE = {
    "OPENAI_API_KEY": None,
    "AGENT_PLANNER_ENABLED": True,
    "AGENT_SUPERVISOR_ENABLED": True,
    "AGENT_SUPERVISOR_POST_CONTEXT_COMPARE_ENABLED": True,
}

_OFF = Settings(**{**_BASE, "AGENT_PLANNER_DYNAMIC_SPECS_ENABLED": False, "AGENT_DYNAMIC_AGENTS_ENABLED": False})
_ON = Settings(
    **{
        **_BASE,
        "AGENT_PLANNER_DYNAMIC_SPECS_ENABLED": True,
        "AGENT_PLANNER_DYNAMIC_SPECS_DRY_RUN": True,
        "AGENT_DYNAMIC_AGENTS_ENABLED": True,
        "AGENT_DYNAMIC_AGENTS_DRY_RUN": True,
    }
)
_VALIDATE_ONLY = Settings(
    **{
        **_BASE,
        "AGENT_PLANNER_DYNAMIC_SPECS_ENABLED": True,
        "AGENT_DYNAMIC_AGENTS_ENABLED": False,
    }
)


class FakeReasoningBlock:
    def __init__(self) -> None:
        self.calls: list[ReasoningBlockInput] = []

    async def run(self, input: ReasoningBlockInput) -> ReasoningBlockOutput:
        self.calls.append(input)
        return ReasoningBlockOutput(
            status="completed",
            result={
                "status": "completed",
                "result": {"comparison": "plan_a_is_lighter"},
                "decision_summary": "Plan A is lighter overall.",
                "key_findings": ["Plan A has fewer credits"],
                "missing_context": [],
                "warnings": [],
                "validation_notes": [],
                "sources": [],
                "confidence": 0.82,
            },
            tool_requests=[],
            decision_summary="Plan A is lighter overall.",
            confidence=0.82,
            schema_valid=True,
            iterations_used=2,
            repair_attempts_used=0,
        )


def _dynamic_agent_spec() -> dict[str, Any]:
    return {
        "spec_id": "spec_compare_001",
        "agent_name": "semester_plan_comparison_agent",
        "role": "comparison analyst",
        "objective": "Compare two semester plans",
        "reasoning_pattern": "compare_and_synthesize",
        "expected_output_schema_name": "dynamic_agent_output_v1",
        "shadow_only": True,
    }


def _invalid_spec() -> dict[str, Any]:
    return {
        **_dynamic_agent_spec(),
        "allowed_observations": ["not_a_real_observation"],
    }


def _fake_dynamic_plan(*, spec: dict[str, Any] | None = None) -> PlannerOutput:
    return PlannerOutput(
        status="completed",
        plan_id="plan-dynamic-spec-1",
        user_goal=_MESSAGE,
        execution_mode="single_capability",
        recommended_autonomy_level=4,
        primary_intent="semester_planning",
        subtasks=[
            PlannerSubtask(
                id="run_dynamic_agent",
                title="Run comparison dynamic agent",
                kind="analyze",
                capability_name="dynamic_agent",
                objective="Compare two semester plans",
                depends_on=[],
                required_context_sections=["user_message"],
                dynamic_agent_spec=spec or _dynamic_agent_spec(),
            )
        ],
        decision_summary="test",
        confidence=0.85,
    )


@pytest.fixture(autouse=True)
def _mock_student_user_context(monkeypatch):
    from app.retrieval import mongodb_user_retriever

    async def _fake_fetch_student_user_context(*, user_id: str, settings=None):
        return {"completed_courses": [], "data_quality": {"warnings": [], "ok": True}}

    monkeypatch.setattr(mongodb_user_retriever, "fetch_student_user_context", _fake_fetch_student_user_context)


def _inject_fake_plan(monkeypatch, *, spec: dict[str, Any] | None = None) -> None:
    async def _fake_build_plan_with_diagnostics(**kwargs):
        settings = kwargs.get("settings") or _ON
        plan = _fake_dynamic_plan(spec=spec)
        normalized, diagnostics = normalize_planner_dynamic_specs(
            planner_output=plan,
            settings=settings,
        )
        normalized = normalized.model_copy(update={"dynamic_spec_diagnostics": diagnostics})
        summary: dict[str, Any] = {"status": normalized.status, "planId": normalized.plan_id}
        if settings.is_agent_planner_dynamic_specs_enabled() and diagnostics.get("specsGenerated"):
            summary["plannerDynamicAgents"] = {
                "status": diagnostics.get("status"),
                "specsGenerated": diagnostics.get("specsGenerated"),
                "specsValidated": diagnostics.get("specsValidated"),
                "specsRejected": diagnostics.get("specsRejected"),
                "agents": diagnostics.get("agents"),
            }
        return normalized, summary

    monkeypatch.setattr("app.agent.orchestrator.build_plan_with_diagnostics", _fake_build_plan_with_diagnostics)


async def _seed_user(mongo_database) -> tuple[str, str]:
    fixtures = await seed_graduation_progress_fixtures(mongo_database)
    email = f"planner-dynamic-{uuid.uuid4().hex[:10]}@example.com"
    user = await create_user(mongo_database, email=email, password_hash="hashed")
    user_id = str(user["_id"])
    await create_student_profile(
        mongo_database,
        user_id,
        {
            "institutionId": "technion",
            "programType": "BSc",
            "degreeId": fixtures["programId"],
            "catalogYear": 2025,
            "currentSemesterCode": "2025-1",
            "academicPath": {"trackSlug": "track-data-information-engineering"},
        },
    )
    conversation = await create_agent_conversation(mongo_database, user_id=user_id, title="Planner dynamic spec test")
    return user_id, str(conversation["id"])


async def _run_turn(mongo_database, *, settings: Settings, fake_block: FakeReasoningBlock):
    user_id, conversation_id = await _seed_user(mongo_database)
    with patch("app.agent.dynamic_agents.runtime.ReasoningBlock", return_value=fake_block):
        events = [
            event
            async for event in run_agent_turn(
                mongo_database,
                user_id=user_id,
                conversation_id=conversation_id,
                user_message=_MESSAGE,
                trigger_message_id=str(ObjectId()),
                settings=settings,
            )
        ]
    run_doc = await mongo_database[settings.agent_runs_collection].find_one(
        {"userId": ObjectId(user_id)}, sort=[("startedAt", -1)]
    )
    return events, run_doc


@pytest.mark.asyncio
async def test_flags_off_preserves_behavior(mongo_database, monkeypatch) -> None:
    _inject_fake_plan(monkeypatch)
    events, run_doc = await _run_turn(mongo_database, settings=_OFF, fake_block=FakeReasoningBlock())
    metadata = run_doc.get("retrievalMetadata") or {}
    assert "plannerDynamicAgents" not in metadata.get("plannerDiagnostics", {})
    assert not any(event.type == "run.failed" for event in events)


@pytest.mark.asyncio
async def test_supervisor_executes_validated_spec_in_shadow(mongo_database, monkeypatch) -> None:
    _inject_fake_plan(monkeypatch)
    fake_block = FakeReasoningBlock()
    events, run_doc = await _run_turn(mongo_database, settings=_ON, fake_block=fake_block)
    metadata = run_doc.get("retrievalMetadata") or {}
    assert metadata.get("dynamicAgents") is not None
    assert metadata.get("plannerDiagnostics", {}).get("plannerDynamicAgents") is not None
    assert fake_block.calls
    assert not any(event.type == "run.failed" for event in events)


@pytest.mark.asyncio
async def test_dynamic_agent_output_does_not_affect_final_response(mongo_database, monkeypatch) -> None:
    _inject_fake_plan(monkeypatch)
    events_off, _ = await _run_turn(mongo_database, settings=_OFF, fake_block=FakeReasoningBlock())
    events_on, _ = await _run_turn(mongo_database, settings=_ON, fake_block=FakeReasoningBlock())
    off = next(event for event in events_off if event.type == "message.completed")
    on = next(event for event in events_on if event.type == "message.completed")
    assert off.text == on.text


@pytest.mark.asyncio
async def test_invalid_planner_spec_rejected_and_not_executed(mongo_database, monkeypatch) -> None:
    _inject_fake_plan(monkeypatch, spec=_invalid_spec())
    fake_block = FakeReasoningBlock()
    _, run_doc = await _run_turn(mongo_database, settings=_ON, fake_block=fake_block)
    metadata = run_doc.get("retrievalMetadata") or {}
    planner_dynamic = metadata.get("plannerDiagnostics", {}).get("plannerDynamicAgents") or {}
    assert planner_dynamic.get("specsRejected", 0) >= 1
    assert fake_block.calls == []


@pytest.mark.asyncio
async def test_dynamic_agents_disabled_validates_but_does_not_execute(mongo_database, monkeypatch) -> None:
    _inject_fake_plan(monkeypatch)
    fake_block = FakeReasoningBlock()
    _, run_doc = await _run_turn(mongo_database, settings=_VALIDATE_ONLY, fake_block=fake_block)
    metadata = run_doc.get("retrievalMetadata") or {}
    assert metadata.get("plannerDiagnostics", {}).get("plannerDynamicAgents") is not None
    assert "dynamicAgents" not in metadata
    assert fake_block.calls == []


@pytest.mark.asyncio
async def test_no_action_proposals(mongo_database, monkeypatch) -> None:
    _inject_fake_plan(monkeypatch)
    events, run_doc = await _run_turn(mongo_database, settings=_ON, fake_block=FakeReasoningBlock())
    assert "proposed_actions" not in str(run_doc.get("retrievalMetadata") or {})
    assert [event for event in events if event.type == "action.proposed"] == []
