"""Read and normalize Technion semester course JSON files for staging import."""

from __future__ import annotations

import json
import re
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

from app.models.staging_course import StagedTechnionCourse, StagedTechnionCourseOffering
from app.sources.technion_course_json_index import SEMESTER_CODE_LABELS, list_semester_course_json_paths
from app.utils.course_numbers import normalize_course_number

FILENAME_PATTERN = re.compile(r"courses_(\d{4})_(\d{3})\.json$")

DDS_FACULTY_HEBREW = "הפקולטה למדעי הנתונים וההחלטות"
DDS_FACULTY_VARIANTS = frozenset(
    {
        DDS_FACULTY_HEBREW,
        "פקולטה למדעי הנתונים וההחלטות",
        # Semester JSON often omits the "הפקולטה ל" prefix.
        "מדעי הנתונים וההחלטות",
    }
)

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
    "instructors": "אחראים",
    "notes": "הערות",
    "examA": "מועד א",
    "examB": "מועד ב",
}

SOURCE_NAME = "technion-course-json"
SOURCE_TYPE = "technion_semester_offerings"


@dataclass
class InvalidCourseRecord:
    sourceFile: str
    recordIndex: int
    reason: str


@dataclass
class TechnionCourseParseResult:
    files_read: int = 0
    raw_records_read: int = 0
    invalid_records: list[InvalidCourseRecord] = field(default_factory=list)
    warnings: list[str] = field(default_factory=list)
    courses: list[StagedTechnionCourse] = field(default_factory=list)
    offerings: list[StagedTechnionCourseOffering] = field(default_factory=list)
    dds_faculty_course_count: int = 0


def semester_code_from_filename(path: Path) -> int | None:
    match = FILENAME_PATTERN.search(path.name)
    if not match:
        return None
    code = int(match.group(2))
    if code in SEMESTER_CODE_LABELS:
        return code
    return None


def academic_year_from_filename(path: Path) -> int | None:
    match = FILENAME_PATTERN.search(path.name)
    if not match:
        return None
    return int(match.group(1))


def course_staging_key(course_number: str) -> str:
    return f"technion:course:{course_number}"


def offering_staging_key(course_number: str, academic_year: int, semester_code: int) -> str:
    return f"technion:course-offering:{course_number}:{academic_year}:{semester_code}"


def normalize_faculty_name(faculty: str | None) -> str | None:
    if not faculty:
        return None
    cleaned = re.sub(r"\s+", " ", str(faculty)).strip()
    return cleaned or None


def is_dds_faculty(faculty: str | None) -> bool:
    normalized = normalize_faculty_name(faculty)
    if not normalized:
        return False
    return normalized in DDS_FACULTY_VARIANTS


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
    cleaned = re.sub(r"\s+", " ", str(text)).strip()
    if not cleaned:
        return None
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


def _exam_dates(general: dict[str, Any]) -> dict[str, str | None]:
    return {
        "examA": _truncate(str(general.get(GENERAL_FIELD_MAP["examA"]) or ""), 80),
        "examB": _truncate(str(general.get(GENERAL_FIELD_MAP["examB"]) or ""), 80),
    }


def default_course_json_paths() -> list[Path]:
    return list_semester_course_json_paths()


def _read_json_array(path: Path) -> list[dict[str, Any]]:
    payload = json.loads(path.read_text(encoding="utf-8"))
    if not isinstance(payload, list):
        raise ValueError(f"Expected JSON array in {path}")
    return payload


@dataclass
class _MergeAccumulator:
    course_number: str
    title_hebrew: str | None = None
    syllabus: str | None = None
    faculty: str | None = None
    study_framework: str | None = None
    credits: float | None = None
    prerequisites_text: str | None = None
    corequisites_text: str | None = None
    no_additional_credit_text: str | None = None
    instructors: str | None = None
    notes: str | None = None
    source_files: list[str] = field(default_factory=list)
    semesters_offered: list[int] = field(default_factory=list)
    offerings_embedded: list[dict[str, Any]] = field(default_factory=list)
    exams: dict[str, str | None] = field(default_factory=dict)
    schedule_summary: str | None = None
    raw_field_keys: list[str] = field(default_factory=list)
    warnings: list[str] = field(default_factory=list)


def _merge_text_field(
    current: str | None,
    incoming: str | None,
    *,
    field_name: str,
    source_file: str,
    warnings: list[str],
) -> str | None:
    if not incoming:
        return current
    if current and current != incoming:
        warnings.append(
            f"{field_name} conflict in {source_file}: kept {current!r}, saw {incoming!r}",
        )
        return current
    return incoming


def _merge_credits(
    current: float | None,
    incoming: float | None,
    *,
    source_file: str,
    warnings: list[str],
) -> float | None:
    if incoming is None:
        return current
    if current is not None and current != incoming:
        warnings.append(
            f"credits conflict in {source_file}: kept {current}, saw {incoming}",
        )
        return current
    return incoming if current is None else current


def read_and_normalize_course_json_files(
    paths: list[Path],
    *,
    dds_only: bool = False,
) -> TechnionCourseParseResult:
    result = TechnionCourseParseResult()
    merge_index: dict[str, _MergeAccumulator] = {}
    offerings: list[StagedTechnionCourseOffering] = []

    for path in paths:
        if not path.exists():
            result.warnings.append(f"Source file not found, skipped: {path}")
            continue

        semester_code = semester_code_from_filename(path)
        academic_year = academic_year_from_filename(path)
        if semester_code is None or academic_year is None:
            result.warnings.append(f"Could not infer academic year/semester from filename: {path.name}")
            continue

        semester_name = SEMESTER_CODE_LABELS[semester_code]
        result.files_read += 1

        try:
            records = _read_json_array(path)
        except (OSError, json.JSONDecodeError, ValueError) as exc:
            result.warnings.append(f"Failed to read {path.name}: {exc}")
            continue

        for index, entry in enumerate(records):
            result.raw_records_read += 1
            if not isinstance(entry, dict):
                result.invalid_records.append(
                    InvalidCourseRecord(path.name, index, "Record is not a JSON object"),
                )
                continue

            general = entry.get("general")
            if not isinstance(general, dict):
                result.invalid_records.append(
                    InvalidCourseRecord(path.name, index, "Missing general object"),
                )
                continue

            raw_number = general.get(GENERAL_FIELD_MAP["courseNumber"])
            course_number = normalize_course_number(str(raw_number or ""))
            if course_number is None:
                result.invalid_records.append(
                    InvalidCourseRecord(path.name, index, f"Invalid course number: {raw_number!r}"),
                )
                continue

            faculty = normalize_faculty_name(
                _truncate(str(general.get(GENERAL_FIELD_MAP["faculty"]) or ""), 200),
            )
            if dds_only and not is_dds_faculty(faculty):
                continue

            title = _truncate(str(general.get(GENERAL_FIELD_MAP["titleHebrew"]) or ""), 300)
            credits = _parse_credits(general.get(GENERAL_FIELD_MAP["credits"]))
            schedule = entry.get("schedule") if isinstance(entry.get("schedule"), list) else []
            exams = _exam_dates(general)
            instructors = _truncate(str(general.get(GENERAL_FIELD_MAP["instructors"]) or ""), 300)
            notes = _truncate(str(general.get(GENERAL_FIELD_MAP["notes"]) or ""), 500)

            offering = StagedTechnionCourseOffering(
                stagingKey=offering_staging_key(course_number, academic_year, semester_code),
                courseNumber=course_number,
                academicYear=academic_year,
                semesterCode=semester_code,
                semesterName=semester_name,
                scheduleGroups=schedule,
                examDates=exams,
                instructors=instructors,
                sourceFile=path.name,
            )
            offerings.append(offering)

            if course_number not in merge_index:
                merge_index[course_number] = _MergeAccumulator(
                    course_number=course_number,
                    title_hebrew=title,
                    syllabus=_truncate(str(general.get(GENERAL_FIELD_MAP["syllabus"]) or ""), 400),
                    faculty=faculty,
                    study_framework=_truncate(
                        str(general.get(GENERAL_FIELD_MAP["studyFramework"]) or ""),
                        120,
                    ),
                    credits=credits,
                    prerequisites_text=_truncate(
                        str(general.get(GENERAL_FIELD_MAP["prerequisitesText"]) or ""),
                        300,
                    ),
                    corequisites_text=_truncate(
                        str(general.get(GENERAL_FIELD_MAP["corequisitesText"]) or ""),
                        300,
                    ),
                    no_additional_credit_text=_truncate(
                        str(general.get(GENERAL_FIELD_MAP["noAdditionalCreditText"]) or ""),
                        300,
                    ),
                    instructors=instructors,
                    notes=notes,
                    source_files=[path.name],
                    semesters_offered=[semester_code],
                    exams=exams,
                    schedule_summary=_schedule_summary(schedule),
                    raw_field_keys=sorted(general.keys()),
                )
                merge_index[course_number].offerings_embedded.append(
                    {
                        "academicYear": academic_year,
                        "semesterCode": semester_code,
                        "semesterName": semester_name,
                        "sourceFile": path.name,
                        "scheduleSummary": _schedule_summary(schedule),
                    }
                )
                continue

            acc = merge_index[course_number]
            if path.name not in acc.source_files:
                acc.source_files.append(path.name)
            if semester_code not in acc.semesters_offered:
                acc.semesters_offered.append(semester_code)

            acc.title_hebrew = _merge_text_field(
                acc.title_hebrew,
                title,
                field_name="titleHebrew",
                source_file=path.name,
                warnings=acc.warnings,
            )
            acc.credits = _merge_credits(
                acc.credits,
                credits,
                source_file=path.name,
                warnings=acc.warnings,
            )
            acc.syllabus = _merge_text_field(
                acc.syllabus,
                _truncate(str(general.get(GENERAL_FIELD_MAP["syllabus"]) or ""), 400),
                field_name="syllabus",
                source_file=path.name,
                warnings=acc.warnings,
            )
            acc.faculty = _merge_text_field(
                acc.faculty,
                faculty,
                field_name="faculty",
                source_file=path.name,
                warnings=acc.warnings,
            )
            if not acc.instructors and instructors:
                acc.instructors = instructors
            if not acc.notes and notes:
                acc.notes = notes
            if not acc.schedule_summary:
                acc.schedule_summary = _schedule_summary(schedule)
            if not acc.exams.get("examA") and exams.get("examA"):
                acc.exams = exams
            acc.raw_field_keys = sorted(set(acc.raw_field_keys) | set(general.keys()))
            acc.offerings_embedded.append(
                {
                    "academicYear": academic_year,
                    "semesterCode": semester_code,
                    "semesterName": semester_name,
                    "sourceFile": path.name,
                    "scheduleSummary": _schedule_summary(schedule),
                }
            )

    courses: list[StagedTechnionCourse] = []
    for acc in merge_index.values():
        course_warnings = list(acc.warnings)
        if not acc.title_hebrew:
            course_warnings.append(f"{acc.course_number}: missing titleHebrew in source JSON")

        try:
            course = StagedTechnionCourse(
                stagingKey=course_staging_key(acc.course_number),
                courseNumber=acc.course_number,
                titleHebrew=acc.title_hebrew,
                syllabus=acc.syllabus,
                faculty=acc.faculty,
                studyFramework=acc.study_framework,
                credits=acc.credits,
                prerequisitesText=acc.prerequisites_text,
                corequisitesText=acc.corequisites_text,
                noAdditionalCreditText=acc.no_additional_credit_text,
                instructors=acc.instructors,
                notes=acc.notes,
                sourceFiles=sorted(set(acc.source_files)),
                semestersOffered=sorted(set(acc.semesters_offered)),
                offerings=acc.offerings_embedded,
                exams=acc.exams,
                scheduleSummary=acc.schedule_summary,
                rawFieldKeys=acc.raw_field_keys,
                metadata={
                    "offeringSnapshotOnly": True,
                    "notCanonicalCatalog": True,
                    "degreeRequirementsInferred": False,
                },
                warnings=course_warnings,
                sourceName=SOURCE_NAME,
                sourceType=SOURCE_TYPE,
            )
        except Exception as exc:
            result.invalid_records.append(
                InvalidCourseRecord(
                    ",".join(acc.source_files),
                    -1,
                    f"Failed to build staged course {acc.course_number}: {exc}",
                ),
            )
            continue

        courses.append(course)
        result.warnings.extend(course_warnings)

    if dds_only:
        dds_numbers = {course.courseNumber for course in courses if is_dds_faculty(course.faculty)}
        offerings = [o for o in offerings if o.courseNumber in dds_numbers]
        courses = [c for c in courses if c.courseNumber in dds_numbers]

    result.courses = sorted(courses, key=lambda item: item.courseNumber)
    result.offerings = offerings
    result.dds_faculty_course_count = sum(1 for course in courses if is_dds_faculty(course.faculty))
    return result
