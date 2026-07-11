"""Unit tests for `find_requirement_substitutes` (docs/agent/HIGHER_LEVEL_TOOLS.md).

Real-data facts verified directly against the real engine before writing
assertions, not assumed (reused/extended from
test_search_over_state.py's own `find_substitute` verification):
- track-materials-engineering has 57 required courses, including
  "00350022" (used as the course being substituted here).
- Substituting for "00350022" within the default 8-semester bound yields
  13 schedulable candidates, the first ("00350053") landing in 2025-2 with
  a predicted_pattern/0.95 certainty; 43 candidates stay unscheduled.
- Capping to max_semesters=1 narrows the schedulable candidates to 9.
"""

from __future__ import annotations

from typing import Any

from app.agent_core.tools.composites.find_requirement_substitutes import (
    FindRequirementSubstitutesInput,
    run_find_requirement_substitutes,
)
from app.agent_core.tools.envelope import ToolOutputEnvelope


def _state() -> dict[str, Any]:
    return {"currentSemesterCode": "2025-1", "completedCourses": [], "plannedSemesters": {}}


async def test_empty_course_id_fails_closed():
    result = await run_find_requirement_substitutes(
        FindRequirementSubstitutesInput(course_id="  ", track_slug="track-materials-engineering")
    )
    assert result.ok is False
    assert "course_id_required" in result.error


async def test_empty_track_slug_fails_closed():
    result = await run_find_requirement_substitutes(
        FindRequirementSubstitutesInput(course_id="00350022", track_slug="  ")
    )
    assert result.ok is False
    assert "track_slug_required" in result.error


async def test_unknown_track_fails_closed(use_real_academic_engine):
    result = await run_find_requirement_substitutes(
        FindRequirementSubstitutesInput(course_id="00350022", track_slug="track-does-not-exist")
    )
    assert result.ok is False
    assert "track_requirements_failed" in result.error
    assert "track_not_found: track-does-not-exist" in result.error


async def test_course_not_in_track_fails_closed(use_real_academic_engine):
    result = await run_find_requirement_substitutes(
        FindRequirementSubstitutesInput(course_id="00000000", track_slug="track-materials-engineering")
    )
    assert result.ok is False
    assert "course_not_in_track: 00000000 not in track-materials-engineering" in result.error


async def test_finds_candidates_from_real_data(use_real_academic_data):
    result = await run_find_requirement_substitutes(
        FindRequirementSubstitutesInput(
            course_id="00350022", track_slug="track-materials-engineering", state=_state()
        )
    )
    assert result.ok is True
    assert result.data["courseId"] == "00350022"
    assert result.data["trackSlug"] == "track-materials-engineering"
    assert len(result.data["candidates"]) == 13
    assert result.data["candidates"][0] == {
        "courseNumber": "00350053",
        "semester": "2025-2",
        "offeringCertainty": {"basis": "predicted_pattern", "confidence": 0.95},
    }
    assert all(c["courseNumber"] != "00350022" for c in result.data["candidates"])
    assert len(result.data["unscheduledCandidates"]) == 43
    assert "not a semantic verification" in result.data["note"]
    assert result.certainty.basis == "predicted_pattern"
    assert result.warnings == []


async def test_max_semesters_override_narrows_candidates(use_real_academic_data):
    result = await run_find_requirement_substitutes(
        FindRequirementSubstitutesInput(
            course_id="00350022",
            track_slug="track-materials-engineering",
            state=_state(),
            max_semesters=1,
        )
    )
    assert result.ok is True
    assert len(result.data["candidates"]) == 9


async def test_substitute_search_failure_propagates(use_real_academic_engine, monkeypatch):
    import app.agent_core.tools.composites.find_requirement_substitutes as module

    async def _fake_search(*_a, **_k):
        return ToolOutputEnvelope(ok=False, data=None, error="academic_graph_unavailable: boom")

    monkeypatch.setattr(module, "run_search_over_state", _fake_search)

    result = await run_find_requirement_substitutes(
        FindRequirementSubstitutesInput(
            course_id="00350022", track_slug="track-materials-engineering", state=_state()
        )
    )
    assert result.ok is False
    assert "substitute_search_failed" in result.error


async def test_track_requirements_warnings_propagate(use_real_academic_engine, monkeypatch):
    import app.agent_core.tools.composites.find_requirement_substitutes as module

    async def _fake_track_requirements(*_a, **_k):
        return ToolOutputEnvelope(
            ok=True,
            data={
                "trackSlug": "track-materials-engineering",
                "track": {},
                "requiredCourses": [{"id": "00350022", "nodeType": "course"}],
            },
            warnings=["required_courses_unavailable"],
        )

    async def _fake_search(*_a, **_k):
        return ToolOutputEnvelope(ok=True, data={"plan": {}, "unscheduledCourses": []})

    monkeypatch.setattr(module, "run_get_track_requirements", _fake_track_requirements)
    monkeypatch.setattr(module, "run_search_over_state", _fake_search)

    result = await run_find_requirement_substitutes(
        FindRequirementSubstitutesInput(
            course_id="00350022", track_slug="track-materials-engineering", state=_state()
        )
    )
    assert result.ok is True
    assert "required_courses_unavailable" in result.warnings
