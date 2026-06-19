"""Parse Technion DDS catalog markdown into a draft curated JSON document."""

from __future__ import annotations

import json
import re
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

from app.models.catalog import (
    CatalogCourseReference,
    CatalogRequirementGroup,
    CuratedCatalogDocument,
    CuratedCatalogSource,
    NormalizedDegreePath,
    NormalizedDegreeProgram,
)
from app.sources.technion_dds_catalog_pdf import service_root
from app.utils.course_numbers import clean_cell_text, extract_course_title_pairs, normalize_course_number
from app.utils.hebrew_rtl import normalize_hebrew_punctuation, normalize_whitespace

PROGRAM_CODES = ["009216-1-000", "009009-1-000", "009118-1-000"]

PROGRAM_DEFINITIONS: dict[str, dict[str, str]] = {
    "009216-1-000": {
        "name": "הנדסת נתונים ומידע",
        "nameEn": "Data Science and Engineering",
        "header": "לימודי הסמכה בהנדסת נתונים ומידע",
    },
    "009009-1-000": {
        "name": "הנדסת תעשייה וניהול",
        "nameEn": "Industrial Engineering and Management",
        "header": "לימודי הסמכה בהנדסת תעשייה וניהול",
    },
    "009118-1-000": {
        "name": "הנדסת מערכות מידע",
        "nameEn": "Information Systems Engineering",
        "header": "לימודי הסמכה בהנדסת מערכות מידע",
    },
}


def extract_shared_footnote_credits(section: str) -> dict[str, float]:
    buckets: dict[str, float] = {}
    enrichment = re.search(r"(\d+)\s*נק['\s]*העשרה#", section)
    if enrichment:
        buckets["enrichment"] = float(enrichment.group(1))
    free = re.search(r"(\d+)\s*נק['\s]*בחירה חופשית##", section)
    if free:
        buckets["free-elective"] = float(free.group(1))
    pe = re.search(r"(\d+)\s*נק['\s]*חינוך גופני", section)
    if pe:
        buckets["physical-education"] = float(pe.group(1))
    return buckets


def extract_program_credit_buckets(program_code: str, section: str) -> dict[str, float]:
    buckets = extract_shared_footnote_credits(section)

    if program_code == "009216-1-000":
        core = re.search(r"(\d+(?:\.\d+)?)\s*נק['\s]*\n\s*קורסי חובה", section)
        if not core:
            core = re.search(r"(\d+(?:\.\d+)?)\s*נק['\s]+קורסי חובה", section)
        if core:
            buckets["core-mandatory"] = float(core.group(1))
        ds = re.search(r"מינימום\s+(\d+(?:\.\d+)?)\s*נק['\s]", section)
        if not ds:
            ds = re.search(
                r"(\d+(?:\.\d+)?)\s*נק['\s]+קורסי בחירה בהנדסת נתונים ומידע",
                section,
            )
        if ds:
            buckets["elective-ds"] = float(ds.group(1))
        faculty = re.search(r"קורסי בחירה פקולטיים:\s*(\d+(?:\.\d+)?)\s*נק", section)
        if not faculty:
            faculty = re.search(
                r"(\d+(?:\.\d+)?)\s*נק['\s]+קורסי בחירה פקולטיים",
                section,
            )
        if faculty:
            buckets["elective-faculty"] = float(faculty.group(1))
        general = re.search(
            r"^\s*12\.0\s*$\s*\n\s*קורסי בחירה בהנדסת נתונים",
            section,
            flags=re.MULTILINE,
        )
        if general:
            buckets["elective-general"] = 12.0
        else:
            inline_general = re.search(
                r"12\.0\s*נק['\s]+קורסי בחירה כלל-טכניונית",
                section,
            )
            if inline_general:
                buckets["elective-general"] = 12.0

    if program_code == "009009-1-000":
        core = re.search(r"קורסי חובה\s+(\d+(?:\.\d+)?)\s*נק", section)
        if not core:
            core = re.search(r"(\d+(?:\.\d+)?)\s*נק['\s]*\n\s*קורסי חובה", section)
        if core:
            buckets["core-mandatory"] = float(core.group(1))
        faculty_general = re.search(
            r"^\s*40\.0\s*$\s*\n\s*12\.0\s*$\s*\n\s*קורסי בחירה פקולטית",
            section,
            flags=re.MULTILINE,
        )
        if faculty_general:
            buckets["elective-faculty"] = 40.0
            buckets["elective-general"] = 12.0
        else:
            inline_faculty = re.search(r"40\.0\s+קורסי בחירה פקולטית", section)
            if inline_faculty:
                buckets["elective-faculty"] = 40.0
            inline_general = re.search(
                r"12\.0\s*נק['\s]*\n\s*קורסי בחירה כלל-טכניונית",
                section,
            )
            if inline_general:
                buckets["elective-general"] = 12.0

    if program_code == "009118-1-000":
        core = re.search(r"(\d+(?:\.\d+)?)\s*נק['\s]*\n\s*35\.5\s*נק", section)
        if core:
            buckets["core-mandatory"] = float(core.group(1))
        faculty_general = re.search(r"35\.5\s*נק['\s]*12\.0\s*נק", section)
        if faculty_general:
            buckets["elective-faculty"] = 35.5
            buckets["elective-general"] = 12.0

    return buckets


@dataclass
class ParserReport:
    warnings: list[str] = field(default_factory=list)
    normalizedCourseNumbers: int = 0
    rejectedCourseNumbers: int = 0
    requirementGroups: int = 0
    courseReferences: int = 0

    def to_dict(self) -> dict[str, Any]:
        return {
            "warnings": self.warnings,
            "normalizedCourseNumbers": self.normalizedCourseNumbers,
            "rejectedCourseNumbers": self.rejectedCourseNumbers,
            "requirementGroups": self.requirementGroups,
            "courseReferences": self.courseReferences,
            "manualReviewRequired": True,
        }


def default_markdown_path() -> Path:
    return (
        service_root()
        / "data"
        / "raw"
        / "technion"
        / "technion_dds_catalog_from_docx_clean.md"
    )


def default_draft_output_path() -> Path:
    return service_root() / "data" / "generated" / "technion" / "dds_catalog" / "dds_catalog_curated_draft.json"


def resolve_markdown_path(md_path: str | None, env_path: str | None = None) -> Path:
    candidate = md_path or env_path
    if not candidate:
        candidate = str(default_markdown_path())
    resolved = Path(candidate)
    if not resolved.is_absolute():
        resolved = (Path.cwd() / resolved).resolve()
    if not resolved.exists():
        raise FileNotFoundError(f"DDS catalog markdown not found: {resolved}")
    return resolved


def preprocess_markdown(raw_text: str) -> str:
    """Normalize markdown without global RTL line reversal (tables stay structured)."""
    normalized = normalize_whitespace(raw_text)
    return normalize_hebrew_punctuation(normalized)


def split_program_sections(text: str) -> dict[str, str]:
    sections: dict[str, str] = {}
    for index, code in enumerate(PROGRAM_CODES):
        start = text.find(code)
        if start < 0:
            continue
        end = len(text)
        for next_code in PROGRAM_CODES[index + 1 :]:
            next_start = text.find(next_code, start + len(code))
            if next_start >= 0:
                end = next_start
                break
        sections[code] = text[start:end]
    return sections


def _course_ref(raw: dict[str, object], *, semester: int | None = None) -> CatalogCourseReference:
    page_numbers = [semester] if semester is not None else []
    return CatalogCourseReference(
        courseNumber=str(raw["courseNumber"]),
        titleHint=raw.get("titleHint"),  # type: ignore[arg-type]
        creditsHint=raw.get("creditsHint"),  # type: ignore[arg-type]
        pageNumbers=page_numbers,
        manualReviewRequired=True,
        confidence="medium" if raw.get("titleHint") else "low",
    )


def build_credit_requirement_groups(
    program_code: str,
    section: str,
    report: ParserReport,
) -> list[CatalogRequirementGroup]:
    groups: list[CatalogRequirementGroup] = []
    buckets = extract_program_credit_buckets(program_code, section)
    for bucket_id, value in buckets.items():
        requirement_type = "core" if bucket_id == "core-mandatory" else "elective"
        if bucket_id in {"enrichment", "free-elective", "physical-education"}:
            requirement_type = "credit"
        groups.append(
            CatalogRequirementGroup(
                groupId=f"{program_code}:{bucket_id}",
                title=bucket_id.replace("-", " "),
                requirementType=requirement_type,
                minCredits=value,
                ruleExpression={"type": "credit_bucket", "operator": "min_credits"},
                notes=["Parsed from markdown credit summary; review before staging import."],
                manualReviewRequired=True,
                confidence="medium",
            )
        )
    report.requirementGroups += len(groups)
    return groups


MAX_REQUIREMENT_SEMESTER = 6


def _accept_semester_number(value: int) -> bool:
    return 1 <= value <= MAX_REQUIREMENT_SEMESTER


def _semester_schedule_section(section: str) -> str:
    start = section.find("קורסי חובה - שיבוץ מומלץ לפי סמסטרים")
    if start < 0:
        return section
    tail = section[start:]
    end_markers = [
        "\nקורסי בחירה פקולטית\n",
        "ריכוז נקודות לפי סמסטרים",
        "שנה א' - סמסטר",
    ]
    end = len(tail)
    for marker in end_markers:
        pos = tail.find(marker, 100)
        if pos >= 0:
            end = min(end, pos)
    return tail[:end]


def extract_semester_matrix_courses(section: str, report: ParserReport) -> dict[int, list[CatalogCourseReference]]:
    section = _semester_schedule_section(section)
    semester_courses: dict[int, list[CatalogCourseReference]] = {}
    current_semester: int | None = None
    pending_semester: int | None = None
    pending_expiry = 0

    for line in section.splitlines():
        sem_only = re.match(r"^\s*סמסטר\s*(\d+)\s*$", line)
        if sem_only:
            semester_number = int(sem_only.group(1))
            if _accept_semester_number(semester_number):
                pending_semester = semester_number
                pending_expiry = 12

        if "|" in line:
            semester_match = re.search(r"סמסטר\s*(\d+)", line)
            if semester_match:
                semester_number = int(semester_match.group(1))
                if _accept_semester_number(semester_number):
                    current_semester = semester_number
                else:
                    current_semester = None
                pending_semester = None
                pending_expiry = 0
            elif pending_semester is not None and pending_expiry > 0:
                current_semester = pending_semester
                pending_expiry -= 1

        if current_semester is None or "|" not in line:
            continue

        for cell in line.split("|"):
            cell_text = clean_cell_text(cell.strip())
            if not cell_text or not re.search(r"(?:0\d{6,8}|\d{7,8})", cell_text):
                continue
            pairs = extract_course_title_pairs(cell_text)
            if not pairs:
                number = normalize_course_number(cell_text.split()[0])
                if number:
                    pairs = [{"courseNumber": number, "titleHint": None, "creditsHint": None}]
                else:
                    report.rejectedCourseNumbers += 1
                    continue

            for pair in pairs:
                report.normalizedCourseNumbers += 1
                semester_courses.setdefault(current_semester, []).append(
                    _course_ref(pair, semester=current_semester)
                )

    return semester_courses


def extract_prose_semester_courses(
    section: str,
    report: ParserReport,
) -> dict[int, list[CatalogCourseReference]]:
    """Extract semester-1 style courses listed as prose (no markdown table pipes)."""
    semester_courses: dict[int, list[CatalogCourseReference]] = {}
    for match in re.finditer(r"^\s*סמסטר\s*1\s*$", section, flags=re.MULTILINE):
        tail = section[match.end() :]
        end_match = re.search(
            r"^\s*\.2\s+קורסי|^\s*קורסי בחירה בהנדסת נתונים ומידע\s+0\d|^\|.*סמסטר\s*2",
            tail,
            flags=re.MULTILINE,
        )
        block = tail[: end_match.start()] if end_match else tail[:900]
        if block.count("|") >= 3:
            continue
        courses = extract_inline_courses(block, report)
        if courses:
            semester_courses.setdefault(1, []).extend(courses)
    return semester_courses


DS_ELECTIVE_BLOCK_END_MARKERS = [
    "מגמה במדעי הקוגניציה",
    "מגמת אנליזה מתמטית למדעי הנתונים",
    "למדעי הנתונים וההחלטות לא יוכרו",
    "+-----------------------------------+",
]
DS_ELECTIVE_HEADER = re.compile(
    r"^קורסי בחירה בהנדסת נתונים ומידע",
    flags=re.MULTILINE,
)


def extract_ds_elective_pool(section: str, report: ParserReport) -> list[CatalogCourseReference]:
    candidates: list[str] = []
    for match in DS_ELECTIVE_HEADER.finditer(section):
        tail = section[match.start() :]
        end = len(tail)
        for marker in DS_ELECTIVE_BLOCK_END_MARKERS:
            pos = tail.find(marker, len(match.group(0)))
            if pos >= 0:
                end = min(end, pos)
        block = tail[:end]
        if re.search(r"(?:0\d{6,8}|\d{7,8})", block[:500]):
            candidates.append(block)
    if not candidates:
        return []
    block = max(candidates, key=lambda value: len(extract_course_title_pairs(value)))
    return extract_inline_courses(block, report)


def build_ds_faculty_elective_group(program_code: str) -> CatalogRequirementGroup:
    return CatalogRequirementGroup(
        groupId=f"{program_code}:elective-faculty-pool",
        title="Faculty elective pool (prefix rule)",
        requirementType="elective",
        minCredits=10.5,
        ruleExpression={
            "type": "course_pool",
            "operator": "choose_credits",
            "allowedPrefixes": ["094", "095", "096", "097"],
        },
        courseReferences=[],
        notes=[
            "Source defines 10.5 faculty elective credits by prefix rule (094/095/096/097), not a fixed list.",
            "2160035 may also count per catalog footnotes — verify manually.",
        ],
        manualReviewRequired=True,
        confidence="low",
    )


def extract_inline_courses(section: str, report: ParserReport) -> list[CatalogCourseReference]:
    refs: list[CatalogCourseReference] = []
    seen: set[str] = set()
    for pair in extract_course_title_pairs(section):
        number = str(pair["courseNumber"])
        if number in seen:
            continue
        seen.add(number)
        report.normalizedCourseNumbers += 1
        refs.append(_course_ref(pair))
    return refs


def extract_elective_block(section: str, marker: str, report: ParserReport) -> list[CatalogCourseReference]:
    """Legacy helper — prefer bounded extractors for DS catalog sections."""
    start = section.find(marker)
    if start < 0:
        return []
    block = section[start : start + 4000]
    return extract_inline_courses(block, report)


def build_semester_requirement_groups(
    program_code: str,
    semester_courses: dict[int, list[CatalogCourseReference]],
    report: ParserReport,
) -> list[CatalogRequirementGroup]:
    groups: list[CatalogRequirementGroup] = []
    for semester, courses in sorted(semester_courses.items()):
        if not courses:
            continue
        groups.append(
            CatalogRequirementGroup(
                groupId=f"{program_code}:semester-{semester}-matrix",
                title=f"Recommended mandatory semester {semester}",
                requirementType="core",
                ruleExpression={
                    "type": "semester_matrix",
                    "operator": "all_of",
                    "semester": semester,
                },
                courseReferences=courses,
                pageNumbers=[semester],
                notes=["Parsed from markdown semester table; verify mandatory vs elective markers (*)."],
                manualReviewRequired=True,
                confidence="medium",
            )
        )
    report.requirementGroups += len(groups)
    return groups


def extract_degree_paths(program_code: str, section: str) -> list[NormalizedDegreePath]:
    if program_code != "009216-1-000":
        return []

    paths: list[NormalizedDegreePath] = []
    path_markers = [
        ("cognition-track", "מגמה במדעי הקוגניציה"),
        ("math-analytics-track", "מגמת אנליזה מתמטית למדעי הנתונים"),
    ]
    for path_code, marker in path_markers:
        if marker not in section:
            continue
        start = section.find(marker)
        snippet = section[start : start + 1200]
        paths.append(
            NormalizedDegreePath(
                pathCode=path_code,
                title=marker,
                description=snippet.splitlines()[0][:300] if snippet else None,
                requirementGroupIds=[f"{program_code}:{path_code}:requirements"],
                manualReviewRequired=True,
                confidence="medium",
            )
        )
    return paths


def build_path_requirement_groups(
    program_code: str,
    section: str,
    report: ParserReport,
) -> list[CatalogRequirementGroup]:
    groups: list[CatalogRequirementGroup] = []
    if program_code != "009216-1-000":
        return groups

    if "מגמת אנליזה מתמטית למדעי הנתונים" in section:
        block_start = section.find("מגמת אנליזה מתמטית למדעי הנתונים")
        block = section[block_start : block_start + 2500]
        track_courses = extract_inline_courses(block, report)
        groups.append(
            CatalogRequirementGroup(
                groupId=f"{program_code}:math-analytics-track:requirements",
                title="Mathematical analytics track requirements",
                requirementType="elective",
                minCredits=26.0,
                ruleExpression={
                    "type": "track_requirement",
                    "operator": "credit_pool",
                    "chooseFromLists": True,
                },
                courseReferences=track_courses,
                notes=[
                    "Parsed track requirement: 26 credits from listed courses.",
                    "Review footnotes ¹²⁴ for elective classification.",
                ],
                manualReviewRequired=True,
                confidence="low",
            )
        )

    if "מגמה במדעי הקוגניציה" in section:
        block_start = section.find("מגמה במדעי הקוגניציה")
        block = section[block_start : block_start + 2000]
        track_courses = extract_inline_courses(block, report)
        groups.append(
            CatalogRequirementGroup(
                groupId=f"{program_code}:cognition-track:requirements",
                title="Cognition track requirements",
                requirementType="elective",
                ruleExpression={"type": "track_requirement", "operator": "choose_n"},
                courseReferences=track_courses,
                notes=["Includes project-heavy courses marked with * in source."],
                manualReviewRequired=True,
                confidence="low",
            )
        )

    report.requirementGroups += len(groups)
    return groups


def parse_program(
    program_code: str,
    section: str,
    report: ParserReport,
) -> NormalizedDegreeProgram:
    definition = PROGRAM_DEFINITIONS[program_code]
    processed_section = preprocess_markdown(section)

    credit_groups = build_credit_requirement_groups(program_code, processed_section, report)
    semester_courses = extract_semester_matrix_courses(processed_section, report)
    if program_code == "009216-1-000":
        for semester, courses in extract_prose_semester_courses(processed_section, report).items():
            semester_courses.setdefault(semester, []).extend(courses)
    semester_groups = build_semester_requirement_groups(program_code, semester_courses, report)

    elective_groups: list[CatalogRequirementGroup] = []
    if program_code == "009216-1-000":
        ds_electives = extract_ds_elective_pool(processed_section, report)
        if ds_electives:
            elective_groups.append(
                CatalogRequirementGroup(
                    groupId=f"{program_code}:elective-ds-pool",
                    title="Data science elective pool",
                    requirementType="elective",
                    minCredits=24.5,
                    ruleExpression={"type": "course_pool", "operator": "choose_credits"},
                    courseReferences=ds_electives,
                    notes=["Minimum 24.5 credits; at least two * courses required per source."],
                    manualReviewRequired=True,
                    confidence="medium",
                )
            )
        elective_groups.append(build_ds_faculty_elective_group(program_code))

    path_groups = build_path_requirement_groups(program_code, processed_section, report)
    paths = extract_degree_paths(program_code, processed_section)

    all_groups = [*credit_groups, *semester_groups, *elective_groups, *path_groups]
    report.courseReferences += sum(len(group.courseReferences) for group in all_groups)

    return NormalizedDegreeProgram(
        institutionId="technion",
        programCode=program_code,
        name=definition["name"],
        nameEn=definition["nameEn"],
        catalogYear=2025,
        catalogVersion="2025-2026",
        totalCredits=155.0,
        paths=paths,
        requirementGroups=all_groups,
        metadata={
            "sourceHeader": definition["header"],
            "footnoteMarkers": {"#": "enrichment", "##": "free_elective", "*": "project_or_timing"},
        },
        manualReviewRequired=True,
        confidence="medium",
    )


def _collect_course_refs(programs: list[NormalizedDegreeProgram]) -> list[CatalogCourseReference]:
    refs: list[CatalogCourseReference] = []
    for program in programs:
        for group in program.requirementGroups:
            refs.extend(group.courseReferences)
    return refs


def finalize_parser_warnings(
    document: CuratedCatalogDocument,
    report: ParserReport,
    *,
    markdown_text: str,
) -> None:
    from app.utils.course_numbers import normalize_course_number

    refs = _collect_course_refs(document.programs)
    if not refs:
        report.warnings.append("No course references were extracted from markdown.")
        return

    missing_titles = sum(1 for ref in refs if not ref.titleHint)
    if missing_titles:
        report.warnings.append(
            f"{missing_titles}/{len(refs)} course references lack titleHint; manual title review required.",
        )

    md_numbers = {
        value
        for raw in re.findall(r"(?<!\d)(0\d{6,8}|\d{7,8})(?!\d)", markdown_text)
        if (value := normalize_course_number(raw))
    }
    draft_numbers = {ref.courseNumber for ref in refs}
    missing = sorted(md_numbers - draft_numbers)
    if missing:
        report.warnings.append(
            f"{len(missing)} normalized course numbers appear in markdown but not in draft "
            f"(sample: {', '.join(missing[:5])}).",
        )

    ds_program = next((p for p in document.programs if p.programCode == "009216-1-000"), None)
    if ds_program:
        ds_pool = next(
            (g for g in ds_program.requirementGroups if g.groupId.endswith(":elective-ds-pool")),
            None,
        )
        faculty_pool = next(
            (g for g in ds_program.requirementGroups if g.groupId.endswith(":elective-faculty-pool")),
            None,
        )
        if ds_pool and faculty_pool and ds_pool.courseReferences and faculty_pool.courseReferences:
            ds_nums = {ref.courseNumber for ref in ds_pool.courseReferences}
            faculty_nums = {ref.courseNumber for ref in faculty_pool.courseReferences}
            overlap = ds_nums & faculty_nums
            if overlap:
                report.warnings.append(
                    f"DS elective and faculty pools share {len(overlap)} course numbers; review pool boundaries.",
                )

        sem_nums = {
            g.ruleExpression.get("semester")
            for g in ds_program.requirementGroups
            if g.ruleExpression.get("type") == "semester_matrix"
        }
        if 1 not in sem_nums:
            report.warnings.append(
                "DS semester-1 mandatory courses may be incomplete (prose block parsing is partial).",
            )

    for program in document.programs:
        high_semesters = [
            g.ruleExpression.get("semester")
            for g in program.requirementGroups
            if g.ruleExpression.get("type") == "semester_matrix"
            and isinstance(g.ruleExpression.get("semester"), int)
            and g.ruleExpression["semester"] > 6
        ]
        if high_semesters:
            report.warnings.append(
                f"Program {program.programCode} has semester_matrix groups for semesters "
                f"{sorted(high_semesters)} — likely cross-program sample schedules; verify manually.",
            )


def parse_curated_catalog_draft(
    md_path: str | None = None,
    *,
    env_path: str | None = None,
) -> tuple[CuratedCatalogDocument, ParserReport]:
    resolved = resolve_markdown_path(md_path, env_path)
    raw_text = resolved.read_text(encoding="utf-8")
    processed = preprocess_markdown(raw_text)
    report = ParserReport()

    programs: list[NormalizedDegreeProgram] = []
    for program_code, section in split_program_sections(processed).items():
        programs.append(parse_program(program_code, section, report))

    if not programs:
        report.warnings.append("No program sections were detected in markdown.")

    document = CuratedCatalogDocument(
        source=CuratedCatalogSource(
            institutionId="technion",
            sourceType="dds_catalog_markdown_draft",
            catalogYear=2025,
            catalogVersion="2025-2026",
            sourceFile=str(resolved),
            manualReviewRequired=True,
            confidence="medium",
            notes=[
                "Draft generated by markdown parser; not validated for staging import.",
                "Review semester tables, elective pools, and track rules manually.",
            ],
        ),
        programs=programs,
        parserReport={},
    )
    finalize_parser_warnings(document, report, markdown_text=processed)
    document = document.model_copy(update={"parserReport": report.to_dict()})
    return document, report


def write_curated_catalog_draft(
    md_path: str | None = None,
    *,
    env_path: str | None = None,
    output_path: str | Path | None = None,
) -> tuple[CuratedCatalogDocument, Path]:
    document, _report = parse_curated_catalog_draft(md_path, env_path=env_path)
    target = Path(output_path) if output_path else default_draft_output_path()
    if not target.is_absolute():
        target = (service_root() / target).resolve()
    target.parent.mkdir(parents=True, exist_ok=True)
    target.write_text(
        json.dumps(document.model_dump(mode="json"), ensure_ascii=False, indent=2),
        encoding="utf-8",
    )
    return document, target
