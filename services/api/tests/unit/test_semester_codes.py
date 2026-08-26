"""Tests for plan semester ↔ offering key mapping."""

from app.planning.semester_codes import (
    pick_best_offering,
    plan_semester_to_offering_keys,
    resolve_plan_term,
)


def test_plan_semester_to_offering_keys_maps_spring():
    assert plan_semester_to_offering_keys("2025-2") == (2025, 201)


def test_resolve_plan_term_passes_a_year_code_through():
    assert resolve_plan_term("2025-2", preferred_year=2030) == ("2025-2", 2025, 201)


def test_resolve_plan_term_maps_a_bare_name_to_the_preferred_year():
    # winter -> index 1 -> semesterCode 200; the label is echoed back unchanged.
    assert resolve_plan_term("winter", preferred_year=2025) == ("winter", 2025, 200)


def test_resolve_plan_term_is_case_insensitive_and_keeps_the_label():
    assert resolve_plan_term("Spring", preferred_year=2026) == ("Spring", 2026, 201)


def test_resolve_plan_term_accepts_a_year_and_name():
    assert resolve_plan_term("2027-summer", preferred_year=2025) == ("2027-summer", 2027, 202)


def test_resolve_plan_term_rejects_an_unknown_term():
    assert resolve_plan_term("2025-9", preferred_year=2025) is None
    assert resolve_plan_term("autumn", preferred_year=2025) is None


def test_pick_best_offering_prefers_exact_academic_year():
    offerings = [
        {"academicYear": 2024, "semesterCode": 201},
        {"academicYear": 2025, "semesterCode": 201, "scheduleGroups": [{"day": "Sunday"}]},
    ]
    picked = pick_best_offering(offerings, preferred_academic_year=2025, semester_code=201)
    assert picked["academicYear"] == 2025


def test_pick_best_offering_falls_back_to_nearest_year_for_same_term():
    offerings = [
        {"academicYear": 2025, "semesterCode": 201, "scheduleGroups": [{"day": "Monday"}]},
    ]
    picked = pick_best_offering(offerings, preferred_academic_year=2026, semester_code=201)
    assert picked["academicYear"] == 2025
