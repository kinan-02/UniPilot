"""Unit tests for simulation scenario parser."""

from __future__ import annotations

from app.services.simulation_scenario_parser import parse_simulation_text


def test_parse_drop_course_en():
    operations = parse_simulation_text("What happens if I drop course 00940219 next semester?")
    assert operations[0]["type"] == "drop_course"
    assert operations[0]["courseNumber"] == "00940219"


def test_parse_add_planned_course_en():
    operations = parse_simulation_text("Add 00940411 to my next semester plan")
    assert operations[0]["type"] == "add_planned_course"
    assert operations[0]["courseNumber"] == "00940411"


def test_parse_change_track():
    operations = parse_simulation_text("Switch to track track-data-information-engineering")
    assert operations[0]["type"] == "change_track"
    assert operations[0]["trackSlug"] == "track-data-information-engineering"
