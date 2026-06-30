"""Tests for semester catalog discovery and query resolution."""

from __future__ import annotations

import json
from datetime import date
from pathlib import Path

from app.services.semester_catalog import (
    infer_current_semester,
    offering_keys_to_plan_semester_code,
    plan_semester_code_from_filename,
    resolve_semester_from_query,
)


def test_plan_semester_code_from_filename():
    assert plan_semester_code_from_filename("courses_2025_200.json") == "2025-1"
    assert plan_semester_code_from_filename("courses_2025_201.json") == "2025-2"
    assert plan_semester_code_from_filename("courses_2025_202.json") == "2025-3"


def test_offering_keys_to_plan_semester_code():
    assert offering_keys_to_plan_semester_code(2025, 201) == "2025-2"


def test_resolve_semester_from_hebrew_spring_query(tmp_path: Path):
    (tmp_path / "courses_2025_201.json").write_text("[]", encoding="utf-8")
    (tmp_path / "courses_2025_202.json").write_text("[]", encoding="utf-8")

    from app.services.semester_catalog import discover_semester_catalogs

    catalogs = discover_semester_catalogs(tmp_path)
    result = resolve_semester_from_query("מה לוח הזמנים בסמסטר אביב 2026?", catalogs)
    semester = result["semester"]
    assert semester is not None
    assert semester.filename == "courses_2025_201.json"
    assert result["confidence"] in {"high", "medium"}


def test_resolve_semester_from_hebrew_winter_query(tmp_path: Path):
    (tmp_path / "courses_2025_200.json").write_text("[]", encoding="utf-8")
    (tmp_path / "courses_2025_201.json").write_text("[]", encoding="utf-8")
    (tmp_path / "courses_2025_202.json").write_text("[]", encoding="utf-8")

    from app.services.semester_catalog import discover_semester_catalogs

    catalogs = discover_semester_catalogs(tmp_path)
    result = resolve_semester_from_query("סמסטר חורף 2026", catalogs, today=date(2026, 4, 1))
    semester = result["semester"]
    assert semester is not None
    assert semester.filename == "courses_2025_200.json"


def test_resolve_semester_flags_contradictory_terms(tmp_path: Path):
    (tmp_path / "courses_2025_200.json").write_text("[]", encoding="utf-8")
    (tmp_path / "courses_2025_201.json").write_text("[]", encoding="utf-8")
    (tmp_path / "courses_2025_202.json").write_text("[]", encoding="utf-8")

    from app.services.semester_catalog import discover_semester_catalogs

    catalogs = discover_semester_catalogs(tmp_path)
    result = resolve_semester_from_query("Winter Spring 2026", catalogs, today=date(2026, 4, 1))
    assert result["needs_clarification"] is True
    assert result["semester"] is not None
    assert len(result["candidates"]) >= 2


def test_resolve_semester_defaults_when_unspecified(tmp_path: Path):
    (tmp_path / "courses_2025_201.json").write_text("[]", encoding="utf-8")
    from app.services.semester_catalog import discover_semester_catalogs

    catalogs = discover_semester_catalogs(tmp_path)
    result = resolve_semester_from_query("מה הסילבוס של הקורס?", catalogs, today=date(2026, 4, 1))
    assert result["semester"] is not None
    assert result["needs_clarification"] is True
    assert result["assumption_note"]


def test_calendar_year_mapping(tmp_path: Path):
    path = tmp_path / "courses_2025_202.json"
    path.write_text("[]", encoding="utf-8")
    from app.services.semester_catalog import discover_semester_catalogs

    catalogs = discover_semester_catalogs(tmp_path)
    assert catalogs[0].calendar_year == 2026
    assert catalogs[0].label_en == "Summer"


def test_discover_from_manifest_without_all_files(tmp_path: Path):
    manifest = {
        "sources": [
            {"path": "courses_2025_201.json", "semesterCode": "2025-201"},
            {"path": "courses_2025_202.json", "semesterCode": "2025-202"},
        ]
    }
    (tmp_path / "manifest.json").write_text(json.dumps(manifest), encoding="utf-8")
    (tmp_path / "courses_2025_201.json").write_text("[]", encoding="utf-8")

    from app.services.semester_catalog import discover_semester_catalogs

    catalogs = discover_semester_catalogs(tmp_path)
    assert [catalog.filename for catalog in catalogs] == ["courses_2025_201.json"]


def test_infer_current_semester_summer(tmp_path: Path):
    (tmp_path / "courses_2025_202.json").write_text("[]", encoding="utf-8")
    from app.services.semester_catalog import discover_semester_catalogs

    catalogs = discover_semester_catalogs(tmp_path)
    current = infer_current_semester(catalogs, today=date(2026, 8, 1))
    assert current is not None
    assert current.offering_code == 202
