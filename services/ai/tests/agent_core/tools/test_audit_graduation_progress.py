"""Unit tests for `audit_graduation_progress` (docs/agent/HIGHER_LEVEL_TOOLS.md).

Real-data facts verified directly against the real engine before writing
assertions, not assumed:
- track-materials-engineering has 57 required courses (reused from
  test_get_track_requirements.py).
- With the first 10 of those 57 marked completed: completedRequiredCourses
  has 10 entries, remainingRequiredCourses has 47, the default
  count_threshold(>=57) rule is not satisfied, and include_plan=True
  produces a real projected plan (semestersUsed=3, 37 still unscheduled
  within the default 8-semester bound) with a predicted_pattern-basis
  certainty (confidence 0.95).
- With all 57 marked completed: graduationComplete is True and
  remainingRequiredCourses is empty, so include_plan=True correctly skips
  calling search_over_state entirely (projectedPlan stays None -- verified
  there's nothing left to schedule, not that the call silently failed).
"""

from __future__ import annotations

from typing import Any

from app.agent_core.tools.composites.audit_graduation_progress import (
    AuditGraduationProgressInput,
    run_audit_graduation_progress,
)
from app.agent_core.tools.envelope import ToolOutputEnvelope


async def test_empty_track_slug_fails_closed():
    result = await run_audit_graduation_progress(AuditGraduationProgressInput(track_slug="  "))
    assert result.ok is False
    assert "track_slug_required" in result.error


async def test_unknown_track_fails_closed(use_real_academic_engine):
    result = await run_audit_graduation_progress(AuditGraduationProgressInput(track_slug="track-does-not-exist"))
    assert result.ok is False
    assert "track_requirements_failed" in result.error
    assert "track_not_found: track-does-not-exist" in result.error


async def _real_required_course_ids(track_slug: str) -> list[str]:
    from app.agent_core.tools.composites.get_track_requirements import (
        GetTrackRequirementsInput,
        run_get_track_requirements,
    )

    result = await run_get_track_requirements(GetTrackRequirementsInput(track_slug=track_slug))
    return [entry["id"] for entry in result.data["requiredCourses"]]


def _state_with_completed(course_ids: list[str]) -> dict[str, Any]:
    return {
        "currentSemesterCode": "2025-1",
        "completedCourses": [{"courseNumber": cid, "status": "completed"} for cid in course_ids],
        "plannedSemesters": {},
    }


async def test_partial_progress_with_default_rule(use_real_academic_engine):
    required_ids = await _real_required_course_ids("track-materials-engineering")
    completed_ids = required_ids[:10]
    result = await run_audit_graduation_progress(
        AuditGraduationProgressInput(
            track_slug="track-materials-engineering", state=_state_with_completed(completed_ids)
        )
    )
    assert result.ok is True
    assert result.data["totalRequiredCourses"] == 57
    assert len(result.data["completedRequiredCourses"]) == 10
    assert len(result.data["remainingRequiredCourses"]) == 47
    assert result.data["graduationComplete"] is False
    assert result.data["completionRuleResult"] == {
        "type": "count_threshold",
        "count": 10,
        "comparator": ">=",
        "threshold": 57,
        "satisfied": False,
    }
    assert result.data["projectedPlan"] is None
    assert result.data["projectedPlanCertainty"] is None
    assert result.warnings == []
    assert result.certainty.basis == "official_record"


async def test_custom_completion_rule_overrides_default(use_real_academic_engine):
    required_ids = await _real_required_course_ids("track-materials-engineering")
    completed_ids = required_ids[:10]
    result = await run_audit_graduation_progress(
        AuditGraduationProgressInput(
            track_slug="track-materials-engineering",
            state=_state_with_completed(completed_ids),
            completion_rule={
                "type": "count_threshold",
                "source": "requiredCourses",
                "filter": {"completed": True},
                "comparator": ">=",
                "threshold": 5,
            },
        )
    )
    assert result.ok is True
    assert result.data["graduationComplete"] is True
    assert result.data["completionRuleResult"]["threshold"] == 5


async def test_malformed_completion_rule_fails_closed(use_real_academic_engine):
    result = await run_audit_graduation_progress(
        AuditGraduationProgressInput(
            track_slug="track-materials-engineering",
            completion_rule={"type": "count_threshold", "source": "requiredCourses"},
        )
    )
    assert result.ok is False
    assert "completion_rule_evaluation_failed" in result.error


async def test_include_plan_produces_real_projection(use_real_academic_data):
    required_ids = await _real_required_course_ids("track-materials-engineering")
    completed_ids = required_ids[:10]
    result = await run_audit_graduation_progress(
        AuditGraduationProgressInput(
            track_slug="track-materials-engineering",
            state=_state_with_completed(completed_ids),
            include_plan=True,
        )
    )
    assert result.ok is True
    assert result.data["projectedPlan"] is not None
    assert result.data["projectedPlan"]["semestersUsed"] == 3
    assert len(result.data["projectedPlan"]["unscheduledCourses"]) == 37
    assert result.data["projectedPlanCertainty"]["basis"] == "predicted_pattern"
    assert result.data["projectedPlanCertainty"]["confidence"] == 0.95
    assert result.warnings == []


async def test_full_completion_skips_plan_entirely(use_real_academic_engine):
    required_ids = await _real_required_course_ids("track-materials-engineering")
    result = await run_audit_graduation_progress(
        AuditGraduationProgressInput(
            track_slug="track-materials-engineering",
            state=_state_with_completed(required_ids),
            include_plan=True,
        )
    )
    assert result.ok is True
    assert result.data["graduationComplete"] is True
    assert result.data["remainingRequiredCourses"] == []
    assert result.data["projectedPlan"] is None
    assert result.warnings == []


async def test_graduation_plan_unavailable_degrades_gracefully(use_real_academic_engine, monkeypatch):
    import app.agent_core.tools.composites.audit_graduation_progress as module

    async def _fake_search(*_a, **_k):
        return ToolOutputEnvelope(ok=False, data=None, error="academic_graph_unavailable: boom")

    monkeypatch.setattr(module, "run_search_over_state", _fake_search)

    required_ids = await _real_required_course_ids("track-materials-engineering")
    completed_ids = required_ids[:10]
    result = await run_audit_graduation_progress(
        AuditGraduationProgressInput(
            track_slug="track-materials-engineering",
            state=_state_with_completed(completed_ids),
            include_plan=True,
        )
    )
    assert result.ok is True
    assert result.data["projectedPlan"] is None
    assert "graduation_plan_unavailable" in result.warnings


async def test_track_requirements_warnings_propagate(use_real_academic_engine, monkeypatch):
    import app.agent_core.tools.composites.audit_graduation_progress as module

    async def _fake_track_requirements(*_a, **_k):
        return ToolOutputEnvelope(
            ok=True,
            data={"trackSlug": "track-materials-engineering", "track": {}, "requiredCourses": []},
            warnings=["required_courses_unavailable"],
        )

    monkeypatch.setattr(module, "run_get_track_requirements", _fake_track_requirements)

    result = await run_audit_graduation_progress(
        AuditGraduationProgressInput(track_slug="track-materials-engineering")
    )
    assert result.ok is True
    assert result.data["totalRequiredCourses"] == 0
    assert "required_courses_unavailable" in result.warnings
