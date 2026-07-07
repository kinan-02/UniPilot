"""Integration tests for Phase 16 monitor diagnostics."""

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
}

_OFF_SETTINGS = Settings(**{**_BASE_KWARGS, "AGENT_MONITOR_ENABLED": False})
_ON_SETTINGS = Settings(**{**_BASE_KWARGS, "AGENT_MONITOR_ENABLED": True, "AGENT_MONITOR_DRY_RUN": True})
_MISCONFIGURED_SETTINGS = Settings(**{**_BASE_KWARGS, "AGENT_MONITOR_ENABLED": True, "AGENT_MONITOR_DRY_RUN": False})


def _fake_plan(*, failing: bool = False) -> PlannerOutput:
    return PlannerOutput(
        status="completed",
        plan_id="plan-monitor-diag-1",
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


def _inject_fake_plan(monkeypatch, *, failing: bool = False) -> None:
    async def _fake_build_plan_with_diagnostics(**_kwargs):
        plan = _fake_plan(failing=failing)
        return plan, {"status": plan.status, "planId": plan.plan_id}

    monkeypatch.setattr("app.agent.orchestrator.build_plan_with_diagnostics", _fake_build_plan_with_diagnostics)


async def _seed_user(mongo_database) -> tuple[str, str]:
    fixtures = await seed_graduation_progress_fixtures(mongo_database)
    email = f"monitor-{uuid.uuid4().hex[:10]}@example.com"
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
    conversation = await create_agent_conversation(mongo_database, user_id=user_id, title="Monitor test")
    return user_id, str(conversation["id"])


async def _run_turn(mongo_database, *, user_id: str, conversation_id: str, settings: Settings):
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


async def test_monitor_flag_off_preserves_behavior(mongo_database, monkeypatch) -> None:
    _inject_fake_plan(monkeypatch)
    user_id, conversation_id = await _seed_user(mongo_database)

    events, run_doc = await _run_turn(
        mongo_database, user_id=user_id, conversation_id=conversation_id, settings=_OFF_SETTINGS
    )

    assert not any(event.type == "run.failed" for event in events)
    metadata = run_doc.get("retrievalMetadata") or {}
    assert "monitorDiagnostics" not in metadata


async def test_monitor_flag_on_attaches_monitor_diagnostics(mongo_database, monkeypatch) -> None:
    _inject_fake_plan(monkeypatch)
    user_id, conversation_id = await _seed_user(mongo_database)

    _, run_doc = await _run_turn(
        mongo_database, user_id=user_id, conversation_id=conversation_id, settings=_ON_SETTINGS
    )

    monitor = (run_doc.get("retrievalMetadata") or {}).get("monitorDiagnostics")
    assert monitor is not None
    assert "status" in monitor
    assert "decision" in monitor


async def test_monitor_flag_on_does_not_change_user_visible_response_or_sse_sequence(mongo_database, monkeypatch) -> None:
    _inject_fake_plan(monkeypatch)
    user_id_off, conversation_id_off = await _seed_user(mongo_database)
    events_off, _ = await _run_turn(
        mongo_database, user_id=user_id_off, conversation_id=conversation_id_off, settings=_OFF_SETTINGS
    )

    user_id_on, conversation_id_on = await _seed_user(mongo_database)
    events_on, _ = await _run_turn(
        mongo_database, user_id=user_id_on, conversation_id=conversation_id_on, settings=_ON_SETTINGS
    )

    assert [event.type for event in events_off] == [event.type for event in events_on]
    completed_off = next(event for event in events_off if event.type == "message.completed")
    completed_on = next(event for event in events_on if event.type == "message.completed")
    assert completed_off.text == completed_on.text


async def test_monitor_detects_failed_shadow_subtask_but_does_not_break_live_turn(mongo_database, monkeypatch) -> None:
    _inject_fake_plan(monkeypatch, failing=True)
    user_id, conversation_id = await _seed_user(mongo_database)

    events, run_doc = await _run_turn(
        mongo_database, user_id=user_id, conversation_id=conversation_id, settings=_ON_SETTINGS
    )

    assert run_doc is not None
    assert not any(event.type == "run.failed" for event in events)


async def test_monitor_detects_unsafe_diagnostic_payload(mongo_database, monkeypatch) -> None:
    _inject_fake_plan(monkeypatch)

    def _fake_validate_shadow_run(**kwargs):
        from app.agent.supervisor.validation_schemas import SupervisorValidationResult, ValidationIssue

        comparison = kwargs.get("comparison")
        return SupervisorValidationResult(
            status="failed",
            safe_to_promote=False,
            comparison=comparison,
            issues=[ValidationIssue(code="proposed_action_detected", severity="error", message="unsafe")],
            warnings=[],
        )

    monkeypatch.setattr("app.agent.supervisor.post_context_runner.validate_shadow_run", _fake_validate_shadow_run)

    user_id, conversation_id = await _seed_user(mongo_database)
    _, run_doc = await _run_turn(
        mongo_database, user_id=user_id, conversation_id=conversation_id, settings=_ON_SETTINGS
    )

    monitor = (run_doc.get("retrievalMetadata") or {}).get("monitorDiagnostics")
    assert monitor is not None
    assert monitor.get("status") in {"diverged", "failed", "passed_with_warnings"}


async def test_monitor_diagnostics_are_compact(mongo_database, monkeypatch) -> None:
    _inject_fake_plan(monkeypatch)
    user_id, conversation_id = await _seed_user(mongo_database)

    _, run_doc = await _run_turn(
        mongo_database, user_id=user_id, conversation_id=conversation_id, settings=_ON_SETTINGS
    )

    metadata_text = str((run_doc.get("retrievalMetadata") or {}).get("monitorDiagnostics") or {})
    assert "compiled_context" not in metadata_text
    assert "planner_output" not in metadata_text


async def test_dry_run_false_misconfiguration_remains_diagnostic_only(mongo_database, monkeypatch) -> None:
    _inject_fake_plan(monkeypatch)
    user_id, conversation_id = await _seed_user(mongo_database)

    events, run_doc = await _run_turn(
        mongo_database, user_id=user_id, conversation_id=conversation_id, settings=_MISCONFIGURED_SETTINGS
    )

    assert not any(event.type == "run.failed" for event in events)
    monitor = (run_doc.get("retrievalMetadata") or {}).get("monitorDiagnostics")
    assert monitor is not None
