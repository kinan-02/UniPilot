"""Build a course reference index from local Technion semester offering JSON files."""

from __future__ import annotations

import json
import re
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

from app.paths import service_root
from app.utils.course_numbers import normalize_course_number

SEMESTER_CODE_LABELS: dict[int, str] = {
    200: "winter",
    201: "spring",
    202: "summer",
}

GENERAL_FIELD_MAP = {
    "courseNumber": "מספר מקצוע",
    "titleHebrew": "שם מקצוע",
    "credits": "נקודות",
    "faculty": "פקולטה",
    "studyFramework": "מסגרת לימודים",
    "syllabus": "סילבוס",
    "prerequisitesText": "מקצועות קדם",
    "corequisitesText": "מקצועות צמודים",
    "noAdditionalCreditText": "מקצועות ללא זיכוי נוסף",
}


@dataclass
class CourseOfferingRecord:
    courseNumber: str
    titleHebrew: str | None = None
    credits: float | None = None
    faculty: str | None = None
    studyFramework: str | None = None
    syllabus: str | None = None
    prerequisitesText: str | None = None
    corequisitesText: str | None = None
    noAdditionalCreditText: str | None = None
    semestersOffered: list[int] = field(default_factory=list)
    sourceFiles: list[str] = field(default_factory=list)
    scheduleSummary: str | None = None
    titleConflicts: list[str] = field(default_factory=list)
    creditsConflicts: list[str] = field(default_factory=list)

    def to_dict(self) -> dict[str, Any]:
        return {
            "courseNumber": self.courseNumber,
            "titleHebrew": self.titleHebrew,
            "credits": self.credits,
            "faculty": self.faculty,
            "studyFramework": self.studyFramework,
            "syllabus": self.syllabus,
            "prerequisitesText": self.prerequisitesText,
            "corequisitesText": self.corequisitesText,
            "noAdditionalCreditText": self.noAdditionalCreditText,
            "semestersOffered": sorted(set(self.semestersOffered)),
            "sourceFiles": sorted(set(self.sourceFiles)),
            "scheduleSummary": self.scheduleSummary,
            "titleConflicts": self.titleConflicts,
            "creditsConflicts": self.creditsConflicts,
        }


def default_technion_raw_dir() -> Path:
    return service_root() / "data" / "raw" / "technion"


SEMESTER_COURSE_JSON_FILENAME = re.compile(r"^courses_(\d{4})_(200|201|202)\.json$")


def list_semester_course_json_paths(raw_dir: Path | None = None) -> list[Path]:
    """All ``courses_YYYY_20X.json`` semester offering files in the Technion raw directory."""
    directory = raw_dir or default_technion_raw_dir()
    if not directory.is_dir():
        return []
    paths: list[Path] = []
    for path in sorted(directory.glob("courses_*.json")):
        if path.is_file() and SEMESTER_COURSE_JSON_FILENAME.match(path.name):
            paths.append(path)
    return paths


def semester_code_from_filename(path: Path) -> int | None:
    match = re.search(r"_(\d{3})\.json$", path.name)
    if not match:
        return None
    code = int(match.group(1))
    if code in SEMESTER_CODE_LABELS:
        return code
    return None


def _parse_credits(raw: Any) -> float | None:
    if raw is None:
        return None
    text = str(raw).strip().replace(",", ".")
    if not text:
        return None
    try:
        return float(text)
    except ValueError:
        return None


def _truncate(text: str | None, limit: int) -> str | None:
    if not text:
        return None
    cleaned = re.sub(r"\s+", " ", text).strip()
    if len(cleaned) <= limit:
        return cleaned
    return cleaned[: limit - 3] + "..."


def _schedule_summary(schedule: list[dict[str, Any]]) -> str | None:
    if not schedule:
        return None
    first = schedule[0]
    parts = [
        str(first.get("סוג") or "").strip(),
        str(first.get("יום") or "").strip(),
        str(first.get("שעה") or "").strip(),
    ]
    summary = ", ".join(part for part in parts if part)
    return _truncate(summary, 120)


def _read_offering(path: Path) -> tuple[int | None, list[dict[str, Any]]]:
    semester_code = semester_code_from_filename(path)
    payload = json.loads(path.read_text(encoding="utf-8"))
    if not isinstance(payload, list):
        raise ValueError(f"Expected JSON array in {path}")
    return semester_code, payload


def _general_fields(entry: dict[str, Any]) -> dict[str, Any]:
    general = entry.get("general")
    if not isinstance(general, dict):
        return {}
    return general


def build_course_index_from_paths(paths: list[Path]) -> dict[str, CourseOfferingRecord]:
    index: dict[str, CourseOfferingRecord] = {}

    for path in paths:
        semester_code, offerings = _read_offering(path)
        source_name = path.name

        for entry in offerings:
            general = _general_fields(entry)
            raw_number = general.get(GENERAL_FIELD_MAP["courseNumber"])
            course_number = normalize_course_number(str(raw_number or ""))
            if course_number is None:
                continue

            title = general.get(GENERAL_FIELD_MAP["titleHebrew"])
            credits = _parse_credits(general.get(GENERAL_FIELD_MAP["credits"]))
            schedule = entry.get("schedule") if isinstance(entry.get("schedule"), list) else []

            if course_number not in index:
                index[course_number] = CourseOfferingRecord(
                    courseNumber=course_number,
                    titleHebrew=str(title).strip() if title else None,
                    credits=credits,
                    faculty=_truncate(str(general.get(GENERAL_FIELD_MAP["faculty"]) or ""), 200),
                    studyFramework=_truncate(
                        str(general.get(GENERAL_FIELD_MAP["studyFramework"]) or ""),
                        120,
                    ),
                    syllabus=_truncate(str(general.get(GENERAL_FIELD_MAP["syllabus"]) or ""), 400),
                    prerequisitesText=_truncate(
                        str(general.get(GENERAL_FIELD_MAP["prerequisitesText"]) or ""),
                        300,
                    ),
                    corequisitesText=_truncate(
                        str(general.get(GENERAL_FIELD_MAP["corequisitesText"]) or ""),
                        300,
                    ),
                    noAdditionalCreditText=_truncate(
                        str(general.get(GENERAL_FIELD_MAP["noAdditionalCreditText"]) or ""),
                        300,
                    ),
                    semestersOffered=[semester_code] if semester_code is not None else [],
                    sourceFiles=[source_name],
                    scheduleSummary=_schedule_summary(schedule),
                )
                continue

            record = index[course_number]
            if semester_code is not None and semester_code not in record.semestersOffered:
                record.semestersOffered.append(semester_code)
            if source_name not in record.sourceFiles:
                record.sourceFiles.append(source_name)

            if title:
                title_text = str(title).strip()
                if record.titleHebrew and record.titleHebrew != title_text:
                    conflict = f"{source_name}: {title_text}"
                    if conflict not in record.titleConflicts:
                        record.titleConflicts.append(conflict)
                elif not record.titleHebrew:
                    record.titleHebrew = title_text

            if credits is not None:
                if record.credits is not None and record.credits != credits:
                    conflict = f"{source_name}: {credits}"
                    if conflict not in record.creditsConflicts:
                        record.creditsConflicts.append(conflict)
                elif record.credits is None:
                    record.credits = credits

            if not record.scheduleSummary:
                record.scheduleSummary = _schedule_summary(schedule)

    return index


def default_course_json_paths() -> list[Path]:
    return list_semester_course_json_paths()


def build_course_index(course_json_paths: list[Path] | None = None) -> dict[str, CourseOfferingRecord]:
    paths = course_json_paths if course_json_paths is not None else default_course_json_paths()
    existing = [path for path in paths if path.exists()]
    if not existing:
        return {}
    return build_course_index_from_paths(existing)
