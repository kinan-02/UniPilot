"""Unit tests for `extract_temporal_pattern` (docs/agent/AGENT_VISION.md §5, primitive 5).

Output shape, `fact_type` vocabulary, bucket classification, and the
confidence formula are defined in
docs/agent/TEMPORAL_PATTERN_CONTRACT.md. Real-data cases run against the
real raw Technion directory (`use_real_technion_raw_dir`) using facts
verified directly before writing assertions (not assumed):
- 7 real semester files exist: 2023_201, 2024_{200,201,202}, 2025_{200,201,202}
  -> 2 Winters (term 1), 3 Springs (term 2), 2 Summers (term 3).
- Course "00440148" is offered in all 7 files -> "reliable" every term.
- Course "00440105" is offered in all 5 Winter+Spring files, 0 of 2 Summers
  -> "reliable" Winter/Spring, "never" Summer.
- Course "99999999" appears in none of the 7 files -> "never" every term.
"""

from __future__ import annotations

import json

import pytest

from app.agent_core.tools.primitives.extract_temporal_pattern import (
    ExtractTemporalPatternInput,
    _confidence_from_history_size,
    _course_codes_in_file,
    run_extract_temporal_pattern,
)


async def test_missing_fact_type_fails_closed():
    result = await run_extract_temporal_pattern(ExtractTemporalPatternInput(fact_type="  ", entity="00440148"))
    assert result.ok is False
    assert "fact_type_required" in result.error


async def test_unknown_fact_type_fails_closed():
    result = await run_extract_temporal_pattern(
        ExtractTemporalPatternInput(fact_type="course_difficulty", entity="00440148")
    )
    assert result.ok is False
    assert "unknown_fact_type: course_difficulty" in result.error


async def test_missing_entity_fails_closed():
    result = await run_extract_temporal_pattern(
        ExtractTemporalPatternInput(fact_type="course_offering", entity="  ")
    )
    assert result.ok is False
    assert "entity_required" in result.error


async def test_raw_data_not_configured_fails_closed(monkeypatch):
    from app.retrieval.graph_engine.graph_registry import graph_registry

    monkeypatch.setattr(graph_registry, "is_configured", lambda *_a, **_k: False)
    result = await run_extract_temporal_pattern(
        ExtractTemporalPatternInput(fact_type="course_offering", entity="00440148")
    )
    assert result.ok is False
    assert "academic_raw_data_not_configured" in result.error


async def test_raw_data_unavailable_fails_closed(monkeypatch):
    from app.retrieval.graph_engine.graph_registry import graph_registry

    monkeypatch.setattr(graph_registry, "is_configured", lambda *_a, **_k: True)

    import app.agent_core.tools.primitives.extract_temporal_pattern as module

    def _raise(*_a, **_k):
        raise RuntimeError("disk on fire")

    monkeypatch.setattr(module, "get_settings", _raise)
    result = await run_extract_temporal_pattern(
        ExtractTemporalPatternInput(fact_type="course_offering", entity="00440148")
    )
    assert result.ok is False
    assert "academic_raw_data_unavailable" in result.error


async def test_insufficient_history_fails_closed(use_real_technion_raw_dir, monkeypatch):
    import app.agent_core.tools.primitives.extract_temporal_pattern as module

    monkeypatch.setattr(module, "discover_semester_catalogs", lambda *_a, **_k: [])
    result = await run_extract_temporal_pattern(
        ExtractTemporalPatternInput(fact_type="course_offering", entity="00440148")
    )
    assert result.ok is False
    assert "insufficient_history" in result.error


async def test_course_reliable_every_term(use_real_technion_raw_dir):
    result = await run_extract_temporal_pattern(
        ExtractTemporalPatternInput(fact_type="course_offering", entity="00440148")
    )
    assert result.ok is True
    assert result.data["factType"] == "course_offering"
    assert result.data["entity"] == "00440148"
    assert result.data["totalSemestersInHistory"] == 7
    assert result.data["termPatterns"] == {
        "1": {"label": "reliable", "observed": 2, "total": 2},
        "2": {"label": "reliable", "observed": 3, "total": 3},
        "3": {"label": "reliable", "observed": 2, "total": 2},
    }
    # Scalar projection (root fix): a directly-surfaceable label per term.
    assert result.data["termLabels"] == {"1": "reliable", "2": "reliable", "3": "reliable"}
    # Scalar count (§19): sum of observed across terms = 2+3+2, the grain `map` reads.
    assert result.data["semestersOffered"] == 7
    assert result.certainty.basis == "predicted_pattern"
    assert result.certainty.confidence == pytest.approx(0.95)


async def test_course_reliable_winter_spring_never_summer(use_real_technion_raw_dir):
    result = await run_extract_temporal_pattern(
        ExtractTemporalPatternInput(fact_type="course_offering", entity="00440105")
    )
    assert result.ok is True
    assert result.data["termPatterns"] == {
        "1": {"label": "reliable", "observed": 2, "total": 2},
        "2": {"label": "reliable", "observed": 3, "total": 3},
        "3": {"label": "never", "observed": 0, "total": 2},
    }
    # never offered in summer -> 2+3+0 = 5 semesters offered (< the 7 in history).
    assert result.data["semestersOffered"] == 5


async def test_course_irregular_in_one_term(use_real_technion_raw_dir):
    """Course "03180530" is offered in exactly 1 of 2 Winter files (2024,
    not 2025) and 0 of the Spring/Summer files -- verified directly against
    the real data before writing this assertion, the one real course found
    with a genuinely partial (neither 1.0 nor 0.0) ratio in this dataset."""
    result = await run_extract_temporal_pattern(
        ExtractTemporalPatternInput(fact_type="course_offering", entity="03180530")
    )
    assert result.ok is True
    assert result.data["termPatterns"]["1"] == {"label": "irregular", "observed": 1, "total": 2}
    assert result.data["termPatterns"]["2"]["label"] == "never"
    assert result.data["termPatterns"]["3"]["label"] == "never"


async def test_nonexistent_course_is_never_every_term_not_a_failure(use_real_technion_raw_dir):
    """Mining a history for a course that never appears anywhere is still a
    legitimate, successful result -- whether the course code is a *real*
    course is get_entity's concern, not this primitive's."""
    result = await run_extract_temporal_pattern(
        ExtractTemporalPatternInput(fact_type="course_offering", entity="99999999")
    )
    assert result.ok is True
    assert all(term["label"] == "never" and term["observed"] == 0 for term in result.data["termPatterns"].values())
    assert result.data["totalSemestersInHistory"] == 7
    assert result.data["semestersOffered"] == 0  # never appears -> offered in zero semesters


# -- _confidence_from_history_size -------------------------------------


def test_confidence_formula_capped_at_0_95():
    assert _confidence_from_history_size(7) == pytest.approx(0.95)
    assert _confidence_from_history_size(100) == pytest.approx(0.95)


def test_confidence_formula_scales_with_history_size():
    assert _confidence_from_history_size(0) == pytest.approx(0.5)
    assert _confidence_from_history_size(1) == pytest.approx(0.6)


# -- _course_codes_in_file -------------------------------------------------


def test_course_codes_in_file_missing_file_returns_empty_set():
    assert _course_codes_in_file("/does/not/exist.json") == set()


def test_course_codes_in_file_malformed_json_returns_empty_set(tmp_path):
    bad_file = tmp_path / "bad.json"
    bad_file.write_text("{not valid json", encoding="utf-8")
    assert _course_codes_in_file(str(bad_file)) == set()


def test_course_codes_in_file_parses_real_shape(tmp_path):
    good_file = tmp_path / "good.json"
    good_file.write_text(
        json.dumps([{"general": {"מספר מקצוע": "00440148"}}, {"general": {"מספר מקצוע": "00440105"}}]),
        encoding="utf-8",
    )
    assert _course_codes_in_file(str(good_file)) == {"00440148", "00440105"}


async def test_unknown_offering_code_skipped(use_real_technion_raw_dir, monkeypatch):
    """A discovered catalog whose offering_code isn't in OFFERING_LABELS
    (shouldn't happen via the real filename regex, but defensively handled)
    is skipped rather than crashing or corrupting the term-index buckets."""
    import app.agent_core.tools.primitives.extract_temporal_pattern as module
    from app.retrieval.graph_engine.semester_catalog import SemesterCatalogInfo

    real_catalogs = module.discover_semester_catalogs(use_real_technion_raw_dir)
    bogus = SemesterCatalogInfo(
        filename="courses_2099_999.json",
        path="/does/not/exist.json",
        file_academic_year=2099,
        offering_code=999,
        plan_semester_code="2099-9",
        calendar_year=2099,
        label_en="Unknown",
        label_he="לא ידוע",
        display_label="Unknown 2099",
    )
    monkeypatch.setattr(module, "discover_semester_catalogs", lambda *_a, **_k: [*real_catalogs, bogus])

    result = await run_extract_temporal_pattern(
        ExtractTemporalPatternInput(fact_type="course_offering", entity="00440148")
    )
    assert result.ok is True
    # The bogus catalog contributes to totalSemestersInHistory (it's a real
    # discovered semester) but not to any term bucket.
    assert result.data["totalSemestersInHistory"] == 8
    assert set(result.data["termPatterns"]) == {"1", "2", "3"}
