#!/usr/bin/env python3
"""Report course references missing titleHint after full vault export + signoff."""

from __future__ import annotations

import argparse
import json
import sys
from dataclasses import dataclass, field
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[1]
DE_ROOT = REPO_ROOT / "services" / "data-engineering"
SCRIPTS_ROOT = REPO_ROOT / "scripts"
sys.path.insert(0, str(DE_ROOT))
sys.path.insert(0, str(SCRIPTS_ROOT))

from lib.parallel_faculties import default_worker_count, map_faculties_parallel  # noqa: E402

from app.sources.technion_course_json_index import (  # noqa: E402
    build_course_index,
    default_course_json_paths,
)
from app.vault.title_index import build_wiki_title_index  # noqa: E402
from app.vault.loader import load_pages_by_slug, wiki_root  # noqa: E402
from app.paths import catalog_vault_root  # noqa: E402
from app.vault.vault_export_registry import export_vault_catalog, supported_export_faculties  # noqa: E402


@dataclass
class MissingTitleEntry:
    courseNumber: str
    inSemesterJson: bool
    inWikiTitleIndex: bool
    programWikiPages: list[str] = field(default_factory=list)


@dataclass
class FacultyMissingReport:
    facultyId: str
    missingCount: int
    uniqueCourseNumbers: list[str]
    entries: list[MissingTitleEntry]


def _semester_json_numbers() -> set[str]:
    paths = [path for path in default_course_json_paths() if path.exists()]
    return set(build_course_index(paths).keys())


def _wiki_title_index_numbers() -> set[str]:
    pages = load_pages_by_slug(wiki_root(catalog_vault_root()))
    return set(build_wiki_title_index(pages).keys())


def _audit_faculty(
    faculty_id: str,
    *,
    semester_numbers: set[str],
    wiki_index_numbers: set[str],
) -> FacultyMissingReport:
    document, _ = export_vault_catalog(faculty=faculty_id)
    by_number: dict[str, MissingTitleEntry] = {}

    for program in document.get("programs") or []:
        wiki_page = (program.get("metadata") or {}).get("wikiPage")
        for group in program.get("requirementGroups") or []:
            for ref in group.get("courseReferences") or []:
                if ref.get("titleHint"):
                    continue
                number = ref.get("courseNumber")
                if not number:
                    continue
                number = str(number)
                entry = by_number.get(number)
                if entry is None:
                    entry = MissingTitleEntry(
                        courseNumber=number,
                        inSemesterJson=number in semester_numbers,
                        inWikiTitleIndex=number in wiki_index_numbers,
                    )
                    by_number[number] = entry
                if wiki_page and wiki_page not in entry.programWikiPages:
                    entry.programWikiPages.append(str(wiki_page))

    entries = sorted(by_number.values(), key=lambda item: item.courseNumber)
    return FacultyMissingReport(
        facultyId=faculty_id,
        missingCount=sum(
            1
            for program in document.get("programs") or []
            for group in program.get("requirementGroups") or []
            for ref in group.get("courseReferences") or []
            if not ref.get("titleHint") and ref.get("courseNumber")
        ),
        uniqueCourseNumbers=[entry.courseNumber for entry in entries],
        entries=entries,
    )


def _audit_faculty_worker(faculty_id: str) -> FacultyMissingReport:
    semester_numbers = _semester_json_numbers()
    wiki_index_numbers = _wiki_title_index_numbers()
    return _audit_faculty(
        faculty_id,
        semester_numbers=semester_numbers,
        wiki_index_numbers=wiki_index_numbers,
    )


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--workers",
        type=int,
        default=None,
        help=f"Process pool size (default: min(cpu, 8) = {default_worker_count(None)})",
    )
    parser.add_argument("--json", type=Path, help="Write full report JSON")
    args = parser.parse_args()

    faculty_ids = sorted(supported_export_faculties())
    reports = map_faculties_parallel(faculty_ids, _audit_faculty_worker, workers=args.workers)
    semester_numbers = _semester_json_numbers()
    wiki_index_numbers = _wiki_title_index_numbers()
    total_missing = sum(report.missingCount for report in reports)
    faculties_with_gaps = [report for report in reports if report.missingCount]

    summary = {
        "totalMissingRefs": total_missing,
        "facultiesWithGaps": len(faculties_with_gaps),
        "semesterJsonPresent": bool(semester_numbers),
        "semesterJsonCourseCount": len(semester_numbers),
        "wikiTitleIndexCount": len(wiki_index_numbers),
        "workers": default_worker_count(args.workers),
        "faculties": [
            {
                "facultyId": report.facultyId,
                "missingCount": report.missingCount,
                "uniqueCourseNumbers": report.uniqueCourseNumbers,
                "entries": [
                    {
                        "courseNumber": entry.courseNumber,
                        "inSemesterJson": entry.inSemesterJson,
                        "inWikiTitleIndex": entry.inWikiTitleIndex,
                        "programWikiPages": entry.programWikiPages,
                    }
                    for entry in report.entries
                ],
            }
            for report in reports
        ],
    }

    print(f"Missing titleHint refs: {total_missing} across {len(faculties_with_gaps)} faculties")
    for report in faculties_with_gaps:
        print(
            f"  {report.facultyId}: {report.missingCount} refs, "
            f"{len(report.uniqueCourseNumbers)} unique course numbers"
        )
    print(json.dumps(summary, indent=2, ensure_ascii=False))

    if args.json:
        args.json.write_text(json.dumps(summary, indent=2, ensure_ascii=False), encoding="utf-8")
        print(f"\nWrote {args.json}")

    return 1 if total_missing else 0


if __name__ == "__main__":
    raise SystemExit(main())
