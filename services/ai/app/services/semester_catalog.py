"""Technion semester offering catalog discovery and query resolution."""

from __future__ import annotations

import json
import re
from dataclasses import dataclass
from datetime import date
from pathlib import Path

COURSE_JSON_FILENAME = re.compile(r"^courses_(\d{4})_(200|201|202)\.json$")
MANIFEST_SEMESTER_CODE = re.compile(r"^(\d{4})-(200|201|202)$")

OFFERING_LABELS = {
    200: {"en": "Winter", "he": "חורף", "plan_term": 1},
    201: {"en": "Spring", "he": "אביב", "plan_term": 2},
    202: {"en": "Summer", "he": "קיץ", "plan_term": 3},
}

HEBREW_TERM_KEYWORDS: dict[int, list[str]] = {
    200: ["חורף", "סמסטר א", "סמסטר חורף", "חורףי", "חורפי"],
    201: ["אביב", "סמסטר ב", "סמסטר אביב"],
    202: ["קיץ", "סמסטר קיץ", "קיץי"],
}

ENGLISH_TERM_KEYWORDS: dict[int, list[str]] = {
    200: ["winter"],
    201: ["spring"],
    202: ["summer"],
}


@dataclass(frozen=True)
class SemesterCatalogInfo:
    filename: str
    path: str
    file_academic_year: int
    offering_code: int
    plan_semester_code: str
    calendar_year: int
    label_en: str
    label_he: str
    display_label: str

    @property
    def id(self) -> str:
        return self.filename.removesuffix(".json")


def offering_keys_to_plan_semester_code(academic_year: int, semester_code: int) -> str | None:
    if semester_code not in OFFERING_LABELS:
        return None
    term_index = semester_code - 199
    return f"{academic_year}-{term_index}"


def plan_semester_code_from_filename(filename: str) -> str | None:
    match = COURSE_JSON_FILENAME.match(filename.strip())
    if not match:
        return None
    return offering_keys_to_plan_semester_code(int(match.group(1)), int(match.group(2)))


def _calendar_year_from_file_academic_year(file_academic_year: int) -> int:
    """Filename academic year is one year behind the calendar year of the offering."""
    return file_academic_year + 1


def _build_semester_info(path: Path) -> SemesterCatalogInfo | None:
    match = COURSE_JSON_FILENAME.match(path.name)
    if not match:
        return None
    file_academic_year = int(match.group(1))
    offering_code = int(match.group(2))
    plan_code = offering_keys_to_plan_semester_code(file_academic_year, offering_code)
    if not plan_code:
        return None
    labels = OFFERING_LABELS[offering_code]
    calendar_year = _calendar_year_from_file_academic_year(file_academic_year)
    return SemesterCatalogInfo(
        filename=path.name,
        path=str(path),
        file_academic_year=file_academic_year,
        offering_code=offering_code,
        plan_semester_code=plan_code,
        calendar_year=calendar_year,
        label_en=labels["en"],
        label_he=labels["he"],
        display_label=f"{labels['en']} {calendar_year} ({labels['he']} {calendar_year})",
    )


def semester_info_from_path(path: Path) -> SemesterCatalogInfo | None:
    return _build_semester_info(path)


def discover_semester_catalogs(raw_dir: Path) -> list[SemesterCatalogInfo]:
    if not raw_dir.is_dir():
        return []

    catalogs: list[SemesterCatalogInfo] = []
    for path in sorted(raw_dir.glob("courses_*.json")):
        if not path.is_file():
            continue
        info = _build_semester_info(path)
        if info:
            catalogs.append(info)

    if catalogs:
        return sorted(catalogs, key=lambda c: (c.file_academic_year, c.offering_code))

    manifest_path = raw_dir / "manifest.json"
    if not manifest_path.is_file():
        return []

    try:
        payload = json.loads(manifest_path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        return []

    for source in payload.get("sources") or []:
        if not isinstance(source, dict):
            continue
        relative_path = str(source.get("path") or "").strip()
        if not relative_path:
            continue
        full_path = raw_dir / relative_path
        if not full_path.is_file():
            continue
        info = _build_semester_info(full_path)
        if info:
            catalogs.append(info)

    return sorted(catalogs, key=lambda c: (c.file_academic_year, c.offering_code))


def infer_current_semester(
    catalogs: list[SemesterCatalogInfo],
    today: date | None = None,
) -> SemesterCatalogInfo | None:
    """Pick the most likely current semester from available catalogs."""
    if not catalogs:
        return None

    current = today or date.today()
    month = current.month
    calendar_year = current.year

    if month in (7, 8, 9):
        offering_code = 202
    elif month in (3, 4, 5, 6):
        offering_code = 201
    else:
        offering_code = 200

    file_academic_year = calendar_year - 1
    exact = next(
        (
            catalog
            for catalog in catalogs
            if catalog.file_academic_year == file_academic_year
            and catalog.offering_code == offering_code
        ),
        None,
    )
    if exact:
        return exact

    return catalogs[-1]


def _extract_year_tokens(query: str) -> list[int]:
    years = [int(match) for match in re.findall(r"(20\d{2})", query)]
    return list(dict.fromkeys(years))


def _term_keywords_for_offering(offering_code: int) -> list[str]:
    return (
        HEBREW_TERM_KEYWORDS.get(offering_code, [])
        + ENGLISH_TERM_KEYWORDS.get(offering_code, [])
    )


def _score_catalog_for_query(catalog: SemesterCatalogInfo, query: str) -> int:
    lowered = query.lower()
    score = 0

    if catalog.filename.lower() in lowered:
        score += 20
    if catalog.plan_semester_code in lowered:
        score += 15
    if str(catalog.calendar_year) in query:
        score += 8
    if str(catalog.file_academic_year) in query:
        score += 4

    if any(keyword in lowered for keyword in _term_keywords_for_offering(catalog.offering_code)):
        score += 10

    year_tokens = _extract_year_tokens(query)
    if year_tokens:
        if catalog.calendar_year in year_tokens:
            score += 12
        if catalog.file_academic_year in year_tokens:
            score += 6

    return score


def resolve_semester_from_query(
    query: str,
    catalogs: list[SemesterCatalogInfo],
    *,
    explicit_filename: str | None = None,
    explicit_plan_code: str | None = None,
    today: date | None = None,
) -> dict[str, object]:
    """Resolve which semester JSON to use."""
    if not catalogs:
        return {
            "semester": None,
            "confidence": "low",
            "needs_clarification": True,
            "assumption_note": "No semester catalog files were found on disk.",
            "candidates": [],
        }

    if explicit_filename:
        match = next(
            (catalog for catalog in catalogs if catalog.filename == explicit_filename),
            None,
        )
        if match:
            return {
                "semester": match,
                "confidence": "high",
                "needs_clarification": False,
                "assumption_note": None,
                "candidates": [match],
            }

    if explicit_plan_code:
        match = next(
            (
                catalog
                for catalog in catalogs
                if catalog.plan_semester_code == explicit_plan_code
            ),
            None,
        )
        if match:
            return {
                "semester": match,
                "confidence": "high",
                "needs_clarification": False,
                "assumption_note": None,
                "candidates": [match],
            }

    scored = sorted(
        ((catalog, _score_catalog_for_query(catalog, query)) for catalog in catalogs),
        key=lambda item: item[1],
        reverse=True,
    )
    top_catalog, top_score = scored[0]
    second_score = scored[1][1] if len(scored) > 1 else 0

    if top_score >= 10 and top_score > second_score:
        confidence = "high" if top_score >= 15 else "medium"
        return {
            "semester": top_catalog,
            "confidence": confidence,
            "needs_clarification": False,
            "assumption_note": None,
            "candidates": [catalog for catalog, score in scored[:3] if score > 0],
        }

    tied_at_top = [catalog for catalog, score in scored if score == top_score and score >= 10]
    if len(tied_at_top) > 1:
        default_catalog = infer_current_semester(catalogs, today=today) or top_catalog
        labels = ", ".join(catalog.display_label for catalog in tied_at_top[:3])
        return {
            "semester": default_catalog,
            "confidence": "low",
            "needs_clarification": True,
            "assumption_note": (
                f"Multiple semesters match ({labels}). "
                f"Using {default_catalog.display_label} until clarified."
            ),
            "candidates": tied_at_top[:5],
        }

    # No clear semester in query — default to inferred current semester.
    default_catalog = infer_current_semester(catalogs, today=today) or top_catalog
    return {
        "semester": default_catalog,
        "confidence": "medium",
        "needs_clarification": top_score == 0,
        "assumption_note": (
            f"Assuming {default_catalog.display_label} "
            f"({default_catalog.filename}) because the question did not specify a semester."
        ),
        "candidates": [catalog for catalog, _ in scored[:3]],
    }


def format_semester_catalog_summary(catalogs: list[SemesterCatalogInfo]) -> str:
    lines = [
        "Available semester offering catalogs (JSON):",
        "Note: filename year is one calendar year behind (courses_2025_202 = Summer 2026).",
    ]
    for catalog in catalogs:
        lines.append(
            f"- {catalog.filename} → {catalog.display_label} "
            f"[plan code {catalog.plan_semester_code}]"
        )
    return "\n".join(lines)
