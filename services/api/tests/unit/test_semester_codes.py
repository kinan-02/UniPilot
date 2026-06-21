"""Tests for plan semester ↔ offering key mapping."""

from app.planning.semester_codes import pick_best_offering, plan_semester_to_offering_keys


def test_plan_semester_to_offering_keys_maps_spring():
    assert plan_semester_to_offering_keys("2025-2") == (2025, 201)


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
