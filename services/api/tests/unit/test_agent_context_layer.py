"""Unit tests for context validation and retrieval planning."""

from app.agent.context_validator import validate_context_pack
from app.agent.intent_router import classify_intent
from app.agent.retrieval_planner import build_retrieval_plan
from app.agent.schemas import AgentContextPack, ContextValidation
from app.agent.task_planner import build_task_plan


def test_retrieval_plan_orders_structured_sources_first():
    classification = classify_intent("What am I missing to graduate?")
    plan = build_task_plan(classification)
    steps = build_retrieval_plan(classification=classification, task_plan=plan, entities={})
    assert steps[0]["source"] == "mongodb"
    assert any(step["source"] == "obsidian_wiki" for step in steps)


def test_context_validator_flags_missing_profile():
    pack = AgentContextPack(
        conversation_id="c1",
        run_id="r1",
        user_id="u1",
        intent="graduation_progress_check",
        entities={},
        user_context={},
        validation=ContextValidation(status="valid"),
    )
    result = validate_context_pack(pack)
    assert result.status == "partial"
    assert any("profile" in error.lower() for error in result.errors)


def test_context_validator_accepts_populated_graduation_context():
    pack = AgentContextPack(
        conversation_id="c1",
        run_id="r1",
        user_id="u1",
        intent="graduation_progress_check",
        entities={},
        user_context={
            "profile": {"catalogYear": 2025, "track": "track-test"},
            "completedCourses": ["00940139"],
        },
        academic_context={"degreeRequirements": [{"id": "rule-1"}]},
        validation=ContextValidation(status="valid"),
    )
    result = validate_context_pack(pack)
    assert result.status == "valid"
