"""Tests for wiki page parsing used in deterministic academic lookups."""

from __future__ import annotations

from pathlib import Path

from app.services.academic_lookup_service import compose_track_credit_breakdown_answer, track_credit_breakdown
from app.services.wiki_lookup_parser import parse_track_page, read_wiki_page


_WIKI_ROOT = Path(
    "/Users/tymoribrahim/Desktop/UniPilot/services/data-engineering/data/catalog_valut/catalog_valut/wiki"
)
_BME_TRACK = _WIKI_ROOT / "entities/tracks/track-biomedical-engineering.md"


def test_parse_bme_track_page_extracts_total_and_breakdown() -> None:
    if not _BME_TRACK.is_file():
        import pytest

        pytest.skip("catalog wiki not available locally")

    text = read_wiki_page(_BME_TRACK)
    assert text
    record = parse_track_page(text, source_path="wiki/entities/tracks/track-biomedical-engineering.md")

    assert record["totalCredits"] == 160.0
    assert record["requiredCourseCredits"] == 118.0
    assert record["facultyElectiveCredits"] == 30.0
    assert record["technionWideElectiveCredits"] == 12.0
    assert record["enrichmentMinimumCredits"] == 6.0
    assert record["peMinimumCredits"] == 2.0
    assert record["trackCode"] == "033033-1-000"


def test_compose_bme_track_credit_breakdown_answer() -> None:
    if not _BME_TRACK.is_file():
        import pytest

        pytest.skip("catalog wiki not available locally")

    text, sources = compose_track_credit_breakdown_answer("track-biomedical-engineering")
    assert "160" in text
    assert "None" not in text
    assert "118" in text
    assert "033033-1-000" in text
    assert sources == ["wiki/entities/tracks/track-biomedical-engineering.md"]
