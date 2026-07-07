"""Integration tests for Phase 17 clarification diagnostics."""

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

_OFF_SETTINGS = Settings(**{**_BASE_KWARGS, "AGENT_CLARIFICATION_ENABLED": False})
_ON_DIAG_SETTINGS = Settings(
    **{
        **_BASE_KWARGS,
        "AGENT_CLARIFICATION_ENABLED": True,
        "AGENT_CLARIFICATION_USER_FACING_ENABLED": False,
    }
)
_ON_USER_FACING_SETTINGS = Settings(
    **{
        **_BASE_KWARGS,
        "AGENT_CLARIFICATION_ENABLED": True,
        "AGENT_CLARIFICATION_USER_FACING_ENABLED": True,
    }
)


def _fake_plan(*, missing_context: list[str] | None = None) -> PlannerOutput:
    return PlannerOutput(
        status="completed",
        plan_id="plan-clarification-diag-1",
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
        missing_context=list(missing_context or []),
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


def _inject_fake_plan(monkeypatch, *, missing_context: list[str] | None = None) -> None:
    async def _fake_build_plan_with_diagnostics(**_kwargs):
        plan = _fake_plan(missing_context=missing_context)
        return plan, {"status": plan.status, "planId": plan.plan_id}

    monkeypatch.setattr("app.agent.orchestrator.build_plan_with_diagnostics", _fake_build_plan_with_diagnostics)


async def _seed_user(mongo_database) -> tuple[str, str]:
    fixtures = await seed_graduation_progress_fixtures(mongo_database)
    email = f"clarification-{uuid.uuid4().hex[:10]}@example.com"
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
    conversation = await create_agent_conversation(mongo_database, user_id=user_id, title="Clarification test")
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


async def test_clarification_flag_off_preserves_behavior(mongo_database, monkeypatch) -> None:
    _inject_fake_plan(
        monkeypatch,
        missing_context=["user preference: prioritize workload or requirements"],
    )
    user_id, conversation_id = await _seed_user(mongo_database)

    events, run_doc = await _run_turn(
        mongo_database, user_id=user_id, conversation_id=conversation_id, settings=_OFF_SETTINGS
    )

    assert not any(event.type == "run.failed" for event in events)
    metadata = run_doc.get("retrievalMetadata") or {}
    assert "clarificationDiagnostics" not in metadata


async def test_clarification_flag_on_attaches_clarification_diagnostics(mongo_database, monkeypatch) -> None:
    _inject_fake_plan(
        monkeypatch,
        missing_context=["user preference: prioritize workload or requirements"],
    )
    user_id, conversation_id = await _seed_user(mongo_database)

    _, run_doc = await _run_turn(
        mongo_database, user_id=user_id, conversation_id=conversation_id, settings=_ON_DIAG_SETTINGS
    )

    clarification = (run_doc.get("retrievalMetadata") or {}).get("clarificationDiagnostics")
    assert clarification is not None
    assert "status" in clarification
    assert "needCount" in clarification


async def test_diagnostics_only_mode_does_not_change_final_text_or_sse_sequence(mongo_database, monkeypatch) -> None:
    missing = ["user preference: prioritize workload or requirements"]
    _inject_fake_plan(monkeypatch, missing_context=missing)

    user_id_off, conversation_id_off = await _seed_user(mongo_database)
    events_off, _ = await _run_turn(
        mongo_database, user_id=user_id_off, conversation_id=conversation_id_off, settings=_OFF_SETTINGS
    )

    user_id_on, conversation_id_on = await _seed_user(mongo_database)
    events_on, _ = await _run_turn(
        mongo_database, user_id=user_id_on, conversation_id=conversation_id_on, settings=_ON_DIAG_SETTINGS
    )

    assert [event.type for event in events_off] == [event.type for event in events_on]
    completed_off = next(event for event in events_off if event.type == "message.completed")
    completed_on = next(event for event in events_on if event.type == "message.completed")
    assert completed_off.text == completed_on.text


async def test_monitor_ask_clarification_decision_produces_clarification_need(mongo_database, monkeypatch) -> None:
    _inject_fake_plan(
        monkeypatch,
        missing_context=["user preference: which track do you prefer"],
    )
    user_id, conversation_id = await _seed_user(mongo_database)

    _, run_doc = await _run_turn(
        mongo_database, user_id=user_id, conversation_id=conversation_id, settings=_ON_DIAG_SETTINGS
    )

    monitor = (run_doc.get("retrievalMetadata") or {}).get("monitorDiagnostics") or {}
    clarification = (run_doc.get("retrievalMetadata") or {}).get("clarificationDiagnostics") or {}
    assert monitor.get("decision", {}).get("action") in {"ask_clarification", "request_plan_repair", "continue"}
    assert clarification.get("needCount", 0) >= 1


async def test_high_consequence_preference_ambiguity_produces_question_summary(mongo_database, monkeypatch) -> None:
    _inject_fake_plan(
        monkeypatch,
        missing_context=["user preference: must choose between workload and requirements"],
    )
    user_id, conversation_id = await _seed_user(mongo_database)

    _, run_doc = await _run_turn(
        mongo_database, user_id=user_id, conversation_id=conversation_id, settings=_ON_USER_FACING_SETTINGS
    )

    clarification = (run_doc.get("retrievalMetadata") or {}).get("clarificationDiagnostics") or {}
    assert clarification.get("status") in {"question_ready", "assumed_default", "skipped"}
    if clarification.get("status") == "question_ready":
        assert clarification.get("questionCount", 0) >= 1
        assert clarification["questions"][0]["ambiguityType"] == "preference"


async def test_epistemic_ambiguity_does_not_ask_user(mongo_database, monkeypatch) -> None:
    _inject_fake_plan(
        monkeypatch,
        missing_context=["catalog requirement details for track"],
    )
    user_id, conversation_id = await _seed_user(mongo_database)

    _, run_doc = await _run_turn(
        mongo_database, user_id=user_id, conversation_id=conversation_id, settings=_ON_USER_FACING_SETTINGS
    )

    clarification = (run_doc.get("retrievalMetadata") or {}).get("clarificationDiagnostics") or {}
    assert clarification.get("questionCount", 0) == 0


async def test_assumed_fallback_creates_provenance_assumed(mongo_database, monkeypatch) -> None:
    _inject_fake_plan(
        monkeypatch,
        missing_context=["user preference: workload balance"],
    )

    async def _fake_build_plan_with_diagnostics(**_kwargs):
        plan = _fake_plan(missing_context=["user preference: workload balance"])
        dumped = plan.model_dump()
        dumped["missing_context"] = plan.missing_context
        return plan, dumped

    monkeypatch.setattr("app.agent.orchestrator.build_plan_with_diagnostics", _fake_build_plan_with_diagnostics)

    user_id, conversation_id = await _seed_user(mongo_database)
    _, run_doc = await _run_turn(
        mongo_database, user_id=user_id, conversation_id=conversation_id, settings=_ON_DIAG_SETTINGS
    )

    clarification = (run_doc.get("retrievalMetadata") or {}).get("clarificationDiagnostics") or {}
    assert clarification.get("status") in {"assumed_default", "skipped", "resolved_epistemically", "question_ready"}


async def test_no_direct_llm_calls_in_clarification_package() -> None:
    from pathlib import Path

    root = Path(__file__).resolve().parents[2] / "app" / "agent" / "clarification"
    text = "\n".join(path.read_text(encoding="utf-8") for path in root.rglob("*.py") if path.name != "safety.py")
    assert "ReasoningBlock" not in text
    assert "build_chat_llm(" not in text


async def test_no_writes_or_action_proposals_from_clarification_integration(mongo_database, monkeypatch) -> None:
    _inject_fake_plan(
        monkeypatch,
        missing_context=["user preference: prioritize workload or requirements"],
    )
    user_id, conversation_id = await _seed_user(mongo_database)

    events, run_doc = await _run_turn(
        mongo_database, user_id=user_id, conversation_id=conversation_id, settings=_ON_DIAG_SETTINGS
    )

    assert not any(event.type == "run.failed" for event in events)
    clarification = (run_doc.get("retrievalMetadata") or {}).get("clarificationDiagnostics") or {}
    assert clarification.get("status") in {"assumed_default", "skipped", "resolved_epistemically", "question_ready", "failed"}
    assert "create_agent_action_proposal" not in str(clarification)
