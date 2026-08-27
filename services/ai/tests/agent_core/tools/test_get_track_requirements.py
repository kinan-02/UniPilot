"""Unit tests for `get_track_requirements` (docs/agent/HIGHER_LEVEL_TOOLS.md).

Real-data fact verified directly before writing assertions: `get_entity`
for entity_type="track" never populates `warnings` (only the course path
does), so `track_result.warnings` is always `[]` in practice -- covered
implicitly by the success-path assertion below rather than as a separate
case.

- track-materials-engineering has 57 required courses (graph "contains"
  edges), including "01040019".
"""

from __future__ import annotations

import pytest

from app.agent_core.tools.composites.get_track_requirements import (
    GetTrackRequirementsInput,
    parse_total_credits,
    run_get_track_requirements,
)


async def test_empty_track_slug_fails_closed():
    result = await run_get_track_requirements(GetTrackRequirementsInput(track_slug="  "))
    assert result.ok is False
    assert "track_slug_required" in result.error


async def test_unknown_track_fails_closed(use_real_academic_engine):
    result = await run_get_track_requirements(GetTrackRequirementsInput(track_slug="track-does-not-exist"))
    assert result.ok is False
    assert "track_not_found: track-does-not-exist" in result.error


async def test_successful_track_requirements(use_real_academic_engine):
    result = await run_get_track_requirements(
        GetTrackRequirementsInput(track_slug="track-materials-engineering")
    )
    assert result.ok is True
    assert result.data["trackSlug"] == "track-materials-engineering"
    assert result.data["track"]["slug"] == "track-materials-engineering"
    assert len(result.data["requiredCourses"]) == 57
    required_ids = {entry["id"] for entry in result.data["requiredCourses"]}
    assert "01040019" in required_ids
    assert all(entry["nodeType"] == "course" for entry in result.data["requiredCourses"])
    assert result.warnings == []


async def test_required_courses_unavailable_degrades_gracefully(use_real_academic_engine, monkeypatch):
    import app.agent_core.tools.composites.get_track_requirements as module
    from app.agent_core.tools.envelope import ToolOutputEnvelope

    async def _fake_traverse(*_a, **_k):
        return ToolOutputEnvelope(ok=False, data=None, error="relation_unavailable")

    monkeypatch.setattr(module, "run_traverse_relationship", _fake_traverse)

    result = await run_get_track_requirements(
        GetTrackRequirementsInput(track_slug="track-materials-engineering")
    )
    assert result.ok is True
    assert result.data["requiredCourses"] == []
    assert "required_courses_unavailable" in result.warnings


# -- total credits: the scalar projection -------------------------------------
#
# The live eval (2026-07-18) answered "how many credits do I still need?" with
# "your track requires 35.5" -- grounded, and wrong by 119.5 credits. The total
# existed ONLY as prose inside the returned markdown blob, reachable by no path,
# so `surface_fact` could not bind it and the model fell back to `interpret_text`,
# which returned 35.5: the "Faculty electives" ROW of the credit breakdown table.
#
# Fix mirrors §19 #4b (`termLabels`): project the scalar at the tool boundary so
# every path exposes the same directly-surfaceable number. 51 of 67 track pages
# carry an unambiguous total; the rest must degrade, never guess.


@pytest.mark.parametrize(
    "content, expected",
    [
        ("**Total credits required:** 155", (155.0, "Total credits required")),
        ("**Total Credits:** 160.5", (160.5, "Total Credits")),
        ("**Total credits:** 120", (120.0, "Total credits")),
        ("**Total Credits Required:** 98.0", (98.0, "Total Credits Required")),
        ('**סה"כ נקודות זכות:** 155', (155.0, 'סה"כ נקודות זכות')),
        ("**נקודות זכות כוללות:** 155", (155.0, "נקודות זכות כוללות")),
    ],
)
def test_parses_every_label_variant_found_in_the_vault(content, expected):
    assert parse_total_credits(content) == expected


def test_the_same_total_stated_twice_is_not_ambiguous():
    """Most pages state the total in English prose AND again in Hebrew. Two
    matches agreeing on one value is one fact, not a conflict."""
    content = "**Total credits required:** 155\n\n**נקודות זכות כוללות:** 155"
    assert parse_total_credits(content) == (155.0, "Total credits required")


def test_conflicting_totals_refuse_rather_than_pick_one():
    """Guessing here would reintroduce the exact bug: silently shipping one
    number as if it were the degree total."""
    content = "**Total Credits (pre-clinical):** 238.0\n**Total Credits (clinical):** 128.5"
    assert parse_total_credits(content) is None


def test_a_qualified_total_keeps_its_qualifier():
    """`track-medicine-md` states only the CLINICAL-years total. Returning 128.5
    as a bare degree total would misrepresent it, so the label rides along."""
    value, label = parse_total_credits("**Total Credits (clinical years):** 128.5")
    assert value == 128.5
    assert "clinical years" in label


def test_breakdown_rows_are_not_mistaken_for_the_total():
    """35.5 is the row that caused the bug -- it must never match."""
    content = "| Required courses | 107.5 |\n| Faculty electives | 35.5 |\n**Total Credits:** 155.0"
    assert parse_total_credits(content) == (155.0, "Total Credits")


def test_page_without_a_total_returns_none():
    assert parse_total_credits("## Overview\nNo credit total is stated here.") is None


async def test_total_credits_is_surfaceable_as_a_scalar(use_real_academic_engine):
    """The regression case, end to end: 155 must be reachable BY PATH so the loop
    can ground it, instead of interpreting prose. 155 - 62.5 = the 92.5 the eval
    expects."""
    result = await run_get_track_requirements(
        GetTrackRequirementsInput(track_slug="track-information-systems-engineering")
    )
    assert result.ok is True
    assert result.data["totalCreditsRequired"] == 155.0
    assert "total_credits_not_parsed" not in result.warnings


async def test_track_without_a_stated_total_degrades_with_a_warning(use_real_academic_engine):
    """16 of 67 pages state no total. The tool must omit the field and say so --
    the model can still fall back to interpret_text, which is today's behaviour."""
    result = await run_get_track_requirements(
        GetTrackRequirementsInput(track_slug="track-aerospace-engineering")
    )
    assert result.ok is True
    assert "totalCreditsRequired" not in result.data
    assert "total_credits_not_parsed" in result.warnings
