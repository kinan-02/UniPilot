"""Tests for Technion JSON-backed offering benchmark cases."""

from __future__ import annotations

from pathlib import Path

import pytest

from app.retrieval.evaluation.offering_benchmark import (
    _default_technion_raw_dir,
    _list_technion_json_paths,
    build_offering_case,
    pick_offering_semester,
)

_HAS_TECHNION_JSON = bool(_list_technion_json_paths(_default_technion_raw_dir()))
requires_technion_json = pytest.mark.skipif(
    not _HAS_TECHNION_JSON,
    reason="Technion semester JSON files are not present (gitignored local data)",
)


@requires_technion_json
def test_pick_offering_semester_uses_2025_when_available():
    semester = pick_offering_semester("00940101")
    assert semester == "2025-1"


@requires_technion_json
def test_build_offering_case_uses_json_semester():
    case = build_offering_case("00940139")
    assert case is not None
    assert case["entities"]["targetSemesterCode"] == "2025-2"
    assert case["mustRetrieve"] == ["offering:2025-2:00940139"]


def test_missing_course_returns_none():
    assert build_offering_case("00000000") is None


def test_technion_raw_dir_override(tmp_path: Path):
    sample = [
        {
            "general": {
                "מספר מקצוע": "00999999",
                "שם מקצוע": "Sample",
            },
            "schedule": [],
        }
    ]
    (tmp_path / "courses_2025_201.json").write_text(
        __import__("json").dumps(sample),
        encoding="utf-8",
    )
    case = build_offering_case("00999999", raw_dir=tmp_path)
    assert case is not None
    assert case["entities"]["targetSemesterCode"] == "2025-2"
