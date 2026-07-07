"""Integration tests for Phase 22 synthesis text promotion."""

from __future__ import annotations

import uuid
from typing import Any

import pytest
from bson import ObjectId

from app.agent.orchestrator import run_agent_turn
from app.agent.planner.schemas import PlannerOutput, PlannerSubtask
from app.agent.synthesis.promotion_schemas import SynthesisTextPromotionDecision, SynthesisTextPromotionReason
from app.agent.synthesis.schemas import SynthesisOutput
from app.config import Settings
from app.repositories.agent_conversation_repository import create_agent_conversation
from app.repositories.student_profile_repository import create_student_profile
from app.repositories.user_repository import create_user
from tests.fixtures.graduation_progress_fixtures import seed_graduation_progress_fixtures

_MESSAGE = "What am I missing to graduate?"
_CANDIDATE_TEXT = "Synthesized graduation guidance: focus on remaining core credits."

_BASE = {
    "OPENAI_API_KEY": None,
    "AGENT_PLANNER_ENABLED": True,
    "AGENT_SUPERVISOR_ENABLED": True,
    "AGENT_SUPERVISOR_POST_CONTEXT_COMPARE_ENABLED": True,
    "AGENT_MONITOR_ENABLED": True,
    "AGENT_MONITOR_DRY_RUN": True,
    "AGENT_SYNTHESIS_ENABLED": True,
    "AGENT_SYNTHESIS_DRY_RUN": True,
    "AGENT_SYNTHESIS_USE_LLM": False,
}

_OFF = Settings(**{**_BASE, "AGENT_SYNTHESIS_TEXT_PROMOTION_ENABLED": False})
_SHADOW = Settings(
    **{
        **_BASE,
        "AGENT_SYNTHESIS_TEXT_PROMOTION_ENABLED": True,
        "AGENT_SYNTHESIS_TEXT_PROMOTION_MODE": "shadow_only",
    }
)
_PROMOTE = Settings(
    **{
        **_BASE,
        "AGENT_SYNTHESIS_TEXT_PROMOTION_ENABLED": True,
        "AGENT_SYNTHESIS_TEXT_PROMOTION_MODE": "promote_validated",
    }
)


def _fake_plan() -> PlannerOutput:
    return PlannerOutput(
        status="completed",
        plan_id="syn-promo-1",
        user_goal=_MESSAGE,
        execution_mode="single_capability",
        recommended_autonomy_level=3,
        primary_intent="graduation_progress_check",
        subtasks=[
            PlannerSubtask(
                id="ask_specialist",
                title="Ask graduation specialist",
                kind="analyze",
                capability_name="graduation_progress_agent",
                objective="Determine remaining requirements toward graduation.",
                depends_on=[],
                required_context_sections=["user_message"],
            )
        ],
        assumptions=["Student wants graduation guidance"],
        decision_summary="test",
        confidence=0.85,
    )


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
            "progress": {"creditsRemaining": 40.0, "requirementProgress": []},
            "errors": [],
            "warnings": [],
            "assumptions": [],
            "blockers": [],
            "graduation_status": "not_ready",
            "can_graduate": False,
        }

    monkeypatch.setattr(graduation_audit_client, "fetch_graduation_audit", lambda **_: _fake_graduation_audit_coro())


def _inject_fake_plan(monkeypatch) -> None:
    async def _fake_build_plan_with_diagnostics(**_kwargs):
        plan = _fake_plan()
        return plan, {"status": plan.status, "planId": plan.plan_id}

    monkeypatch.setattr("app.agent.orchestrator.build_plan_with_diagnostics", _fake_build_plan_with_diagnostics)


def _inject_promotable_synthesis(monkeypatch) -> None:
    synthesis_output = SynthesisOutput(
        status="candidate_ready",
        synthesis_id="syn-promo-test",
        decision_summary="ready",
        candidate_answer_text=_CANDIDATE_TEXT,
        safe_to_show=True,
        safe_to_promote=True,
        confidence=0.92,
    )

    async def _fake_run_synthesis_diagnostics(**_kwargs):
        return synthesis_output, {"status": "candidate_ready", "safeToShow": True}

    monkeypatch.setattr(
        "app.agent.synthesis.synthesis_agent.run_synthesis_diagnostics",
        _fake_run_synthesis_diagnostics,
    )


async def _seed_user(mongo_database) -> tuple[str, str]:
    fixtures = await seed_graduation_progress_fixtures(mongo_database)
    email = f"syn-promo-{uuid.uuid4().hex[:10]}@example.com"
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
    conversation = await create_agent_conversation(mongo_database, user_id=user_id, title="syn promo test")
    return user_id, str(conversation["id"])


async def _run_turn(mongo_database, *, settings: Settings) -> tuple[list[Any], dict[str, Any]]:
    user_id, conversation_id = await _seed_user(mongo_database)
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
    assert run_doc is not None
    return events, run_doc


def _event_types(events: list[Any]) -> list[str]:
    return [event.type for event in events]


@pytest.mark.asyncio
async def test_flags_off_preserves_behavior(mongo_database, monkeypatch) -> None:
    _inject_fake_plan(monkeypatch)
    _inject_promotable_synthesis(monkeypatch)
    _, run_doc = await _run_turn(mongo_database, settings=_OFF)
    assert "synthesisPromotion" not in (run_doc.get("retrievalMetadata") or {})


@pytest.mark.asyncio
async def test_shadow_only_attaches_diagnostics_without_changing_text(mongo_database, monkeypatch) -> None:
    _inject_fake_plan(monkeypatch)
    _inject_promotable_synthesis(monkeypatch)
    events_off, _ = await _run_turn(mongo_database, settings=_OFF)
    events_shadow, run_doc = await _run_turn(mongo_database, settings=_SHADOW)
    completed_off = next(event for event in events_off if event.type == "message.completed")
    completed_shadow = next(event for event in events_shadow if event.type == "message.completed")
    assert completed_off.text == completed_shadow.text
    promo = (run_doc.get("retrievalMetadata") or {}).get("synthesisPromotion") or {}
    assert promo.get("mode") == "shadow_only"
    assert promo.get("promoted") is False
    assert promo.get("wouldPromote") is True or (promo.get("diagnostics") or {}).get("wouldPromote") is True


@pytest.mark.asyncio
async def test_promote_validated_changes_only_response_text(mongo_database, monkeypatch) -> None:
    _inject_fake_plan(monkeypatch)
    _inject_promotable_synthesis(monkeypatch)
    events_off, _ = await _run_turn(mongo_database, settings=_OFF)
    events_on, run_doc = await _run_turn(mongo_database, settings=_PROMOTE)
    completed_off = next(event for event in events_off if event.type == "message.completed")
    completed_on = next(event for event in events_on if event.type == "message.completed")
    assert completed_on.text == _CANDIDATE_TEXT
    assert completed_on.text != completed_off.text
    promo = (run_doc.get("retrievalMetadata") or {}).get("synthesisPromotion") or {}
    assert promo.get("promoted") is True


@pytest.mark.asyncio
async def test_promoted_response_preserves_blocks(mongo_database, monkeypatch) -> None:
    _inject_fake_plan(monkeypatch)
    _inject_promotable_synthesis(monkeypatch)
    events_off, _ = await _run_turn(mongo_database, settings=_OFF)
    events_on, _ = await _run_turn(mongo_database, settings=_PROMOTE)
    blocks_off = [event.block for event in events_off if event.type == "structured_output"]
    blocks_on = [event.block for event in events_on if event.type == "structured_output"]
    assert [block.type for block in blocks_off] == [block.type for block in blocks_on]


@pytest.mark.asyncio
async def test_promoted_response_preserves_warnings(mongo_database, monkeypatch) -> None:
    _inject_fake_plan(monkeypatch)
    _inject_promotable_synthesis(monkeypatch)
    events_off, _ = await _run_turn(mongo_database, settings=_OFF)
    events_on, _ = await _run_turn(mongo_database, settings=_PROMOTE)
    completed_off = next(event for event in events_off if event.type == "message.completed")
    completed_on = next(event for event in events_on if event.type == "message.completed")
    assert completed_off.text != completed_on.text
    assert completed_on.text == _CANDIDATE_TEXT


@pytest.mark.asyncio
async def test_promoted_response_preserves_proposed_actions(mongo_database, monkeypatch) -> None:
    _inject_fake_plan(monkeypatch)
    _inject_promotable_synthesis(monkeypatch)
    events_on, _ = await _run_turn(mongo_database, settings=_PROMOTE)
    assert not any(event.type == "action.proposed" for event in events_on)


@pytest.mark.asyncio
async def test_blocked_candidate_leaves_response_unchanged(mongo_database, monkeypatch) -> None:
    _inject_fake_plan(monkeypatch)

    async def _unsafe_synthesis(**_kwargs):
        return (
            SynthesisOutput(
                status="unsafe",
                synthesis_id="syn-bad",
                decision_summary="unsafe",
                candidate_answer_text="bad",
                safe_to_show=False,
            ),
            {"status": "unsafe"},
        )

    monkeypatch.setattr("app.agent.synthesis.synthesis_agent.run_synthesis_diagnostics", _unsafe_synthesis)
    events_off, _ = await _run_turn(mongo_database, settings=_OFF)
    events_blocked, run_doc = await _run_turn(mongo_database, settings=_PROMOTE)
    completed_off = next(event for event in events_off if event.type == "message.completed")
    completed_blocked = next(event for event in events_blocked if event.type == "message.completed")
    assert completed_blocked.text == completed_off.text
    promo = (run_doc.get("retrievalMetadata") or {}).get("synthesisPromotion") or {}
    assert promo.get("promoted") is False


@pytest.mark.asyncio
async def test_existing_workflow_promotion_blocks_synthesis_promotion(mongo_database, monkeypatch) -> None:
    from app.agent.synthesis.promotion_policy import evaluate_synthesis_text_promotion as real_eval

    _inject_fake_plan(monkeypatch)
    _inject_promotable_synthesis(monkeypatch)

    def _eval_with_workflow_promotion(**kwargs):
        return real_eval(**{**kwargs, "workflow_promotion_already_applied": True})

    monkeypatch.setattr(
        "app.agent.synthesis.promotion_policy.evaluate_synthesis_text_promotion",
        _eval_with_workflow_promotion,
    )
    _, run_doc = await _run_turn(mongo_database, settings=_PROMOTE)
    promo = (run_doc.get("retrievalMetadata") or {}).get("synthesisPromotion") or {}
    assert promo.get("promoted") is False
    assert any(r.get("code") == "existing_workflow_promotion_applied" for r in promo.get("reasons") or [])


@pytest.mark.asyncio
async def test_sse_event_types_unchanged_excluding_message_deltas(mongo_database, monkeypatch) -> None:
    _inject_fake_plan(monkeypatch)
    _inject_promotable_synthesis(monkeypatch)
    events_off, _ = await _run_turn(mongo_database, settings=_OFF)
    events_on, _ = await _run_turn(mongo_database, settings=_PROMOTE)
    off_types = [event_type for event_type in _event_types(events_off) if event_type != "message.delta"]
    on_types = [event_type for event_type in _event_types(events_on) if event_type != "message.delta"]
    assert off_types == on_types
