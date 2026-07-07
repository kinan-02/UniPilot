"""Integration tests for Phase 12's Specialist Tool Observation Layer, wired
into the Supervisor Orchestrator Runtime + live-turn diagnostics.

Mirrors `test_specialist_agents_supervisor_diagnostics.py` (Phase 10):
`OPENAI_API_KEY=None` throughout, so every specialist call safely degrades
to its Phase 10 fallback (`status="skipped"`) before any network call --
the observation layer itself never calls an LLM regardless, so its
behavior is fully exercised independent of that fallback.
"""

from __future__ import annotations

import uuid

import pytest
from bson import ObjectId

from app.agent.orchestrator import run_agent_turn
from app.agent.schemas import AgentContextPack
from app.agent.supervisor.runtime import run_supervisor_shadow
from app.agent.supervisor.schemas import SupervisorRunInput, SupervisorRuntimeContext
from app.config import Settings
from app.repositories.agent_conversation_repository import create_agent_conversation
from app.repositories.student_profile_repository import create_student_profile
from app.repositories.user_repository import create_user

_GRADUATION_MESSAGE = "What am I missing to graduate?"
# Used for the full-`run_agent_turn` tests below -- an unrecognized message
# keeps the *live* workflow selection on the safe deterministic fallback
# path (mirrors `test_specialist_agents_supervisor_diagnostics.py`'s own
# `_MESSAGE`), so these tests don't need graduation-audit fixtures/mocks;
# the `run_supervisor_shadow`-level tests below inject a plan directly and
# never touch live intent classification/routing at all.
_UNRECOGNIZED_MESSAGE = "asdfgh this is not a recognizable academic request qwerty"

_BASE_KWARGS = {"OPENAI_API_KEY": None, "AGENT_PLANNER_ENABLED": True, "AGENT_SUPERVISOR_ENABLED": True}

_OBSERVATIONS_OFF_SETTINGS = Settings(
    **{**_BASE_KWARGS, "AGENT_SPECIALIST_AGENTS_ENABLED": True, "AGENT_SPECIALIST_OBSERVATIONS_ENABLED": False}
)
_OBSERVATIONS_ON_SETTINGS = Settings(
    **{**_BASE_KWARGS, "AGENT_SPECIALIST_AGENTS_ENABLED": True, "AGENT_SPECIALIST_OBSERVATIONS_ENABLED": True}
)


@pytest.fixture(autouse=True)
def _mock_student_user_context(monkeypatch):
    from app.retrieval import mongodb_user_retriever

    async def _fake_fetch_student_user_context(*, user_id: str, settings=None):
        return {"completed_courses": [], "data_quality": {"warnings": [], "ok": True}}

    monkeypatch.setattr(
        mongodb_user_retriever, "fetch_student_user_context", _fake_fetch_student_user_context
    )


def _specialist_plan(capability_name: str = "graduation_progress_agent") -> dict:
    return {
        "status": "completed",
        "plan_id": "plan-specialist-obs-1",
        "user_goal": _GRADUATION_MESSAGE,
        "execution_mode": "single_capability",
        "recommended_autonomy_level": 3,
        "primary_intent": "graduation_progress_check",
        "subtasks": [
            {
                "id": "ask_specialist",
                "title": "Ask the graduation progress specialist",
                "kind": "analyze",
                "capability_name": capability_name,
                "objective": "Determine remaining requirements toward graduation.",
                "depends_on": [],
                "required_context_sections": ["user_message"],
            }
        ],
        "decision_summary": "test",
        "confidence": 0.85,
    }


def _real_pack(**overrides) -> AgentContextPack:
    """A populated (but hand-built, not DB-backed) `AgentContextPack` --
    exactly the shape `context_builder.build_agent_context_pack` produces
    for a `graduation_progress_check` turn once catalog/profile data
    exists, without needing full Mongo fixtures for the `run_supervisor_shadow`-
    level tests below."""
    defaults = dict(
        conversation_id="c1",
        run_id="r1",
        user_id="u1",
        intent="graduation_progress_check",
        user_context={
            "profile": {"degreeProgram": "BSc CS", "track": "cs", "catalogYear": 2024},
            "completedCourses": ["234123", "104031"],
            "completedCourseIds": ["a1", "a2"],
            "dataQuality": {"ok": True},
        },
        academic_context={
            "degreeRequirements": [
                {"id": "r1", "name": "Intro CS", "minCredits": 5.0},
                {"id": "r2", "name": "Math", "minCredits": 10.0},
            ],
            "degreeProgram": {"programCode": "P1", "name": "CS", "catalogYear": 2024},
        },
        assumptions=["Using latest completed-course data on file."],
    )
    defaults.update(overrides)
    return AgentContextPack(**defaults)


async def _seed_user_and_conversation(mongo_database) -> tuple[str, str]:
    email = f"specialist-obs-{uuid.uuid4().hex[:10]}@example.com"
    user = await create_user(mongo_database, email=email, password_hash="hashed")
    user_id = str(user["_id"])
    await create_student_profile(
        mongo_database,
        user_id,
        {
            "institutionId": "technion",
            "programType": "BSc",
            "degreeId": str(ObjectId()),
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
            user_message=_UNRECOGNIZED_MESSAGE,
            trigger_message_id=str(ObjectId()),
            settings=settings,
        )
    ]
    run_doc = await mongo_database[settings.agent_runs_collection].find_one(
        {"userId": ObjectId(user_id)}, sort=[("startedAt", -1)]
    )
    return events, run_doc


# ---------------------------------------------------------------------------
# 1. Specialist observations flag off keeps behavior unchanged.
# ---------------------------------------------------------------------------


async def test_flag_off_keeps_behavior_unchanged() -> None:
    run_input = SupervisorRunInput(user_message=_GRADUATION_MESSAGE, planner_output=_specialist_plan())
    runtime_context = SupervisorRuntimeContext(agent_context_pack=_real_pack())

    output = await run_supervisor_shadow(
        input=run_input, runtime_context=runtime_context, settings=_OBSERVATIONS_OFF_SETTINGS
    )

    record = output.subtask_records[0]
    assert "observationCount" not in record.result_summary
    assert "observationNames" not in record.result_summary
    assert set(record.result_summary) == {
        "agentName",
        "status",
        "confidence",
        "keyFindingCount",
        "warningCount",
        "sourceCount",
        "missingContextCount",
        "hasProposedActions",
        "resultKeys",
        "decisionSummaryPreview",
    }


# ---------------------------------------------------------------------------
# 2. Flag on attaches compact observation metadata in specialist diagnostics.
# ---------------------------------------------------------------------------


async def test_flag_on_attaches_compact_observation_metadata() -> None:
    run_input = SupervisorRunInput(user_message=_GRADUATION_MESSAGE, planner_output=_specialist_plan())
    runtime_context = SupervisorRuntimeContext(agent_context_pack=_real_pack())

    output = await run_supervisor_shadow(
        input=run_input, runtime_context=runtime_context, settings=_OBSERVATIONS_ON_SETTINGS
    )

    record = output.subtask_records[0]
    assert "observationCount" in record.result_summary
    assert "observationNames" in record.result_summary
    assert "observationWarningCount" in record.result_summary
    assert "missingObservationCount" in record.result_summary
    # profile_summary/completed_courses_summary/requirement_bucket_summary are
    # all derivable from the populated `_real_pack()` above.
    assert record.result_summary["observationCount"] >= 3
    assert "profile_summary" in record.result_summary["observationNames"]
    assert "completed_courses_summary" in record.result_summary["observationNames"]


@pytest.mark.parametrize(
    "capability_name", ["graduation_progress_agent", "course_catalog_agent", "requirement_explanation_agent"]
)
async def test_flag_on_works_for_every_specialist_capability(capability_name: str) -> None:
    run_input = SupervisorRunInput(user_message="test", planner_output=_specialist_plan(capability_name))
    runtime_context = SupervisorRuntimeContext(agent_context_pack=_real_pack())

    output = await run_supervisor_shadow(
        input=run_input, runtime_context=runtime_context, settings=_OBSERVATIONS_ON_SETTINGS
    )

    record = output.subtask_records[0]
    assert record.capability_name == capability_name
    assert "observationCount" in record.result_summary


# ---------------------------------------------------------------------------
# 3. Flag on does not change final text/blocks/actions/SSE sequence.
# ---------------------------------------------------------------------------


async def test_flag_on_does_not_change_user_visible_response_or_sse_sequence(mongo_database) -> None:
    user_id_off, conversation_id_off = await _seed_user_and_conversation(mongo_database)
    events_off, _ = await _run_turn(
        mongo_database, user_id=user_id_off, conversation_id=conversation_id_off, settings=_OBSERVATIONS_OFF_SETTINGS
    )

    user_id_on, conversation_id_on = await _seed_user_and_conversation(mongo_database)
    events_on, _ = await _run_turn(
        mongo_database, user_id=user_id_on, conversation_id=conversation_id_on, settings=_OBSERVATIONS_ON_SETTINGS
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
# 4. Missing observations produce warnings but do not fail the live turn.
# ---------------------------------------------------------------------------


async def test_missing_observations_produce_warnings_but_do_not_fail_the_turn() -> None:
    """No `runtime_context` at all -> every observation is `"missing"` --
    the subtask must still complete (never `"failed"`)."""
    run_input = SupervisorRunInput(user_message=_GRADUATION_MESSAGE, planner_output=_specialist_plan())

    output = await run_supervisor_shadow(input=run_input, settings=_OBSERVATIONS_ON_SETTINGS)

    record = output.subtask_records[0]
    assert record.status != "failed"
    assert record.result_summary["missingObservationCount"] >= 1


async def test_missing_observations_do_not_break_a_live_turn(mongo_database) -> None:
    user_id, conversation_id = await _seed_user_and_conversation(mongo_database)

    events, _ = await _run_turn(
        mongo_database, user_id=user_id, conversation_id=conversation_id, settings=_OBSERVATIONS_ON_SETTINGS
    )

    assert not any(e.type == "run.failed" for e in events)
    completed = next(e for e in events if e.type == "message.completed")
    assert completed.text


# ---------------------------------------------------------------------------
# 5. Forbidden observation payloads are sanitized.
# ---------------------------------------------------------------------------


async def test_forbidden_observation_payloads_are_sanitized() -> None:
    hostile_pack = _real_pack(
        academic_context={
            "degreeRequirements": [{"id": "r1", "name": "Intro CS"}],
            "degreeProgram": {"programCode": "P1"},
            "graduationAudit": {
                "creditsEarned": 80.0,
                "creditsRequired": 120.0,
                "chain_of_thought": "secret internal reasoning that must never leak",
            },
        }
    )
    run_input = SupervisorRunInput(user_message=_GRADUATION_MESSAGE, planner_output=_specialist_plan())
    runtime_context = SupervisorRuntimeContext(agent_context_pack=hostile_pack)

    output = await run_supervisor_shadow(
        input=run_input, runtime_context=runtime_context, settings=_OBSERVATIONS_ON_SETTINGS
    )

    record = output.subtask_records[0]
    summary_text = str(record.result_summary)
    assert "secret internal reasoning" not in summary_text
    assert "chain_of_thought" not in summary_text


# ---------------------------------------------------------------------------
# 6. No raw observations stored in retrievalMetadata.
# ---------------------------------------------------------------------------


async def test_no_raw_observations_stored_in_retrieval_metadata(mongo_database) -> None:
    user_id, conversation_id = await _seed_user_and_conversation(mongo_database)

    _events, run_doc = await _run_turn(
        mongo_database, user_id=user_id, conversation_id=conversation_id, settings=_OBSERVATIONS_ON_SETTINGS
    )

    metadata_text = str(run_doc.get("retrievalMetadata") or {})
    for forbidden in (
        "observationCount",
        "observationNames",
        "sampleSnippets",
        "sampleCourseNumbers",
        "sampleBuckets",
        "raw_context",
        "chain_of_thought",
    ):
        assert forbidden not in metadata_text


# ---------------------------------------------------------------------------
# 7. No writes/action proposals created.
# ---------------------------------------------------------------------------


async def test_no_writes_or_action_proposals_created(mongo_database) -> None:
    user_id, conversation_id = await _seed_user_and_conversation(mongo_database)

    events, _ = await _run_turn(
        mongo_database, user_id=user_id, conversation_id=conversation_id, settings=_OBSERVATIONS_ON_SETTINGS
    )

    assert not any(e.type == "action.proposed" for e in events)
    proposals = await mongo_database["agent_action_proposals"].count_documents({"userId": ObjectId(user_id)})
    assert proposals == 0


# ---------------------------------------------------------------------------
# 8. No direct LLM calls introduced.
# ---------------------------------------------------------------------------


async def test_observations_built_with_no_openai_api_key_configured() -> None:
    """`OPENAI_API_KEY=None` throughout this module -- observations are
    still built (they never call an LLM), confirming the observation layer
    itself has no LLM dependency, independent of the specialist's own
    (separately gated) `ReasoningBlock` fallback."""
    assert _OBSERVATIONS_ON_SETTINGS.openai_api_key is None

    run_input = SupervisorRunInput(user_message=_GRADUATION_MESSAGE, planner_output=_specialist_plan())
    runtime_context = SupervisorRuntimeContext(agent_context_pack=_real_pack())

    output = await run_supervisor_shadow(
        input=run_input, runtime_context=runtime_context, settings=_OBSERVATIONS_ON_SETTINGS
    )

    record = output.subtask_records[0]
    assert record.result_summary["observationCount"] >= 1
    # The specialist itself still safely fell back (no LLM available).
    assert record.result_summary["status"] == "skipped"
