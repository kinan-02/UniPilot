"""Integration tests for Controlled Planner-first live execution (post-Phase-9).

Confirms `run_agent_turn` genuinely dispatches to the Planner-first-live
path (via `app.agent.planner_first_live`) instead of the deterministic
`task_planner.py` + `workflow.run()` path when every gate passes, and falls
back cleanly to the exact same deterministic behavior when any gate is
missing (flag off, no manifest approval, wrong readiness level).
"""

from __future__ import annotations

import json
import uuid
from pathlib import Path

import pytest
from bson import ObjectId

from app.agent.orchestrator import run_agent_turn
from app.config import Settings
from app.repositories.agent_conversation_repository import create_agent_conversation
from app.repositories.student_profile_repository import create_student_profile
from app.repositories.user_repository import create_user
from tests.fixtures.completed_course_fixtures import seed_production_course_fixture
from tests.fixtures.graduation_progress_fixtures import seed_graduation_progress_fixtures

_MESSAGE = "What am I missing to graduate?"

_BASE_KWARGS = {
    "OPENAI_API_KEY": None,
    "AGENT_PLANNER_ENABLED": True,
    "AGENT_SUPERVISOR_ENABLED": True,
    "AGENT_SUPERVISOR_REAL_HANDLERS_ENABLED": True,
    # Explicit, not relied-on-default: keep the separate Phase 9 workflow
    # promotion axis off so this file only ever exercises Planner-first-live.
    "AGENT_SUPERVISOR_POST_CONTEXT_COMPARE_ENABLED": False,
    "AGENT_SUPERVISOR_PROMOTION_ENABLED": False,
    "AGENT_PLANNER_FIRST_LIVE_WORKFLOWS": "graduation_progress_workflow",
}


def _manifest_path(tmp_path: Path, *, level: str = "ready_for_broader_promotion") -> str:
    manifest = {
        "schemaVersion": "1",
        "reviewedAt": "2026-07-06T00:00:00Z",
        "reviewedBy": "test-reviewer",
        "candidates": [
            {
                "candidateId": "planner_first_live.graduation_progress_workflow",
                "level": level,
                "approved": True,
                "scope": ["graduation_progress_workflow"],
                "expiresAt": "2099-01-01T00:00:00Z",
            }
        ],
    }
    path = tmp_path / "manifest.json"
    path.write_text(json.dumps(manifest), encoding="utf-8")
    return str(path)


def _live_eligible_settings(tmp_path: Path, **overrides: object) -> Settings:
    kwargs = {
        **_BASE_KWARGS,
        "AGENT_PLANNER_FIRST_LIVE_ENABLED": True,
        "AGENT_RUNTIME_READINESS_GATE_ENABLED": True,
        "AGENT_RUNTIME_READINESS_MANIFEST_PATH": _manifest_path(tmp_path),
    }
    kwargs.update(overrides)
    return Settings(**kwargs)


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

    monkeypatch.setattr(graduation_audit_client, "fetch_graduation_audit", lambda **_: _fake_graduation_audit_coro())


async def _seed_graduation_user(mongo_database) -> tuple[str, str]:
    fixtures = await seed_graduation_progress_fixtures(mongo_database)
    email = f"planner-first-live-{uuid.uuid4().hex[:10]}@example.com"
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


async def test_planner_first_live_used_when_every_gate_passes(mongo_database, tmp_path):
    user_id, conversation_id = await _seed_graduation_user(mongo_database)

    events, run_doc = await _run_turn(
        mongo_database, user_id=user_id, conversation_id=conversation_id, settings=_live_eligible_settings(tmp_path)
    )

    assert not any(e.type == "run.failed" for e in events)
    completed = next(e for e in events if e.type == "message.completed")
    assert completed.text
    blocks = [e.block for e in events if e.type == "structured_output"]
    assert blocks

    metadata = run_doc.get("retrievalMetadata") or {}
    planner_first_live = metadata.get("plannerFirstLive")
    assert planner_first_live is not None
    assert planner_first_live["attempted"] is True
    assert planner_first_live["used"] is True
    assert planner_first_live["workflowName"] == "graduation_progress_workflow"
    assert planner_first_live["runStatus"] in {"completed", "completed_with_warnings"}
    # The deterministic-comparison path (Phase 9) never ran this turn.
    assert "supervisorValidation" not in metadata
    assert "supervisorPromotion" not in metadata


async def test_falls_back_to_deterministic_path_when_flag_off(mongo_database, tmp_path):
    user_id, conversation_id = await _seed_graduation_user(mongo_database)

    settings = _live_eligible_settings(tmp_path, AGENT_PLANNER_FIRST_LIVE_ENABLED=False)
    events, run_doc = await _run_turn(mongo_database, user_id=user_id, conversation_id=conversation_id, settings=settings)

    assert not any(e.type == "run.failed" for e in events)
    completed = next(e for e in events if e.type == "message.completed")
    assert completed.text

    metadata = run_doc.get("retrievalMetadata") or {}
    assert "plannerFirstLive" not in metadata


async def test_falls_back_to_deterministic_path_when_manifest_not_approved_at_top_rung(mongo_database, tmp_path):
    user_id, conversation_id = await _seed_graduation_user(mongo_database)

    settings = _live_eligible_settings(tmp_path)
    # Overwrite the manifest with a lower readiness rung after construction.
    manifest_path = json.loads(Path(settings.agent_runtime_readiness_manifest_path).read_text())
    manifest_path["candidates"][0]["level"] = "ready_for_limited_promotion"
    Path(settings.agent_runtime_readiness_manifest_path).write_text(json.dumps(manifest_path))

    events, run_doc = await _run_turn(mongo_database, user_id=user_id, conversation_id=conversation_id, settings=settings)

    assert not any(e.type == "run.failed" for e in events)
    completed = next(e for e in events if e.type == "message.completed")
    assert completed.text

    metadata = run_doc.get("retrievalMetadata") or {}
    assert "plannerFirstLive" not in metadata


async def test_response_text_matches_deterministic_path(mongo_database, tmp_path):
    """The Planner-first-live path executes the *same* underlying workflow,
    so its answer must be identical to the deterministic path's -- this is
    a genuinely different dispatch mechanism, not a different answer."""
    user_id_live, conversation_id_live = await _seed_graduation_user(mongo_database)
    events_live, _ = await _run_turn(
        mongo_database,
        user_id=user_id_live,
        conversation_id=conversation_id_live,
        settings=_live_eligible_settings(tmp_path),
    )

    user_id_det, conversation_id_det = await _seed_graduation_user(mongo_database)
    events_det, _ = await _run_turn(
        mongo_database,
        user_id=user_id_det,
        conversation_id=conversation_id_det,
        settings=Settings(**{**_BASE_KWARGS, "AGENT_PLANNER_FIRST_LIVE_ENABLED": False}),
    )

    completed_live = next(e for e in events_live if e.type == "message.completed")
    completed_det = next(e for e in events_det if e.type == "message.completed")
    assert completed_live.text == completed_det.text


# ---------------------------------------------------------------------------
# Phase 3 (post-Phase-9) — proposal-capable Planner-first-live execution
# (transcript_import_workflow). A wholly separate gate from the read-only
# tests above -- enabling one must never enable the other.
# ---------------------------------------------------------------------------

_TRANSCRIPT_MESSAGE = "Import my transcript"


def _proposal_manifest_path(tmp_path: Path, *, level: str = "ready_for_broader_promotion") -> str:
    manifest = {
        "schemaVersion": "1",
        "reviewedAt": "2026-07-06T00:00:00Z",
        "reviewedBy": "test-reviewer",
        "candidates": [
            {
                "candidateId": "planner_first_live_proposal.transcript_import_workflow",
                "level": level,
                "approved": True,
                "scope": ["transcript_import_workflow"],
                "expiresAt": "2099-01-01T00:00:00Z",
            }
        ],
    }
    path = tmp_path / "proposal_manifest.json"
    path.write_text(json.dumps(manifest), encoding="utf-8")
    return str(path)


def _proposal_eligible_settings(tmp_path: Path, **overrides: object) -> Settings:
    kwargs = {
        "OPENAI_API_KEY": None,
        "AGENT_PLANNER_ENABLED": True,
        "AGENT_SUPERVISOR_ENABLED": True,
        "AGENT_SUPERVISOR_REAL_HANDLERS_ENABLED": True,
        "AGENT_SUPERVISOR_POST_CONTEXT_COMPARE_ENABLED": False,
        "AGENT_SUPERVISOR_PROMOTION_ENABLED": False,
        # Read-only Planner-first-live stays off -- this file's proposal
        # tests must only ever exercise the separate proposal-capable gate.
        "AGENT_PLANNER_FIRST_LIVE_ENABLED": False,
        "AGENT_PLANNER_FIRST_LIVE_PROPOSAL_ENABLED": True,
        "AGENT_PLANNER_FIRST_LIVE_PROPOSAL_WORKFLOWS": "transcript_import_workflow",
        "AGENT_RUNTIME_READINESS_GATE_ENABLED": True,
        "AGENT_RUNTIME_READINESS_MANIFEST_PATH": _proposal_manifest_path(tmp_path),
    }
    kwargs.update(overrides)
    return Settings(**kwargs)


async def _seed_transcript_user(mongo_database) -> tuple[str, str, dict]:
    course = await seed_production_course_fixture(mongo_database)
    email = f"planner-first-live-proposal-{uuid.uuid4().hex[:10]}@example.com"
    user = await create_user(mongo_database, email=email, password_hash="hashed")
    user_id = str(user["_id"])
    conversation = await create_agent_conversation(mongo_database, user_id=user_id, title="Test")
    return user_id, str(conversation["id"]), course


def _transcript_attachments(course: dict) -> list[dict]:
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
    return [{"type": "transcript_pdf", "filename": "transcript.pdf", "parsePreview": parse_preview}]


async def _run_transcript_turn(mongo_database, *, user_id: str, conversation_id: str, course: dict, settings: Settings):
    events = [
        event
        async for event in run_agent_turn(
            mongo_database,
            user_id=user_id,
            conversation_id=conversation_id,
            user_message=_TRANSCRIPT_MESSAGE,
            trigger_message_id=str(ObjectId()),
            message_attachments=_transcript_attachments(course),
            settings=settings,
        )
    ]
    run_doc = await mongo_database[settings.agent_runs_collection].find_one(
        {"userId": ObjectId(user_id)}, sort=[("startedAt", -1)]
    )
    return events, run_doc


async def test_proposal_capable_planner_first_live_used_when_every_gate_passes(mongo_database, tmp_path):
    user_id, conversation_id, course = await _seed_transcript_user(mongo_database)

    events, run_doc = await _run_transcript_turn(
        mongo_database,
        user_id=user_id,
        conversation_id=conversation_id,
        course=course,
        settings=_proposal_eligible_settings(tmp_path),
    )

    assert not any(e.type == "run.failed" for e in events)
    action_events = [e for e in events if e.type == "action.proposed"]
    assert action_events, [e.type for e in events]
    assert action_events[0].action.action_type == "import_completed_courses"

    metadata = run_doc.get("retrievalMetadata") or {}
    planner_first_live = metadata.get("plannerFirstLive")
    assert planner_first_live is not None
    assert planner_first_live["used"] is True
    assert planner_first_live["workflowName"] == "transcript_import_workflow"

    # The action was proposed, never executed -- no confirm/reject happened.
    completed = next(e for e in events if e.type == "message.completed")
    assert completed.text


async def test_proposal_capable_falls_back_when_its_own_flag_is_off(mongo_database, tmp_path):
    user_id, conversation_id, course = await _seed_transcript_user(mongo_database)

    settings = _proposal_eligible_settings(tmp_path, AGENT_PLANNER_FIRST_LIVE_PROPOSAL_ENABLED=False)
    events, run_doc = await _run_transcript_turn(
        mongo_database, user_id=user_id, conversation_id=conversation_id, course=course, settings=settings
    )

    assert not any(e.type == "run.failed" for e in events)
    action_events = [e for e in events if e.type == "action.proposed"]
    assert action_events, "the deterministic path still proposes the action, just not via Planner-first-live"

    metadata = run_doc.get("retrievalMetadata") or {}
    assert "plannerFirstLive" not in metadata


async def test_read_only_flag_alone_never_enables_proposal_capable_dispatch(mongo_database, tmp_path):
    """Defense in depth at the integration level: even with the read-only
    Planner-first-live flag on, transcript import must never be dispatched
    through Planner-first-live without its own, separate proposal flag."""
    user_id, conversation_id, course = await _seed_transcript_user(mongo_database)

    settings = _proposal_eligible_settings(
        tmp_path,
        AGENT_PLANNER_FIRST_LIVE_PROPOSAL_ENABLED=False,
        AGENT_PLANNER_FIRST_LIVE_ENABLED=True,
        AGENT_PLANNER_FIRST_LIVE_WORKFLOWS="graduation_progress_workflow,course_question_workflow,requirement_explanation_workflow",
    )
    events, run_doc = await _run_transcript_turn(
        mongo_database, user_id=user_id, conversation_id=conversation_id, course=course, settings=settings
    )

    assert not any(e.type == "run.failed" for e in events)
    metadata = run_doc.get("retrievalMetadata") or {}
    assert "plannerFirstLive" not in metadata


async def test_proposal_capable_response_matches_deterministic_path(mongo_database, tmp_path):
    user_id_live, conversation_id_live, course_live = await _seed_transcript_user(mongo_database)
    events_live, _ = await _run_transcript_turn(
        mongo_database,
        user_id=user_id_live,
        conversation_id=conversation_id_live,
        course=course_live,
        settings=_proposal_eligible_settings(tmp_path),
    )

    user_id_det, conversation_id_det, course_det = await _seed_transcript_user(mongo_database)
    events_det, _ = await _run_transcript_turn(
        mongo_database,
        user_id=user_id_det,
        conversation_id=conversation_id_det,
        course=course_det,
        settings=_proposal_eligible_settings(tmp_path, AGENT_PLANNER_FIRST_LIVE_PROPOSAL_ENABLED=False),
    )

    completed_live = next(e for e in events_live if e.type == "message.completed")
    completed_det = next(e for e in events_det if e.type == "message.completed")
    assert completed_live.text == completed_det.text

    action_live = next(e for e in events_live if e.type == "action.proposed")
    action_det = next(e for e in events_det if e.type == "action.proposed")
    assert action_live.action.action_type == action_det.action.action_type
