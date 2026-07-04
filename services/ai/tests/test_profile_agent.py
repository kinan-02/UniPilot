"""Unit tests for profile specialist sub-agent (no OpenAI calls)."""

from __future__ import annotations

from pathlib import Path

import pytest

from app.schemas.advisor import TranscriptEntryPayload, UserContextPayload
from app.services.academic_graph_engine import AcademicGraphEngine
from app.services.profile_agent import (
    ProfileAgentResult,
    _assess_course_fit,
    _build_profile_summary,
    _format_transcript,
    _profile_has_data,
    run_profile_agent,
)

REPO_ROOT = Path(__file__).resolve().parents[3]
WIKI_DIR = REPO_ROOT / "services/data-engineering/data/catalog_valut/catalog_valut/wiki"
TECHNION_RAW_DIR = REPO_ROOT / "services/data-engineering/data/raw/technion"
CATALOG_JSON = TECHNION_RAW_DIR / "courses_2025_201.json"


@pytest.fixture(scope="module")
def engine() -> AcademicGraphEngine:
    if not WIKI_DIR.exists() or not CATALOG_JSON.exists():
        pytest.skip("Real wiki/catalog data not available locally")
    graph_engine = AcademicGraphEngine()
    graph_engine.load_from_paths(
        str(WIKI_DIR),
        str(TECHNION_RAW_DIR),
        semester_filename="courses_2025_201.json",
    )
    graph_engine.build_graph()
    return graph_engine


def test_profile_has_data_detects_transcript():
    empty = UserContextPayload()
    assert not _profile_has_data(empty)
    with_data = UserContextPayload(completed_courses=["00440105"])
    assert _profile_has_data(with_data)


def test_build_profile_summary_includes_track():
    ctx = UserContextPayload(
        track_slug="track-electrical-engineering",
        faculty="009",
        catalog_year=2025,
        plan_semester_code="2025-201",
        completed_courses=["00440105", "00440140"],
    )
    summary = _build_profile_summary(ctx)
    assert "track-electrical-engineering" in summary
    assert "Completed courses: 2" in summary


def test_format_transcript_prefers_rows():
    ctx = UserContextPayload(
        completed_courses=["00440105"],
        transcript=[
            TranscriptEntryPayload(
                course_number="00440105",
                semester_code="2024-200",
                grade="85",
            )
        ],
    )
    text = _format_transcript(ctx, 10)
    assert "00440105" in text
    assert "2024-200" in text
    assert "85" in text


def test_assess_course_fit_uses_graph(engine: AcademicGraphEngine):
    ctx = UserContextPayload(completed_courses=["00440105", "00440140"])
    facts = _assess_course_fit("00440148", ctx, engine)
    assert "eligible" in facts
    assert facts["course_id"] == "00440148"


def test_run_profile_agent_empty_profile(engine: AcademicGraphEngine):
    result = run_profile_agent("Can I take 00440148?", UserContextPayload(), engine)
    assert isinstance(result, ProfileAgentResult)
    assert result.status == "empty_profile"
    assert result.blocks
