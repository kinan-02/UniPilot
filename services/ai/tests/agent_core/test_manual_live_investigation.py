"""Manual, one-case-at-a-time live investigation of the full AGENT_VISION
pipeline (`run_agent_turn`), run explicitly with `pytest -m live -k <case>`.

Not part of the regular suite's intent -- this is a deliberately curated set
of scenarios (cheap sanity checks through the flagship what-if example and a
multi-concern stress case) used to manually walk the real system end to end,
one case at a time, watching `reasoning_block_trace` log lines (per-block
`duration_ms`) and the written `live_eval_logs/manual_investigation-*.json`
for the full prompt/response trail. Each case also records its own
wall-clock `elapsed_seconds` directly into the log entry.

Seeds one throwaway CS student whose every completed course is a REAL
catalog course with its exact name/code/credits (the General CS 4-year
track's own Semester 1 + Semester 2 required set), having just failed
Semester 3's Data Structures 1 -- see the `cs_student` fixture for the full
rationale on why each curated case is genuinely answerable from the
knowledge base rather than a data mismatch. Seeded into the shared dev
Mongo cluster and deleted again after each case -- same pattern as
`test_specialist_subagents_live_eval.py`.

Every case's premise references only entities that actually exist in the
source-of-truth KB (real course codes, the real Inter-Faculty Robotics
Minor rather than the graduate-only "Autonomous Systems and Robotics"
program, the real reserve-duty regulation page) -- so a failure is an agent
bug, not the agent correctly failing to find something fictional.
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
    """A grounded 3rd-semester CS student on the General CS 4-year track
    (`track-computer-science-general-4year`, track code 023023-1-000).

    Every completed course below is a REAL course in the source-of-truth
    knowledge base, with its EXACT catalog name, code, and credit value --
    and the set is exactly the track's own Semester 1 + Semester 2 required
    courses (verified against the track doc's semester-by-semester
    schedule), so the profile is internally coherent, not a plausible-
    looking invention. The student is now in Semester 3 (`2025-1`) and has
    just FAILED that semester's Data Structures 1 (`02340218`, grade 45).

    Why this exact shape makes the curated cases genuinely answerable from
    the KB (not a data mismatch masquerading as an agent bug):
    - Algorithms 1 (`02340247`) requires DS1 (`02340218`) AND Combinatorics
      for CS (`02340141`). This student HAS Combinatorics but FAILED DS1 --
      so "can I take Algorithms next semester?" has one crisp correct
      answer: no, DS1 is an unmet prerequisite (case 04).
    - DS1/Algorithms are offered Winter+Spring but NOT Summer in the real
      offering catalog (`courses_2025_{200,201}` vs `..._202`), so "when
      will DS1 run again?" is a real, checkable answer (case 06).
    - The Inter-Faculty Robotics Minor (`minor-robotics`) needs GPA >= 87
      and >= 60 accrued credits; this student's credit-weighted average is
      ~80.7 over ~39.5 credits, so the minor-feasibility answer is a
      grounded "not yet eligible", not a guess (case 07).

    grade is the Technion 0-100 score (creditsEarned=0 on the failed
    course); gradePoints stays None because the Technion GPA is the
    credit-weighted average of the 0-100 grade, not a US 4.0 scale (the old
    fixture's 3.7-style gradePoints were both wrong for the schema, which
    bounds gradePoints to 0-100, and misleading to the agent).
    """
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

    def _completed(semester: str, number: str, name: str, credits: float, grade: int) -> dict:
        return {
            "userId": user_id,
            "courseId": ObjectId(),
            "courseOfferingId": None,
            "semesterCode": semester,
            "grade": grade,
            "gradePoints": None,
            "creditsEarned": credits,
            "attempt": 1,
            "source": "manual",
            "metadata": {"courseNumber": number, "courseName": name},
            "recordedAt": now,
            "createdAt": now,
            "updatedAt": now,
        }

    completed_course_documents = [
        # Semester 1 (2024-1) -- the track's own required Semester 1 set.
        _completed("2024-1", "01040031", "Infinitesimal Calculus 1M", 5.5, 74),
        _completed("2024-1", "01040166", "Algebra AM", 5.5, 81),
        _completed("2024-1", "02340114", "Introduction to Computer Science M", 4.0, 92),
        _completed("2024-1", "02340129", "Intro to Set Theory and Automata for CS", 3.0, 85),
        _completed("2024-1", "03240033", "Technical English Advanced B", 3.0, 90),
        # Semester 2 (2024-2) -- the track's own required Semester 2 set.
        _completed("2024-2", "01040032", "Infinitesimal Calculus 2M", 5.0, 68),
        _completed("2024-2", "01140071", "Physics 1M", 3.5, 77),
        _completed("2024-2", "02340124", "Introduction to Systems Programming", 4.0, 83),
        _completed("2024-2", "02340125", "Numerical Algorithms", 3.0, 88),
        _completed("2024-2", "02340141", "Combinatorics for Computer Science", 3.0, 79),
        # Semester 3 (2025-1, current) -- FAILED. The flagship "what if I
        # fail X" scenario, and the unmet Algorithms prerequisite.
        _completed("2025-1", "02340218", "Data Structures 1", 0.0, 45),
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
            # The Inter-Faculty Robotics Minor is the real undergraduate minor
            # (minor-robotics: GPA >= 87 and >= 60 credits to be admitted).
            # The "Autonomous Systems and Robotics" program in the KB is a
            # graduate MSc/ME/PhD program, NOT an undergrad minor -- asking
            # about it sent the agent hunting for a nonexistent undergrad
            # minor and looping. This student (~80.7 GPA, ~39.5 credits) is
            # not yet eligible, which is the grounded, checkable answer.
            "I'm a CS student and I want to also complete the Robotics minor -- "
            "is that realistic at this point in my degree?"
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
            # Robotics minor = the real Inter-Faculty Robotics Minor (see case 07);
            # all three concerns here reference real KB entities.
            "I'm a CS student who just failed Data Structures 1, and I'm also considering the "
            "Robotics minor, and I might have a month of reserve duty next "
            "semester -- how does all of this affect my graduation timeline?"
        ),
        user_id=cs_student,
        adapter=adapter,
        live_eval_log=live_eval_log,
    )
