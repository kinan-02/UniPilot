"""Integration tests for Phase 11 specialist output validation + workflow-vs-
specialist compare, wired into the post-context supervisor diagnostics hook.

`OPENAI_API_KEY=None` throughout — no real LLM call is ever made; a real
specialist call (when `AGENT_SPECIALIST_AGENTS_ENABLED=true`) safely
degrades to its Phase 10 fallback (`status="skipped"`, `confidence=0.0`)
before any network call happens.

Since the deterministic planner fallback never targets a specialist
capability, most tests here monkeypatch `orchestrator.build_plan_with_diagnostics`
to inject a fake `PlannerOutput` whose single subtask targets
`graduation_progress_agent` — this only ever affects the *shadow*
supervisor run (`post_context_runner`), never the live workflow selection
(`task_planner.build_task_plan` is completely independent of the planner
output), so injecting it can never change what the student actually sees.
"""

from __future__ import annotations

import uuid

import pytest
from bson import ObjectId

from app.agent.orchestrator import run_agent_turn
from app.agent.planner.schemas import PlannerOutput, PlannerSubtask
from app.agent.specialists.diagnostics import (
    build_specialist_compare_diagnostics,
    build_specialist_validation_metadata,
)
from app.agent.specialists.registry import build_default_specialist_agent_registry
from app.agent.supervisor.promotion import eligible_promotion_workflows
from app.agent.supervisor.schemas import SubtaskExecutionRecord, SupervisorRunOutput
from app.config import Settings
from app.repositories.agent_conversation_repository import create_agent_conversation
from app.repositories.student_profile_repository import create_student_profile
from app.repositories.user_repository import create_user
from tests.fixtures.graduation_progress_fixtures import seed_graduation_progress_fixtures

_GRADUATION_MESSAGE = "What am I missing to graduate?"

_BASE_KWARGS = {
    "OPENAI_API_KEY": None,
    "AGENT_PLANNER_ENABLED": True,
    "AGENT_SUPERVISOR_ENABLED": True,
    "AGENT_SUPERVISOR_POST_CONTEXT_COMPARE_ENABLED": True,
    "AGENT_SUPERVISOR_VALIDATION_ENABLED": True,
}

_VALIDATION_OFF_SETTINGS = Settings(
    **{**_BASE_KWARGS, "AGENT_SPECIALIST_VALIDATION_ENABLED": False, "AGENT_SPECIALIST_COMPARE_ENABLED": False}
)
_VALIDATION_ON_SETTINGS = Settings(
    **{**_BASE_KWARGS, "AGENT_SPECIALIST_VALIDATION_ENABLED": True, "AGENT_SPECIALIST_COMPARE_ENABLED": False}
)
_VALIDATION_AND_COMPARE_ON_SETTINGS = Settings(
    **{
        **_BASE_KWARGS,
        "AGENT_SPECIALIST_VALIDATION_ENABLED": True,
        "AGENT_SPECIALIST_COMPARE_ENABLED": True,
        "AGENT_SPECIALIST_AGENTS_ENABLED": True,
    }
)


def _fake_specialist_plan(capability_name: str = "graduation_progress_agent") -> PlannerOutput:
    return PlannerOutput(
        status="completed",
        plan_id="plan-specialist-diag-1",
        user_goal=_GRADUATION_MESSAGE,
        execution_mode="single_capability",
        recommended_autonomy_level=3,
        primary_intent="graduation_progress_check",
        subtasks=[
            PlannerSubtask(
                id="ask_specialist",
                title="Ask the graduation progress specialist",
                kind="analyze",
                capability_name=capability_name,
                objective="Determine remaining requirements toward graduation.",
                depends_on=[],
                required_context_sections=["user_message"],
            )
        ],
        decision_summary="test",
        confidence=0.85,
    )


@pytest.fixture(autouse=True)
def _mock_student_user_context(monkeypatch):
    from app.retrieval import mongodb_user_retriever

    async def _fake_fetch_student_user_context(*, user_id: str, settings=None):
        return {"completed_courses": [], "data_quality": {"warnings": [], "ok": True}}

    monkeypatch.setattr(
        mongodb_user_retriever, "fetch_student_user_context", _fake_fetch_student_user_context
    )


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

    monkeypatch.setattr(
        graduation_audit_client, "fetch_graduation_audit", lambda **_: _fake_graduation_audit_coro()
    )


def _inject_fake_plan(monkeypatch, capability_name: str = "graduation_progress_agent"):
    async def _fake_build_plan_with_diagnostics(**_kwargs):
        plan = _fake_specialist_plan(capability_name)
        return plan, {"status": plan.status, "planId": plan.plan_id}

    monkeypatch.setattr(
        "app.agent.orchestrator.build_plan_with_diagnostics", _fake_build_plan_with_diagnostics
    )


async def _seed_graduation_user(mongo_database) -> tuple[str, str]:
    fixtures = await seed_graduation_progress_fixtures(mongo_database)
    email = f"specialist-validation-{uuid.uuid4().hex[:10]}@example.com"
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
            user_message=_GRADUATION_MESSAGE,
            trigger_message_id=str(ObjectId()),
            settings=settings,
        )
    ]
    run_doc = await mongo_database[settings.agent_runs_collection].find_one(
        {"userId": ObjectId(user_id)}, sort=[("startedAt", -1)]
    )
    return events, run_doc


# ---------------------------------------------------------------------------
# 1. Specialist validation flag off keeps behavior unchanged.
# ---------------------------------------------------------------------------


async def test_flag_off_keeps_behavior_unchanged(mongo_database, monkeypatch):
    _inject_fake_plan(monkeypatch)
    user_id, conversation_id = await _seed_graduation_user(mongo_database)

    events, run_doc = await _run_turn(
        mongo_database, user_id=user_id, conversation_id=conversation_id, settings=_VALIDATION_OFF_SETTINGS
    )

    assert not any(e.type == "run.failed" for e in events)
    metadata = run_doc.get("retrievalMetadata") or {}
    assert "specialistValidation" not in metadata
    # Phase 8 supervisor diagnostics still ran independently.
    assert "supervisorValidation" in metadata


# ---------------------------------------------------------------------------
# 2. Specialist validation flag on attaches compact specialistValidation metadata.
# ---------------------------------------------------------------------------


async def test_flag_on_attaches_compact_specialist_validation_metadata(mongo_database, monkeypatch):
    _inject_fake_plan(monkeypatch)
    user_id, conversation_id = await _seed_graduation_user(mongo_database)

    events, run_doc = await _run_turn(
        mongo_database, user_id=user_id, conversation_id=conversation_id, settings=_VALIDATION_ON_SETTINGS
    )

    assert not any(e.type == "run.failed" for e in events)
    metadata = run_doc.get("retrievalMetadata") or {}
    specialist_validation = metadata.get("specialistValidation")
    assert specialist_validation is not None
    assert set(specialist_validation) == {
        "status",
        "safeToConsider",
        "validationCount",
        "comparisonCount",
        "issues",
        "agents",
        "comparisons",
    }
    assert specialist_validation["agents"] == ["graduation_progress_agent"]
    assert specialist_validation["validationCount"] == 1
    # Compare flag was off for this settings object.
    assert specialist_validation["comparisonCount"] == 0


# ---------------------------------------------------------------------------
# 3. Specialist validation flag on does not change text/blocks/actions/SSE sequence.
# ---------------------------------------------------------------------------


async def test_flag_on_does_not_change_user_visible_response_or_sse_sequence(mongo_database, monkeypatch):
    _inject_fake_plan(monkeypatch)
    user_id_off, conversation_id_off = await _seed_graduation_user(mongo_database)
    events_off, _ = await _run_turn(
        mongo_database, user_id=user_id_off, conversation_id=conversation_id_off, settings=_VALIDATION_OFF_SETTINGS
    )

    user_id_on, conversation_id_on = await _seed_graduation_user(mongo_database)
    events_on, _ = await _run_turn(
        mongo_database,
        user_id=user_id_on,
        conversation_id=conversation_id_on,
        settings=_VALIDATION_AND_COMPARE_ON_SETTINGS,
    )

    assert [e.type for e in events_off] == [e.type for e in events_on]

    completed_off = next(e for e in events_off if e.type == "message.completed")
    completed_on = next(e for e in events_on if e.type == "message.completed")
    assert completed_off.text == completed_on.text

    # Compare block *types* (not full content) across the two runs — two
    # separate users/conversations can legitimately see slightly different
    # `SourceSummaryBlock.data.provenance` wiki-retrieval ordering/details
    # between runs (unrelated to this flag), the same non-determinism
    # already tolerated by the equivalent Phase 6/9 parity tests.
    blocks_off = [e.block for e in events_off if e.type == "structured_output"]
    blocks_on = [e.block for e in events_on if e.type == "structured_output"]
    assert [b.type for b in blocks_off] == [b.type for b in blocks_on]

    actions_off = [e.action for e in events_off if e.type == "action.proposed"]
    actions_on = [e.action for e in events_on if e.type == "action.proposed"]
    assert actions_off == actions_on


# ---------------------------------------------------------------------------
# 4. Specialist comparison flag on compares a comparable workflow/specialist pair.
# ---------------------------------------------------------------------------


async def test_compare_flag_on_produces_a_comparable_pair(mongo_database, monkeypatch):
    _inject_fake_plan(monkeypatch)
    user_id, conversation_id = await _seed_graduation_user(mongo_database)

    events, run_doc = await _run_turn(
        mongo_database,
        user_id=user_id,
        conversation_id=conversation_id,
        settings=_VALIDATION_AND_COMPARE_ON_SETTINGS,
    )

    assert not any(e.type == "run.failed" for e in events)
    metadata = run_doc.get("retrievalMetadata") or {}
    specialist_validation = metadata.get("specialistValidation")
    assert specialist_validation is not None
    assert specialist_validation["comparisonCount"] == 1
    comparison = specialist_validation["comparisons"][0]
    assert comparison["workflowName"] == "graduation_progress_workflow"
    assert comparison["specialistAgentName"] == "graduation_progress_agent"
    assert comparison["comparable"] is True


# ---------------------------------------------------------------------------
# 5. Specialist output failure does not break the live turn.
# ---------------------------------------------------------------------------


async def test_specialist_failure_does_not_break_live_turn(mongo_database, monkeypatch):
    _inject_fake_plan(monkeypatch)

    class _BoomRegistry:
        def get(self, _name):
            def _boom(*_args, **_kwargs):
                raise RuntimeError("boom")

            return _boom

    monkeypatch.setattr(
        "app.agent.specialists.supervisor_handler.build_default_specialist_agent_registry",
        lambda: _BoomRegistry(),
    )

    user_id, conversation_id = await _seed_graduation_user(mongo_database)
    events, run_doc = await _run_turn(
        mongo_database,
        user_id=user_id,
        conversation_id=conversation_id,
        settings=_VALIDATION_AND_COMPARE_ON_SETTINGS,
    )

    assert not any(e.type == "run.failed" for e in events)
    completed = next(e for e in events if e.type == "message.completed")
    assert completed.text


# ---------------------------------------------------------------------------
# 6. Specialist output with proposed actions is blocked.
# ---------------------------------------------------------------------------


def test_specialist_output_with_proposed_actions_is_blocked() -> None:
    """`SpecialistAgentOutput.proposed_actions` is always forced to `[]` by
    the model itself, so this exercises the validator's defense-in-depth
    check directly against a (hypothetically buggy/tampered) summary that
    still carries `hasProposedActions=True`."""
    malicious_summary = {
        "agentName": "graduation_progress_agent",
        "status": "completed",
        "confidence": 0.9,
        "warningCount": 0,
        "sourceCount": 1,
        "missingContextCount": 0,
        "hasProposedActions": True,
        "resultKeys": ["creditsRemaining"],
    }
    record = SubtaskExecutionRecord(
        subtask_id="ask_specialist",
        capability_name="graduation_progress_agent",
        status="completed",
        result_summary=malicious_summary,
    )
    shadow_output = SupervisorRunOutput(
        status="completed", plan_id="p", execution_mode="single_capability", subtask_records=[record]
    )

    diagnostics = build_specialist_compare_diagnostics(
        shadow_run_output=shadow_output, validation_enabled=True, compare_enabled=False
    )

    assert diagnostics is not None
    assert diagnostics.status == "failed"
    assert diagnostics.safe_to_consider is False
    metadata = build_specialist_validation_metadata(diagnostics)
    codes = [issue["code"] for issue in metadata["issues"]]
    assert "specialist_proposed_actions_detected" in codes


# ---------------------------------------------------------------------------
# 7. Diagnostics contain no raw context/raw text/raw blocks.
# ---------------------------------------------------------------------------


async def test_diagnostics_contain_no_raw_context_or_text_or_blocks(mongo_database, monkeypatch):
    _inject_fake_plan(monkeypatch)
    user_id, conversation_id = await _seed_graduation_user(mongo_database)

    _events, run_doc = await _run_turn(
        mongo_database,
        user_id=user_id,
        conversation_id=conversation_id,
        settings=_VALIDATION_AND_COMPARE_ON_SETTINGS,
    )

    metadata = run_doc.get("retrievalMetadata") or {}
    specialist_validation_text = str(metadata.get("specialistValidation"))
    for forbidden in (
        "raw_context",
        "compiled_context",
        "raw_prompt",
        "system_prompt",
        "user_prompt",
        "raw_response",
        "raw_text",
        "full_text",
        "raw_blocks",
        "full_blocks",
        "chain_of_thought",
        "hidden_reasoning",
        "private_reasoning",
        "scratchpad",
        "thoughts",
    ):
        assert forbidden not in specialist_validation_text


# ---------------------------------------------------------------------------
# 8. Specialist outputs still cannot be promoted.
# ---------------------------------------------------------------------------


def test_specialist_outputs_cannot_be_promoted() -> None:
    settings = Settings(
        AGENT_SUPERVISOR_PROMOTION_ENABLED=True,
        AGENT_SUPERVISOR_PROMOTION_MODE="promote_validated",
        AGENT_SUPERVISOR_PROMOTION_WORKFLOWS=(
            "graduation_progress_workflow,graduation_progress_agent,course_catalog_agent,requirement_explanation_agent"
        ),
    )

    eligible = eligible_promotion_workflows(settings)

    assert eligible == {"graduation_progress_workflow"}
    registry = build_default_specialist_agent_registry()
    for agent_name in registry.list_agents():
        assert agent_name not in eligible
