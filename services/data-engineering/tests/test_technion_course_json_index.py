"""Tests for Technion course JSON reference index."""

import json
from pathlib import Path

from app.sources.technion_course_json_index import (
    SEMESTER_CODE_LABELS,
    build_course_index_from_paths,
    semester_code_from_filename,
)

FIXTURE_201 = Path(__file__).parent / "fixtures" / "courses_sample_201.json"
FIXTURE_202 = Path(__file__).parent / "fixtures" / "courses_sample_202.json"


def test_semester_code_mapping() -> None:
    assert semester_code_from_filename(Path("courses_2025_200.json")) == 200
    assert semester_code_from_filename(Path("courses_2025_201.json")) == 201
    assert semester_code_from_filename(Path("courses_2025_202.json")) == 202
    assert SEMESTER_CODE_LABELS[200] == "winter"
    assert SEMESTER_CODE_LABELS[201] == "spring"
    assert SEMESTER_CODE_LABELS[202] == "summer"


def test_build_course_index_merges_semesters() -> None:
    index = build_course_index_from_paths([FIXTURE_201, FIXTURE_202])
    record = index["00940345"]
    assert record.titleHebrew == "מתמטיקה דיסקרטית ת'"
    assert record.credits == 4.0
    assert set(record.semestersOffered) == {201, 202}
    assert "courses_sample_201.json" in record.sourceFiles
    assert "courses_sample_202.json" in record.sourceFiles


def test_course_index_normalizes_numbers() -> None:
    index = build_course_index_from_paths([FIXTURE_201])
    assert "00940139" in index
    assert index["00940139"].prerequisitesText == "01040031"
