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


# ---------------------------------------------------------------------------
# Additional coverage for _parse_exam_datetime and _moed_from_key
# ---------------------------------------------------------------------------

from app.planning.exam_summary import _moed_from_key, _parse_exam_datetime


def test_parse_exam_datetime_returns_none_for_empty():
    d, t, r = _parse_exam_datetime(None)
    assert d is None and t is None and r is None

    d, t, r = _parse_exam_datetime("")
    assert d is None and t is None and r is None


def test_parse_exam_datetime_parses_iso_format():
    d, t, r = _parse_exam_datetime("2025-06-15 09:00")
    assert d is not None
    assert str(d) == "2025-06-15"
    assert t == "09:00"


def test_parse_exam_datetime_parses_dd_mm_yyyy():
    d, t, r = _parse_exam_datetime("15-06-2025 10:30")
    assert d is not None
    assert str(d) == "2025-06-15"
    assert t == "10:30"


def test_parse_exam_datetime_returns_text_for_unparseable():
    d, t, r = _parse_exam_datetime("TBD")
    assert d is None
    assert r == "TBD"


def test_moed_from_key_returns_a_for_moed_a():
    assert _moed_from_key("moedA") == "A"
    assert _moed_from_key("מועד א") == "A"
    assert _moed_from_key("examA") == "A"
    assert _moed_from_key("moed_a") == "A"


def test_moed_from_key_returns_b_for_moed_b():
    assert _moed_from_key("moedB") == "B"
    assert _moed_from_key("מועד ב") == "B"
    assert _moed_from_key("examB") == "B"
    assert _moed_from_key("moed_b") == "B"


def test_moed_from_key_returns_none_for_unknown():
    assert _moed_from_key("unknown") is None


def test_exams_from_offering_empty_exam_dates():
    offering = {"examDates": {}}
    exams = exams_from_offering(offering, course_number="00940101", course_name="Test")
    assert exams == []


def test_build_exam_summary_includes_inactive_when_flagged():
    planned = [
        {"courseNumber": "00940345", "courseTitle": "Active", "isActive": True},
        {"courseNumber": "00940411", "courseTitle": "Inactive", "isActive": False},
    ]
    offerings = {
        "00940345": {"examDates": {"moedA": "2025-06-01"}},
        "00940411": {"examDates": {"moedA": "2025-07-01"}},
    }
    summary = build_exam_summary(planned, offerings, include_inactive=True)
    assert len(summary["exams"]) == 2


def test_build_exam_summary_no_warnings_for_different_days():
    planned = [
        {"courseNumber": "00940345", "courseTitle": "A", "isActive": True},
        {"courseNumber": "00940411", "courseTitle": "B", "isActive": True},
    ]
    offerings = {
        "00940345": {"examDates": {"moedA": "2025-06-01"}},
        "00940411": {"examDates": {"moedA": "2025-06-02"}},
    }
    summary = build_exam_summary(planned, offerings)
    assert summary["warnings"] == []


def test_moed_from_key_fallback_exama_lowercase():
    """Keys not in exact frozenset but matching lowercase pattern hit fallback returns."""
    assert _moed_from_key("ExamA") == "A"   # "exama" in lower → line 49
    assert _moed_from_key("ExamB") == "B"   # "examb" in lower → line 51


def test_moed_from_key_hebrew_substring_fallback():
    """Hebrew substrings not in exact frozenset match via 'in' check."""
    assert _moed_from_key("מועד א סמסטר") == "A"  # not in frozenset, but contains "מועד א" → line 53
    assert _moed_from_key("מועד ב סמסטר") == "B"  # not in frozenset, but contains "מועד ב" → line 55


def test_parse_exam_datetime_skips_invalid_date_value():
    """date(year, month, day) with invalid date (e.g. Feb 30) skips via ValueError."""
    d, t, raw = _parse_exam_datetime("2025-02-30 10:00")
    assert d is None
