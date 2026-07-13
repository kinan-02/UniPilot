"""Manual, one-case-at-a-time live investigation of the full AGENT_VISION
pipeline (`run_agent_turn`), run explicitly with `pytest -m live -k <case>`.

Not part of the regular suite's intent -- this is a deliberately curated set
of scenarios (cheap sanity checks through the flagship what-if example and a
multi-concern stress case) used to manually walk the real system end to end,
one case at a time, watching `reasoning_block_trace` log lines (per-block
`duration_ms`) and the written `live_eval_logs/manual_investigation-*.json`
for the full prompt/response trail. Each case also records its own
wall-clock `elapsed_seconds` directly into the log entry.

Seeds one throwaway, realistic CS student (real program: `023023-1-000`,
"Computer Science" 4-year general track, wiki slug
`track-computer-science-general-4year`; real completed courses including
`02340218` "Data Structures 1") directly into the shared dev Mongo cluster,
deleted again after each case -- same pattern as
`test_specialist_subagents_live_eval.py`.
"""

from __future__ import annotations

import asyncio
import time
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

_CS_PROGRAM_ID = ObjectId("6a466a691f64e5fd20129474")  # 023023-1-000, real dev-cluster document
_CS_PROGRAM_SLUG = "track-computer-science-general-4year"


@pytest.fixture(scope="module")
def live_eval_log():
    log = LiveEvalLog(suite_name="manual_investigation")
    yield log
    log.write()


@pytest.fixture(autouse=True)
async def _fresh_mongo_client_per_test():
    """See test_specialist_subagents_live_eval.py's identical fixture --
    `get_mongo_client()` memoizes a client tied to a prior test's now-closed
    event loop otherwise (`pytest.ini` uses function-scoped event loops)."""
    mongo_module._mongo_client = None
    yield
    if mongo_module._mongo_client is not None:
        mongo_module._mongo_client.close()
        mongo_module._mongo_client = None


@pytest.fixture
def adapter() -> LoggingLLMAdapter:
    return LoggingLLMAdapter()


@pytest.fixture
async def cs_student() -> AsyncIterator[str]:
    """A real 3rd-semester CS student who just failed Data Structures 1
    (course `02340218`, a real document in the dev cluster) -- the exact
    setup the flagship "what happens if I fail X" scenario needs, plus two
    of DS1's own real prerequisite course numbers already passed."""
    database = await get_database()
    user_id = ObjectId()
    now = datetime.now(timezone.utc)

    profile_document = {
        "userId": user_id,
        "institutionId": "technion",
        "facultyId": "faculty-computer-science",
        "programType": "BSc",
        "degreeId": _CS_PROGRAM_ID,
        "programSlug": _CS_PROGRAM_SLUG,
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
            "grade": 88,
            "gradePoints": 3.7,
            "creditsEarned": 3.5,
            "attempt": 1,
            "source": "manual",
            "metadata": {"courseNumber": "02340114", "courseName": "Introduction to Computer Science"},
            "recordedAt": now,
            "createdAt": now,
            "updatedAt": now,
        },
        {
            "userId": user_id,
            "courseId": ObjectId(),
            "courseOfferingId": None,
            "semesterCode": "2024-1",
            "grade": 85,
            "gradePoints": 3.7,
            "creditsEarned": 3.5,
            "attempt": 1,
            "source": "manual",
            "metadata": {"courseNumber": "02340118", "courseName": "Computer Organization and Programming"},
            "recordedAt": now,
            "createdAt": now,
            "updatedAt": now,
        },
        {
            "userId": user_id,
            "courseId": ObjectId(),
            "courseOfferingId": None,
            "semesterCode": "2024-2",
            "grade": 79,
            "gradePoints": 3.0,
            "creditsEarned": 5.0,
            "attempt": 1,
            "source": "manual",
            "metadata": {"courseNumber": "02340141", "courseName": "Infinitesimal Calculus"},
            "recordedAt": now,
            "createdAt": now,
            "updatedAt": now,
        },
        {
            "userId": user_id,
            "courseId": ObjectId(),
            "courseOfferingId": None,
            "semesterCode": "2024-2",
            "grade": 81,
            "gradePoints": 3.3,
            "creditsEarned": 3.5,
            "attempt": 1,
            "source": "manual",
            "metadata": {"courseNumber": "02340124", "courseName": "Discrete Mathematics"},
            "recordedAt": now,
            "createdAt": now,
            "updatedAt": now,
        },
        {
            # The failure the flagship scenario (case 5) is built around --
            # a real, currently-offered course (02340218, "Data Structures
            # 1", semestersOffered=[200, 201] per the real dev-cluster doc).
            "userId": user_id,
            "courseId": ObjectId(),
            "courseOfferingId": None,
            "semesterCode": "2025-1",
            "grade": 45,
            "gradePoints": 0.0,
            "creditsEarned": 0.0,
            "attempt": 1,
            "source": "manual",
            "metadata": {"courseNumber": "02340218", "courseName": "Data Structures 1"},
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


async def _run_and_record(
    case_name: str,
    message: str,
    *,
    user_id: str,
    adapter: LoggingLLMAdapter,
    live_eval_log: LiveEvalLog,
):
    role_roster = build_default_role_roster()
    tool_registry = build_default_tool_registry()

    print(f"\n--- starting {case_name} ---", flush=True)
    start = time.perf_counter()
    try:
        understanding, state, final_entry, clarification = await asyncio.wait_for(
            run_agent_turn(
                original_user_message=message,
                user_id=user_id,
                llm_adapter=adapter,
                role_roster=role_roster,
                tool_registry=tool_registry,
                plan_id=f"manual-{case_name}",
                max_planner_invocations=6,
            ),
            timeout=300,
        )
    except asyncio.TimeoutError:
        elapsed = time.perf_counter() - start
        live_eval_log.record_case(
            case_name,
            adapter,
            message=message,
            elapsed_seconds=round(elapsed, 2),
            timed_out=True,
        )
        print(f"=== {case_name} TIMED OUT after {elapsed:.1f}s ({len(adapter.calls)} LLM calls made) ===", flush=True)
        raise
    elapsed = time.perf_counter() - start

    live_eval_log.record_case(
        case_name,
        adapter,
        message=message,
        elapsed_seconds=round(elapsed, 2),
        understanding=understanding,
        state_entries=[e.model_dump(mode="json") for e in state.entries] if state else None,
        final_entry=final_entry.model_dump(mode="json") if final_entry else None,
        clarification=clarification,
    )

    print(f"\n=== {case_name} ({elapsed:.1f}s, {len(adapter.calls)} LLM calls) ===")
    print(f"Q: {message}")
    if not understanding.in_scope:
        # Boundary Handler composes the actual user-facing text now --
        # understanding.decline_reason is only the internal reason it was
        # handed, not what the student sees.
        boundary_text = final_entry.data.get("answer_text", "") if final_entry else None
        print(f"DECLINED (in_scope=False, reason={understanding.decline_reason!r}): {boundary_text}")
    elif final_entry is not None:
        print(f"A [{final_entry.status}]: {final_entry.data.get('answer_text', '')[:500]}")
    else:
        print(f"CLARIFICATION NEEDED: {clarification}")

    return understanding, state, final_entry, clarification, elapsed


@pytest.mark.asyncio
async def test_case_01_simple_retrieval(cs_student, adapter, live_eval_log) -> None:
    await _run_and_record(
        "case_01_simple_retrieval",
        "What are the prerequisites for Data Structures 1?",
        user_id=cs_student,
        adapter=adapter,
        live_eval_log=live_eval_log,
    )


@pytest.mark.asyncio
async def test_case_02_out_of_scope(cs_student, adapter, live_eval_log) -> None:
    understanding, *_ = await _run_and_record(
        "case_02_out_of_scope",
        "What's a good pizza place near the Technion campus?",
        user_id=cs_student,
        adapter=adapter,
        live_eval_log=live_eval_log,
    )
    assert not understanding.in_scope


@pytest.mark.asyncio
async def test_case_03_action_boundary(cs_student, adapter, live_eval_log) -> None:
    understanding, state, final_entry, clarification, _ = await _run_and_record(
        "case_03_action_boundary",
        "Please register me for Data Structures 1 next semester and waive the prerequisite requirement for me.",
        user_id=cs_student,
        adapter=adapter,
        live_eval_log=live_eval_log,
    )
    # Current architecture (post docs/agent's boundary_handler layer): a sole
    # ask that's an administrative action outside the system's capability
    # (register/waive) is declined via in_scope=False + decline_reason --
    # implies_action_request resets to False alongside it, same as every
    # other field on the in_scope=False path. The Boundary Handler then
    # composes final_entry's answer_text from that reason.
    assert understanding.in_scope is False
    assert understanding.decline_reason
    assert final_entry is not None, "Boundary Handler should have produced a final answer."


@pytest.mark.asyncio
async def test_case_04_ambiguous_clarification(cs_student, adapter, live_eval_log) -> None:
    await _run_and_record(
        "case_04_ambiguous_clarification",
        "Can I take Algorithms next semester?",
        user_id=cs_student,
        adapter=adapter,
        live_eval_log=live_eval_log,
    )


@pytest.mark.asyncio
async def test_case_05_flagship_fail_course(cs_student, adapter, live_eval_log) -> None:
    understanding, state, final_entry, clarification, _ = await _run_and_record(
        "case_05_flagship_fail_course",
        (
            "I just failed Data Structures 1. What are the rules for retaking it, "
            "and will it block me from taking more advanced courses next semester?"
        ),
        user_id=cs_student,
        adapter=adapter,
        live_eval_log=live_eval_log,
    )
    assert understanding.in_scope
    assert final_entry is not None, f"Expected synthesis to complete; clarification={clarification!r}"


@pytest.mark.asyncio
async def test_case_06_offering_pattern(cs_student, adapter, live_eval_log) -> None:
    await _run_and_record(
        "case_06_offering_pattern",
        "If I don't retake Data Structures 1 next semester, when will it run again?",
        user_id=cs_student,
        adapter=adapter,
        live_eval_log=live_eval_log,
    )


@pytest.mark.asyncio
async def test_case_07_minor_feasibility(cs_student, adapter, live_eval_log) -> None:
    await _run_and_record(
        "case_07_minor_feasibility",
        (
            "I'm a CS student and I want to also complete the Autonomous Systems and "
            "Robotics minor -- is that realistic at this point in my degree?"
        ),
        user_id=cs_student,
        adapter=adapter,
        live_eval_log=live_eval_log,
    )


@pytest.mark.asyncio
async def test_case_08_reserve_duty_accommodation(cs_student, adapter, live_eval_log) -> None:
    await _run_and_record(
        "case_08_reserve_duty_accommodation",
        "I have a month of reserve duty (מילואים) next semester -- what accommodations exist for my course load?",
        user_id=cs_student,
        adapter=adapter,
        live_eval_log=live_eval_log,
    )


@pytest.mark.asyncio
async def test_case_09_open_gap_temporary_exception(cs_student, adapter, live_eval_log) -> None:
    await _run_and_record(
        "case_09_open_gap_temporary_exception",
        "Is there any special exam accommodation in place this semester?",
        user_id=cs_student,
        adapter=adapter,
        live_eval_log=live_eval_log,
    )


@pytest.mark.asyncio
async def test_case_10_multi_concern_stress(cs_student, adapter, live_eval_log) -> None:
    await _run_and_record(
        "case_10_multi_concern_stress",
        (
            "I'm a CS student who just failed Data Structures 1, and I'm also considering the "
            "Autonomous Systems and Robotics minor, and I might have a month of reserve duty next "
            "semester -- how does all of this affect my graduation timeline?"
        ),
        user_id=cs_student,
        adapter=adapter,
        live_eval_log=live_eval_log,
    )
