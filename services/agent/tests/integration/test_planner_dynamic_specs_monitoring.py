"""Integration tests for Phase 20 dynamic-agent monitor diagnostics."""

from __future__ import annotations

import uuid
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

_SETTINGS = Settings(
    OPENAI_API_KEY=None,
    AGENT_PLANNER_ENABLED=True,
    AGENT_SUPERVISOR_ENABLED=True,
    AGENT_SUPERVISOR_POST_CONTEXT_COMPARE_ENABLED=True,
    AGENT_MONITOR_ENABLED=True,
    AGENT_MONITOR_DRY_RUN=True,
    AGENT_PLANNER_DYNAMIC_SPECS_ENABLED=True,
    AGENT_DYNAMIC_AGENTS_ENABLED=True,
    AGENT_DYNAMIC_AGENTS_DRY_RUN=True,
)


class FakeReasoningBlock:
    async def run(self, input: ReasoningBlockInput) -> ReasoningBlockOutput:
        return ReasoningBlockOutput(
            status="completed",
            result={
                "status": "completed",
                "result": {"comparison": "ok"},
                "decision_summary": "Compared plans.",
                "confidence": 0.8,
            },
            tool_requests=[],
            decision_summary="Compared plans.",
            confidence=0.8,
            schema_valid=True,
            iterations_used=2,
            repair_attempts_used=0,
        )


class FailingDynamicBlock(FakeReasoningBlock):
    async def run(self, input: ReasoningBlockInput) -> ReasoningBlockOutput:
        raise RuntimeError("dynamic agent failed")


def _plan() -> PlannerOutput:
    return PlannerOutput(
        status="completed",
        plan_id="plan-monitor-dynamic",
        user_goal=_MESSAGE,
        execution_mode="single_capability",
        recommended_autonomy_level=4,
        primary_intent="semester_planning",
        subtasks=[
            PlannerSubtask(
                id="run_dynamic_agent",
                title="Run dynamic agent",
                kind="analyze",
                capability_name="dynamic_agent",
                objective="Compare plans",
                dynamic_agent_spec={
                    "spec_id": "spec_monitor_001",
                    "agent_name": "semester_plan_comparison_agent",
                    "role": "comparison analyst",
                    "objective": "Compare plans",
                    "reasoning_pattern": "single_pass",
                    "expected_output_schema_name": "dynamic_agent_output_v1",
                    "shadow_only": True,
                },
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


def _inject_plan(monkeypatch) -> None:
    async def _fake_build_plan_with_diagnostics(**_kwargs):
        plan = _plan()
        normalized, diagnostics = normalize_planner_dynamic_specs(planner_output=plan, settings=_SETTINGS)
        normalized = normalized.model_copy(update={"dynamic_spec_diagnostics": diagnostics})
        return normalized, {"status": normalized.status, "planId": normalized.plan_id}

    monkeypatch.setattr("app.agent.orchestrator.build_plan_with_diagnostics", _fake_build_plan_with_diagnostics)


async def _seed_user(mongo_database) -> tuple[str, str]:
    fixtures = await seed_graduation_progress_fixtures(mongo_database)
    email = f"monitor-dynamic-{uuid.uuid4().hex[:10]}@example.com"
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
    conversation = await create_agent_conversation(mongo_database, user_id=user_id, title="Monitor dynamic")
    return user_id, str(conversation["id"])


async def _run_turn(mongo_database, *, fake_block) -> tuple[list, dict]:
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
                settings=_SETTINGS,
            )
        ]
    run_doc = await mongo_database[_SETTINGS.agent_runs_collection].find_one(
        {"userId": ObjectId(user_id)}, sort=[("startedAt", -1)]
    )
    return events, run_doc


@pytest.mark.asyncio
async def test_monitor_sees_dynamic_agent_status_metadata(mongo_database, monkeypatch) -> None:
    _inject_plan(monkeypatch)
    _, run_doc = await _run_turn(mongo_database, fake_block=FakeReasoningBlock())
    monitor = (run_doc.get("retrievalMetadata") or {}).get("monitorDiagnostics")
    assert monitor is not None
    assert "status" in monitor


@pytest.mark.asyncio
async def test_failed_dynamic_agent_subtask_creates_diagnostic_signal(mongo_database, monkeypatch) -> None:
    _inject_plan(monkeypatch)
    _, run_doc = await _run_turn(mongo_database, fake_block=FailingDynamicBlock())
    monitor = (run_doc.get("retrievalMetadata") or {}).get("monitorDiagnostics")
    assert monitor is not None


@pytest.mark.asyncio
async def test_monitor_diagnostics_remain_compact(mongo_database, monkeypatch) -> None:
    _inject_plan(monkeypatch)
    _, run_doc = await _run_turn(mongo_database, fake_block=FakeReasoningBlock())
    metadata_text = str(run_doc.get("retrievalMetadata") or {})
    assert "compiled_context" not in metadata_text
    assert "dynamic_agent_spec" not in metadata_text


@pytest.mark.asyncio
async def test_final_response_unchanged_with_monitor_on(mongo_database, monkeypatch) -> None:
    _inject_plan(monkeypatch)
    events, _ = await _run_turn(mongo_database, fake_block=FakeReasoningBlock())
    assert any(event.type == "message.completed" for event in events)
