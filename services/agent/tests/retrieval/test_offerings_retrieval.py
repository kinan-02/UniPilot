"""Regression tests for offerings retrieval and validation."""

from __future__ import annotations

import pytest

from app.agent.context_validator import validate_context_pack
from app.agent.schemas import AgentContextPack, ContextValidation
from app.agent.context_builder import resolve_target_semester_code
from app.retrieval.evaluation.retrieval_metrics import hit_at_k, wrong_source_rate


def test_resolve_next_semester_code():
    resolved = resolve_target_semester_code(
        {"targetSemester": "next"},
        profile_semester="2025-1",
        available_semesters=["2025-1", "2025-2", "2025-3"],
    )
    assert resolved == "2025-2"


def test_wrong_semester_avoidance_metric():
    retrieved = ["offering:2025-2:00940139", "wiki:course:00940139"]
    negative = ["offering:2024-1:00940139"]
    assert wrong_source_rate(retrieved, negative) == 0.0
    bad = ["offering:2024-1:00940139", "offering:2025-2:00940139"]
    assert wrong_source_rate(bad, negative) > 0


def test_hit_at_one_for_offering_source():
    retrieved = ["offering:2025-2:00940139", "wiki:course:00940139"]
    required = ["offering:2025-2:00940139"]
    assert hit_at_k(retrieved, required, 1) == 1.0


def test_context_validator_rejects_unresolved_semester_for_planning():
    pack = AgentContextPack(
        conversation_id="c1",
        run_id="r1",
        user_id="u1",
        intent="semester_plan_generation",
        entities={},
        user_context={"profile": {"catalogYear": 2025}, "completedCourses": []},
        validation=ContextValidation(status="valid"),
    )
    result = validate_context_pack(pack)
    assert any("semester" in error.lower() for error in result.errors)
