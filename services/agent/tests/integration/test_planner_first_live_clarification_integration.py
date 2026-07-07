"""Integration tests for Phase 6 (post-Phase-9) live clarification.

Confirms `run_agent_turn` genuinely lets a Planner-first-live turn pause on
a real user-facing clarification question -- via the exact same
`offer_user_facing_clarification` call the deterministic path already uses,
newly fed a real `ClarificationCapabilityOutput` for Planner-first-live
turns instead of always `None`.
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


def _manifest_path(tmp_path: Path) -> str:
    manifest = {
        "schemaVersion": "1",
        "reviewedAt": "2026-07-06T00:00:00Z",
        "reviewedBy": "test-reviewer",
        "candidates": [
            {
                "candidateId": "planner_first_live.graduation_progress_workflow",
                "level": "ready_for_broader_promotion",
                "approved": True,
                "scope": ["graduation_progress_workflow"],
                "expiresAt": "2099-01-01T00:00:00Z",
            }
        ],
    }
    path = tmp_path / "manifest.json"
    path.write_text(json.dumps(manifest), encoding="utf-8")
    return str(path)


def _settings(tmp_path: Path, **overrides: object) -> Settings:
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
        "AGENT_RUNTIME_READINESS_MANIFEST_PATH": _manifest_path(tmp_path),
        "AGENT_MONITOR_ENABLED": True,
        "AGENT_MONITOR_DRY_RUN": True,
        "AGENT_CLARIFICATION_ENABLED": True,
        "AGENT_CLARIFICATION_USER_FACING_ENABLED": True,
        "AGENT_CLARIFICATION_STATE_ENABLED": False,
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


def _inject_monitor_ask_clarification(monkeypatch) -> None:
    from app.agent.monitoring.schemas import DivergenceSignal, MonitorOutput, ReplanDecision

    def _fake_monitor_plan_execution(_input, *, enabled=True, dry_run=True):
        return MonitorOutput(
            status="diverged",
            plan_id="plan-clarify-1",
            signals=[
                DivergenceSignal(
                    kind="assumption_violation",
                    severity="warning",
                    message="Preference ambiguity about elective track",
                    related_subtask_ids=["run_legacy_workflow"],
                )
            ],
            decision=ReplanDecision(
                action="ask_clarification",
                reason="preference ambiguity about elective track",
                confidence=0.7,
                divergence_kinds=["assumption_violation"],
                affected_subtasks=["run_legacy_workflow"],
            ),
            checked_assumption_count=1,
            checked_expectation_count=1,
        )

    monkeypatch.setattr(
        "app.agent.monitoring.monitor.monitor_plan_execution",
        _fake_monitor_plan_execution,
    )


async def _seed_graduation_user(mongo_database) -> tuple[str, str]:
    fixtures = await seed_graduation_progress_fixtures(mongo_database)
    email = f"planner-first-live-clarify-{uuid.uuid4().hex[:10]}@example.com"
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


async def test_live_clarification_offered_when_monitor_signals_ask_clarification(
    mongo_database, tmp_path, monkeypatch
):
    _inject_monitor_ask_clarification(monkeypatch)
    user_id, conversation_id = await _seed_graduation_user(mongo_database)

    events, run_doc = await _run_turn(
        mongo_database, user_id=user_id, conversation_id=conversation_id, settings=_settings(tmp_path)
    )

    assert not any(e.type == "run.failed" for e in events)
    metadata = run_doc.get("retrievalMetadata") or {}
    assert metadata.get("plannerFirstLive", {}).get("used") is True

    clarification_diag = metadata.get("clarificationDiagnostics")
    assert clarification_diag is not None
    assert clarification_diag["status"] == "question_ready"
    assert clarification_diag["questionCount"] >= 1

    # The turn genuinely pauses on the question -- the response text itself
    # becomes the clarification prompt, not just a metadata-only signal.
    completed = next(e for e in events if e.type == "message.completed")
    assert completed.text
    assert "preference" in completed.text.lower()
    assert "?" in completed.text


async def test_no_clarification_offered_without_user_facing_flag(mongo_database, tmp_path, monkeypatch):
    _inject_monitor_ask_clarification(monkeypatch)
    user_id, conversation_id = await _seed_graduation_user(mongo_database)

    settings = _settings(tmp_path, AGENT_CLARIFICATION_USER_FACING_ENABLED=False)
    events, run_doc = await _run_turn(mongo_database, user_id=user_id, conversation_id=conversation_id, settings=settings)

    assert not any(e.type == "run.failed" for e in events)
    metadata = run_doc.get("retrievalMetadata") or {}
    assert metadata.get("plannerFirstLive", {}).get("used") is True
    clarification_diag = metadata.get("clarificationDiagnostics")
    # The capability still runs (assumed-answer diagnostics), it just never
    # reaches "question_ready" without the user-facing flag.
    if clarification_diag is not None:
        assert clarification_diag["status"] != "question_ready"


async def test_no_clarification_metadata_when_clarification_disabled(mongo_database, tmp_path, monkeypatch):
    _inject_monitor_ask_clarification(monkeypatch)
    user_id, conversation_id = await _seed_graduation_user(mongo_database)

    settings = _settings(tmp_path, AGENT_CLARIFICATION_ENABLED=False, AGENT_CLARIFICATION_USER_FACING_ENABLED=False)
    events, run_doc = await _run_turn(mongo_database, user_id=user_id, conversation_id=conversation_id, settings=settings)

    assert not any(e.type == "run.failed" for e in events)
    metadata = run_doc.get("retrievalMetadata") or {}
    assert metadata.get("plannerFirstLive", {}).get("used") is True
    assert "clarificationDiagnostics" not in metadata


async def test_no_clarification_offered_when_monitor_does_not_ask(mongo_database, tmp_path):
    """No monkeypatch injected -- the real Monitor sees a clean run and
    never asks for clarification."""
    user_id, conversation_id = await _seed_graduation_user(mongo_database)

    events, run_doc = await _run_turn(
        mongo_database, user_id=user_id, conversation_id=conversation_id, settings=_settings(tmp_path)
    )

    assert not any(e.type == "run.failed" for e in events)
    metadata = run_doc.get("retrievalMetadata") or {}
    clarification_diag = metadata.get("clarificationDiagnostics")
    if clarification_diag is not None:
        assert clarification_diag["questionCount"] == 0
