"""End-to-end orchestrator tests for the agent service (post-extraction).

These replace the old `api`-side HTTP integration tests
(`test_agent_graduation_workflow.py`, `test_agent_course_question_workflow.py`,
`test_agent_semester_planning_workflow.py`,
`test_agent_transcript_import_workflow.py`), which drove the same logic
through `api`'s HTTP layer before `orchestrator.run_agent_turn` moved here.

`run_agent_turn` is now called directly against a mongomock database (the
agent service's own direct connection). The three computation calls that
intentionally stay in `api` (`graduation-audit`, `semester-plan-options`,
`course-requirement-contribution`) are mocked at the
`app.clients.internal_api_client` boundary — the same boundary a real
`api` process would satisfy over HTTP.
"""

from __future__ import annotations

import pytest
from bson import ObjectId

from app.agent.orchestrator import run_agent_turn
from app.config import Settings
from app.repositories.agent_conversation_repository import create_agent_conversation
from app.repositories.completed_course_repository import create_completed_course
from app.repositories.student_profile_repository import create_student_profile
from app.repositories.user_repository import create_user
from tests.fixtures.completed_course_fixtures import KNOWN_COURSE_NUMBER, seed_production_course_fixture
from tests.fixtures.graduation_progress_fixtures import seed_graduation_progress_fixtures

# Explicit settings (not env/.env-derived) guarantee no LLM is configured,
# regardless of what a developer's local .env happens to contain (see
# services/api/docs — pydantic-settings falls back to reading `.env` for any
# field not present in os.environ, so `monkeypatch.delenv` alone is not
# enough). Every `run_agent_turn` call below passes this explicitly.
_NO_LLM_SETTINGS = Settings(**{"OPENAI_API_KEY": None})


@pytest.fixture(autouse=True)
def _mock_student_user_context(monkeypatch):
    """`api`'s `/internal/user-context/users/{id}` is mocked at the retrieval boundary.

    Every workflow test below goes through `context_builder`, which always
    needs at least the completed-courses summary; without this, tests would
    attempt a real HTTP call to a non-existent `api` host.
    """
    from app.retrieval import mongodb_user_retriever

    async def _fake_fetch_student_user_context(*, user_id: str, settings=None):
        return {"completed_courses": [], "data_quality": {"warnings": [], "ok": True}}

    monkeypatch.setattr(
        mongodb_user_retriever, "fetch_student_user_context", _fake_fetch_student_user_context
    )


async def _seed_user_with_profile(mongo_database, *, program_id: str) -> tuple[str, str]:
    user = await create_user(mongo_database, email="agent-turn@example.com", password_hash="hashed")
    user_id = str(user["_id"])
    await create_student_profile(
        mongo_database,
        user_id,
        {
            "institutionId": "technion",
            "programType": "BSc",
            "degreeId": program_id,
            "catalogYear": 2025,
            "currentSemesterCode": "2025-1",
            "academicPath": {"trackSlug": "track-data-information-engineering"},
        },
    )
    conversation = await create_agent_conversation(mongo_database, user_id=user_id, title="Test")
    return user_id, str(conversation["id"])


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


async def test_graduation_progress_workflow_produces_summary(mongo_database, monkeypatch):
    from app.services import graduation_audit_client

    monkeypatch.setattr(
        graduation_audit_client, "fetch_graduation_audit", lambda **_: _fake_graduation_audit_coro()
    )

    fixtures = await seed_graduation_progress_fixtures(mongo_database)
    user_id, conversation_id = await _seed_user_with_profile(mongo_database, program_id=fixtures["programId"])
    await create_completed_course(
        mongo_database,
        user_id,
        {
            "courseId": fixtures["courseBId"],
            "semesterCode": "2024-2",
            "grade": 88,
            "gradePoints": 88,
            "creditsEarned": 3.5,
            "attempt": 1,
        },
    )

    events = [
        event
        async for event in run_agent_turn(
            mongo_database,
            user_id=user_id,
            conversation_id=conversation_id,
            user_message="What am I missing to graduate?",
            trigger_message_id=str(ObjectId()),
            settings=_NO_LLM_SETTINGS,
        )
    ]

    completed = [e for e in events if e.type == "message.completed"]
    assert completed, [e.type for e in events]
    assert "credits" in completed[0].text.lower() or "graduation" in completed[0].text.lower()
    assert any(e.type == "run.completed" for e in events)
    assert not any(e.type == "run.failed" for e in events)


async def test_course_question_workflow_answers_contribution_question(mongo_database, monkeypatch):
    from app.retrieval import catalog_retriever

    monkeypatch.setattr(
        catalog_retriever,
        "fetch_course_requirement_contribution",
        lambda **_: _fake_contribution_coro(),
    )

    fixtures = await seed_graduation_progress_fixtures(mongo_database)
    user_id, conversation_id = await _seed_user_with_profile(mongo_database, program_id=fixtures["programId"])

    events = [
        event
        async for event in run_agent_turn(
            mongo_database,
            user_id=user_id,
            conversation_id=conversation_id,
            user_message=f"Does course {fixtures['courseBNumber']} count toward my degree?",
            trigger_message_id=str(ObjectId()),
            settings=_NO_LLM_SETTINGS,
        )
    ]

    completed = [e for e in events if e.type == "message.completed"]
    assert completed
    assert not any(e.type == "run.failed" for e in events)
    blocks = [e.block for e in events if e.type == "structured_output" and e.block]
    assert blocks  # course question workflow always attaches at least one structured block


async def test_course_question_workflow_requires_course_number(mongo_database):
    fixtures = await seed_graduation_progress_fixtures(mongo_database)
    user_id, conversation_id = await _seed_user_with_profile(mongo_database, program_id=fixtures["programId"])

    events = [
        event
        async for event in run_agent_turn(
            mongo_database,
            user_id=user_id,
            conversation_id=conversation_id,
            user_message="Can I take this course next semester?",
            trigger_message_id=str(ObjectId()),
            settings=_NO_LLM_SETTINGS,
        )
    ]

    completed = [e for e in events if e.type == "message.completed"]
    assert completed
    assert "course number" in completed[0].text.lower()


async def test_transcript_import_workflow_requires_upload(mongo_database):
    user = await create_user(mongo_database, email="agent-transcript-nofile@example.com", password_hash="x")
    user_id = str(user["_id"])
    conversation = await create_agent_conversation(mongo_database, user_id=user_id, title="Test")

    events = [
        event
        async for event in run_agent_turn(
            mongo_database,
            user_id=user_id,
            conversation_id=str(conversation["id"]),
            user_message="Import my transcript",
            trigger_message_id=str(ObjectId()),
            settings=_NO_LLM_SETTINGS,
        )
    ]

    completed = [e for e in events if e.type == "message.completed"]
    assert completed
    assert "upload" in completed[0].text.lower()


async def test_transcript_import_workflow_proposes_action_with_attachment(mongo_database):
    course = await seed_production_course_fixture(mongo_database)
    user = await create_user(mongo_database, email="agent-transcript@example.com", password_hash="x")
    user_id = str(user["_id"])
    conversation = await create_agent_conversation(mongo_database, user_id=user_id, title="Test")

    parse_preview = {
        "courses": [
            {
                "courseNumber": course["courseNumber"],
                "semesterCode": "2024-2",
                "grade": 88,
                "creditsEarned": 4,
                "confidence": 0.95,
                "title": "Discrete Math",
                "warnings": [],
            }
        ],
        "warnings": [],
        "parseMetadata": {"pageCount": 1},
    }
    attachments = [{"type": "transcript_pdf", "filename": "transcript.pdf", "parsePreview": parse_preview}]

    events = [
        event
        async for event in run_agent_turn(
            mongo_database,
            user_id=user_id,
            conversation_id=str(conversation["id"]),
            user_message="Import my transcript",
            trigger_message_id=str(ObjectId()),
            message_attachments=attachments,
            settings=_NO_LLM_SETTINGS,
        )
    ]

    action_events = [e for e in events if e.type == "action.proposed"]
    assert action_events, [e.type for e in events]
    assert action_events[0].action.action_type == "import_completed_courses"
    assert KNOWN_COURSE_NUMBER == course["courseNumber"]
    assert not any(e.type == "run.failed" for e in events)


async def _fake_graduation_audit_coro():
    return _fake_graduation_audit()


async def _fake_contribution_coro():
    return {
        "degreeProgram": {"programCode": "009216-1-000", "name": "Test Program"},
        "contribution": {
            "countsTowardDegree": True,
            "isMandatoryCurriculum": False,
            "eligiblePools": [],
            "referencedInPools": [],
            "claimingPool": None,
            "summary": "This course counts toward your degree.",
            "status": "matched",
        },
    }
