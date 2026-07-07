"""Unit tests for requirement explanation response builder."""

from app.agent.requirement_explanation_response_builder import (
    build_requirement_explanation_text,
    _pick_target_entry,
)
from app.agent.schemas import AgentContextPack
from app.services.requirement_matching_service import RequirementMatchEntry, RequirementMatchingSummary


def test_pick_target_entry_by_status():
    matching = RequirementMatchingSummary(
        entries=[
            RequirementMatchEntry(
                requirement_group_id="electives",
                title="Faculty electives",
                status="missing",
            )
        ]
    )
    target = _pick_target_entry(
        matching=matching,
        entities={},
        user_message="Explain my missing electives",
    )
    assert target is not None
    assert target.requirement_group_id == "electives"


def test_build_requirement_explanation_text():
    target = RequirementMatchEntry(
        requirement_group_id="math",
        title="Math requirement",
        status="partial",
        credits_completed=2,
        credits_required=6,
        credits_remaining=4,
    )
    context = AgentContextPack(
        conversation_id="c1",
        run_id="r1",
        user_id="u1",
        intent="requirement_explanation",
    )
    text = build_requirement_explanation_text(
        target_entry=target,
        audit=type("Audit", (), {"progress": {"requirementProgress": []}, "warnings": []})(),
        context=context,
    )
    assert "Math requirement" in text
    assert "partial" in text.lower()
