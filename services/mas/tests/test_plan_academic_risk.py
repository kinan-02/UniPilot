"""Unit tests for academic risk preview mapping in MAS."""

from __future__ import annotations

from app.orchestrator.artifacts import ViolationType
from app.services.plan_academic_risk import violations_from_academic_risk_preview


def test_violations_from_academic_risk_preview_maps_high_severity() -> None:
    analysis = {
        "summary": {"highSeverityCount": 1},
        "risks": [
            {
                "riskType": "course_already_completed",
                "severity": "high",
                "title": "Course already completed",
                "explanation": "Discrete Math is already completed.",
                "relatedCourseIds": ["abc123"],
            },
            {
                "riskType": "failed_course_retake",
                "severity": "medium",
                "title": "Retake",
                "explanation": "Previously failed.",
                "relatedCourseIds": ["abc123"],
            },
        ],
    }

    violations, references, evidence = violations_from_academic_risk_preview(analysis)

    assert len(violations) == 1
    assert violations[0].type == ViolationType.OTHER
    assert "already completed" in violations[0].message.lower()
    assert "academic_risk:hard_vetoes=1" in references
    assert evidence["academicRiskCount"] == 2
