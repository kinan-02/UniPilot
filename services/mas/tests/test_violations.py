"""Unit tests for typed violations."""

from __future__ import annotations

from app.orchestrator.artifacts import ViolationType
from app.orchestrator.violations import has_violation_type, violation_from_message


def test_violation_from_message_classifies_schedule_conflict() -> None:
    violation = violation_from_message(
        "Schedule conflict between 00140008 and 00140102 on Sunday (08:30 vs 09:30)."
    )
    assert violation.type == ViolationType.SCHEDULE_CONFLICT
    assert "00140008" in violation.course_ids


def test_has_violation_type_detects_credit_overload() -> None:
    typed = [violation_from_message("Credit overload: 20 credits exceeds limit of 18.")]
    assert has_violation_type(typed, ViolationType.CREDIT_OVERLOAD)
