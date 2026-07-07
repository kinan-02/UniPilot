"""Integration tests for Phase 7 real read-only workflow adapter execution.

Two layers are tested, deliberately kept separate:

1. Through `run_agent_turn` (the live turn): confirms that toggling
   `AGENT_SUPERVISOR_REAL_HANDLERS_ENABLED` never changes user-facing
   behavior, and that today it still behaves exactly like Phase 6 — the
   orchestrator's own diagnostic call site does not yet pass a populated
   `SupervisorRuntimeContext` (no `AgentContextPack` is available at that
   point in the turn; see `docs/agent/CURRENT_STATE.md` for why this was a
   deliberate Phase 7 safety choice), so no real handler actually runs
   automatically yet.
2. Directly against `run_supervisor_shadow`/`run_supervisor_dry_run` with an
   explicitly constructed `SupervisorRuntimeContext` (a real mongomock
   database + a real `AgentContextPack` built the same way
   `context_builder.build_agent_context_pack` would): proves the Phase 7
   infrastructure genuinely executes a real, read-only workflow end to end,
   and that proposal-sensitive workflows are still refused.
"""

from __future__ import annotations

import uuid

import pytest
from bson import ObjectId

from app.agent.context_builder import build_agent_context_pack
from app.agent.orchestrator import run_agent_turn
from app.agent.schemas import IntentClassification, TaskPlan
from app.agent.supervisor.diagnostics import run_supervisor_dry_run
from app.agent.supervisor.runtime import run_supervisor_shadow
from app.agent.supervisor.schemas import SupervisorRunInput, SupervisorRuntimeContext
from app.config import Settings
from app.repositories.agent_conversation_repository import create_agent_conversation
from app.repositories.student_profile_repository import create_student_profile
from app.repositories.user_repository import create_user
from tests.fixtures.graduation_progress_fixtures import seed_graduation_progress_fixtures

_MESSAGE = "asdfgh this is not a recognizable academic request qwerty"

_BASE_SETTINGS_KWARGS = {"OPENAI_API_KEY": None, "AGENT_PLANNER_ENABLED": True, "AGENT_SUPERVISOR_ENABLED": True}

_REAL_HANDLERS_OFF_SETTINGS = Settings(
    **{**_BASE_SETTINGS_KWARGS, "AGENT_SUPERVISOR_REAL_HANDLERS_ENABLED": False}
)
_REAL_HANDLERS_ON_SETTINGS = Settings(
    **{**_BASE_SETTINGS_KWARGS, "AGENT_SUPERVISOR_REAL_HANDLERS_ENABLED": True}
)


@pytest.fixture(autouse=True)
def _mock_student_user_context(monkeypatch):
    from app.retrieval import mongodb_user_retriever

    async def _fake_fetch_student_user_context(*, user_id: str, settings=None):
        return {"completed_courses": [], "data_quality": {"warnings": [], "ok": True}}

    monkeypatch.setattr(
        mongodb_user_retriever, "fetch_student_user_context", _fake_fetch_student_user_context
    )


def _fake_graduation_audit() -> dict:
    return {
        "status": "ok",
        "progress": {
            "statusSummary": "in_progress",
            "creditsRemaining": 40.0,
            "requirementProgress": [],
            "remainingMandatoryCourses": [],
            "missingRequirements": [],
        },
        "errors": [],
        "warnings": [],
        "assumptions": [],
        "blockers": [],
        "graduation_status": "not_ready",
        "can_graduate": False,
    }


async def _seed_user_and_conversation(mongo_database, *, program_id: str | None = None) -> tuple[str, str]:
    email = f"supervisor-real-{uuid.uuid4().hex[:10]}@example.com"
    user = await create_user(mongo_database, email=email, password_hash="hashed")
    user_id = str(user["_id"])
    await create_student_profile(
        mongo_database,
        user_id,
        {
            "institutionId": "technion",
            "programType": "BSc",
            "degreeId": program_id or str(ObjectId()),
            "catalogYear": 2025,
            "currentSemesterCode": "2025-1",
            "academicPath": {"trackSlug": "track-data-information-engineering"},
        },
    )
    conversation = await create_agent_conversation(mongo_database, user_id=user_id, title="Test")
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


# ---------------------------------------------------------------------------
# Layer 1 — through `run_agent_turn` (live turn behavior never changes).
# ---------------------------------------------------------------------------


async def test_real_handlers_flag_off_preserves_phase6_dry_run_behavior(mongo_database):
    user_id, conversation_id = await _seed_user_and_conversation(mongo_database)

    events, run_doc = await _run_turn(
        mongo_database, user_id=user_id, conversation_id=conversation_id, settings=_REAL_HANDLERS_OFF_SETTINGS
    )

    assert not any(e.type == "run.failed" for e in events)
    metadata = run_doc.get("retrievalMetadata") or {}
    diagnostics = metadata.get("supervisorDiagnostics")
    assert diagnostics is not None
    assert diagnostics["completedSubtasks"] == ["run_legacy_workflow"]


async def test_real_handlers_flag_on_still_dry_run_through_live_orchestrator(mongo_database):
    """Documents current integration status: the flag exists and is read,
    but the orchestrator's automatic diagnostic call doesn't yet supply a
    populated `SupervisorRuntimeContext`, so no real handler executes
    automatically even with the flag on (Phase 8 follow-up)."""
    user_id, conversation_id = await _seed_user_and_conversation(mongo_database)

    events, run_doc = await _run_turn(
        mongo_database, user_id=user_id, conversation_id=conversation_id, settings=_REAL_HANDLERS_ON_SETTINGS
    )

    assert not any(e.type == "run.failed" for e in events)
    metadata = run_doc.get("retrievalMetadata") or {}
    diagnostics = metadata.get("supervisorDiagnostics")
    assert diagnostics is not None
    assert diagnostics["completedSubtasks"] == ["run_legacy_workflow"]


async def test_flag_does_not_change_user_visible_response_or_sse_sequence(mongo_database):
    user_id_off, conversation_id_off = await _seed_user_and_conversation(mongo_database)
    events_off, _ = await _run_turn(
        mongo_database, user_id=user_id_off, conversation_id=conversation_id_off, settings=_REAL_HANDLERS_OFF_SETTINGS
    )

    user_id_on, conversation_id_on = await _seed_user_and_conversation(mongo_database)
    events_on, _ = await _run_turn(
        mongo_database, user_id=user_id_on, conversation_id=conversation_id_on, settings=_REAL_HANDLERS_ON_SETTINGS
    )

    assert [e.type for e in events_off] == [e.type for e in events_on]

    completed_off = next(e for e in events_off if e.type == "message.completed")
    completed_on = next(e for e in events_on if e.type == "message.completed")
    assert completed_off.text == completed_on.text

    blocks_off = [e.block for e in events_off if e.type == "structured_output"]
    blocks_on = [e.block for e in events_on if e.type == "structured_output"]
    assert [b.model_dump() for b in blocks_off] == [b.model_dump() for b in blocks_on]

    actions_off = [e.action for e in events_off if e.type == "action.proposed"]
    actions_on = [e.action for e in events_on if e.type == "action.proposed"]
    assert actions_off == actions_on


async def test_supervisor_diagnostic_failure_does_not_fail_the_turn(mongo_database, monkeypatch):
    from app.agent.supervisor import diagnostics as supervisor_diagnostics

    async def _boom(**_kwargs):
        raise RuntimeError("boom")

    monkeypatch.setattr(supervisor_diagnostics, "run_supervisor_shadow", _boom)

    user_id, conversation_id = await _seed_user_and_conversation(mongo_database)
    events, run_doc = await _run_turn(
        mongo_database, user_id=user_id, conversation_id=conversation_id, settings=_REAL_HANDLERS_ON_SETTINGS
    )

    assert not any(e.type == "run.failed" for e in events)
    metadata = run_doc.get("retrievalMetadata") or {}
    assert "supervisorDiagnostics" not in metadata


# ---------------------------------------------------------------------------
# Layer 2 — direct `run_supervisor_shadow` calls with a real runtime context,
# proving the Phase 7 infrastructure genuinely executes end to end.
# ---------------------------------------------------------------------------


def _graduation_plan(program_capability: str = "graduation_progress_workflow") -> dict:
    return {
        "status": "completed",
        "plan_id": "plan-real-1",
        "user_goal": "What am I missing to graduate?",
        "execution_mode": "single_capability",
        "recommended_autonomy_level": 3,
        "primary_intent": "graduation_progress_check",
        "subtasks": [
            {
                "id": "check_progress",
                "title": "Check graduation progress",
                "kind": "analyze",
                "capability_name": program_capability,
                "objective": "Determine remaining requirements toward graduation.",
                "depends_on": [],
                "required_context_sections": ["user_message"],
            }
        ],
        "decision_summary": "test",
        "confidence": 0.85,
    }


async def test_real_handler_executes_graduation_progress_workflow_end_to_end(mongo_database, monkeypatch):
    from app.services import graduation_audit_client

    async def _fake_graduation_audit_coro():
        return _fake_graduation_audit()

    monkeypatch.setattr(
        graduation_audit_client, "fetch_graduation_audit", lambda **_: _fake_graduation_audit_coro()
    )

    fixtures = await seed_graduation_progress_fixtures(mongo_database)
    user_id, conversation_id = await _seed_user_and_conversation(mongo_database, program_id=fixtures["programId"])

    classification = IntentClassification(intent="graduation_progress_check", confidence=0.95)
    task_plan = TaskPlan(workflow="graduation_progress_workflow", read_only=True, requires_confirmation=False)
    context = await build_agent_context_pack(
        mongo_database,
        conversation_id=conversation_id,
        run_id=str(ObjectId()),
        user_id=user_id,
        intent="graduation_progress_check",
        entities={},
        classification=classification,
        task_plan=task_plan,
        user_message="What am I missing to graduate?",
        settings=_REAL_HANDLERS_ON_SETTINGS,
    )

    runtime_context = SupervisorRuntimeContext(
        database=mongo_database,
        agent_context_pack=context,
        user_message="What am I missing to graduate?",
        user_id=user_id,
        conversation_id=conversation_id,
    )
    run_input = SupervisorRunInput(
        user_message="What am I missing to graduate?", planner_output=_graduation_plan()
    )

    output = await run_supervisor_shadow(
        input=run_input, runtime_context=runtime_context, settings=_REAL_HANDLERS_ON_SETTINGS
    )

    assert output.status in ("completed", "completed_with_warnings")
    assert output.completed_subtasks == ["check_progress"]
    record = output.subtask_records[0]
    assert record.result_summary["shadowExecuted"] is True
    assert record.result_summary["workflowName"] == "graduation_progress_workflow"
    assert record.result_summary["blockCount"] > 0

    # Hard safety invariants, regardless of what actually happened above.
    assert runtime_context.allow_side_effects is False
    assert runtime_context.shadow_execution is True


async def test_proposal_workflow_is_skipped_not_executed_even_with_real_context(mongo_database):
    fixtures = await seed_graduation_progress_fixtures(mongo_database)
    user_id, conversation_id = await _seed_user_and_conversation(mongo_database, program_id=fixtures["programId"])

    classification = IntentClassification(intent="semester_plan_generation", confidence=0.9)
    task_plan = TaskPlan(workflow="semester_planning_workflow", read_only=False, requires_confirmation=True)
    context = await build_agent_context_pack(
        mongo_database,
        conversation_id=conversation_id,
        run_id=str(ObjectId()),
        user_id=user_id,
        intent="semester_plan_generation",
        entities={},
        classification=classification,
        task_plan=task_plan,
        user_message="Build my semester plan",
        settings=_REAL_HANDLERS_ON_SETTINGS,
    )

    runtime_context = SupervisorRuntimeContext(
        database=mongo_database, agent_context_pack=context, user_message="Build my semester plan"
    )
    plan = _graduation_plan(program_capability="semester_planning_workflow")
    plan["execution_mode"] = "single_capability"
    run_input = SupervisorRunInput(user_message="Build my semester plan", planner_output=plan)

    output = await run_supervisor_shadow(
        input=run_input, runtime_context=runtime_context, settings=_REAL_HANDLERS_ON_SETTINGS
    )

    assert output.skipped_subtasks == ["check_progress"]
    record = output.subtask_records[0]
    assert record.result_summary["shadowExecuted"] is False
    assert any("shadow_execution_not_safe_for_capability" in w for w in record.warnings)
    # No proposal was ever created by this shadow run.
    proposals = await mongo_database[_REAL_HANDLERS_ON_SETTINGS.agent_action_proposals_collection].find(
        {}
    ).to_list(length=10)
    assert proposals == []


async def test_diagnostics_are_compact_and_never_include_raw_context_or_response(mongo_database, monkeypatch):
    from app.services import graduation_audit_client

    async def _fake_graduation_audit_coro():
        return _fake_graduation_audit()

    monkeypatch.setattr(
        graduation_audit_client, "fetch_graduation_audit", lambda **_: _fake_graduation_audit_coro()
    )

    fixtures = await seed_graduation_progress_fixtures(mongo_database)
    user_id, conversation_id = await _seed_user_and_conversation(mongo_database, program_id=fixtures["programId"])

    classification = IntentClassification(intent="graduation_progress_check", confidence=0.95)
    task_plan = TaskPlan(workflow="graduation_progress_workflow", read_only=True, requires_confirmation=False)
    context = await build_agent_context_pack(
        mongo_database,
        conversation_id=conversation_id,
        run_id=str(ObjectId()),
        user_id=user_id,
        intent="graduation_progress_check",
        entities={},
        classification=classification,
        task_plan=task_plan,
        user_message="What am I missing to graduate?",
        settings=_REAL_HANDLERS_ON_SETTINGS,
    )
    runtime_context = SupervisorRuntimeContext(
        database=mongo_database, agent_context_pack=context, user_message="What am I missing to graduate?"
    )

    summary = await run_supervisor_dry_run(
        user_message="What am I missing to graduate?",
        planner_diagnostics={"status": "completed"},
        planner_output=_graduation_plan(),
        deterministic_intent="graduation_progress_check",
        deterministic_entities={},
        runtime_context=runtime_context,
        settings=_REAL_HANDLERS_ON_SETTINGS,
    )

    assert summary is not None
    summary_text = str(summary)
    assert "context" not in summary
    for forbidden in ("chain_of_thought", "hidden_reasoning", "scratchpad", "raw_mongo_document"):
        assert forbidden not in summary_text
