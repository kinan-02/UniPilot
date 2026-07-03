"""Discover planner semester codes from Technion raw course JSON files."""

from __future__ import annotations

import json
import re
from pathlib import Path

from app.planning.semester_codes import offering_keys_to_plan_semester_code

COURSE_JSON_FILENAME = re.compile(r"^courses_(\d{4})_(200|201|202)\.json$")
MANIFEST_SEMESTER_CODE = re.compile(r"^(\d{4})-(200|201|202)$")

_PACKAGE_ROOT = Path(__file__).resolve().parent.parent
_EMBEDDED_MANIFEST = _PACKAGE_ROOT / "data" / "technion_planner_semesters.json"


def plan_semester_code_from_course_json_filename(filename: str) -> str | None:
    """Map ``courses_2025_201.json`` to plan code ``2025-2``."""
    match = COURSE_JSON_FILENAME.match(filename.strip())
    if not match:
        return None
    academic_year = int(match.group(1))
    semester_code = int(match.group(2))
    return offering_keys_to_plan_semester_code(academic_year, semester_code)


def _sort_plan_semester_codes(codes: list[str]) -> list[str]:
    def sort_key(code: str) -> tuple[int, int]:
        parts = code.split("-", 1)
        if len(parts) != 2 or not parts[0].isdigit() or not parts[1].isdigit():
            return (0, 0)
        return (int(parts[0]), int(parts[1]))

    return sorted(dict.fromkeys(codes), key=sort_key)


def discover_planner_semester_codes_from_raw_dir(raw_dir: Path) -> list[str]:
    """Return plan semester codes for each ``courses_YYYY_20X.json`` file that exists."""
    if not raw_dir.is_dir():
        return []

    codes: list[str] = []
    for path in sorted(raw_dir.glob("courses_*.json")):
        if not path.is_file():
            continue
        code = plan_semester_code_from_course_json_filename(path.name)
        if code:
            codes.append(code)

    if codes:
        return _sort_plan_semester_codes(codes)

    manifest_path = raw_dir / "manifest.json"
    if manifest_path.is_file():
        return _plan_semester_codes_from_manifest(manifest_path, require_existing_files=True)

    return []


def _plan_semester_codes_from_manifest(
    manifest_path: Path,
    *,
    require_existing_files: bool,
) -> list[str]:
    try:
        payload = json.loads(manifest_path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        return []

    if not isinstance(payload, dict):
        return []

    raw_dir = manifest_path.parent
    codes: list[str] = []
    for source in payload.get("sources") or []:
        if not isinstance(source, dict):
            continue
        relative_path = str(source.get("path") or "").strip()
        semester_code = str(source.get("semesterCode") or "").strip()
        if not relative_path or not semester_code:
            continue
        if require_existing_files and not (raw_dir / relative_path).is_file():
            continue
        match = MANIFEST_SEMESTER_CODE.match(semester_code)
        if not match:
            continue
        academic_year = int(match.group(1))
        offering_code = int(match.group(2))
        plan_code = offering_keys_to_plan_semester_code(academic_year, offering_code)
        if plan_code:
            codes.append(plan_code)

    return _sort_plan_semester_codes(codes)


def embedded_planner_semester_codes() -> list[str]:
    """Committed fallback when raw Technion JSON is not mounted on the API container."""
    if not _EMBEDDED_MANIFEST.is_file():
        return []
    try:
        payload = json.loads(_EMBEDDED_MANIFEST.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        return []
    if not isinstance(payload, dict):
        return []
    raw_codes = payload.get("planSemesterCodes") or []
    if not isinstance(raw_codes, list):
        return []
    codes = [str(code).strip() for code in raw_codes if str(code).strip()]
    return _sort_plan_semester_codes(codes)


def resolve_planner_semester_codes(
    *,
    raw_dir: Path | None,
    mongo_codes: list[str] | None = None,
) -> list[str]:
    """Prefer on-disk semester JSON; fall back to Mongo offerings, then embedded defaults."""
    if raw_dir is not None:
        raw_codes = discover_planner_semester_codes_from_raw_dir(raw_dir)
        if raw_codes:
            return raw_codes

    if mongo_codes:
        return _sort_plan_semester_codes(mongo_codes)

    return embedded_planner_semester_codes()
