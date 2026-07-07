"""Unit tests for offline eval oracles (Phase 23)."""

from __future__ import annotations

from app.agent.evaluation.oracles import (
    check_oracle_contradictions,
    compute_graduation_oracle_facts,
    compute_prerequisite_oracle_facts,
    compute_semester_plan_oracle_facts,
    derive_oracle_facts,
)

_WORLD = {
    "degree": {
        "totalRequiredCredits": 120,
        "mandatoryCourses": ["A", "B", "C"],
    },
    "courses": {
        "A": {"credits": 3, "prerequisites": []},
        "B": {"credits": 4, "prerequisites": ["A"]},
        "C": {"credits": 3, "prerequisites": []},
    },
    "student": {"completedCourses": ["A"]},
}


def test_credits_oracle_computes_completed_credits() -> None:
    facts = compute_graduation_oracle_facts(_WORLD)
    assert facts["completedCredits"] == 3


def test_graduation_oracle_computes_missing_credits() -> None:
    facts = compute_graduation_oracle_facts(_WORLD)
    assert facts["missingCredits"] == 117


def test_mandatory_course_oracle_computes_missing_courses() -> None:
    facts = compute_graduation_oracle_facts(_WORLD)
    assert facts["missingMandatoryCourses"] == ["B", "C"]


def test_prerequisite_oracle_computes_satisfaction() -> None:
    facts = compute_prerequisite_oracle_facts(_WORLD)
    assert facts["satisfiedPrerequisites"]["B"] is True
    assert facts["satisfiedPrerequisites"]["C"] is True


def test_semester_plan_oracle_detects_conflict() -> None:
    world = {
        **_WORLD,
        "semesterPlan": {"maxCredits": 5, "selectedCourses": ["B", "C"]},
    }
    facts = compute_semester_plan_oracle_facts(world)
    assert facts["creditLimitExceeded"] is True


def test_oracle_handles_malformed_synthetic_world_safely() -> None:
    facts = derive_oracle_facts({"courses": "not-a-dict"})
    assert isinstance(facts, dict)


def test_check_oracle_contradictions_detects_mismatch() -> None:
    derived = derive_oracle_facts(_WORLD)
    failures = check_oracle_contradictions(
        expected_facts={"completedCredits": 99},
        derived_facts=derived,
    )
    assert failures == ["oracle_mismatch:completedCredits"]
