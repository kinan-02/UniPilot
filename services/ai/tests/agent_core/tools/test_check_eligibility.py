"""Unit tests for `check_eligibility` (docs/agent/HIGHER_LEVEL_TOOLS.md).

Real-data facts verified directly before writing assertions, not assumed:
- "00440148" requires {"00440105", "00440140"} (reused throughout this
  suite).
- "00140008" has zero prerequisites, reliable Winter(1)/Spring(2), never
  Summer(3) (reused from test_search_over_state.py).
"""

from __future__ import annotations

from app.agent_core.tools.composites.check_eligibility import (
    CheckEligibilityInput,
    run_check_eligibility,
)


async def test_empty_course_id_fails_closed():
    result = await run_check_eligibility(CheckEligibilityInput(course_id="  "))
    assert result.ok is False
    assert "course_id_required" in result.error


async def test_unparseable_target_semester_fails_closed():
    result = await run_check_eligibility(
        CheckEligibilityInput(course_id="00440148", target_semester="not-a-semester")
    )
    assert result.ok is False
    assert "unparseable_target_semester" in result.error


async def test_graph_not_configured_fails_closed(monkeypatch):
    from app.retrieval.graph_engine.graph_registry import graph_registry

    monkeypatch.setattr(graph_registry, "is_configured", lambda *_a, **_k: False)
    result = await run_check_eligibility(CheckEligibilityInput(course_id="00440148"))
    assert result.ok is False
    assert "academic_graph_not_configured" in result.error


async def test_graph_unavailable_fails_closed(monkeypatch):
    from app.retrieval.graph_engine.graph_registry import graph_registry

    monkeypatch.setattr(graph_registry, "is_configured", lambda *_a, **_k: True)

    def _raise(*_a, **_k):
        raise RuntimeError("boom")

    monkeypatch.setattr(graph_registry, "get_engine", _raise)
    result = await run_check_eligibility(CheckEligibilityInput(course_id="00440148"))
    assert result.ok is False
    assert "academic_graph_unavailable" in result.error


async def test_unknown_course_fails_closed(use_real_academic_engine):
    result = await run_check_eligibility(CheckEligibilityInput(course_id="99999999"))
    assert result.ok is False
    assert "entity_not_found: 99999999" in result.error


async def test_eligible_when_prerequisites_completed(use_real_academic_engine):
    state = {
        "completedCourses": [
            {"courseNumber": "00440105", "status": "completed"},
            {"courseNumber": "00440140", "status": "completed"},
        ]
    }
    result = await run_check_eligibility(CheckEligibilityInput(course_id="00440148", state=state))
    assert result.ok is True
    assert result.data["eligible"] is True
    assert result.data["missingPrerequisites"] == []
    assert result.certainty.basis == "official_record"
    assert result.certainty.confidence == 1.0


async def test_not_eligible_when_prerequisites_missing(use_real_academic_engine):
    result = await run_check_eligibility(
        CheckEligibilityInput(course_id="00440148", state={"completedCourses": []})
    )
    assert result.ok is True
    assert result.data["eligible"] is False
    assert set(result.data["missingPrerequisites"]) == {"00440105", "00440140"}


async def test_failed_course_does_not_count_as_satisfying_prerequisite(use_real_academic_engine):
    state = {
        "completedCourses": [
            {"courseNumber": "00440105", "status": "failed"},
            {"courseNumber": "00440140", "status": "completed"},
        ]
    }
    result = await run_check_eligibility(CheckEligibilityInput(course_id="00440148", state=state))
    assert result.ok is True
    assert result.data["eligible"] is False
    assert result.data["missingPrerequisites"] == ["00440105"]


async def test_no_target_semester_leaves_offering_fields_null(use_real_academic_engine):
    result = await run_check_eligibility(CheckEligibilityInput(course_id="00140008"))
    assert result.ok is True
    assert result.data["offeringPattern"] is None
    assert result.data["schedulable"] is None
    assert result.warnings == []


async def test_target_semester_excluded_by_offering_pattern(use_real_academic_data):
    result = await run_check_eligibility(
        CheckEligibilityInput(course_id="00140008", target_semester="2025-3")
    )
    assert result.ok is True
    assert result.data["eligible"] is True
    assert result.data["offeringPattern"]["termPatterns"]["3"]["label"] == "never"
    assert result.data["schedulable"] is False


async def test_target_semester_allowed_by_offering_pattern(use_real_academic_data):
    result = await run_check_eligibility(
        CheckEligibilityInput(course_id="00140008", target_semester="2025-1")
    )
    assert result.ok is True
    assert result.data["schedulable"] is True


async def test_offering_pattern_unavailable_degrades_gracefully(use_real_academic_engine, monkeypatch):
    import app.agent_core.tools.composites.check_eligibility as module
    from app.agent_core.tools.envelope import ToolOutputEnvelope

    async def _fake_offering(*_a, **_k):
        return ToolOutputEnvelope(ok=False, data=None, error="insufficient_history")

    monkeypatch.setattr(module, "run_extract_temporal_pattern", _fake_offering)

    result = await run_check_eligibility(
        CheckEligibilityInput(course_id="00140008", target_semester="2025-1")
    )
    assert result.ok is True
    assert result.data["offeringPattern"] is None
    assert result.data["schedulable"] is None
    assert "offering_pattern_unavailable" in result.warnings
