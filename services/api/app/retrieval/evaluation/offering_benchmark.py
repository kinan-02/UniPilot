"""Build offering benchmark cases from Technion semester JSON exports."""

from __future__ import annotations

import json
import re
from pathlib import Path
from typing import Any

from app.planning.prerequisite_resolver import canonical_course_number

_FILENAME_PATTERN = re.compile(r"courses_(\d{4})_(\d{3})\.json$")
_COURSE_NUMBER_FIELD = "מספר מקצוע"


def _api_root() -> Path:
    return Path(__file__).resolve().parents[3]


def _default_technion_raw_dir() -> Path:
    return _api_root().parent / "data-engineering" / "data" / "raw" / "technion"


def _plan_semester_code(academic_year: int, semester_code: int) -> str | None:
    if semester_code not in {200, 201, 202}:
        return None
    return f"{academic_year}-{semester_code - 199}"


def _list_technion_json_paths(raw_dir: Path | None = None) -> list[Path]:
    root = raw_dir or _default_technion_raw_dir()
    return sorted(path for path in root.glob("courses_*.json") if path.is_file())


def _offerings_by_course(raw_dir: Path | None = None) -> dict[str, list[tuple[int, int, str]]]:
    grouped: dict[str, list[tuple[int, int, str]]] = {}
    for path in _list_technion_json_paths(raw_dir):
        match = _FILENAME_PATTERN.search(path.name)
        if not match:
            continue
        academic_year = int(match.group(1))
        semester_code = int(match.group(2))
        plan_code = _plan_semester_code(academic_year, semester_code)
        if not plan_code:
            continue
        try:
            records = json.loads(path.read_text(encoding="utf-8"))
        except (OSError, json.JSONDecodeError):
            continue
        if not isinstance(records, list):
            continue
        for record in records:
            if not isinstance(record, dict):
                continue
            general = record.get("general")
            if not isinstance(general, dict):
                general = record
            course_number = canonical_course_number(str(general.get(_COURSE_NUMBER_FIELD) or ""))
            if not course_number:
                continue
            grouped.setdefault(course_number, []).append(
                (academic_year, semester_code, plan_code)
            )
    return grouped


def pick_offering_semester(
    course_number: str,
    *,
    raw_dir: Path | None = None,
    preferred_year: int = 2025,
) -> str | None:
    """Pick a stable plan semester code for benchmark offering cases."""
    normalized = canonical_course_number(course_number)
    if not normalized:
        return None
    offerings = _offerings_by_course(raw_dir).get(normalized, [])
    if not offerings:
        return None
    unique = sorted(set(offerings))
    preferred = [item for item in unique if item[0] == preferred_year]
    if preferred:
        return preferred[0][2]
    return unique[-1][2]


def _negative_semesters(target_semester: str, course_number: str, *, raw_dir: Path | None) -> list[str]:
    normalized = canonical_course_number(course_number) or course_number
    offerings = sorted(
        {plan for _year, _code, plan in _offerings_by_course(raw_dir).get(normalized, [])}
    )
    negatives = [semester for semester in offerings if semester != target_semester]
    if len(negatives) >= 2:
        return negatives[:2]
    year, term = target_semester.split("-", 1)
    prior_year = str(int(year) - 1)
    return [f"{prior_year}-{term}", f"{year}-{int(term) % 3 + 1}"]


def build_offering_case(
    course_number: str,
    *,
    raw_dir: Path | None = None,
    preferred_year: int = 2025,
) -> dict[str, Any] | None:
    normalized = canonical_course_number(course_number)
    if not normalized:
        return None
    semester = pick_offering_semester(
        normalized,
        raw_dir=raw_dir,
        preferred_year=preferred_year,
    )
    if not semester:
        return None
    return {
        "id": f"dds_offering_{normalized}_{semester.replace('-', '_')}",
        "evalType": "offering",
        "query": f"Is {normalized} offered in {semester}?",
        "intent": "course_question",
        "profile": "semester_offering_lookup",
        "language": "en",
        "entities": {"courseNumber": normalized, "targetSemesterCode": semester},
        "metadataContext": {"catalogYear": preferred_year},
        "mustRetrieve": [f"offering:{semester}:{normalized}"],
        "negativeSources": [
            f"offering:{negative}:{normalized}"
            for negative in _negative_semesters(semester, normalized, raw_dir=raw_dir)
        ],
        "notes": "Structured offering lookup (semester from Technion JSON)",
    }


def build_offering_cases(
    course_numbers: list[str],
    *,
    raw_dir: Path | None = None,
    preferred_year: int = 2025,
) -> list[dict[str, Any]]:
    cases: list[dict[str, Any]] = []
    for number in course_numbers:
        case = build_offering_case(
            number,
            raw_dir=raw_dir,
            preferred_year=preferred_year,
        )
        if case is not None:
            cases.append(case)
    return cases


def offering_case_lines(
    course_numbers: list[str],
    *,
    raw_dir: Path | None = None,
    preferred_year: int = 2025,
) -> list[str]:
    return [
        json.dumps(case, ensure_ascii=False)
        for case in build_offering_cases(
            course_numbers,
            raw_dir=raw_dir,
            preferred_year=preferred_year,
        )
    ]
