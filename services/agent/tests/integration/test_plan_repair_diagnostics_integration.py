"""Integration tests for Phase 19 plan repair diagnostics."""

from __future__ import annotations

import uuid

import pytest
from bson import ObjectId

from app.agent.orchestrator import run_agent_turn
from app.agent.planner.schemas import PlannerOutput, PlannerSubtask
from app.config import Settings
from app.repositories.agent_conversation_repository import create_agent_conversation
from app.repositories.student_profile_repository import create_student_profile
from app.repositories.user_repository import create_user
from tests.fixtures.graduation_progress_fixtures import seed_graduation_progress_fixtures

_MESSAGE = "What am I missing to graduate?"

_BASE_KWARGS = {
    "OPENAI_API_KEY": None,
    "AGENT_PLANNER_ENABLED": True,
    "AGENT_SUPERVISOR_ENABLED": True,
    "AGENT_SUPERVISOR_POST_CONTEXT_COMPARE_ENABLED": True,
    "AGENT_MONITOR_ENABLED": True,
    "AGENT_MONITOR_DRY_RUN": True,
}

_OFF_SETTINGS = Settings(**{**_BASE_KWARGS, "AGENT_PLAN_REPAIR_ENABLED": False})
_ON_SETTINGS = Settings(
    **{
        **_BASE_KWARGS,
        "AGENT_PLAN_REPAIR_ENABLED": True,
        "AGENT_PLAN_REPAIR_DRY_RUN": True,
        "AGENT_PLAN_REPAIR_USE_LLM": False,
    }
)
_EFFECTIVE_CONTEXT_SETTINGS = Settings(
    **{
        **_BASE_KWARGS,
        "AGENT_PLAN_REPAIR_ENABLED": True,
        "AGENT_PLAN_REPAIR_DRY_RUN": True,
        "AGENT_PLAN_REPAIR_USE_LLM": False,
        "AGENT_CLARIFICATION_ENABLED": True,
        "AGENT_CLARIFICATION_STATE_ENABLED": True,
        "AGENT_CLARIFICATION_EFFECTIVE_CONTEXT_ENABLED": True,
    }
)


def _fake_plan(*, failing: bool = False) -> PlannerOutput:
    return PlannerOutput(
        status="completed",
        plan_id="plan-repair-diag-1",
        user_goal=_MESSAGE,
        execution_mode="single_capability",
        recommended_autonomy_level=3,
        primary_intent="graduation_progress_check",
        subtasks=[
            PlannerSubtask(
                id="ask_specialist",
                title="Ask graduation specialist",
                kind="analyze",
                capability_name="graduation_progress_agent",
                objective="Determine remaining requirements toward graduation.",
                depends_on=[],
                required_context_sections=["user_message"],
            )
        ],
        assumptions=["Student wants graduation guidance"],
        decision_summary="test",
        confidence=0.85,
    )


@pytest.fixture(autouse=True)
def _mock_student_user_context(monkeypatch):
    from app.retrieval import mongodb_user_retriever

    async def _fake_fetch_student_user_context(*, user_id: str, settings=None):
        return {"completed_courses": [], "data_quality": {"warnings": [], "ok": True}}

    monkeypatch.setattr(mongodb_user_retriever, "fetch_student_user_context", _fake_fetch_student_user_context)


@pytest.fixture(autouse=True)
def _mock_graduation_audit(monkeypatch):
    from app.services import graduation_audit_client

    async def _fake_graduation_audit_coro():
        return {
            "status": "ok",
            "progress": {"creditsRemaining": 40.0, "requirementProgress": []},
            "errors": [],
            "warnings": [],
            "assumptions": [],
            "blockers": [],
            "graduation_status": "not_ready",
            "can_graduate": False,
        }

    monkeypatch.setattr(graduation_audit_client, "fetch_graduation_audit", lambda **_: _fake_graduation_audit_coro())


def _inject_fake_plan(monkeypatch) -> None:
    async def _fake_build_plan_with_diagnostics(**_kwargs):
        plan = _fake_plan()
        return plan, {"status": plan.status, "planId": plan.plan_id}

    monkeypatch.setattr("app.agent.orchestrator.build_plan_with_diagnostics", _fake_build_plan_with_diagnostics)


def _inject_monitor_repair_request(monkeypatch) -> None:
    from app.agent.monitoring.diagnostics import build_monitor_metadata
    from app.agent.monitoring.schemas import DivergenceSignal, MonitorOutput, ReplanDecision

    def _fake_monitor_plan_execution(_input, *, enabled=True, dry_run=True):
        output = MonitorOutput(
            status="diverged",
            plan_id="plan-repair-diag-1",
            signals=[
                DivergenceSignal(
                    kind="assumption_violation",
                    severity="warning",
                    message="Assumption violated",
                    related_subtask_ids=["ask_specialist"],
                )
            ],
            decision=ReplanDecision(
                action="request_plan_repair",
                reason="assumption_violation_detected",
                confidence=0.8,
                divergence_kinds=["assumption_violation"],
                affected_subtasks=["ask_specialist"],
            ),
            checked_assumption_count=1,
            checked_expectation_count=1,
        )
        return output

    monkeypatch.setattr(
        "app.agent.monitoring.monitor.monitor_plan_execution",
        _fake_monitor_plan_execution,
    )


async def _seed_user(mongo_database) -> tuple[str, str]:
    fixtures = await seed_graduation_progress_fixtures(mongo_database)
    email = f"repair-{uuid.uuid4().hex[:10]}@example.com"
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
    conversation = await create_agent_conversation(mongo_database, user_id=user_id, title="repair test")
    return user_id, str(conversation["id"])


async def _run_turn(mongo_database, *, settings: Settings) -> dict:
    user_id, conversation_id = await _seed_user(mongo_database)
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
    assert run_doc is not None
    return {
        "events": [event.model_dump() if hasattr(event, "model_dump") else event for event in events],
        "retrieval_metadata": run_doc.get("retrievalMetadata") or {},
        "run": run_doc,
    }


@pytest.mark.asyncio
async def test_plan_repair_flags_off_preserves_behavior(mongo_database, monkeypatch) -> None:
    _inject_fake_plan(monkeypatch)
    result = await _run_turn(mongo_database, settings=_OFF_SETTINGS)
    assert "planRepairDiagnostics" not in result["retrieval_metadata"]


@pytest.mark.asyncio
async def test_plan_repair_enabled_dry_run_attaches_diagnostics(mongo_database, monkeypatch) -> None:
    _inject_fake_plan(monkeypatch)
    _inject_monitor_repair_request(monkeypatch)
    result = await _run_turn(mongo_database, settings=_ON_SETTINGS)
    diagnostics = result["retrieval_metadata"].get("planRepairDiagnostics")
    assert diagnostics is not None
    assert diagnostics.get("safeToUse") is False


@pytest.mark.asyncio
async def test_monitor_request_plan_repair_produces_repair_diagnostic(mongo_database, monkeypatch) -> None:
    _inject_fake_plan(monkeypatch)
    _inject_monitor_repair_request(monkeypatch)
    result = await _run_turn(mongo_database, settings=_ON_SETTINGS)
    diagnostics = result["retrieval_metadata"]["planRepairDiagnostics"]
    assert diagnostics["deltaCount"] >= 1


@pytest.mark.asyncio
async def test_repaired_plan_does_not_affect_selected_response(mongo_database, monkeypatch) -> None:
    _inject_fake_plan(monkeypatch)
    _inject_monitor_repair_request(monkeypatch)
    result = await _run_turn(mongo_database, settings=_ON_SETTINGS)
    completed = [event for event in result["events"] if event.get("type") == "message.completed"]
    assert completed
    assert completed[0].get("text")


@pytest.mark.asyncio
async def test_no_action_proposals_from_repair_path(mongo_database, monkeypatch) -> None:
    _inject_fake_plan(monkeypatch)
    _inject_monitor_repair_request(monkeypatch)
    result = await _run_turn(mongo_database, settings=_ON_SETTINGS)
    proposed = [event for event in result["events"] if event.get("type") == "action.proposed"]
    assert proposed == []


@pytest.mark.asyncio
async def test_effective_clarification_context_flag_attaches_compact_context_safely(
    mongo_database, monkeypatch
) -> None:
    _inject_fake_plan(monkeypatch)

    async def _fake_turn_start(*_args, **_kwargs):
        from app.agent.clarification.turn_handler import TurnStartClarificationResult

        return TurnStartClarificationResult(
            effective_user_message=_MESSAGE,
            confirmed_clarification_answers=[{"value": "mandatory first", "provenance": "confirmed"}],
            clarification_assumptions_created=[{"kind": "user_preference", "provenance": "confirmed"}],
            original_user_message_for_resume=_MESSAGE,
            skip_user_facing_offer=True,
        )

    monkeypatch.setattr(
        "app.agent.clarification.turn_handler.process_turn_start_clarification",
        _fake_turn_start,
    )
    result = await _run_turn(mongo_database, settings=_EFFECTIVE_CONTEXT_SETTINGS)
    metadata = result["retrieval_metadata"]
    assert metadata.get("effectiveClarificationContext") is not None
    assert metadata["effectiveClarificationContext"]["confirmedClarifications"]
