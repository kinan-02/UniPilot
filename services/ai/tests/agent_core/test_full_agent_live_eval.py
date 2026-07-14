"""Live evaluation of the entire agent system (End-to-End), against a real,
seeded student with a realistic full profile and real, verified course/
track data -- not a nonexistent user_id ("student_123") and hypothetical
course names ("Machine Learning") the real catalog/wiki can never resolve.

This suite tests `run_agent_turn` directly, starting from a raw user
message, through Request Understanding, Planner, Task Dispatch, and
Synthesis. It exercises the fully wired loop and writes all intermediate
steps and LLM calls to the live_eval_logs.

Seeds one throwaway student directly into the shared dev Mongo cluster
before each test (same pattern as `test_specialist_subagents_live_eval.py`),
using real, independently-verified course codes (`docs/agent/
HIGHER_LEVEL_TOOLS.md`'s own design notes, `test_check_eligibility.py`/
`test_get_course_profile.py`'s own verified real-data facts):
- "00440148" (has both a catalog entry and a wiki page) requires BOTH
  "00440105" and "00440140" (AND logic), and belongs to
  "track-electrical-engineering" among other tracks.
- "00140008" has zero prerequisites and a reliable Winter/Spring (never
  Summer) offering pattern.
The seeded student has completed "00440105" but NOT "00440140" --
a genuine, real partial-eligibility case for "00440148", not a contrived
one.
"""

from __future__ import annotations

from datetime import datetime, timezone
from typing import AsyncIterator

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
    log = LiveEvalLog(suite_name="full_agent_e2e")
    yield log
    log.write()


@pytest.fixture(autouse=True)
async def _fresh_mongo_client_per_test():
    """`get_mongo_client()` memoizes an `AsyncIOMotorClient` at module scope,
    but `pytest.ini` sets `asyncio_default_fixture_loop_scope = function` --
    a fresh event loop per test. Reusing a client created under a prior
    test's (now-closed) loop raises `RuntimeError: Event loop is closed`."""
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
    """A realistic, fully-declared Electrical Engineering student -- unlike
    the specialist_subagents live-eval file's deliberately-undeclared
    profile, this one exercises the "real data, real determination" path
    rather than the "confirmed-absent fact" path."""
    database = await get_database()
    user_id = ObjectId()
    now = datetime.now(timezone.utc)

    profile_document = {
        "userId": user_id,
        "institutionId": "uni-main",
        "facultyId": None,
        "programType": "BSc",
        "degreeId": None,
        # A specific, unambiguous track slug (not the bare "electrical-engineering",
        # which maps to several real tracks) so the graduation-audit scenario can
        # actually synthesise a progress report instead of stopping to ask which
        # track applies. The other scenarios key off course codes, not the track.
        "programSlug": "track-electrical-engineering",
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
        {
            # One of "00440148"'s two AND-prerequisites -- completed.
            "userId": user_id,
            "courseId": ObjectId(),
            "courseOfferingId": None,
            "semesterCode": "2024-2",
            "grade": 88,
            "gradePoints": 4.0,
            "creditsEarned": 3.0,
            "attempt": 1,
            "source": "manual",
            "metadata": {"courseNumber": "00440105", "courseName": "Circuit Theory"},
            "recordedAt": now,
            "createdAt": now,
            "updatedAt": now,
        },
        # "00440140" (the other AND-prerequisite) is deliberately NOT
        # completed -- a genuine, real partial-eligibility case for
        # "00440148", not a contrived one.
    ]

    await database["student_profiles"].insert_one(profile_document)
    await database["completed_courses"].insert_many(completed_course_documents)
    try:
        yield str(user_id)
    finally:
        await database["student_profiles"].delete_one({"userId": user_id})
        await database["completed_courses"].delete_many({"userId": user_id})


async def _run_full_turn(message: str, adapter: LoggingLLMAdapter, user_id: str, *, block_prefix: str):
    role_roster = build_default_role_roster()
    tool_registry = build_default_tool_registry()

    understanding, state, final_entry, clarification = await run_agent_turn(
        original_user_message=message,
        user_id=user_id,
        llm_adapter=adapter,
        role_roster=role_roster,
        tool_registry=tool_registry,
        plan_id=block_prefix,
        max_planner_invocations=5,
    )
    return understanding, state, final_entry, clarification


def _record(live_eval_log, case_name, adapter, understanding, state, final_entry, clarification):
    live_eval_log.record_case(
        case_name,
        adapter,
        understanding=understanding,
        state_entries=[e.model_dump(mode="json") for e in state.entries] if state else None,
        final_entry=final_entry.model_dump(mode="json") if final_entry else None,
        clarification=clarification,
    )


async def test_completed_courses_status_check(
    adapter: LoggingLLMAdapter, live_eval_log: LiveEvalLog, live_test_student: str
) -> None:
    """Simple retrieval sanity check against real Mongo-backed student data."""
    message = "What courses have I completed so far, and what's my declared program?"
    understanding, state, final_entry, clarification = await _run_full_turn(
        message, adapter, live_test_student, block_prefix="eval-e2e-status-check"
    )
    _record(live_eval_log, "completed_courses_status_check", adapter, understanding, state, final_entry, clarification)

    assert understanding.in_scope
    assert final_entry is not None, f"Agent failed to reach synthesis. Clarification: {clarification}"
    assert "answer_text" in final_entry.data


async def test_course_eligibility_check(
    adapter: LoggingLLMAdapter, live_eval_log: LiveEvalLog, live_test_student: str
) -> None:
    """Real, partial-prerequisite eligibility determination -- the student
    has completed one of "00440148"'s two required courses, not both."""
    message = "Am I eligible to take course 00440148 next semester?"
    understanding, state, final_entry, clarification = await _run_full_turn(
        message, adapter, live_test_student, block_prefix="eval-e2e-eligibility"
    )
    _record(live_eval_log, "course_eligibility_check", adapter, understanding, state, final_entry, clarification)

    assert understanding.in_scope
    assert final_entry is not None, f"Agent failed to reach synthesis. Clarification: {clarification}"
    assert "answer_text" in final_entry.data


async def test_course_disruption_simulation(
    adapter: LoggingLLMAdapter, live_eval_log: LiveEvalLog, live_test_student: str
) -> None:
    """The flagship simulate_course_disruption use case (AGENT_VISION.md
    §10), against a real completed course and a real dependent course."""
    message = "If I fail course 00440105 this semester, how would that affect my ability to take course 00440148 later?"
    understanding, state, final_entry, clarification = await _run_full_turn(
        message, adapter, live_test_student, block_prefix="eval-e2e-disruption"
    )
    _record(live_eval_log, "course_disruption_simulation", adapter, understanding, state, final_entry, clarification)

    assert understanding.in_scope
    assert final_entry is not None, f"Agent failed to reach synthesis. Clarification: {clarification}"
    assert "answer_text" in final_entry.data


async def test_policy_interpretation_question(
    adapter: LoggingLLMAdapter, live_eval_log: LiveEvalLog, live_test_student: str
) -> None:
    """A generic, real wiki-backed policy question -- exercises
    get_policy_answer against the real (now-reachable) wiki index."""
    message = "What is the retake policy if I fail a course?"
    understanding, state, final_entry, clarification = await _run_full_turn(
        message, adapter, live_test_student, block_prefix="eval-e2e-policy"
    )
    _record(live_eval_log, "policy_interpretation_question", adapter, understanding, state, final_entry, clarification)

    assert understanding.in_scope
    assert final_entry is not None, f"Agent failed to reach synthesis. Clarification: {clarification}"
    assert "answer_text" in final_entry.data


async def test_graduation_progress_audit(
    adapter: LoggingLLMAdapter, live_eval_log: LiveEvalLog, live_test_student: str
) -> None:
    """audit_graduation_progress against a real track, real completed
    courses."""
    message = "How am I progressing toward my Electrical Engineering track requirements?"
    understanding, state, final_entry, clarification = await _run_full_turn(
        message, adapter, live_test_student, block_prefix="eval-e2e-audit"
    )
    _record(live_eval_log, "graduation_progress_audit", adapter, understanding, state, final_entry, clarification)

    assert understanding.in_scope
    # The seeded student's programSlug ("electrical-engineering") maps to several
    # real tracks (track-electrical-engineering, -mathematics, -physics) with no
    # specific one declared, so asking WHICH track is a legitimate outcome -- the
    # same either/or shape test_action_boundary_challenge already uses. (An
    # earlier version demanded a synthesis and only "passed" on a fabricated
    # "could not be located" answer.)
    assert final_entry is not None or clarification is not None, (
        "Agent should either audit progress in synthesis, or ask a clarifying question when the "
        "declared program maps to multiple tracks with none specified -- either is valid."
    )
    if final_entry is not None:
        assert "answer_text" in final_entry.data


async def test_action_boundary_challenge(
    adapter: LoggingLLMAdapter, live_eval_log: LiveEvalLog, live_test_student: str
) -> None:
    """A challenge testing the boundary of what the agent can actually DO --
    using a REAL, resolvable course this time, so "can't find the course"
    is no longer a confound for "can't waive a prerequisite"."""
    message = "Please register me for course 00440148 next semester, and waive its prerequisite requirement for me."
    understanding, state, final_entry, clarification = await _run_full_turn(
        message, adapter, live_test_student, block_prefix="eval-e2e-action-boundary"
    )
    _record(live_eval_log, "action_boundary_challenge", adapter, understanding, state, final_entry, clarification)

    assert understanding.in_scope
    assert understanding.implies_action_request, "RU should have caught the action request boundary."
    assert final_entry is not None or clarification is not None, (
        "Agent should either gracefully explain the boundary in synthesis, or ask a real clarifying "
        "question -- either is a valid way to avoid silently performing/fabricating the action."
    )
