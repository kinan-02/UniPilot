"""Generate Technion DDS retrieval benchmark cases from the catalog wiki vault."""

from __future__ import annotations

import argparse
import json
import re
from pathlib import Path
from typing import Any

from app.retrieval.evaluation.offering_benchmark import build_offering_cases

_COURSE_FILE = re.compile(r"^(?P<number>0\d{7,8})-", re.IGNORECASE)
_TITLE_HE = re.compile(r"^title_he:\s*(.+)$", re.MULTILINE)
_TITLE = re.compile(r'^title:\s*["\']?(.+?)["\']?\s*$', re.MULTILINE)

DDS_TRACKS = {
    "track-data-information-engineering": "DNE",
    "track-industrial-engineering-management": "IEM",
    "track-information-systems-engineering": "ISE",
}

HEBREW_QUERY_TEMPLATES = [
    "מה הקדם לקורס {number}?",
    "האם אפשר לקחת {number}?",
    "פרטים על קורס {number}",
    "דרישות קדם {number}",
]

EN_QUERY_TEMPLATES = [
    "What are the prerequisites for {number}?",
    "Tell me about course {number}",
    "Can I take {number} next semester?",
    "Course {number} requirements",
]

SEMANTIC_TOPICS = [
    ("database", "Find database courses in DDS"),
    ("machine learning", "DDS machine learning electives"),
    ("statistics", "statistics courses for data engineering track"),
    ("optimization", "operations research optimization courses"),
    ("NLP", "natural language processing DDS courses"),
    ("game theory", "game theory and economics DDS"),
    ("software", "software engineering DDS courses"),
    ("probability", "probability theory DDS required courses"),
]

REQUIREMENT_QUERIES = [
    (
        "requirement_explanation",
        "Explain DNE elective requirements",
        {"track": "track-data-information-engineering", "catalogYear": 2025},
        ["wiki:entities:tracks:track-data-information-engineering"],
    ),
    (
        "requirement_explanation",
        "מה דרישות הבחירה במסלול הנדסת נתונים ומידע?",
        {"track": "track-data-information-engineering", "catalogYear": 2025},
        ["wiki:entities:tracks:track-data-information-engineering"],
    ),
    (
        "catalog_requirement_lookup",
        "How many credits are required for IEM track?",
        {"track": "track-industrial-engineering-management", "catalogYear": 2025},
        ["wiki:entities:tracks:track-industrial-engineering-management"],
    ),
    (
        "catalog_requirement_lookup",
        "ISE track required courses list",
        {"track": "track-information-systems-engineering", "catalogYear": 2025},
        ["wiki:entities:tracks:track-information-systems-engineering"],
    ),
    (
        "requirement_explanation",
        "DDS faculty elective pool rules",
        {"track": "track-data-information-engineering", "catalogYear": 2025},
        ["wiki:entities:faculties:faculty-dds"],
    ),
    (
        "general_catalog_question",
        "What are focus chains in DDS?",
        {"catalogYear": 2025},
        ["wiki:concepts:focus-chains"],
    ),
    (
        "general_catalog_question",
        "מה זה שרשרת מיקוד בפקולטה לנתונים?",
        {"catalogYear": 2025},
        ["wiki:concepts:focus-chains"],
    ),
]


def _read_title(path: Path) -> tuple[str, str | None]:
    try:
        text = path.read_text(encoding="utf-8")
    except OSError:
        return path.stem, None
    he_match = _TITLE_HE.search(text)
    en_match = _TITLE.search(text)
    title = (en_match.group(1).strip() if en_match else path.stem).strip('"')
    title_he = he_match.group(1).strip() if he_match else None
    return title, title_he


def _course_number_from_path(path: Path) -> str | None:
    match = _COURSE_FILE.match(path.name)
    if not match:
        return None
    return match.group("number")


def _wiki_course_source(number: str) -> str:
    return f"wiki:course:{number}"


def _wiki_slug_source(relative: str) -> str:
    slug = relative.replace("/", ":").removesuffix(".md")
    return f"wiki:{slug}"


def generate_cases(*, wiki_root: Path, min_cases: int = 110) -> list[dict[str, Any]]:
    cases: list[dict[str, Any]] = []
    dds_dir = wiki_root / "courses" / "009-dds"
    course_files = sorted(dds_dir.glob("*.md")) if dds_dir.is_dir() else []

    for index, path in enumerate(course_files):
        number = _course_number_from_path(path)
        if not number:
            continue
        relative = str(path.relative_to(wiki_root))
        title, title_he = _read_title(path)

        template = EN_QUERY_TEMPLATES[index % len(EN_QUERY_TEMPLATES)]
        cases.append(
            {
                "id": f"dds_course_exact_en_{number}",
                "evalType": "wiki",
                "query": template.format(number=number),
                "intent": "course_question",
                "profile": "course_exact_lookup",
                "language": "en",
                "entities": {"courseNumber": number},
                "metadataContext": {
                    "track": "track-data-information-engineering",
                    "catalogYear": 2025,
                    "degreeProgram": "DDS",
                },
                "mustRetrieve": [_wiki_course_source(number)],
                "notes": f"DDS course exact lookup — {title}",
            }
        )

        if title_he and index % 3 == 0:
            he_template = HEBREW_QUERY_TEMPLATES[index % len(HEBREW_QUERY_TEMPLATES)]
            cases.append(
                {
                    "id": f"dds_course_exact_he_{number}",
                    "evalType": "wiki",
                    "query": he_template.format(number=number),
                    "intent": "course_question",
                    "profile": "course_exact_lookup",
                    "language": "he",
                    "entities": {"courseNumber": number},
                    "metadataContext": {"catalogYear": 2025},
                    "mustRetrieve": [_wiki_course_source(number)],
                    "notes": f"Hebrew DDS course query — {title_he}",
                }
            )

        if title and index % 5 == 0:
            cases.append(
                {
                    "id": f"dds_transcript_{number}",
                    "evalType": "wiki",
                    "query": f"Match transcript row {number} {title.split('—')[-1].strip()}",
                    "intent": "transcript_import",
                    "profile": "transcript_course_matching",
                    "language": "mixed",
                    "entities": {"courseNumber": number, "courseName": title.split("—")[-1].strip()[:40]},
                    "mustRetrieve": [_wiki_course_source(number)],
                    "notes": "Transcript fuzzy + exact number",
                }
            )

    for index, (topic, query) in enumerate(SEMANTIC_TOPICS):
        cases.append(
            {
                "id": f"dds_semantic_{index:03d}",
                "evalType": "wiki",
                "query": query,
                "intent": "catalog_search",
                "profile": "course_semantic_search",
                "language": "en",
                "entities": {"topic": topic, "targetSemesterCode": "2025-2"},
                "metadataContext": {
                    "track": "track-data-information-engineering",
                    "catalogYear": 2025,
                },
                "mustRetrieve": ["wiki:course:009"],
                "notes": f"Semantic discovery — {topic}",
            }
        )

    for index, (profile, query, metadata, must) in enumerate(REQUIREMENT_QUERIES):
        cases.append(
            {
                "id": f"dds_requirement_{index:03d}",
                "evalType": "wiki",
                "query": query,
                "intent": "graduation_progress_check" if "catalog" in profile else "requirement_explanation",
                "profile": profile,
                "language": "he" if any(ord(c) > 127 for c in query) else "en",
                "metadataContext": metadata,
                "mustRetrieve": must,
                "notes": "DDS requirement / track wiki retrieval",
            }
        )

    offering_candidates = [n for n in (_course_number_from_path(p) for p in course_files) if n]
    offering_numbers: list[str] = []
    for number in offering_candidates:
        if len(offering_numbers) >= 12:
            break
        if build_offering_cases([number]):
            offering_numbers.append(number)
    cases.extend(build_offering_cases(offering_numbers))

    cases.extend(
        [
            {
                "id": "dds_no_result_00000000",
                "evalType": "wiki",
                "query": "Course 00000000 prerequisites",
                "intent": "course_question",
                "profile": "course_exact_lookup",
                "language": "en",
                "entities": {"courseNumber": "00000000"},
                "mustRetrieve": [],
                "notes": "Unknown course should not return wiki hits",
            },
            {
                "id": "dds_planning_001",
                "evalType": "wiki",
                "query": "Build semester plan for DNE with no Friday classes",
                "intent": "semester_plan_generation",
                "profile": "semester_planning_retrieval",
                "language": "en",
                "entities": {"targetSemesterCode": "2025-2", "avoidDays": ["Friday"]},
                "metadataContext": {"track": "track-data-information-engineering", "catalogYear": 2025},
                "mustRetrieve": ["wiki:"],
                "notes": "Planning retrieval support",
            },
            {
                "id": "dds_fallback_001",
                "evalType": "wiki",
                "query": "Technion undergraduate academic regulations",
                "intent": "unknown_or_unsupported",
                "profile": "fallback_academic_search",
                "language": "en",
                "mustRetrieve": ["wiki:concepts:"],
                "notes": "Fallback academic search",
            },
        ]
    )

    if len(cases) < min_cases:
        raise RuntimeError(f"Generated only {len(cases)} cases; expected at least {min_cases}")

    return cases


def main() -> None:
    parser = argparse.ArgumentParser(description="Generate DDS retrieval benchmark JSONL")
    parser.add_argument(
        "--wiki-root",
        type=Path,
        default=Path("services/data-engineering/data/catalog_valut/catalog_valut/wiki"),
        help="Path to Obsidian wiki root",
    )
    parser.add_argument(
        "--output",
        type=Path,
        default=Path("services/api/app/retrieval/evaluation/benchmark_cases.jsonl"),
        help="Output JSONL path",
    )
    parser.add_argument("--min-cases", type=int, default=110)
    args = parser.parse_args()

    wiki_root = args.wiki_root.resolve()
    if not wiki_root.is_dir():
        raise SystemExit(f"Wiki root not found: {wiki_root}")

    cases = generate_cases(wiki_root=wiki_root, min_cases=args.min_cases)
    lines = [json.dumps(case, ensure_ascii=False) for case in cases]
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text("\n".join(lines) + "\n", encoding="utf-8")
    print(json.dumps({"caseCount": len(cases), "output": str(args.output)}, indent=2))


if __name__ == "__main__":
    main()
