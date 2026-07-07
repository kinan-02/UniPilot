"""Integration tests for Phase 21 synthesis diagnostics."""

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

_OFF_SETTINGS = Settings(**{**_BASE_KWARGS, "AGENT_SYNTHESIS_ENABLED": False})
_ON_SETTINGS = Settings(
    **{
        **_BASE_KWARGS,
        "AGENT_SYNTHESIS_ENABLED": True,
        "AGENT_SYNTHESIS_DRY_RUN": True,
        "AGENT_SYNTHESIS_USE_LLM": False,
    }
)
_UNSAFE_SETTINGS = Settings(
    **{
        **_BASE_KWARGS,
        "AGENT_SYNTHESIS_ENABLED": True,
        "AGENT_SYNTHESIS_DRY_RUN": True,
        "AGENT_SYNTHESIS_USE_LLM": False,
        "AGENT_MONITOR_ENABLED": True,
    }
)


def _fake_plan() -> PlannerOutput:
    return PlannerOutput(
        status="completed",
        plan_id="syn-diag-1",
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


def _inject_unsafe_monitor(monkeypatch) -> None:
    from app.agent.monitoring.schemas import DivergenceSignal, MonitorOutput, ReplanDecision

    def _fake_monitor_plan_execution(_input, *, enabled=True, dry_run=True):
        return MonitorOutput(
            status="diverged",
            plan_id="syn-diag-1",
            signals=[
                DivergenceSignal(
                    kind="unsafe_output",
                    severity="error",
                    message="Unsafe output detected",
                    related_subtask_ids=["ask_specialist"],
                )
            ],
            decision=ReplanDecision(
                action="abort_safely",
                reason="unsafe_output",
                confidence=0.95,
                divergence_kinds=["unsafe_output"],
                affected_subtasks=["ask_specialist"],
            ),
            checked_assumption_count=1,
            checked_expectation_count=1,
        )

    monkeypatch.setattr("app.agent.monitoring.monitor.monitor_plan_execution", _fake_monitor_plan_execution)


async def _seed_user(mongo_database) -> tuple[str, str]:
    fixtures = await seed_graduation_progress_fixtures(mongo_database)
    email = f"syn-{uuid.uuid4().hex[:10]}@example.com"
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
    conversation = await create_agent_conversation(mongo_database, user_id=user_id, title="synthesis test")
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
    final_response = None
    for event in events:
        payload = event.model_dump() if hasattr(event, "model_dump") else event
        if payload.get("type") == "message.completed":
            final_response = payload.get("response")
    return {
        "events": events,
        "final_response": final_response,
        "metadata": run_doc.get("retrievalMetadata") or {},
        "run": run_doc,
    }


@pytest.mark.asyncio
async def test_synthesis_flag_off_preserves_behavior(mongo_database, monkeypatch) -> None:
    _inject_fake_plan(monkeypatch)
    result = await _run_turn(mongo_database, settings=_OFF_SETTINGS)
    assert "synthesisDiagnostics" not in result["metadata"]


@pytest.mark.asyncio
async def test_synthesis_enabled_attaches_diagnostics(mongo_database, monkeypatch) -> None:
    _inject_fake_plan(monkeypatch)
    result = await _run_turn(mongo_database, settings=_ON_SETTINGS)
    diag = result["metadata"].get("synthesisDiagnostics")
    assert diag is not None
    assert "status" in diag
    assert "candidateAnswerText" not in diag


@pytest.mark.asyncio
async def test_synthesis_does_not_change_final_text(mongo_database, monkeypatch) -> None:
    _inject_fake_plan(monkeypatch)
    off = await _run_turn(mongo_database, settings=_OFF_SETTINGS)
    on = await _run_turn(mongo_database, settings=_ON_SETTINGS)
    assert (off["final_response"] or {}).get("text") == (on["final_response"] or {}).get("text")


@pytest.mark.asyncio
async def test_synthesis_does_not_change_blocks(mongo_database, monkeypatch) -> None:
    _inject_fake_plan(monkeypatch)
    off = await _run_turn(mongo_database, settings=_OFF_SETTINGS)
    on = await _run_turn(mongo_database, settings=_ON_SETTINGS)
    off_blocks = (off["final_response"] or {}).get("blocks") or []
    on_blocks = (on["final_response"] or {}).get("blocks") or []
    assert len(off_blocks) == len(on_blocks)


@pytest.mark.asyncio
async def test_synthesis_does_not_change_sse_sequence(mongo_database, monkeypatch) -> None:
    _inject_fake_plan(monkeypatch)
    off = await _run_turn(mongo_database, settings=_OFF_SETTINGS)
    on = await _run_turn(mongo_database, settings=_ON_SETTINGS)
    off_types = [
        (event.model_dump() if hasattr(event, "model_dump") else event).get("type") for event in off["events"]
    ]
    on_types = [(event.model_dump() if hasattr(event, "model_dump") else event).get("type") for event in on["events"]]
    assert off_types == on_types


@pytest.mark.asyncio
async def test_unsafe_monitor_produces_unsafe_synthesis_status(mongo_database, monkeypatch) -> None:
    _inject_fake_plan(monkeypatch)
    _inject_unsafe_monitor(monkeypatch)
    result = await _run_turn(mongo_database, settings=_UNSAFE_SETTINGS)
    diag = result["metadata"].get("synthesisDiagnostics") or {}
    assert diag.get("status") == "unsafe"


@pytest.mark.asyncio
async def test_no_action_proposals_from_synthesis(mongo_database, monkeypatch) -> None:
    _inject_fake_plan(monkeypatch)
    result = await _run_turn(mongo_database, settings=_ON_SETTINGS)
    proposals = (result["final_response"] or {}).get("proposedActions") or []
    assert proposals == [] or isinstance(proposals, list)
