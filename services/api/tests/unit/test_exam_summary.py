"""Unit tests for exam summary utilities."""

from app.planning.exam_summary import (
    active_planned_courses,
    build_exam_summary,
    exams_from_offering,
)


def test_exams_from_offering_moed_a_and_b():
    offering = {
        "examDates": {
            "moedA": "2025-06-01 09:00",
            "moedB": "2025-08-10 09:00",
        }
    }
    exams = exams_from_offering(
        offering,
        course_number="00940345",
        course_name="Discrete Math",
    )
    assert len(exams) == 2
    moeds = {exam["moed"] for exam in exams}
    assert moeds == {"A", "B"}
    assert exams[0]["date"] == "2025-06-01"


def test_exams_from_offering_missing_data():
    exams = exams_from_offering(
        None,
        course_number="00940345",
        course_name="Discrete Math",
    )
    assert exams == []


def test_exams_from_offering_skips_unscheduled_entries():
    exams = exams_from_offering(
        {"examDates": {"moedA": "TBD", "moedB": "2025-08-10 09:00"}},
        course_number="00940345",
        course_name="Discrete Math",
    )
    assert len(exams) == 1
    assert exams[0]["moed"] == "B"


def test_exams_from_offering_catalog_exam_keys():
    exams = exams_from_offering(
        {
            "examDates": {
                "examA": "01-06-2025 09:00",
                "examB": "10-08-2025 09:00",
            }
        },
        course_number="00940345",
        course_name="Discrete Math",
    )
    assert len(exams) == 2
    assert {exam["moed"] for exam in exams} == {"A", "B"}


def test_build_exam_summary_excludes_inactive_courses():
    planned = [
        {
            "courseNumber": "00940345",
            "courseTitle": "Active",
            "isActive": True,
        },
        {
            "courseNumber": "00940411",
            "courseTitle": "Inactive",
            "isActive": False,
        },
    ]
    offerings = {
        "00940345": {"examDates": {"moedA": "2025-06-01"}},
        "00940411": {"examDates": {"moedA": "2025-07-01"}},
    }
    summary = build_exam_summary(planned, offerings)
    assert len(summary["exams"]) == 1
    assert summary["exams"][0]["courseNumber"] == "00940345"


def test_build_exam_summary_same_day_warning():
    planned = [
        {"courseNumber": "00940345", "courseTitle": "A", "isActive": True},
        {"courseNumber": "00940411", "courseTitle": "B", "isActive": True},
    ]
    offerings = {
        "00940345": {"examDates": {"moedA": "2025-06-01"}},
        "00940411": {"examDates": {"moedA": "2025-06-01"}},
    }
    summary = build_exam_summary(planned, offerings)
    assert any(w["type"] == "same_day_exams" for w in summary["warnings"])


def test_active_planned_courses_defaults_true():
    planned = [
        {"courseNumber": "00940345", "isActive": False},
        {"courseNumber": "00940411"},
    ]
    active = active_planned_courses(planned)
    assert len(active) == 1
    assert active[0]["courseNumber"] == "00940411"
