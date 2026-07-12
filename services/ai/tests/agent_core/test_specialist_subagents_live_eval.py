"""Live evaluation of a full turn all the way through real specialist
dispatch: raw message -> Request Understanding -> Planner -> Orchestrator ->
task handler -> a real specialist subagent making a real `get_entity` tool
call against a real (seeded, then cleaned up) student's own Mongo-backed
data -> Monitor -> final answer.

Every other live-eval file stops short of this boundary:
`test_turn_live_eval.py` never goes past the Planner;
`test_task_handler_gap_live_eval.py` calls the classifier/task-handler
directly against hand-built `PlanStep`/`StateEntry` objects, never a real
end-to-end `run_agent_turn` dispatch. Specialist subagents
(Retrieval/Interpretation/Composition) have therefore never been exercised,
until this file, against a real LLM actually calling a real tool against
real data for a real student.

Seeds one throwaway student directly into the shared dev Mongo cluster
(`student_profiles`/`completed_courses`, matching services/api's own
document shape -- `services/ai`'s own repositories here are deliberately
read-only, see `student_profile_repository.py`'s module docstring) before
each test, and deletes it again in a `finally` -- this is a real shared
cluster, not a local ephemeral one, so cleanup is mandatory, not best-effort.

`pytest.mark.live`, skipped without `OPENAI_API_KEY`, deselected by default
-- same as every other live-eval file.
"""

from __future__ import annotations

from datetime import datetime, timezone
from typing import AsyncIterator
from uuid import uuid4

import pytest
from bson import ObjectId

import app.db.mongo as mongo_module
from app.agent_core.reasoning.llm_client import agent_llm_available
from app.agent_core.roles.roster import build_default_role_roster
from app.agent_core.tools.default_registry import build_default_tool_registry
from app.agent_core.turn import run_agent_turn
from app.db.mongo import get_database
from tests.agent_core.live_eval_logging import LiveEvalLog, LoggingLLMAdapter

pytestmark = [
    pytest.mark.live,
    pytest.mark.skipif(not agent_llm_available(), reason="no LLM credentials configured (OPENAI_API_KEY)"),
]


@pytest.fixture(scope="module")
def live_eval_log():
    log = LiveEvalLog(suite_name="specialist_subagents")
    yield log
    log.write()


@pytest.fixture(autouse=True)
async def _fresh_mongo_client_per_test():
    """`get_mongo_client()` memoizes an `AsyncIOMotorClient` at module scope,
    but `pytest.ini` sets `asyncio_default_fixture_loop_scope = function` --
    a fresh event loop per test. Reusing a client created under a prior
    test's (now-closed) loop raises `RuntimeError: Event loop is closed` the
    moment a second Mongo-touching test runs in the same session. Force a
    fresh client per test instead."""
    mongo_module._mongo_client = None
    yield
    if mongo_module._mongo_client is not None:
        mongo_module._mongo_client.close()
        mongo_module._mongo_client = None


@pytest.fixture
def adapter() -> LoggingLLMAdapter:
    return LoggingLLMAdapter()


@pytest.fixture
async def live_test_student() -> AsyncIterator[str]:
    database = await get_database()
    user_id = ObjectId()
    now = datetime.now(timezone.utc)

    profile_document = {
        "userId": user_id,
        "institutionId": "uni-main",
        "facultyId": None,
        "programType": "BSc",
        "degreeId": None,
        "programSlug": None,
        "catalogYear": 2025,
        "currentSemesterCode": "2025-1",
        "academicPath": {},
        "preferences": {},
        "revision": 1,
        "createdAt": now,
        "updatedAt": now,
    }
    completed_course_documents = [
        {
            "userId": user_id,
            "courseId": ObjectId(),
            "courseOfferingId": None,
            "semesterCode": "2024-1",
            "grade": 92,
            "gradePoints": 4.0,
            "creditsEarned": 3.5,
            "attempt": 1,
            "source": "manual",
            "metadata": {"courseNumber": "00140003", "courseName": "Statistics"},
            "recordedAt": now,
            "createdAt": now,
            "updatedAt": now,
        },
        {
            "userId": user_id,
            "courseId": ObjectId(),
            "courseOfferingId": None,
            "semesterCode": "2024-2",
            "grade": 78,
            "gradePoints": 3.0,
            "creditsEarned": 3.0,
            "attempt": 1,
            "source": "manual",
            "metadata": {"courseNumber": "104166", "courseName": "Infinitesimal Calculus 2"},
            "recordedAt": now,
            "createdAt": now,
            "updatedAt": now,
        },
    ]

    await database["student_profiles"].insert_one(profile_document)
    await database["completed_courses"].insert_many(completed_course_documents)
    try:
        yield str(user_id)
    finally:
        await database["student_profiles"].delete_one({"userId": user_id})
        await database["completed_courses"].delete_many({"userId": user_id})


def _student_data_tool_calls(state, user_id: str, entity_types: tuple[str, ...]):
    return [
        record
        for entry in state.entries
        for record in entry.tool_audit_trail
        if record.tool_name == "get_entity"
        and record.arguments.get("entity_type") in entity_types
        and record.arguments.get("entity_id") == user_id
    ]


async def test_live_retrieval_subagent_fetches_the_real_seeded_students_completed_courses(
    adapter: LoggingLLMAdapter, live_eval_log: LiveEvalLog, live_test_student: str
) -> None:
    question = "What courses have I already completed, and what grades did I get in each?"
    understanding, state, final_entry, clarification_question = await run_agent_turn(
        original_user_message=question,
        user_id=live_test_student,
        llm_adapter=adapter,
        role_roster=build_default_role_roster(),
        tool_registry=build_default_tool_registry(),
        plan_id=f"live-eval-specialist-completed-courses-{uuid4()}",
    )
    live_eval_log.record_case(
        "retrieval_fetches_real_completed_courses",
        adapter,
        understanding=understanding,
        state=state,
        final_entry=final_entry,
        clarification_question=clarification_question,
    )

    assert understanding.in_scope

    # The property this test exists to prove: a real specialist subagent,
    # driven by a real LLM plan (not a hand-built PlanStep/StateEntry -- every
    # prior live-eval file stops before this boundary), actually called
    # get_entity against this exact seeded student's own completed_courses
    # and got real data back.
    completed_courses_calls = _student_data_tool_calls(state, live_test_student, ("completed_courses",))
    assert completed_courses_calls, "expected at least one get_entity(completed_courses) call in the real plan"
    assert any(record.output_ok for record in completed_courses_calls), (
        "expected a successful lookup against the seeded test student's own user_id"
    )

    if final_entry is not None:
        assert final_entry.status == "succeeded"
        assert final_entry.data.get("answer_text")


async def test_live_full_turn_reasons_over_the_real_seeded_students_profile_and_courses(
    adapter: LoggingLLMAdapter, live_eval_log: LiveEvalLog, live_test_student: str
) -> None:
    question = "Based on what I've completed so far, am I on track for my degree?"
    understanding, state, final_entry, clarification_question = await run_agent_turn(
        original_user_message=question,
        user_id=live_test_student,
        llm_adapter=adapter,
        role_roster=build_default_role_roster(),
        tool_registry=build_default_tool_registry(),
        plan_id=f"live-eval-specialist-progress-{uuid4()}",
    )
    live_eval_log.record_case(
        "reasoning_over_real_student_profile",
        adapter,
        understanding=understanding,
        state=state,
        final_entry=final_entry,
        clarification_question=clarification_question,
    )

    assert understanding.in_scope
    student_data_calls = _student_data_tool_calls(state, live_test_student, ("student_profile", "completed_courses"))
    assert student_data_calls, "expected the plan to actually fetch this student's own profile/courses, not just the catalog"

    if final_entry is None:
        assert clarification_question, "if not answered outright, must at least surface a real clarification question"
    else:
        assert final_entry.status in ("succeeded", "partial")
        assert final_entry.data.get("answer_text")
