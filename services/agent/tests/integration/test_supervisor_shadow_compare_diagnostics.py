"""Integration tests for the Phase 8 post-context Supervisor Shadow Compare
+ Validation wiring (`orchestrator.py` -> `supervisor.post_context_runner`).

Mirrors `test_supervisor_diagnostics.py` (Phase 6) and
`test_supervisor_real_handler_diagnostics.py` (Phase 7): confirms that
toggling `AGENT_SUPERVISOR_POST_CONTEXT_COMPARE_ENABLED` never changes the
SSE event sequence, message text, blocks, warnings, or proposed actions a
student actually sees, and that the resulting `supervisorValidation`
diagnostics are compact and free of any raw/forbidden payload.

`AGENT_PLANNER_ENABLED` and `AGENT_SUPERVISOR_ENABLED` stay `True` in every
test here so a `planner_output` actually exists for the post-context runner
to consume — per the spec, it only ever runs once a live workflow result
exists. Runs with `OPENAI_API_KEY=None` — no real LLM call anywhere.
"""

from __future__ import annotations

import uuid

import pytest
from bson import ObjectId

from app.agent.context_builder import build_agent_context_pack
from app.agent.orchestrator import run_agent_turn
from app.agent.schemas import IntentClassification, TaskPlan
from app.agent.supervisor.post_context_runner import run_post_context_shadow_compare
from app.agent.supervisor.schemas import SupervisorRuntimeContext
from app.config import Settings
from app.repositories.agent_conversation_repository import create_agent_conversation
from app.repositories.student_profile_repository import create_student_profile
from app.repositories.user_repository import create_user
from tests.fixtures.graduation_progress_fixtures import seed_graduation_progress_fixtures

_MESSAGE = "asdfgh this is not a recognizable academic request qwerty"

_BASE_KWARGS = {"OPENAI_API_KEY": None, "AGENT_PLANNER_ENABLED": True, "AGENT_SUPERVISOR_ENABLED": True}

_COMPARE_OFF_SETTINGS = Settings(**{**_BASE_KWARGS, "AGENT_SUPERVISOR_POST_CONTEXT_COMPARE_ENABLED": False})
_COMPARE_ON_SETTINGS = Settings(
    **{
        **_BASE_KWARGS,
        "AGENT_SUPERVISOR_POST_CONTEXT_COMPARE_ENABLED": True,
        "AGENT_SUPERVISOR_VALIDATION_ENABLED": True,
    }
)


@pytest.fixture(autouse=True)
def _mock_student_user_context(monkeypatch):
    from app.retrieval import mongodb_user_retriever

    async def _fake_fetch_student_user_context(*, user_id: str, settings=None):
        return {"completed_courses": [], "data_quality": {"warnings": [], "ok": True}}

    monkeypatch.setattr(
        mongodb_user_retriever, "fetch_student_user_context", _fake_fetch_student_user_context
    )


async def _seed_user_and_conversation(mongo_database, *, program_id: str | None = None) -> tuple[str, str]:
    email = f"supervisor-compare-{uuid.uuid4().hex[:10]}@example.com"
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
# 1. Compare flag off keeps response unchanged (no supervisorValidation).
# ---------------------------------------------------------------------------


async def test_compare_flag_off_keeps_response_unchanged(mongo_database):
    user_id, conversation_id = await _seed_user_and_conversation(mongo_database)

    events, run_doc = await _run_turn(
        mongo_database, user_id=user_id, conversation_id=conversation_id, settings=_COMPARE_OFF_SETTINGS
    )

    assert not any(e.type == "run.failed" for e in events)
    metadata = run_doc.get("retrievalMetadata") or {}
    assert "supervisorValidation" not in metadata
    # Phase 6 supervisor diagnostics are independent and still ran.
    assert "supervisorDiagnostics" in metadata


# ---------------------------------------------------------------------------
# 2 & 3. Compare flag on keeps text/blocks/warnings/proposedActions and the
# SSE event-type sequence unchanged.
# ---------------------------------------------------------------------------


async def test_compare_flag_does_not_change_response_or_sse_sequence(mongo_database):
    user_id_off, conversation_id_off = await _seed_user_and_conversation(mongo_database)
    events_off, _ = await _run_turn(
        mongo_database, user_id=user_id_off, conversation_id=conversation_id_off, settings=_COMPARE_OFF_SETTINGS
    )

    user_id_on, conversation_id_on = await _seed_user_and_conversation(mongo_database)
    events_on, _ = await _run_turn(
        mongo_database, user_id=user_id_on, conversation_id=conversation_id_on, settings=_COMPARE_ON_SETTINGS
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


# ---------------------------------------------------------------------------
# 4. Compare flag on attaches compact supervisorValidation metadata.
# ---------------------------------------------------------------------------


async def test_compare_flag_on_attaches_compact_supervisor_validation_metadata(mongo_database):
    user_id, conversation_id = await _seed_user_and_conversation(mongo_database)

    events, run_doc = await _run_turn(
        mongo_database, user_id=user_id, conversation_id=conversation_id, settings=_COMPARE_ON_SETTINGS
    )

    assert not any(e.type == "run.failed" for e in events)
    metadata = run_doc.get("retrievalMetadata") or {}
    validation = metadata.get("supervisorValidation")
    assert validation is not None
    assert validation["liveWorkflowName"] == "general_academic_workflow"
    assert "status" in validation
    assert "safeToPromote" in validation
    assert isinstance(validation["issues"], list)
    # general_academic_workflow's real execution is deliberately excluded
    # (operationally expensive / may call an LLM) -- dry-run only.
    assert validation["shadowBlockCount"] == 0


# ---------------------------------------------------------------------------
# 5. Unsafe/proposal workflow produces a skipped shadow execution, not a
# duplicate proposal (direct call with a real runtime context, mirroring
# Phase 7's Layer-2 style tests).
# ---------------------------------------------------------------------------


def _semester_plan() -> dict:
    return {
        "status": "completed",
        "plan_id": "plan-compare-1",
        "user_goal": "Build my semester plan",
        "execution_mode": "single_capability",
        "recommended_autonomy_level": 3,
        "primary_intent": "semester_plan_generation",
        "subtasks": [
            {
                "id": "build_plan",
                "title": "Build semester plan",
                "kind": "propose_action",
                "capability_name": "semester_planning_workflow",
                "objective": "Draft a semester schedule.",
                "depends_on": [],
                "required_context_sections": ["user_message"],
            }
        ],
        "decision_summary": "test",
        "confidence": 0.85,
    }


async def test_unsafe_proposal_workflow_skipped_not_executed_via_post_context_runner(mongo_database):
    fixtures = await seed_graduation_progress_fixtures(mongo_database)
    user_id, conversation_id = await _seed_user_and_conversation(mongo_database, program_id=fixtures["programId"])

    settings = Settings(
        **{
            **_BASE_KWARGS,
            "AGENT_SUPERVISOR_POST_CONTEXT_COMPARE_ENABLED": True,
            "AGENT_SUPERVISOR_VALIDATION_ENABLED": True,
            "AGENT_SUPERVISOR_REAL_HANDLERS_ENABLED": True,
        }
    )

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
        settings=settings,
    )

    from app.agent.response_composer import compose_response

    live_response = compose_response(
        conversation_id=conversation_id,
        message_id="",
        run_id=context.run_id,
        text="Here is a draft plan.",
    )

    outcome = await run_post_context_shadow_compare(
        database=mongo_database,
        agent_context_pack=context,
        user_message="Build my semester plan",
        user_id=user_id,
        conversation_id=conversation_id,
        run_id=context.run_id,
        live_workflow_name="semester_planning_workflow",
        live_response=live_response,
        planner_output=_semester_plan(),
        settings=settings,
    )

    assert outcome is not None
    metadata = outcome.validation_metadata
    assert metadata["shadowProposedActionCount"] == 0
    assert metadata["status"] in ("passed", "passed_with_warnings")
    assert outcome.promoted_response is None

    proposals = await mongo_database[settings.agent_action_proposals_collection].find({}).to_list(length=10)
    assert proposals == []


# ---------------------------------------------------------------------------
# 6. Handler failure does not break the live turn.
# ---------------------------------------------------------------------------


async def test_post_context_runner_failure_does_not_fail_the_turn(mongo_database, monkeypatch):
    from app.agent.supervisor import post_context_runner as post_context_runner_module

    async def _boom(**_kwargs):
        raise RuntimeError("boom")

    monkeypatch.setattr(post_context_runner_module, "run_supervisor_shadow", _boom)

    user_id, conversation_id = await _seed_user_and_conversation(mongo_database)
    events, run_doc = await _run_turn(
        mongo_database, user_id=user_id, conversation_id=conversation_id, settings=_COMPARE_ON_SETTINGS
    )

    assert not any(e.type == "run.failed" for e in events)
    metadata = run_doc.get("retrievalMetadata") or {}
    assert "supervisorValidation" not in metadata
    completed = next(e for e in events if e.type == "message.completed")
    assert completed.text


# ---------------------------------------------------------------------------
# 7. Diagnostics contain no raw context/raw blocks/raw text/proposed action
# payloads.
# ---------------------------------------------------------------------------


async def test_supervisor_validation_diagnostics_have_no_forbidden_payloads(mongo_database):
    user_id, conversation_id = await _seed_user_and_conversation(mongo_database)

    _events, run_doc = await _run_turn(
        mongo_database, user_id=user_id, conversation_id=conversation_id, settings=_COMPARE_ON_SETTINGS
    )

    metadata = run_doc.get("retrievalMetadata") or {}
    validation_text = str(metadata.get("supervisorValidation"))
    for forbidden in (
        "raw_context",
        "compiled_context",
        "raw_blocks",
        "raw_response",
        "raw_text",
        "full_text",
        "proposed_action_payload",
        "transcript_rows",
        "full_catalog",
        "raw_pdf_bytes",
        "chain_of_thought",
        "hidden_reasoning",
        "private_reasoning",
        "scratchpad",
        "thoughts",
    ):
        assert forbidden not in validation_text
