"""Unit tests for what-if scenario parsing."""

from __future__ import annotations

from app.services.what_if_scenario import (
    WhatIfScenario,
    apply_what_if_fail,
    apply_what_if_scenario,
    parse_what_if_fail_courses,
    parse_what_if_scenario,
)


def test_parse_what_if_fail_courses_detects_goal() -> None:
    codes = parse_what_if_fail_courses("What if I fail course 00940139 next semester?")
    assert codes == ["00940139"]


def test_parse_what_if_light_load() -> None:
    spec = parse_what_if_scenario("What if I take a lighter load next semester?")
    assert spec is not None
    assert spec.scenario == WhatIfScenario.LIGHT_LOAD
    assert spec.max_credits == 12.0


def test_parse_what_if_summer_term() -> None:
    spec = parse_what_if_scenario("What if I plan summer term courses?")
    assert spec is not None
    assert spec.scenario == WhatIfScenario.SUMMER_TERM
    assert spec.semester_filename == "courses_2025_202.json"


def test_parse_what_if_switch_track() -> None:
    spec = parse_what_if_scenario("What if I switch track to software engineering?")
    assert spec is not None
    assert spec.scenario == WhatIfScenario.SWITCH_TRACK
    assert spec.track_slug == "software-engineering"


def test_parse_what_if_fail_courses_ignores_normal_goal() -> None:
    assert parse_what_if_fail_courses("Plan course 00940139") is None


def test_apply_what_if_light_load_sets_max_credits() -> None:
    spec = parse_what_if_scenario("What if I take a lighter load next semester?")
    assert spec is not None
    adjusted = apply_what_if_scenario({"constraints": {}}, spec)
    assert adjusted["constraints"]["maxCredits"] == 12.0
    assert adjusted["what_if"]["scenario"] == "light_load"


def test_apply_what_if_fail_removes_completed_course() -> None:
    adjusted = apply_what_if_fail(
        {"completed_courses": ["00940139", "0940345"]},
        ["00940139"],
    )
    assert adjusted["completed_courses"] == ["0940345"]
    assert adjusted["what_if"]["simulated_failures"] == ["00940139"]

