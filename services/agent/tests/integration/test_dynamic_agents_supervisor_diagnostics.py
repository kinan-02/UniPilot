"""Integration tests for Phase 15 dynamic agents in supervisor diagnostics."""

from __future__ import annotations

import uuid
from typing import Any
from unittest.mock import patch

import pytest
from bson import ObjectId

from app.agent.orchestrator import run_agent_turn
from app.agent.planner.schemas import PlannerOutput, PlannerSubtask
from app.agent.reasoning.schemas import ReasoningBlockInput, ReasoningBlockOutput
from app.config import Settings
from app.repositories.agent_conversation_repository import create_agent_conversation
from app.repositories.student_profile_repository import create_student_profile
from app.repositories.user_repository import create_user
from tests.fixtures.graduation_progress_fixtures import seed_graduation_progress_fixtures

_MESSAGE = "Compare my two semester plans"

_BASE_KWARGS = {
    "OPENAI_API_KEY": None,
    "AGENT_PLANNER_ENABLED": True,
    "AGENT_SUPERVISOR_ENABLED": True,
    "AGENT_SUPERVISOR_POST_CONTEXT_COMPARE_ENABLED": True,
}

_OFF_SETTINGS = Settings(**{**_BASE_KWARGS, "AGENT_DYNAMIC_AGENTS_ENABLED": False})
_ON_SETTINGS = Settings(**{**_BASE_KWARGS, "AGENT_DYNAMIC_AGENTS_ENABLED": True, "AGENT_DYNAMIC_AGENTS_DRY_RUN": True})


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


def _fake_dynamic_plan() -> PlannerOutput:
    return PlannerOutput(
        status="completed",
        plan_id="plan-dynamic-diag-1",
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
                dynamic_agent_spec=_dynamic_agent_spec(),
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


def _inject_fake_plan(monkeypatch) -> None:
    async def _fake_build_plan_with_diagnostics(**_kwargs):
        plan = _fake_dynamic_plan()
        return plan, {"status": plan.status, "planId": plan.plan_id}

    monkeypatch.setattr("app.agent.orchestrator.build_plan_with_diagnostics", _fake_build_plan_with_diagnostics)


async def _seed_user(mongo_database) -> tuple[str, str]:
    fixtures = await seed_graduation_progress_fixtures(mongo_database)
    email = f"dynamic-agent-{uuid.uuid4().hex[:10]}@example.com"
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
    conversation = await create_agent_conversation(mongo_database, user_id=user_id, title="Dynamic agent test")
    return user_id, str(conversation["id"])


async def _run_turn(mongo_database, *, user_id: str, conversation_id: str, settings: Settings, fake_block: FakeReasoningBlock):
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


async def test_dynamic_agents_flag_off_preserves_behavior(mongo_database, monkeypatch) -> None:
    _inject_fake_plan(monkeypatch)
    user_id, conversation_id = await _seed_user(mongo_database)
    fake_block = FakeReasoningBlock()

    events, run_doc = await _run_turn(
        mongo_database,
        user_id=user_id,
        conversation_id=conversation_id,
        settings=_OFF_SETTINGS,
        fake_block=fake_block,
    )

    assert not any(event.type == "run.failed" for event in events)
    metadata = run_doc.get("retrievalMetadata") or {}
    assert "dynamicAgents" not in metadata
    assert fake_block.calls == []


async def test_dynamic_agent_can_be_built_and_run_in_shadow_diagnostic_path(mongo_database, monkeypatch) -> None:
    _inject_fake_plan(monkeypatch)
    user_id, conversation_id = await _seed_user(mongo_database)
    fake_block = FakeReasoningBlock()

    events, run_doc = await _run_turn(
        mongo_database,
        user_id=user_id,
        conversation_id=conversation_id,
        settings=_ON_SETTINGS,
        fake_block=fake_block,
    )

    assert not any(event.type == "run.failed" for event in events)
    metadata = run_doc.get("retrievalMetadata") or {}
    dynamic = metadata.get("dynamicAgents")
    assert dynamic is not None
    assert dynamic.get("agentCount", 0) >= 1
    assert fake_block.calls


async def test_dynamic_agent_diagnostics_are_compact(mongo_database, monkeypatch) -> None:
    _inject_fake_plan(monkeypatch)
    user_id, conversation_id = await _seed_user(mongo_database)

    _, run_doc = await _run_turn(
        mongo_database,
        user_id=user_id,
        conversation_id=conversation_id,
        settings=_ON_SETTINGS,
        fake_block=FakeReasoningBlock(),
    )

    metadata_text = str(run_doc.get("retrievalMetadata") or {})
    assert "compiled_context" not in metadata_text
    assert "deterministic_observations" not in metadata_text


async def test_dynamic_agent_output_does_not_affect_final_answer(mongo_database, monkeypatch) -> None:
    _inject_fake_plan(monkeypatch)
    user_id_off, conversation_id_off = await _seed_user(mongo_database)
    events_off, _ = await _run_turn(
        mongo_database,
        user_id=user_id_off,
        conversation_id=conversation_id_off,
        settings=_OFF_SETTINGS,
        fake_block=FakeReasoningBlock(),
    )

    user_id_on, conversation_id_on = await _seed_user(mongo_database)
    events_on, _ = await _run_turn(
        mongo_database,
        user_id=user_id_on,
        conversation_id=conversation_id_on,
        settings=_ON_SETTINGS,
        fake_block=FakeReasoningBlock(),
    )

    completed_off = next(event for event in events_off if event.type == "message.completed")
    completed_on = next(event for event in events_on if event.type == "message.completed")
    assert completed_off.text == completed_on.text


async def test_dynamic_agent_cannot_create_proposed_actions(mongo_database, monkeypatch) -> None:
    _inject_fake_plan(monkeypatch)
    user_id, conversation_id = await _seed_user(mongo_database)

    events, run_doc = await _run_turn(
        mongo_database,
        user_id=user_id,
        conversation_id=conversation_id,
        settings=_ON_SETTINGS,
        fake_block=FakeReasoningBlock(),
    )

    metadata_text = str(run_doc.get("retrievalMetadata") or {})
    assert "proposed_actions" not in metadata_text
    actions = [event.action for event in events if event.type == "action.proposed"]
    assert actions == []


async def test_dynamic_agent_failure_does_not_break_live_turn(mongo_database, monkeypatch) -> None:
    _inject_fake_plan(monkeypatch)
    user_id, conversation_id = await _seed_user(mongo_database)

    class FailingBlock(FakeReasoningBlock):
        async def run(self, input: ReasoningBlockInput) -> ReasoningBlockOutput:
            raise RuntimeError("boom")

    events, run_doc = await _run_turn(
        mongo_database,
        user_id=user_id,
        conversation_id=conversation_id,
        settings=_ON_SETTINGS,
        fake_block=FailingBlock(),
    )

    assert run_doc is not None
    assert not any(event.type == "run.failed" for event in events)


async def test_no_sse_event_sequence_changes_without_injected_plan(mongo_database, monkeypatch) -> None:
    user_id_off, conversation_id_off = await _seed_user(mongo_database)
    events_off, _ = await _run_turn(
        mongo_database,
        user_id=user_id_off,
        conversation_id=conversation_id_off,
        settings=_OFF_SETTINGS,
        fake_block=FakeReasoningBlock(),
    )

    user_id_on, conversation_id_on = await _seed_user(mongo_database)
    events_on, _ = await _run_turn(
        mongo_database,
        user_id=user_id_on,
        conversation_id=conversation_id_on,
        settings=_ON_SETTINGS,
        fake_block=FakeReasoningBlock(),
    )

    assert [event.type for event in events_off] == [event.type for event in events_on]
