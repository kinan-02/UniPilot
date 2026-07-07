"""Integration tests for Phase 18 cross-turn clarification flow."""

from __future__ import annotations

import uuid

import pytest
from bson import ObjectId

from app.agent.clarification.schemas import ClarificationCapabilityOutput, ClarificationQuestion
from app.agent.orchestrator import run_agent_turn
from app.agent.planner.schemas import PlannerOutput, PlannerSubtask
from app.config import Settings
from app.repositories.agent_conversation_repository import create_agent_conversation
from app.repositories.clarification_state_repository import ClarificationStateRepository
from app.repositories.student_profile_repository import create_student_profile
from app.repositories.user_repository import create_user
from tests.fixtures.graduation_progress_fixtures import seed_graduation_progress_fixtures

_MESSAGE = "What am I missing to graduate?"
_PREFERENCE_MISSING = ["user preference: must choose between workload and graduation requirements"]

_BASE_KWARGS = {
    "OPENAI_API_KEY": None,
    "AGENT_PLANNER_ENABLED": True,
    "AGENT_SUPERVISOR_ENABLED": True,
    "AGENT_SUPERVISOR_POST_CONTEXT_COMPARE_ENABLED": True,
    "AGENT_MONITOR_ENABLED": True,
    "AGENT_MONITOR_DRY_RUN": True,
    "AGENT_CLARIFICATION_ENABLED": True,
    "AGENT_CLARIFICATION_STATE_ENABLED": True,
}

_OFF_SETTINGS = Settings(**{**_BASE_KWARGS, "AGENT_CLARIFICATION_USER_FACING_ENABLED": False})
_DIAG_SETTINGS = Settings(**{**_BASE_KWARGS, "AGENT_CLARIFICATION_USER_FACING_ENABLED": False})
_ON_SETTINGS = Settings(**{**_BASE_KWARGS, "AGENT_CLARIFICATION_USER_FACING_ENABLED": True})


def _fake_plan(*, missing_context: list[str] | None = None) -> PlannerOutput:
    return PlannerOutput(
        status="completed",
        plan_id="plan-cross-turn-1",
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
    email = f"cross-turn-{uuid.uuid4().hex[:10]}@example.com"
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
    conversation = await create_agent_conversation(mongo_database, user_id=user_id, title="Cross-turn test")
    return user_id, str(conversation["id"])


async def _run_turn(mongo_database, *, user_id: str, conversation_id: str, message: str, settings: Settings):
    events = [
        event
        async for event in run_agent_turn(
            mongo_database,
            user_id=user_id,
            conversation_id=conversation_id,
            user_message=message,
            trigger_message_id=str(ObjectId()),
            settings=settings,
        )
    ]
    run_doc = await mongo_database[settings.agent_runs_collection].find_one(
        {"userId": ObjectId(user_id)}, sort=[("startedAt", -1)]
    )
    return events, run_doc


async def test_flags_off_preserves_behavior(mongo_database, monkeypatch) -> None:
    _inject_fake_plan(monkeypatch, missing_context=_PREFERENCE_MISSING)
    user_id, conversation_id = await _seed_user(mongo_database)
    settings = Settings(**{**_BASE_KWARGS, "AGENT_CLARIFICATION_ENABLED": False})

    _, run_doc = await _run_turn(
        mongo_database,
        user_id=user_id,
        conversation_id=conversation_id,
        message=_MESSAGE,
        settings=settings,
    )

    metadata = run_doc.get("retrievalMetadata") or {}
    assert "clarificationState" not in metadata


async def test_diagnostic_only_mode_preserves_normal_response_shape(mongo_database, monkeypatch) -> None:
    _inject_fake_plan(monkeypatch, missing_context=_PREFERENCE_MISSING)
    user_id, conversation_id = await _seed_user(mongo_database)

    events, run_doc = await _run_turn(
        mongo_database,
        user_id=user_id,
        conversation_id=conversation_id,
        message=_MESSAGE,
        settings=_DIAG_SETTINGS,
    )

    completed = next(event for event in events if event.type == "message.completed")
    assert "Before I continue" not in (completed.text or "")
    repo = ClarificationStateRepository(mongo_database, settings=_DIAG_SETTINGS)
    assert await repo.get_active_for_conversation(conversation_id) is None


async def test_user_facing_enabled_creates_pending_and_returns_question(mongo_database, monkeypatch) -> None:
    _inject_fake_plan(monkeypatch, missing_context=_PREFERENCE_MISSING)
    user_id, conversation_id = await _seed_user(mongo_database)

    events, run_doc = await _run_turn(
        mongo_database,
        user_id=user_id,
        conversation_id=conversation_id,
        message=_MESSAGE,
        settings=_ON_SETTINGS,
    )

    completed = next(event for event in events if event.type == "message.completed")
    assert "To plan this correctly" in (completed.text or "") or "Before I continue" in (completed.text or "")

    repo = ClarificationStateRepository(mongo_database, settings=_ON_SETTINGS)
    pending = await repo.get_active_for_conversation(conversation_id)
    assert pending is not None
    assert pending.original_user_message == _MESSAGE

    state = (run_doc.get("retrievalMetadata") or {}).get("clarificationState") or {}
    assert state.get("status") == "pending"


async def test_next_user_message_resolves_pending_clarification(mongo_database, monkeypatch) -> None:
    _inject_fake_plan(monkeypatch, missing_context=_PREFERENCE_MISSING)
    user_id, conversation_id = await _seed_user(mongo_database)

    await _run_turn(
        mongo_database,
        user_id=user_id,
        conversation_id=conversation_id,
        message=_MESSAGE,
        settings=_ON_SETTINGS,
    )

    events, run_doc = await _run_turn(
        mongo_database,
        user_id=user_id,
        conversation_id=conversation_id,
        message="keep workload lighter",
        settings=_ON_SETTINGS,
    )

    assert not any(event.type == "run.failed" for event in events)
    repo = ClarificationStateRepository(mongo_database, settings=_ON_SETTINGS)
    assert await repo.get_active_for_conversation(conversation_id) is None

    state = (run_doc.get("retrievalMetadata") or {}).get("clarificationState") or {}
    assert state.get("status") == "answered"
    assert "confirmed" in (state.get("provenance") or [])


async def test_unresolved_answer_returns_reminder_without_crashing(mongo_database, monkeypatch) -> None:
    _inject_fake_plan(monkeypatch, missing_context=_PREFERENCE_MISSING)
    user_id, conversation_id = await _seed_user(mongo_database)

    await _run_turn(
        mongo_database,
        user_id=user_id,
        conversation_id=conversation_id,
        message=_MESSAGE,
        settings=_ON_SETTINGS,
    )

    events, _ = await _run_turn(
        mongo_database,
        user_id=user_id,
        conversation_id=conversation_id,
        message="What are my graduation requirements?",
        settings=_ON_SETTINGS,
    )

    failed = [event for event in events if event.type == "run.failed"]
    assert not failed, failed[0].error if failed else None
    completed = next(event for event in events if event.type == "message.completed")
    assert "still need your clarification" in (completed.text or "").lower()


async def test_expired_clarification_does_not_block_future_requests(mongo_database, monkeypatch) -> None:
    _inject_fake_plan(monkeypatch, missing_context=_PREFERENCE_MISSING)
    user_id, conversation_id = await _seed_user(mongo_database)
    repo = ClarificationStateRepository(mongo_database, settings=_ON_SETTINGS)

    pending = await repo.create_pending(
        conversation_id=conversation_id,
        user_id=user_id,
        original_user_message=_MESSAGE,
        questions=[
            {
                "need_id": "need-1",
                "prompt": "Which preference?",
                "options": ["requirements first", "lighter workload"],
                "allow_free_text": True,
                "consequence": "high",
                "ambiguity_type": "preference",
            }
        ],
        needs=[
            {
                "id": "need-1",
                "ambiguity_type": "preference",
                "consequence": "high",
                "question_topic": "workload",
                "reason": "missing",
            }
        ],
        max_pending_turns=1,
    )
    assert pending is not None
    await repo.increment_pending_turn_count(pending.clarification_id)
    await repo.increment_pending_turn_count(pending.clarification_id)

    events, _ = await _run_turn(
        mongo_database,
        user_id=user_id,
        conversation_id=conversation_id,
        message="hello again",
        settings=_ON_SETTINGS,
    )
    assert not any(event.type == "run.failed" for event in events)
    assert await repo.get_active_for_conversation(conversation_id) is None


async def test_sse_event_sequence_remains_compatible(mongo_database, monkeypatch) -> None:
    _inject_fake_plan(monkeypatch, missing_context=_PREFERENCE_MISSING)
    user_id_off, conversation_id_off = await _seed_user(mongo_database)
    events_off, _ = await _run_turn(
        mongo_database,
        user_id=user_id_off,
        conversation_id=conversation_id_off,
        message=_MESSAGE,
        settings=_OFF_SETTINGS,
    )

    user_id_diag, conversation_id_diag = await _seed_user(mongo_database)
    events_diag, _ = await _run_turn(
        mongo_database,
        user_id=user_id_diag,
        conversation_id=conversation_id_diag,
        message=_MESSAGE,
        settings=_DIAG_SETTINGS,
    )

    assert [event.type for event in events_off] == [event.type for event in events_diag]


async def test_no_action_proposals_created(mongo_database, monkeypatch) -> None:
    _inject_fake_plan(monkeypatch, missing_context=_PREFERENCE_MISSING)
    user_id, conversation_id = await _seed_user(mongo_database)

    events, _ = await _run_turn(
        mongo_database,
        user_id=user_id,
        conversation_id=conversation_id,
        message=_MESSAGE,
        settings=_ON_SETTINGS,
    )

    assert not any(event.type == "action.proposed" for event in events)


async def test_no_student_data_writes(mongo_database, monkeypatch) -> None:
    _inject_fake_plan(monkeypatch, missing_context=_PREFERENCE_MISSING)
    user_id, conversation_id = await _seed_user(mongo_database)

    await _run_turn(
        mongo_database,
        user_id=user_id,
        conversation_id=conversation_id,
        message=_MESSAGE,
        settings=_ON_SETTINGS,
    )

    assert await mongo_database["completed_courses"].count_documents({}) == 0


async def test_no_direct_llm_calls_in_cross_turn_modules() -> None:
    from pathlib import Path

    root = Path(__file__).resolve().parents[2] / "app" / "agent" / "clarification"
    text = "\n".join(path.read_text(encoding="utf-8") for path in root.rglob("*.py") if path.name != "safety.py")
    assert "ReasoningBlock" not in text
