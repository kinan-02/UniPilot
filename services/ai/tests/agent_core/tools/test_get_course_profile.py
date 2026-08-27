"""Unit tests for `get_course_profile` (docs/agent/HIGHER_LEVEL_TOOLS.md).

Real-data facts verified directly against the real engine before writing
assertions, not assumed:
- "00440148" has both a catalog entry and a wiki page (reused throughout
  this test suite), prereqs {"00440105", "00440140"}, 9 real dependents
  (courses that list it as *their* prerequisite -- a different, unverified-
  until-now direction from earlier tests), and belongs_to 4 real tracks.
- "02360861" is wiki-only (no catalog entry) -- `get_entity` succeeds with
  warning "course_not_in_active_semester_catalog" (see test_get_entity.py),
  used here only to confirm that warning propagates through the composite,
  not to exercise a traverse_relationship failure (verified this course
  unexpectedly *does* have a graph node -- it's referenced as a prerequisite
  target by another course's prerequisite string -- so it doesn't naturally
  trigger the entity_not_found degradation path).
"""

from __future__ import annotations

from app.agent_core.tools.composites.get_course_profile import (
    GetCourseProfileInput,
    run_get_course_profile,
)
from app.agent_core.tools.envelope import ToolOutputEnvelope


async def test_empty_course_id_fails_closed():
    result = await run_get_course_profile(GetCourseProfileInput(course_id="  "))
    assert result.ok is False
    assert "course_id_required" in result.error


async def test_unknown_course_fails_closed(use_real_academic_engine):
    result = await run_get_course_profile(GetCourseProfileInput(course_id="99999999"))
    assert result.ok is False
    assert "course_not_found: 99999999" in result.error


async def test_full_profile_with_real_data(use_real_academic_data):
    result = await run_get_course_profile(GetCourseProfileInput(course_id="00440148"))
    assert result.ok is True
    assert result.data["courseId"] == "00440148"
    assert result.data["course"]["name"]
    assert result.data["course"]["wikiSlug"] is not None

    prereq_ids = {entry["id"] for entry in result.data["prerequisites"]}
    assert {"00440105", "00440140"} <= prereq_ids

    dependent_ids = {entry["id"] for entry in result.data["dependents"]}
    assert {"00450100", "01140035", "01160210"} <= dependent_ids

    track_ids = {entry["id"] for entry in result.data["tracks"]}
    assert "track-electrical-engineering" in track_ids

    assert result.data["offeringPattern"]["factType"] == "course_offering"
    assert result.data["offeringPattern"]["termPatterns"]["1"]["label"] == "reliable"
    # The scalar projections propagate from extract_temporal_pattern: the per-term
    # label (root fix) and the semesters-offered count (§19, the grain `map` reads).
    assert result.data["offeringPattern"]["termLabels"]["1"] == "reliable"
    assert result.data["offeringPattern"]["semestersOffered"] == 7
    assert "certainty" in result.data["offeringPattern"]
    assert result.data["offeringPattern"]["certainty"]["basis"] == "predicted_pattern"

    assert result.warnings == []
    assert result.certainty.basis == "official_record"
    assert result.certainty.confidence == 1.0


async def test_get_entity_warnings_propagate(use_real_academic_engine):
    result = await run_get_course_profile(GetCourseProfileInput(course_id="02360861"))
    assert result.ok is True
    assert "course_not_in_active_semester_catalog" in result.warnings


async def test_prerequisites_unavailable_degrades_gracefully(monkeypatch):
    import app.agent_core.tools.composites.get_course_profile as module

    async def _fake_get_entity(*_a, **_k):
        return ToolOutputEnvelope(ok=True, data={"entityType": "course", "entityId": "X"}, warnings=[])

    call_count = {"n": 0}

    async def _fake_traverse(payload, *_a, **_k):
        call_count["n"] += 1
        return ToolOutputEnvelope(ok=False, data=None, error="entity_not_found: X")

    async def _fake_offering(*_a, **_k):
        return ToolOutputEnvelope(ok=False, data=None, error="insufficient_history")

    monkeypatch.setattr(module, "run_get_entity", _fake_get_entity)
    monkeypatch.setattr(module, "run_traverse_relationship", _fake_traverse)
    monkeypatch.setattr(module, "run_extract_temporal_pattern", _fake_offering)

    result = await run_get_course_profile(GetCourseProfileInput(course_id="X"))
    assert result.ok is True
    assert result.data["prerequisites"] == []
    assert result.data["dependents"] == []
    assert result.data["tracks"] == []
    assert result.warnings == [
        "prerequisites_unavailable",
        "dependents_unavailable",
        "tracks_unavailable",
        "offering_pattern_unavailable",
    ]
    assert result.data["offeringPattern"] is None
    assert call_count["n"] == 3  # forward+backward has_prerequisite, belongs_to
