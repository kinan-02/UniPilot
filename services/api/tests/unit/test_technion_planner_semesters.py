"""Tests for Technion planner semester discovery."""

from __future__ import annotations

import json
from pathlib import Path
from unittest.mock import patch

from app.planning.semester_codes import offering_keys_to_plan_semester_code
from app.planning.technion_planner_semesters import (
    _plan_semester_codes_from_manifest,
    discover_planner_semester_codes_from_raw_dir,
    embedded_planner_semester_codes,
    plan_semester_code_from_course_json_filename,
    resolve_planner_semester_codes,
)


def test_plan_semester_code_from_course_json_filename() -> None:
    assert plan_semester_code_from_course_json_filename("courses_2025_200.json") == "2025-1"
    assert plan_semester_code_from_course_json_filename("courses_2025_201.json") == "2025-2"
    assert plan_semester_code_from_course_json_filename("courses_2025_202.json") == "2025-3"
    assert plan_semester_code_from_course_json_filename("courses_2026_201.json") == "2026-2"
    assert plan_semester_code_from_course_json_filename("other.json") is None


def test_offering_keys_to_plan_semester_code() -> None:
    assert offering_keys_to_plan_semester_code(2025, 201) == "2025-2"
    assert offering_keys_to_plan_semester_code(2025, 299) is None


def test_discover_planner_semester_codes_from_raw_dir(tmp_path: Path) -> None:
    (tmp_path / "courses_2024_201.json").write_text("[]", encoding="utf-8")
    (tmp_path / "courses_2025_201.json").write_text("[]", encoding="utf-8")
    (tmp_path / "courses_2025_202.json").write_text("[]", encoding="utf-8")

    assert discover_planner_semester_codes_from_raw_dir(tmp_path) == [
        "2024-2",
        "2025-2",
        "2025-3",
    ]


def test_discover_ignores_non_file_glob_matches(tmp_path: Path) -> None:
    (tmp_path / "courses_2025_200.json").mkdir()
    (tmp_path / "courses_2025_201.json").write_text("[]", encoding="utf-8")

    assert discover_planner_semester_codes_from_raw_dir(tmp_path) == ["2025-2"]


def test_discover_rejects_non_directory(tmp_path: Path) -> None:
    file_path = tmp_path / "notadir"
    file_path.write_text("x", encoding="utf-8")

    assert discover_planner_semester_codes_from_raw_dir(file_path) == []


def test_discover_from_manifest_when_files_missing(tmp_path: Path) -> None:
    manifest = {
        "sources": [
            {"path": "courses_2025_200.json", "semesterCode": "2025-200"},
            {"path": "courses_2025_201.json", "semesterCode": "2025-201"},
        ]
    }
    (tmp_path / "manifest.json").write_text(json.dumps(manifest), encoding="utf-8")
    (tmp_path / "courses_2025_201.json").write_text("[]", encoding="utf-8")

    assert discover_planner_semester_codes_from_raw_dir(tmp_path) == ["2025-2"]


def test_discover_from_manifest_without_matching_files_returns_empty(tmp_path: Path) -> None:
    manifest = {
        "sources": [
            {"path": "courses_2025_200.json", "semesterCode": "2025-200"},
        ]
    }
    (tmp_path / "manifest.json").write_text(json.dumps(manifest), encoding="utf-8")

    assert discover_planner_semester_codes_from_raw_dir(tmp_path) == []


def test_plan_semester_codes_from_manifest_handles_invalid_payload(tmp_path: Path) -> None:
    manifest_path = tmp_path / "manifest.json"
    manifest_path.write_text("{not-json", encoding="utf-8")
    assert _plan_semester_codes_from_manifest(manifest_path, require_existing_files=False) == []

    manifest_path.write_text(json.dumps([]), encoding="utf-8")
    assert _plan_semester_codes_from_manifest(manifest_path, require_existing_files=False) == []


def test_plan_semester_codes_from_manifest_skips_invalid_sources(tmp_path: Path) -> None:
    manifest = {
        "sources": [
            "bad",
            {"path": "", "semesterCode": "2025-201"},
            {"path": "courses_2025_201.json", "semesterCode": "invalid"},
            {"path": "courses_2025_201.json", "semesterCode": "2025-201"},
        ]
    }
    (tmp_path / "manifest.json").write_text(json.dumps(manifest), encoding="utf-8")

    codes = _plan_semester_codes_from_manifest(
        tmp_path / "manifest.json",
        require_existing_files=False,
    )
    assert codes == ["2025-2"]


def test_resolve_prefers_raw_dir_over_mongo_codes(tmp_path: Path) -> None:
    (tmp_path / "courses_2025_201.json").write_text("[]", encoding="utf-8")

    resolved = resolve_planner_semester_codes(
        raw_dir=tmp_path,
        mongo_codes=["2025-1", "2025-2", "2025-3"],
    )

    assert resolved == ["2025-2"]


def test_resolve_falls_back_to_mongo_when_raw_dir_has_no_semester_files(tmp_path: Path) -> None:
    assert resolve_planner_semester_codes(raw_dir=tmp_path, mongo_codes=["2025-2"]) == ["2025-2"]
    (tmp_path / "courses_2024_200.json").write_text("[]", encoding="utf-8")
    assert resolve_planner_semester_codes(raw_dir=tmp_path, mongo_codes=["2025-2"]) == ["2024-1"]


def test_resolve_falls_back_to_mongo_then_embedded() -> None:
    assert resolve_planner_semester_codes(raw_dir=None, mongo_codes=["2025-2"]) == ["2025-2"]
    assert resolve_planner_semester_codes(raw_dir=None, mongo_codes=[]) == embedded_planner_semester_codes()


def test_resolve_tolerates_unsortable_mongo_codes() -> None:
    resolved = resolve_planner_semester_codes(raw_dir=None, mongo_codes=["invalid", "2025-1"])
    assert resolved == ["invalid", "2025-1"]
    codes = embedded_planner_semester_codes()
    assert "2025-1" in codes
    assert "2025-2" in codes
    assert "2025-3" in codes


def test_embedded_planner_semester_codes_handles_corrupt_payload(tmp_path: Path) -> None:
    from app.planning import technion_planner_semesters as module

    fake_manifest = tmp_path / "technion_planner_semesters.json"

    with patch.object(module, "_EMBEDDED_MANIFEST", fake_manifest):
        assert embedded_planner_semester_codes() == []

        fake_manifest.write_text("{bad", encoding="utf-8")
        assert embedded_planner_semester_codes() == []

        fake_manifest.write_text(json.dumps([]), encoding="utf-8")
        assert embedded_planner_semester_codes() == []

        fake_manifest.write_text(json.dumps({"planSemesterCodes": "2025-1"}), encoding="utf-8")
        assert embedded_planner_semester_codes() == []

        fake_manifest.write_text(
            json.dumps({"planSemesterCodes": [" 2025-2 ", ""]}),
            encoding="utf-8",
        )
        assert embedded_planner_semester_codes() == ["2025-2"]
