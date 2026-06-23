"""Unit tests for DDS track registry."""

from __future__ import annotations

from app.curriculum.track_registry import (
    program_code_for_track_slug,
    resolve_track_slug_from_program,
)


def test_resolve_track_slug_from_none_program():
    assert resolve_track_slug_from_program(None) is None


def test_resolve_track_slug_from_wiki_page_metadata():
    slug = resolve_track_slug_from_program(
        {
            "programCode": "009216-1-000",
            "metadata": {"wikiPage": "track-data-information-engineering"},
        }
    )
    assert slug == "track-data-information-engineering"


def test_resolve_track_slug_from_program_code_fallback():
    slug = resolve_track_slug_from_program({"programCode": "009118-1-000", "metadata": {}})
    assert slug == "track-information-systems-engineering"


def test_program_code_for_track_slug_returns_none_for_empty():
    assert program_code_for_track_slug(None) is None
    assert program_code_for_track_slug("unknown-track") is None


def test_program_code_for_track_slug_returns_code():
    assert program_code_for_track_slug("track-data-information-engineering") == "009216-1-000"


def test_resolve_track_slug_returns_none_for_unknown_program_code():
    assert resolve_track_slug_from_program({"programCode": "009999-9-999", "metadata": {}}) is None


def test_resolve_track_slug_returns_none_when_program_code_is_not_string():
    assert resolve_track_slug_from_program({"programCode": 123, "metadata": {}}) is None
