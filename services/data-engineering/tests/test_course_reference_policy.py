"""Tests for shared catalog course-reference policy."""

from app.catalog.course_reference_policy import (
    classify_missing_course_reference,
    derive_production_excluded_course_numbers,
    is_cross_faculty_course_reference,
    is_dds_scoped_course_number,
)


def test_cross_faculty_numbers_are_not_dds_scoped() -> None:
    assert is_cross_faculty_course_reference("01040042") is True
    assert is_cross_faculty_course_reference("02340221") is True
    assert is_dds_scoped_course_number("00940345") is True
    assert is_cross_faculty_course_reference("00940345") is False


def test_production_exclusions_use_dds_ingest_scope() -> None:
    catalog = {"00940345", "01040042", "00960226"}
    ingestible = {"00940345"}
    excluded = derive_production_excluded_course_numbers(
        catalog,
        ingestible_course_numbers=ingestible,
    )
    assert excluded == ["00960226", "01040042"]


def test_cross_faculty_missing_reference_is_not_ocr_blocker() -> None:
    classification = classify_missing_course_reference(
        "01040042",
        ingestible_course_numbers={"00940345"},
        production_excluded_course_numbers=set(),
        neighbor_matches=["00940842"],
    )
    assert classification == "cross_faculty"


def test_short_course_numbers_are_not_cross_faculty() -> None:
    assert is_cross_faculty_course_reference("12") is False


def test_classify_ingestible_reference() -> None:
    classification = classify_missing_course_reference(
        "00940345",
        ingestible_course_numbers={"00940345"},
        production_excluded_course_numbers=set(),
    )
    assert classification == "ingestible"


def test_ocr_neighbor_skips_same_candidate() -> None:
    from app.catalog.course_reference_policy import find_dds_ocr_neighbor_matches

    matches = find_dds_ocr_neighbor_matches(
        "00940345",
        {"00940345", "00940346"},
    )
    assert "00940345" not in matches
