"""Integration tests for the Phase 9 Controlled Supervisor Promotion experiment.

Mirrors `test_supervisor_shadow_compare_diagnostics.py` (Phase 8) and
`test_supervisor_real_handler_diagnostics.py` (Phase 7): confirms that
enabling promotion never breaks user-visible behavior when validation fails
or promotion isn't eligible, and that it genuinely selects the supervisor
candidate response (only for `graduation_progress_workflow`, only when every
strict gate passes) end to end through a real `run_agent_turn`.
"""

from __future__ import annotations

import uuid

import pytest
from bson import ObjectId

from app.agent.context_builder import build_agent_context_pack
from app.agent.orchestrator import run_agent_turn
from app.agent.response_composer import compose_response
from app.agent.schemas import IntentClassification, TaskPlan
from app.agent.supervisor import post_context_runner as post_context_runner_module
from app.agent.supervisor.post_context_runner import run_post_context_shadow_compare
from app.agent.supervisor.workflow_adapters import ReadOnlyWorkflowAdapterHandler
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
    "AGENT_SUPERVISOR_REAL_HANDLERS_ENABLED": True,
    # Explicit, not relied-on-default: this file exercises the shadow-compare
    # + Promotion path specifically. An operator's real `.env` may have
    # Planner-first-live turned on (exactly as this repo's own root `.env`
    # does, post-Phase-9) -- if it leaked in here, `planner_first_live_used`
    # would be True and the turn would skip `run_post_context_shadow_compare`
    # entirely, which is the exact mechanism this file is testing.
    "AGENT_PLANNER_FIRST_LIVE_ENABLED": False,
    "AGENT_PLANNER_FIRST_LIVE_PROPOSAL_ENABLED": False,
    "AGENT_RUNTIME_READINESS_GATE_ENABLED": False,
}

_PROMOTION_OFF_SETTINGS = Settings(**{**_BASE_KWARGS, "AGENT_SUPERVISOR_PROMOTION_ENABLED": False})
_PROMOTION_SHADOW_ONLY_SETTINGS = Settings(
    **{**_BASE_KWARGS, "AGENT_SUPERVISOR_PROMOTION_ENABLED": True, "AGENT_SUPERVISOR_PROMOTION_MODE": "shadow_only"}
)
_PROMOTION_VALIDATED_SETTINGS = Settings(
    **{
        **_BASE_KWARGS,
        "AGENT_SUPERVISOR_PROMOTION_ENABLED": True,
        "AGENT_SUPERVISOR_PROMOTION_MODE": "promote_validated",
        # Explicit, not relied-on-default: an operator's real `.env` may
        # deliberately pin this narrower than `config.py`'s default (exactly
        # as this repo's own root `.env` currently does) -- tests exercising
        # the widened `_HARD_ALLOWED_PROMOTION_WORKFLOWS` ceiling must not
        # depend on ambient environment configuration to reach it.
        "AGENT_SUPERVISOR_PROMOTION_WORKFLOWS": (
            "graduation_progress_workflow,course_question_workflow,requirement_explanation_workflow"
        ),
    }
)


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
        return _fake_graduation_audit()

    monkeypatch.setattr(
        graduation_audit_client, "fetch_graduation_audit", lambda **_: _fake_graduation_audit_coro()
    )


async def _seed_user_and_conversation(mongo_database, *, program_id: str | None = None) -> tuple[str, str]:
    email = f"supervisor-promo-{uuid.uuid4().hex[:10]}@example.com"
    user = await create_user(mongo_database, email=email, password_hash="hashed")
    user_id = str(user["_id"])
    await create_student_profile(
        mongo_database,
        user_id,
        {
            "institutionId": "technion",
            "programType": "BSc",
            "degreeId": program_id or str(ObjectId()),
            "catalogYear": 2025,
            "currentSemesterCode": "2025-1",
            "academicPath": {"trackSlug": "track-data-information-engineering"},
        },
    )
    conversation = await create_agent_conversation(mongo_database, user_id=user_id, title="Test")
    return user_id, str(conversation["id"])


async def _seed_graduation_user(mongo_database) -> tuple[str, str]:
    fixtures = await seed_graduation_progress_fixtures(mongo_database)
    return await _seed_user_and_conversation(mongo_database, program_id=fixtures["programId"])


async def _run_turn(mongo_database, *, user_id: str, conversation_id: str, settings: Settings, message: str = _GRADUATION_MESSAGE):
    events = [
        event
        async for event in run_agent_turn(
            mongo_database,
            user_id=user_id,
            conversation_id=conversation_id,
            user_message=message,
            trigger_message_id=str(ObjectId()),
            settings=settings,
        )
    ]
    run_doc = await mongo_database[settings.agent_runs_collection].find_one(
        {"userId": ObjectId(user_id)}, sort=[("startedAt", -1)]
    )
    return events, run_doc


# ---------------------------------------------------------------------------
# 1. Promotion flag off keeps current behavior unchanged.
# ---------------------------------------------------------------------------


async def test_promotion_disabled_keeps_behavior_unchanged(mongo_database):
    user_id, conversation_id = await _seed_graduation_user(mongo_database)

    events, run_doc = await _run_turn(mongo_database, user_id=user_id, conversation_id=conversation_id, settings=_PROMOTION_OFF_SETTINGS)

    assert not any(e.type == "run.failed" for e in events)
    metadata = run_doc.get("retrievalMetadata") or {}
    assert "supervisorPromotion" not in metadata
    assert "supervisorValidation" in metadata


# ---------------------------------------------------------------------------
# 2. Promotion shadow_only keeps current behavior unchanged.
# ---------------------------------------------------------------------------


async def test_promotion_shadow_only_keeps_behavior_unchanged(mongo_database):
    user_id_off, conversation_id_off = await _seed_graduation_user(mongo_database)
    events_off, _ = await _run_turn(mongo_database, user_id=user_id_off, conversation_id=conversation_id_off, settings=_PROMOTION_OFF_SETTINGS)

    user_id_shadow, conversation_id_shadow = await _seed_graduation_user(mongo_database)
    events_shadow, run_doc_shadow = await _run_turn(
        mongo_database, user_id=user_id_shadow, conversation_id=conversation_id_shadow, settings=_PROMOTION_SHADOW_ONLY_SETTINGS
    )

    assert [e.type for e in events_off] == [e.type for e in events_shadow]
    completed_off = next(e for e in events_off if e.type == "message.completed")
    completed_shadow = next(e for e in events_shadow if e.type == "message.completed")
    assert completed_off.text == completed_shadow.text

    metadata = run_doc_shadow.get("retrievalMetadata") or {}
    promotion = metadata.get("supervisorPromotion")
    assert promotion is not None
    assert promotion["status"] == "skipped"
    assert promotion["promoted"] is False


# ---------------------------------------------------------------------------
# 3. promote_validated with failed validation keeps live response.
# ---------------------------------------------------------------------------


async def test_promote_validated_with_failed_validation_keeps_live_response(mongo_database, monkeypatch):
    from app.agent.supervisor.schemas import SupervisorRunOutput

    async def _failed_shadow(**_kwargs):
        return SupervisorRunOutput(status="failed", plan_id="p", execution_mode="single_capability", errors=["boom"])

    monkeypatch.setattr(post_context_runner_module, "run_supervisor_shadow", _failed_shadow)

    user_id, conversation_id = await _seed_graduation_user(mongo_database)
    events, run_doc = await _run_turn(mongo_database, user_id=user_id, conversation_id=conversation_id, settings=_PROMOTION_VALIDATED_SETTINGS)

    assert not any(e.type == "run.failed" for e in events)
    completed = next(e for e in events if e.type == "message.completed")
    assert completed.text

    metadata = run_doc.get("retrievalMetadata") or {}
    validation = metadata.get("supervisorValidation")
    assert validation is not None
    assert validation["status"] == "failed"

    promotion = metadata.get("supervisorPromotion")
    assert promotion is not None
    assert promotion["status"] == "blocked"
    assert promotion["promoted"] is False


# ---------------------------------------------------------------------------
# 4. promote_validated with passing validation selects the candidate
# response, only for graduation_progress_workflow.
# ---------------------------------------------------------------------------


async def test_promote_validated_selects_candidate_when_all_gates_pass(mongo_database):
    user_id, conversation_id = await _seed_graduation_user(mongo_database)

    events, run_doc = await _run_turn(mongo_database, user_id=user_id, conversation_id=conversation_id, settings=_PROMOTION_VALIDATED_SETTINGS)

    assert not any(e.type == "run.failed" for e in events)
    metadata = run_doc.get("retrievalMetadata") or {}
    promotion = metadata.get("supervisorPromotion")
    assert promotion is not None
    assert promotion["workflowName"] == "graduation_progress_workflow"
    assert promotion["mode"] == "promote_validated"
    assert promotion["status"] == "promoted"
    assert promotion["promoted"] is True

    # The turn still produced a normal, complete response.
    completed = next(e for e in events if e.type == "message.completed")
    assert completed.text
    blocks = [e.block for e in events if e.type == "structured_output"]
    assert blocks


# ---------------------------------------------------------------------------
# 4b/4c. promote_validated also selects the candidate for the two other
# read-only workflows widened into `_HARD_ALLOWED_PROMOTION_WORKFLOWS` this
# cycle (`course_question_workflow`, `requirement_explanation_workflow`).
# `general_academic_workflow` is deliberately not covered here — its shadow
# execution is always the dry-run stand-in (operationally-expensive-skipped
# by default), so it can never produce a promotable candidate.
# ---------------------------------------------------------------------------


async def _fake_contribution() -> dict:
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


async def test_promote_validated_selects_candidate_for_course_question_workflow(mongo_database, monkeypatch):
    from app.retrieval import catalog_retriever

    monkeypatch.setattr(catalog_retriever, "fetch_course_requirement_contribution", lambda **_: _fake_contribution())

    fixtures = await seed_graduation_progress_fixtures(mongo_database)
    user_id, conversation_id = await _seed_user_and_conversation(mongo_database, program_id=fixtures["programId"])

    events, run_doc = await _run_turn(
        mongo_database,
        user_id=user_id,
        conversation_id=conversation_id,
        settings=_PROMOTION_VALIDATED_SETTINGS,
        message=f"Does course {fixtures['courseBNumber']} count toward my degree?",
    )

    assert not any(e.type == "run.failed" for e in events)
    metadata = run_doc.get("retrievalMetadata") or {}
    promotion = metadata.get("supervisorPromotion")
    assert promotion is not None
    assert promotion["workflowName"] == "course_question_workflow"
    assert promotion["mode"] == "promote_validated"
    assert promotion["status"] == "promoted"
    assert promotion["promoted"] is True

    completed = next(e for e in events if e.type == "message.completed")
    assert completed.text
    blocks = [e.block for e in events if e.type == "structured_output"]
    assert blocks


async def test_promote_validated_selects_candidate_for_requirement_explanation_workflow(mongo_database):
    user_id, conversation_id = await _seed_graduation_user(mongo_database)

    events, run_doc = await _run_turn(
        mongo_database,
        user_id=user_id,
        conversation_id=conversation_id,
        settings=_PROMOTION_VALIDATED_SETTINGS,
        message="why is this requirement incomplete",
    )

    assert not any(e.type == "run.failed" for e in events)
    metadata = run_doc.get("retrievalMetadata") or {}
    promotion = metadata.get("supervisorPromotion")
    assert promotion is not None
    assert promotion["workflowName"] == "requirement_explanation_workflow"
    assert promotion["mode"] == "promote_validated"
    assert promotion["status"] == "promoted"
    assert promotion["promoted"] is True

    completed = next(e for e in events if e.type == "message.completed")
    assert completed.text
    blocks = [e.block for e in events if e.type == "structured_output"]
    assert blocks


# ---------------------------------------------------------------------------
# 5 & 6. Promotion never runs for transcript_import_workflow / semester_planning_workflow.
# ---------------------------------------------------------------------------


def _proposal_plan(capability_name: str) -> dict:
    return {
        "status": "completed",
        "plan_id": "plan-promotion-unsafe-1",
        "user_goal": "test",
        "execution_mode": "single_capability",
        "recommended_autonomy_level": 3,
        "primary_intent": "semester_plan_generation",
        "subtasks": [
            {
                "id": "run_it",
                "title": "test",
                "kind": "propose_action",
                "capability_name": capability_name,
                "objective": "test",
                "depends_on": [],
                "required_context_sections": ["user_message"],
            }
        ],
        "decision_summary": "test",
        "confidence": 0.85,
    }


@pytest.mark.parametrize("workflow_name", ["transcript_import_workflow", "semester_planning_workflow"])
async def test_promotion_never_runs_for_write_or_proposal_workflows(mongo_database, workflow_name):
    user_id, conversation_id = await _seed_graduation_user(mongo_database)

    classification = IntentClassification(intent="semester_plan_generation", confidence=0.9)
    task_plan = TaskPlan(workflow=workflow_name, read_only=False, requires_confirmation=True)
    context = await build_agent_context_pack(
        mongo_database,
        conversation_id=conversation_id,
        run_id=str(ObjectId()),
        user_id=user_id,
        intent="semester_plan_generation",
        entities={},
        classification=classification,
        task_plan=task_plan,
        user_message="Build my semester plan",
        settings=_PROMOTION_VALIDATED_SETTINGS,
    )
    live_response = compose_response(
        conversation_id=conversation_id, message_id="", run_id=context.run_id, text="Here is a draft plan."
    )

    outcome = await run_post_context_shadow_compare(
        database=mongo_database,
        agent_context_pack=context,
        user_message="Build my semester plan",
        user_id=user_id,
        conversation_id=conversation_id,
        run_id=context.run_id,
        live_workflow_name=workflow_name,
        live_response=live_response,
        planner_output=_proposal_plan(workflow_name),
        settings=_PROMOTION_VALIDATED_SETTINGS,
    )

    assert outcome is not None
    assert outcome.promoted_response is None
    assert outcome.promotion_metadata is not None
    assert outcome.promotion_metadata["status"] == "blocked"
    assert outcome.promotion_metadata["promoted"] is False
    assert any(reason["code"] == "workflow_not_eligible_for_promotion" for reason in outcome.promotion_metadata["reasons"])


# ---------------------------------------------------------------------------
# 7. Promotion never creates action proposals.
# ---------------------------------------------------------------------------


async def test_promotion_never_creates_action_proposals(mongo_database):
    user_id, conversation_id = await _seed_graduation_user(mongo_database)

    await _run_turn(mongo_database, user_id=user_id, conversation_id=conversation_id, settings=_PROMOTION_VALIDATED_SETTINGS)

    proposals = await mongo_database[_PROMOTION_VALIDATED_SETTINGS.agent_action_proposals_collection].find({}).to_list(length=10)
    assert proposals == []


# ---------------------------------------------------------------------------
# 8. Promotion does not alter the SSE event-type sequence.
# ---------------------------------------------------------------------------


async def test_promotion_does_not_alter_sse_event_sequence(mongo_database):
    user_id_off, conversation_id_off = await _seed_graduation_user(mongo_database)
    events_off, _ = await _run_turn(mongo_database, user_id=user_id_off, conversation_id=conversation_id_off, settings=_PROMOTION_OFF_SETTINGS)

    user_id_on, conversation_id_on = await _seed_graduation_user(mongo_database)
    events_on, _ = await _run_turn(mongo_database, user_id=user_id_on, conversation_id=conversation_id_on, settings=_PROMOTION_VALIDATED_SETTINGS)

    assert [e.type for e in events_off] == [e.type for e in events_on]


# ---------------------------------------------------------------------------
# 9. Promotion diagnostics are compact.
# ---------------------------------------------------------------------------


async def test_promotion_diagnostics_are_compact_and_sanitized(mongo_database):
    user_id, conversation_id = await _seed_graduation_user(mongo_database)

    _events, run_doc = await _run_turn(mongo_database, user_id=user_id, conversation_id=conversation_id, settings=_PROMOTION_VALIDATED_SETTINGS)

    metadata = run_doc.get("retrievalMetadata") or {}
    promotion = metadata.get("supervisorPromotion")
    assert promotion is not None
    assert set(promotion) == {"status", "promoted", "workflowName", "mode", "reasons"}
    for reason in promotion["reasons"]:
        assert set(reason) == {"code", "severity"}

    promotion_text = str(promotion)
    for forbidden in (
        "raw_context",
        "compiled_context",
        "raw_blocks",
        "raw_response",
        "raw_text",
        "full_text",
        "proposed_action_payload",
        "chain_of_thought",
        "scratchpad",
        "thoughts",
    ):
        assert forbidden not in promotion_text


# ---------------------------------------------------------------------------
# 10. Malformed supervisor candidate falls back to live response.
# ---------------------------------------------------------------------------


async def test_malformed_candidate_falls_back_to_live_response(mongo_database, monkeypatch):
    class _MalformedCandidateHandler(ReadOnlyWorkflowAdapterHandler):
        async def run(self, *, subtask, compiled_context, blackboard, dry_run, runtime_context=None):
            result = await super().run(
                subtask=subtask, compiled_context=compiled_context, blackboard=blackboard, dry_run=dry_run, runtime_context=runtime_context
            )
            if self._candidate_sink is not None and subtask.capability_name in self._candidate_sink:
                good = self._candidate_sink[subtask.capability_name]
                # Strip every block -- guaranteed to mismatch the live
                # response's block types/count.
                self._candidate_sink[subtask.capability_name] = good.model_copy(update={"blocks": []})
            return result

    monkeypatch.setattr(post_context_runner_module, "ReadOnlyWorkflowAdapterHandler", _MalformedCandidateHandler)

    user_id, conversation_id = await _seed_graduation_user(mongo_database)
    events, run_doc = await _run_turn(mongo_database, user_id=user_id, conversation_id=conversation_id, settings=_PROMOTION_VALIDATED_SETTINGS)

    assert not any(e.type == "run.failed" for e in events)
    metadata = run_doc.get("retrievalMetadata") or {}
    promotion = metadata.get("supervisorPromotion")
    assert promotion is not None
    assert promotion["status"] == "blocked"
    assert promotion["promoted"] is False

    # The live response still went through -- it has real structured blocks.
    blocks = [e.block for e in events if e.type == "structured_output"]
    assert blocks


# ---------------------------------------------------------------------------
# 11. Promotion handler failure falls back to live response.
# ---------------------------------------------------------------------------


async def test_promotion_handler_failure_falls_back_to_live_response(mongo_database, monkeypatch):
    async def _boom(**_kwargs):
        raise RuntimeError("boom")

    monkeypatch.setattr(post_context_runner_module, "run_supervisor_shadow", _boom)

    user_id, conversation_id = await _seed_graduation_user(mongo_database)
    events, run_doc = await _run_turn(mongo_database, user_id=user_id, conversation_id=conversation_id, settings=_PROMOTION_VALIDATED_SETTINGS)

    assert not any(e.type == "run.failed" for e in events)
    completed = next(e for e in events if e.type == "message.completed")
    assert completed.text
    blocks = [e.block for e in events if e.type == "structured_output"]
    assert blocks

    metadata = run_doc.get("retrievalMetadata") or {}
    assert "supervisorPromotion" not in metadata
    assert "supervisorValidation" not in metadata
