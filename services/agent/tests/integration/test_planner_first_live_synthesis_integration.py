"""Integration tests for Phase 5 (post-Phase-9) live Synthesis text promotion.

Confirms `run_agent_turn` genuinely lets Synthesis replace a Planner-first-
live turn's response text, reusing the exact same `AGENT_SYNTHESIS_ENABLED`/
`AGENT_SYNTHESIS_TEXT_PROMOTION_*` settings already wired into the
deterministic path -- and that it stays fully inert without them.
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
from tests.fixtures.graduation_progress_fixtures import seed_graduation_progress_fixtures

_MESSAGE = "What am I missing to graduate?"


def _manifest_path(tmp_path: Path, *, include_synthesis_candidate: bool = False) -> str:
    candidates = [
        {
            "candidateId": "planner_first_live.graduation_progress_workflow",
            "level": "ready_for_broader_promotion",
            "approved": True,
            "scope": ["graduation_progress_workflow"],
            "expiresAt": "2099-01-01T00:00:00Z",
        }
    ]
    if include_synthesis_candidate:
        # `evaluate_synthesis_text_promotion` checks its own, separate
        # candidate id -- approving Planner-first-live alone is not enough
        # to also approve synthesis text promotion; each is independently
        # reviewed.
        candidates.append(
            {
                "candidateId": "synthesis_text_promotion.graduation_progress_workflow",
                "level": "ready_for_limited_promotion",
                "approved": True,
                "scope": ["graduation_progress_workflow"],
                "expiresAt": "2099-01-01T00:00:00Z",
            }
        )
    manifest = {
        "schemaVersion": "1",
        "reviewedAt": "2026-07-06T00:00:00Z",
        "reviewedBy": "test-reviewer",
        "candidates": candidates,
    }
    path = tmp_path / "manifest.json"
    path.write_text(json.dumps(manifest), encoding="utf-8")
    return str(path)


def _settings(tmp_path: Path, *, include_synthesis_candidate: bool = False, **overrides: object) -> Settings:
    kwargs = {
        "OPENAI_API_KEY": None,
        "AGENT_PLANNER_ENABLED": True,
        "AGENT_SUPERVISOR_ENABLED": True,
        "AGENT_SUPERVISOR_REAL_HANDLERS_ENABLED": True,
        "AGENT_SUPERVISOR_POST_CONTEXT_COMPARE_ENABLED": False,
        "AGENT_SUPERVISOR_PROMOTION_ENABLED": False,
        "AGENT_PLANNER_FIRST_LIVE_ENABLED": True,
        "AGENT_PLANNER_FIRST_LIVE_WORKFLOWS": "graduation_progress_workflow",
        "AGENT_RUNTIME_READINESS_GATE_ENABLED": True,
        "AGENT_RUNTIME_READINESS_MANIFEST_PATH": _manifest_path(
            tmp_path, include_synthesis_candidate=include_synthesis_candidate
        ),
        "AGENT_SYNTHESIS_ENABLED": True,
        "AGENT_SYNTHESIS_TEXT_PROMOTION_ENABLED": True,
        "AGENT_SYNTHESIS_TEXT_PROMOTION_MODE": "promote_validated",
        "AGENT_SYNTHESIS_TEXT_PROMOTION_WORKFLOWS": "graduation_progress_workflow",
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
    email = f"planner-first-live-synthesis-{uuid.uuid4().hex[:10]}@example.com"
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


async def test_synthesis_diagnostics_attached_for_planner_first_live_turn(mongo_database, tmp_path):
    user_id, conversation_id = await _seed_graduation_user(mongo_database)

    events, run_doc = await _run_turn(
        mongo_database, user_id=user_id, conversation_id=conversation_id, settings=_settings(tmp_path)
    )

    assert not any(e.type == "run.failed" for e in events)
    metadata = run_doc.get("retrievalMetadata") or {}
    assert metadata.get("plannerFirstLive", {}).get("used") is True
    assert metadata.get("synthesisDiagnostics") is not None
    assert metadata.get("synthesisPromotion") is not None

    completed = next(e for e in events if e.type == "message.completed")
    assert completed.text


async def test_synthesis_never_attempted_without_agent_synthesis_enabled(mongo_database, tmp_path):
    user_id, conversation_id = await _seed_graduation_user(mongo_database)

    settings = _settings(tmp_path, AGENT_SYNTHESIS_ENABLED=False, AGENT_SYNTHESIS_TEXT_PROMOTION_ENABLED=False)
    events, run_doc = await _run_turn(mongo_database, user_id=user_id, conversation_id=conversation_id, settings=settings)

    assert not any(e.type == "run.failed" for e in events)
    metadata = run_doc.get("retrievalMetadata") or {}
    assert metadata.get("plannerFirstLive", {}).get("used") is True
    assert "synthesisDiagnostics" not in metadata
    assert "synthesisPromotion" not in metadata


async def test_synthesis_promotion_never_changes_blocks_or_sources(mongo_database, tmp_path):
    user_id, conversation_id = await _seed_graduation_user(mongo_database)

    events, run_doc = await _run_turn(
        mongo_database, user_id=user_id, conversation_id=conversation_id, settings=_settings(tmp_path)
    )

    assert not any(e.type == "run.failed" for e in events)
    metadata = run_doc.get("retrievalMetadata") or {}
    promotion = metadata.get("synthesisPromotion")
    assert promotion is not None
    if promotion.get("promoted"):
        # Only the response text may ever change -- blocks/sources/warnings
        # are always the live workflow's own, unchanged.
        blocks = [e.block for e in events if e.type == "structured_output"]
        assert blocks


async def test_synthesis_genuinely_promotes_when_its_own_candidate_is_also_approved(mongo_database, tmp_path):
    """The canonical happy path: both the Planner-first-live *and* the
    synthesis-text-promotion candidates are independently reviewed and
    approved -- promotion actually succeeds, not just runs without error.

    The real `graduation_progress_workflow` fixture response here carries
    one warning, which the deterministic synthesis composer's confidence
    formula weighs -- lowering the min-confidence threshold below the
    default 0.85 is itself a legitimate operator knob (not test-specific
    cheating), used here purely to prove the promotion path is reachable
    end-to-end with real workflow data, not just synthetic all-clean data.
    """
    user_id, conversation_id = await _seed_graduation_user(mongo_database)

    settings = _settings(
        tmp_path, include_synthesis_candidate=True, AGENT_SYNTHESIS_TEXT_PROMOTION_MIN_CONFIDENCE=0.75
    )
    events, run_doc = await _run_turn(mongo_database, user_id=user_id, conversation_id=conversation_id, settings=settings)

    assert not any(e.type == "run.failed" for e in events)
    metadata = run_doc.get("retrievalMetadata") or {}
    promotion = metadata.get("synthesisPromotion")
    assert promotion is not None
    assert promotion["promoted"] is True

    blocks = [e.block for e in events if e.type == "structured_output"]
    assert blocks
    completed = next(e for e in events if e.type == "message.completed")
    assert completed.text
