"""Integration tests for Phase 14 Controlled Specialist Text Promotion.

`OPENAI_API_KEY=None` throughout — a real specialist call (when
`AGENT_SPECIALIST_AGENTS_ENABLED=true`) safely degrades to its Phase 10
fallback before any network call happens; the "positive" promotion tests
monkeypatch the specialist registry (exactly like
`test_specialist_validation_diagnostics.py`'s own Phase 11 pattern) to
exercise a high-confidence, `answer_text`-carrying completed output without
ever calling a real LLM.

Since the deterministic planner fallback never targets a specialist
capability, most tests here monkeypatch `orchestrator.build_plan_with_diagnostics`
to inject a fake `PlannerOutput` whose single subtask targets
`graduation_progress_agent` — this only ever affects the *shadow* supervisor
run (`post_context_runner`), never the live workflow selection
(`task_planner.build_task_plan` is completely independent), so injecting it
can never change what the student actually sees beyond the promoted text
itself.
"""

from __future__ import annotations

import uuid

import pytest
from bson import ObjectId

from app.agent.orchestrator import run_agent_turn
from app.agent.planner.schemas import PlannerOutput, PlannerSubtask
from app.agent.specialists.registry import SpecialistAgentRegistry
from app.agent.specialists.schemas import SpecialistAgentOutput
from app.config import Settings
from app.repositories.agent_conversation_repository import create_agent_conversation
from app.repositories.student_profile_repository import create_student_profile
from app.repositories.user_repository import create_user
from tests.fixtures.graduation_progress_fixtures import seed_graduation_progress_fixtures

_GRADUATION_MESSAGE = "What am I missing to graduate?"
_ANSWER_TEXT = (
    "You still need about 40 more credits to graduate. Focus on your remaining core "
    "courses and pick up one more elective next semester."
)

_BASE_KWARGS = {
    "OPENAI_API_KEY": None,
    "AGENT_PLANNER_ENABLED": True,
    "AGENT_SUPERVISOR_ENABLED": True,
    "AGENT_SUPERVISOR_POST_CONTEXT_COMPARE_ENABLED": True,
    "AGENT_SUPERVISOR_VALIDATION_ENABLED": True,
    "AGENT_SPECIALIST_AGENTS_ENABLED": True,
    "AGENT_SPECIALIST_VALIDATION_ENABLED": True,
    "AGENT_SPECIALIST_COMPARE_ENABLED": True,
    # Explicit, not relied-on-default: this file tests specialist text
    # promotion in isolation from the separate workflow-level Phase 9
    # promotion axis (both default off in `config.py`, but an operator's
    # real `.env` may enable them ambiently -- exactly as this repo's own
    # root `.env` now does for the widened Phase 1 promotion rollout).
    "AGENT_SUPERVISOR_REAL_HANDLERS_ENABLED": False,
    "AGENT_SUPERVISOR_PROMOTION_ENABLED": False,
    # Also explicit, same reasoning: the runtime readiness gate (post-Phase-9)
    # would otherwise block `specialist_text_promotion.*` candidates absent a
    # manifest entry, and synthesis-text-promotion (Phase 22, also on in this
    # repo's real `.env` post-Phase-9) runs independently of specialist text
    # promotion and would otherwise interfere with the text this file asserts on.
    "AGENT_RUNTIME_READINESS_GATE_ENABLED": False,
    "AGENT_SYNTHESIS_ENABLED": False,
    "AGENT_SYNTHESIS_TEXT_PROMOTION_ENABLED": False,
    # This file goes through the real `run_agent_turn` orchestrator -- also
    # pin Planner-first-live off so a leaked ambient `.env` can't route the
    # turn through it instead of the deterministic + shadow-compare path
    # this file actually tests.
    "AGENT_PLANNER_FIRST_LIVE_ENABLED": False,
    "AGENT_PLANNER_FIRST_LIVE_PROPOSAL_ENABLED": False,
}

_TEXT_PROMOTION_OFF_SETTINGS = Settings(**{**_BASE_KWARGS, "AGENT_SPECIALIST_TEXT_PROMOTION_ENABLED": False})
_TEXT_PROMOTION_SHADOW_ONLY_SETTINGS = Settings(
    **{**_BASE_KWARGS, "AGENT_SPECIALIST_TEXT_PROMOTION_ENABLED": True, "AGENT_SPECIALIST_TEXT_PROMOTION_MODE": "shadow_only"}
)
_TEXT_PROMOTION_VALIDATED_SETTINGS = Settings(
    **{
        **_BASE_KWARGS,
        "AGENT_SPECIALIST_TEXT_PROMOTION_ENABLED": True,
        "AGENT_SPECIALIST_TEXT_PROMOTION_MODE": "promote_validated",
    }
)


def _fake_specialist_plan(capability_name: str = "graduation_progress_agent") -> PlannerOutput:
    return PlannerOutput(
        status="completed",
        plan_id="plan-text-promotion-1",
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


def _high_quality_specialist_output(**overrides) -> SpecialistAgentOutput:
    defaults = dict(
        status="completed",
        agent_name="graduation_progress_agent",
        subtask_id="ask_specialist",
        decision_summary=_ANSWER_TEXT,
        confidence=0.95,
        result={"answer_text": _ANSWER_TEXT, "creditsRemaining": 40.0},
        sources=[{"type": "graduation_audit"}],
    )
    defaults.update(overrides)
    return SpecialistAgentOutput(**defaults)


def _inject_fake_specialist(monkeypatch, output: SpecialistAgentOutput | None):
    from app.agent.specialists import supervisor_handler as supervisor_handler_module

    class _FakeRegistry(SpecialistAgentRegistry):
        def __init__(self) -> None:
            super().__init__()

            async def _fn(_specialist_input, **_kwargs):
                if output is None:
                    raise RuntimeError("no specialist output configured")
                return output

            self.register("graduation_progress_agent", _fn)

    monkeypatch.setattr(
        supervisor_handler_module, "build_default_specialist_agent_registry", lambda: _FakeRegistry()
    )


async def _seed_graduation_user(mongo_database) -> tuple[str, str]:
    fixtures = await seed_graduation_progress_fixtures(mongo_database)
    email = f"text-promo-{uuid.uuid4().hex[:10]}@example.com"
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
# 1. Flags off keeps behavior unchanged.
# ---------------------------------------------------------------------------


async def test_flags_off_keeps_behavior_unchanged(mongo_database, monkeypatch):
    _inject_fake_plan(monkeypatch)
    _inject_fake_specialist(monkeypatch, _high_quality_specialist_output())

    user_id, conversation_id = await _seed_graduation_user(mongo_database)
    events, run_doc = await _run_turn(
        mongo_database, user_id=user_id, conversation_id=conversation_id, settings=_TEXT_PROMOTION_OFF_SETTINGS
    )

    assert not any(e.type == "run.failed" for e in events)
    completed = next(e for e in events if e.type == "message.completed")
    assert completed.text != _ANSWER_TEXT

    metadata = run_doc.get("retrievalMetadata") or {}
    assert "specialistTextPromotion" not in metadata


# ---------------------------------------------------------------------------
# 2. shadow_only keeps behavior unchanged.
# ---------------------------------------------------------------------------


async def test_shadow_only_keeps_behavior_unchanged(mongo_database, monkeypatch):
    _inject_fake_plan(monkeypatch)
    _inject_fake_specialist(monkeypatch, _high_quality_specialist_output())

    user_id_off, conversation_id_off = await _seed_graduation_user(mongo_database)
    events_off, _ = await _run_turn(
        mongo_database, user_id=user_id_off, conversation_id=conversation_id_off, settings=_TEXT_PROMOTION_OFF_SETTINGS
    )

    user_id_shadow, conversation_id_shadow = await _seed_graduation_user(mongo_database)
    events_shadow, run_doc_shadow = await _run_turn(
        mongo_database,
        user_id=user_id_shadow,
        conversation_id=conversation_id_shadow,
        settings=_TEXT_PROMOTION_SHADOW_ONLY_SETTINGS,
    )

    assert [e.type for e in events_off] == [e.type for e in events_shadow]
    completed_off = next(e for e in events_off if e.type == "message.completed")
    completed_shadow = next(e for e in events_shadow if e.type == "message.completed")
    assert completed_off.text == completed_shadow.text
    assert completed_shadow.text != _ANSWER_TEXT

    metadata = run_doc_shadow.get("retrievalMetadata") or {}
    promotion = metadata.get("specialistTextPromotion")
    assert promotion is not None
    assert promotion["status"] == "skipped"
    assert promotion["promoted"] is False


# ---------------------------------------------------------------------------
# 3. promote_validated with missing specialist output keeps live text.
# ---------------------------------------------------------------------------


async def test_promote_validated_with_missing_specialist_output_keeps_live_text(mongo_database):
    """No fake plan/specialist injected -- the deterministic fallback plan
    never targets a specialist capability, so no specialist output ever
    exists for this turn."""
    user_id, conversation_id = await _seed_graduation_user(mongo_database)

    events, run_doc = await _run_turn(
        mongo_database, user_id=user_id, conversation_id=conversation_id, settings=_TEXT_PROMOTION_VALIDATED_SETTINGS
    )

    assert not any(e.type == "run.failed" for e in events)
    completed = next(e for e in events if e.type == "message.completed")
    assert completed.text != _ANSWER_TEXT
    assert completed.text

    metadata = run_doc.get("retrievalMetadata") or {}
    promotion = metadata.get("specialistTextPromotion")
    assert promotion is not None
    assert promotion["status"] == "blocked"
    assert promotion["promoted"] is False
    assert any(r["code"] == "specialist_output_missing" for r in promotion["reasons"])


# ---------------------------------------------------------------------------
# 4. promote_validated with failed validation keeps live text.
# ---------------------------------------------------------------------------


async def test_promote_validated_with_failed_validation_keeps_live_text(mongo_database, monkeypatch):
    _inject_fake_plan(monkeypatch)
    _inject_fake_specialist(monkeypatch, _high_quality_specialist_output(confidence=0.2))

    user_id, conversation_id = await _seed_graduation_user(mongo_database)
    events, run_doc = await _run_turn(
        mongo_database, user_id=user_id, conversation_id=conversation_id, settings=_TEXT_PROMOTION_VALIDATED_SETTINGS
    )

    assert not any(e.type == "run.failed" for e in events)
    completed = next(e for e in events if e.type == "message.completed")
    assert completed.text != _ANSWER_TEXT

    metadata = run_doc.get("retrievalMetadata") or {}
    promotion = metadata.get("specialistTextPromotion")
    assert promotion is not None
    assert promotion["status"] == "blocked"
    assert promotion["promoted"] is False


# ---------------------------------------------------------------------------
# 5. promote_validated with valid specialist answer replaces text only.
# ---------------------------------------------------------------------------


async def test_promote_validated_with_valid_specialist_answer_replaces_text_only(mongo_database, monkeypatch):
    _inject_fake_plan(monkeypatch)
    _inject_fake_specialist(monkeypatch, _high_quality_specialist_output())

    user_id_off, conversation_id_off = await _seed_graduation_user(mongo_database)
    events_off, _ = await _run_turn(
        mongo_database, user_id=user_id_off, conversation_id=conversation_id_off, settings=_TEXT_PROMOTION_OFF_SETTINGS
    )

    user_id_on, conversation_id_on = await _seed_graduation_user(mongo_database)
    events_on, run_doc_on = await _run_turn(
        mongo_database, user_id=user_id_on, conversation_id=conversation_id_on, settings=_TEXT_PROMOTION_VALIDATED_SETTINGS
    )

    completed_on = next(e for e in events_on if e.type == "message.completed")
    assert completed_on.text == _ANSWER_TEXT

    metadata = run_doc_on.get("retrievalMetadata") or {}
    promotion = metadata.get("specialistTextPromotion")
    assert promotion is not None
    assert promotion["status"] == "promoted"
    assert promotion["promoted"] is True
    assert promotion["workflowName"] == "graduation_progress_workflow"
    assert promotion["specialistAgentName"] == "graduation_progress_agent"

    # 6. Promoted response keeps blocks unchanged (same block types as the
    # flag-off live response). Compares block *types* only, not full
    # content -- two separate users/conversations can legitimately see
    # slightly different `SourceSummaryBlock.data.provenance` wiki-retrieval
    # ordering/details between runs (unrelated to this flag), the same
    # non-determinism already tolerated by the equivalent Phase 11 parity
    # test (`test_specialist_validation_diagnostics.py`).
    blocks_off = [e.block for e in events_off if e.type == "structured_output"]
    blocks_on = [e.block for e in events_on if e.type == "structured_output"]
    assert [b.type for b in blocks_off] == [b.type for b in blocks_on]


# ---------------------------------------------------------------------------
# 7. Promoted response keeps proposed_actions unchanged and empty.
# ---------------------------------------------------------------------------


async def test_promoted_response_keeps_proposed_actions_empty(mongo_database, monkeypatch):
    _inject_fake_plan(monkeypatch)
    _inject_fake_specialist(monkeypatch, _high_quality_specialist_output())

    user_id, conversation_id = await _seed_graduation_user(mongo_database)
    events, _ = await _run_turn(
        mongo_database, user_id=user_id, conversation_id=conversation_id, settings=_TEXT_PROMOTION_VALIDATED_SETTINGS
    )

    assert not any(e.type == "action.proposed" for e in events)
    completed = next(e for e in events if e.type == "message.completed")
    assert completed.text == _ANSWER_TEXT


# ---------------------------------------------------------------------------
# 8 & 9. Promotion never happens for course_catalog_agent / requirement_explanation_agent.
# ---------------------------------------------------------------------------


@pytest.mark.parametrize("agent_name", ["course_catalog_agent", "requirement_explanation_agent"])
async def test_promotion_never_happens_for_non_graduation_specialists(mongo_database, monkeypatch, agent_name):
    _inject_fake_plan(monkeypatch, capability_name=agent_name)

    from app.agent.specialists import supervisor_handler as supervisor_handler_module

    output = SpecialistAgentOutput(
        status="completed",
        agent_name=agent_name,  # type: ignore[arg-type]
        subtask_id="ask_specialist",
        decision_summary=_ANSWER_TEXT,
        confidence=0.95,
        result={"answer_text": _ANSWER_TEXT},
    )

    class _FakeRegistry(SpecialistAgentRegistry):
        def __init__(self) -> None:
            super().__init__()

            async def _fn(_specialist_input, **_kwargs):
                return output

            self.register(agent_name, _fn)

    monkeypatch.setattr(
        supervisor_handler_module, "build_default_specialist_agent_registry", lambda: _FakeRegistry()
    )

    user_id, conversation_id = await _seed_graduation_user(mongo_database)
    events, run_doc = await _run_turn(
        mongo_database, user_id=user_id, conversation_id=conversation_id, settings=_TEXT_PROMOTION_VALIDATED_SETTINGS
    )

    assert not any(e.type == "run.failed" for e in events)
    completed = next(e for e in events if e.type == "message.completed")
    assert completed.text != _ANSWER_TEXT

    metadata = run_doc.get("retrievalMetadata") or {}
    promotion = metadata.get("specialistTextPromotion")
    # Either never attempted (no eligible agent to build a sink for) or
    # attempted-and-blocked -- never promoted.
    if promotion is not None:
        assert promotion["promoted"] is False


# ---------------------------------------------------------------------------
# 10. Promotion never happens for transcript/semester workflows.
# ---------------------------------------------------------------------------


async def test_promotion_never_happens_for_write_or_proposal_workflows(mongo_database):
    from app.agent.context_builder import build_agent_context_pack
    from app.agent.response_composer import compose_response
    from app.agent.schemas import IntentClassification, TaskPlan
    from app.agent.specialists.text_promotion import evaluate_specialist_text_promotion

    settings = _TEXT_PROMOTION_VALIDATED_SETTINGS
    user_id, conversation_id = await _seed_graduation_user(mongo_database)

    classification = IntentClassification(intent="semester_plan_generation", confidence=0.9)
    task_plan = TaskPlan(workflow="semester_planning_workflow", read_only=False, requires_confirmation=True)
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
        settings=settings,
    )
    live_response = compose_response(
        conversation_id=conversation_id, message_id="", run_id=context.run_id, text="Here is a draft plan."
    )

    decision = evaluate_specialist_text_promotion(
        workflow_name="semester_planning_workflow",
        specialist_agent_name="graduation_progress_agent",
        live_response_summary={"blockCount": 1, "proposedActionCount": 0},
        specialist_validation_metadata={"status": "passed", "safeToConsider": True},
        specialist_comparison_metadata={"comparable": True, "safeMatch": True},
        specialist_output_summary={
            "status": "completed", "confidence": 0.95, "missingContextCount": 0, "hasProposedActions": False
        },
        answer_text=_ANSWER_TEXT,
        workflow_promotion_already_promoted=False,
        settings=settings,
    )

    assert decision.status == "blocked"
    assert decision.promoted is False
    assert any(r.code == "workflow_not_eligible_for_text_promotion" for r in decision.reasons)
    assert live_response.text == "Here is a draft plan."


# ---------------------------------------------------------------------------
# 11. Workflow promotion conflict blocks specialist text promotion.
# ---------------------------------------------------------------------------


async def test_workflow_promotion_conflict_blocks_specialist_text_promotion(mongo_database):
    """Uses the real (non-injected) deterministic plan -- exactly like Phase
    9's own `test_promote_validated_selects_candidate_when_all_gates_pass`
    -- so workflow promotion has a real chance to succeed. Text promotion's
    precedence check (`workflow_promotion_already_promoted`) short-circuits
    before ever needing a real specialist output, so no specialist plan
    injection is needed to prove the precedence rule holds."""
    settings = Settings(
        **{
            **_BASE_KWARGS,
            "AGENT_SUPERVISOR_REAL_HANDLERS_ENABLED": True,
            "AGENT_SUPERVISOR_PROMOTION_ENABLED": True,
            "AGENT_SUPERVISOR_PROMOTION_MODE": "promote_validated",
            "AGENT_SPECIALIST_TEXT_PROMOTION_ENABLED": True,
            "AGENT_SPECIALIST_TEXT_PROMOTION_MODE": "promote_validated",
        }
    )

    user_id, conversation_id = await _seed_graduation_user(mongo_database)
    events, run_doc = await _run_turn(mongo_database, user_id=user_id, conversation_id=conversation_id, settings=settings)

    assert not any(e.type == "run.failed" for e in events)
    metadata = run_doc.get("retrievalMetadata") or {}

    supervisor_promotion = metadata.get("supervisorPromotion")
    assert supervisor_promotion is not None
    assert supervisor_promotion["promoted"] is True

    text_promotion = metadata.get("specialistTextPromotion")
    assert text_promotion is not None
    assert text_promotion["promoted"] is False
    assert any(r["code"] == "workflow_promotion_already_selected_response" for r in text_promotion["reasons"])

    # The response text still came from the (Phase 9-promoted) live/candidate
    # response, never the specialist's answer_text.
    completed = next(e for e in events if e.type == "message.completed")
    assert completed.text != _ANSWER_TEXT


# ---------------------------------------------------------------------------
# 12. SSE event-type sequence unchanged.
# ---------------------------------------------------------------------------


def _collapsed_event_types(events) -> list[str]:
    """Event types with consecutive `message.delta` runs collapsed to one.

    `_emit_final_response_events` chunks `response.text` into a
    text-length-dependent number of `message.delta` events (pre-existing
    behavior, unrelated to Phase 14) -- since Phase 14's whole purpose is
    changing `text`, the promoted answer's length legitimately produces a
    different *count* of delta chunks than the original live text. What
    Phase 14 must never change is which event *types* appear and in what
    order/position -- exactly what this collapsed comparison checks.
    """
    collapsed: list[str] = []
    for event in events:
        if event.type == "message.delta" and collapsed and collapsed[-1] == "message.delta":
            continue
        collapsed.append(event.type)
    return collapsed


async def test_sse_event_type_sequence_unchanged(mongo_database, monkeypatch):
    _inject_fake_plan(monkeypatch)
    _inject_fake_specialist(monkeypatch, _high_quality_specialist_output())

    user_id_off, conversation_id_off = await _seed_graduation_user(mongo_database)
    events_off, _ = await _run_turn(
        mongo_database, user_id=user_id_off, conversation_id=conversation_id_off, settings=_TEXT_PROMOTION_OFF_SETTINGS
    )

    user_id_on, conversation_id_on = await _seed_graduation_user(mongo_database)
    events_on, _ = await _run_turn(
        mongo_database, user_id=user_id_on, conversation_id=conversation_id_on, settings=_TEXT_PROMOTION_VALIDATED_SETTINGS
    )

    assert _collapsed_event_types(events_off) == _collapsed_event_types(events_on)


# ---------------------------------------------------------------------------
# 13. Diagnostics are compact and contain no promoted full text.
# ---------------------------------------------------------------------------


async def test_diagnostics_are_compact_and_contain_no_promoted_text(mongo_database, monkeypatch):
    _inject_fake_plan(monkeypatch)
    _inject_fake_specialist(monkeypatch, _high_quality_specialist_output())

    user_id, conversation_id = await _seed_graduation_user(mongo_database)
    _events, run_doc = await _run_turn(
        mongo_database, user_id=user_id, conversation_id=conversation_id, settings=_TEXT_PROMOTION_VALIDATED_SETTINGS
    )

    metadata = run_doc.get("retrievalMetadata") or {}
    promotion = metadata.get("specialistTextPromotion")
    assert promotion is not None
    assert set(promotion) == {"status", "promoted", "mode", "workflowName", "specialistAgentName", "reasons"}
    for reason in promotion["reasons"]:
        assert set(reason) == {"code", "severity"}

    metadata_text = str(metadata)
    assert _ANSWER_TEXT not in metadata_text
    for forbidden in (
        "raw_context",
        "compiled_context",
        "raw_blocks",
        "raw_response",
        "chain_of_thought",
        "hidden_reasoning",
        "private_reasoning",
        "scratchpad",
        "thoughts",
    ):
        assert forbidden not in metadata_text


# ---------------------------------------------------------------------------
# 14. No writes/action proposals created.
# ---------------------------------------------------------------------------


async def test_no_writes_or_action_proposals_created(mongo_database, monkeypatch):
    _inject_fake_plan(monkeypatch)
    _inject_fake_specialist(monkeypatch, _high_quality_specialist_output())

    user_id, conversation_id = await _seed_graduation_user(mongo_database)
    events, _ = await _run_turn(
        mongo_database, user_id=user_id, conversation_id=conversation_id, settings=_TEXT_PROMOTION_VALIDATED_SETTINGS
    )

    assert not any(e.type == "action.proposed" for e in events)
    proposals = await mongo_database[_TEXT_PROMOTION_VALIDATED_SETTINGS.agent_action_proposals_collection].find(
        {}
    ).to_list(length=10)
    assert proposals == []


# ---------------------------------------------------------------------------
# 15. No direct LLM calls introduced.
# ---------------------------------------------------------------------------


async def test_no_direct_llm_calls_introduced(mongo_database, monkeypatch):
    """`OPENAI_API_KEY=None` throughout this module -- the fake specialist
    registry above proves the promoted text can come entirely from an
    in-memory `SpecialistAgentOutput`, with zero real LLM/network calls."""
    _inject_fake_plan(monkeypatch)
    _inject_fake_specialist(monkeypatch, _high_quality_specialist_output())

    assert _TEXT_PROMOTION_VALIDATED_SETTINGS.openai_api_key is None

    user_id, conversation_id = await _seed_graduation_user(mongo_database)
    events, run_doc = await _run_turn(
        mongo_database, user_id=user_id, conversation_id=conversation_id, settings=_TEXT_PROMOTION_VALIDATED_SETTINGS
    )

    assert not any(e.type == "run.failed" for e in events)
    metadata = run_doc.get("retrievalMetadata") or {}
    assert metadata.get("specialistTextPromotion", {}).get("promoted") is True
