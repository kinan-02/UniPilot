"""Deterministic academic lookups from the Obsidian wiki catalog."""

from __future__ import annotations

import re
from functools import lru_cache
from pathlib import Path
from typing import Any, Literal

from app.config import get_settings
from app.planning.prerequisite_resolver import canonical_course_number
from app.retrieval.wiki_paths import resolve_wiki_root
from app.services.wiki_lookup_parser import (
    build_track_code_index,
    find_course_wiki_page,
    find_regulations_page,
    find_track_wiki_page,
    parse_course_page,
    parse_non_regular_standing_section,
    parse_track_page,
    read_wiki_page,
    relative_wiki_path,
)

AcademicQueryKind = Literal[
    "course_catalog_prerequisites",
    "course_tracks_requiring",
    "course_compound_catalog",
    "course_eligibility",
    "track_credit_breakdown",
    "regulation_moed_grade",
    "regulation_standing_list",
    "unknown",
]

_TRACKS_REQUIRING_PATTERNS = (
    re.compile(r"\bwhich\s+(?:study\s+)?(?:tracks?|programs?)\s+(?:formally\s+)?require\b", re.I),
    re.compile(r"\btracks?\s+require\b", re.I),
    re.compile(r"\brequire(?:d)?\s+in\s+(?:which\s+)?tracks?\b", re.I),
    re.compile(r"\bwhich\s+tracks?\s+require\b", re.I),
    re.compile(r"\bwhere\s+is\b.+\bmandatory\b", re.I),
    re.compile(r"\bcount it as mandatory\b", re.I),
    re.compile(r"(באילו\s+מסלולים|אילו\s+מסלולי\s+לימוד).*(נדרש|חובה|מוגדר)", re.I),
    re.compile(r"מוגדר\s+כקורס\s+חובה", re.I),
)

_CATALOG_PREREQ_PATTERNS = (
    re.compile(r"\bwhat\s+are\s+the\s+prerequisites?\b", re.I),
    re.compile(r"\bprerequisites?\s+for\b", re.I),
    re.compile(r"\bprerequisite\s+(?:courses?|list)\b", re.I),
    re.compile(r"\blist the prerequisites?\b", re.I),
    re.compile(r"\bwhat courses? do i need before\b", re.I),
    re.compile(r"\bearlier courses? (?:are )?required\b", re.I),
    re.compile(r"(מהן|מהם)\s+דרישות\s+הקדם", re.I),
)

_ELIGIBILITY_PATTERNS = (
    re.compile(r"\bcan i take\b", re.I),
    re.compile(r"\bam i eligible\b", re.I),
    re.compile(r"\bam i allowed\b", re.I),
    re.compile(r"\bmissing prerequisites?\b", re.I),
    re.compile(r"(אפשר לקחת|זכאי)", re.I),
)

_TRACK_STRUCTURE_PATTERNS = (
    re.compile(r"\btrack code\b", re.I),
    re.compile(r"\bמסלול\b.*\b(נקודות|זכות)\b", re.I),
    re.compile(r"\b(total\s+)?credits?\b.*\b(graduat(?:e|ion)?|breakdown|category|categories)\b", re.I),
    re.compile(r"\bhow many credits\b.*\bgraduat(?:e|ion)?\b", re.I),
    re.compile(r"\bbroken down by category\b", re.I),
)

_MOED_GRADE_PATTERNS = (
    re.compile(r"\bmoed\s+a\b", re.I),
    re.compile(r"\bmoed\s+b\b", re.I),
    re.compile(r"\bfinal grade\b", re.I),
    re.compile(r"\bofficial final grade\b", re.I),
    re.compile(r"\bwhich grade counts\b", re.I),
    re.compile(r"(מועד\s*א|מועד\s*ב)", re.I),
)

_STANDING_LIST_PATTERNS = (
    re.compile(r"\bnon[- ]regular academic standing\b", re.I),
    re.compile(r"\bcomplete list\b", re.I),
    re.compile(r"\ball the conditions\b", re.I),
    re.compile(r"\bnon[- ]regular academic standing conditions\b", re.I),
    re.compile(r"\bמצב אקדמי לא תקין\b", re.I),
    re.compile(r"\bכל התנאים\b", re.I),
    re.compile(r"תנאים.*מצב אקדמי לא תקין", re.I),
)

_TRACK_CODE_CONTEXT = re.compile(r"\btrack code\b", re.I)
_TRACK_CODE_NUMBER = re.compile(r"\btrack code\s+(\d{5,6})\b", re.I)
_GENERIC_TRACK_NAME = re.compile(
    r"\b4[- ]year\s+general\s+computer\s+science\b|\bgeneral\s+cs\b.*\b4[- ]year\b",
    re.I,
)


def _matches(patterns: tuple[re.Pattern[str], ...], text: str) -> bool:
    return any(pattern.search(text) for pattern in patterns)


def resolve_wiki_root_from_settings() -> Path | None:
    configured = (get_settings().catalog_vault_wiki_path or "").strip()
    if not configured:
        return None
    return Path(resolve_wiki_root(configured))


@lru_cache(maxsize=1)
def _cached_track_code_index(wiki_root_str: str) -> dict[str, str]:
    return build_track_code_index(Path(wiki_root_str))


def course_by_code(course_number: str) -> dict[str, Any] | None:
    wiki_root = resolve_wiki_root_from_settings()
    if wiki_root is None:
        return None
    try:
        from app.agent.evaluation.wiki_eval_cache import cached_course_by_code, _course_path_index

        if str(wiki_root.resolve()) in _course_path_index:
            cached = cached_course_by_code(wiki_root, course_number)
            if cached is not None:
                return cached
    except Exception:  # noqa: BLE001
        pass
    path = find_course_wiki_page(wiki_root, course_number)
    if path is None:
        return None
    text = read_wiki_page(path)
    if not text:
        return None
    record = parse_course_page(text, source_path=relative_wiki_path(path, wiki_root))
    record["prerequisites"] = _enrich_prerequisite_labels(wiki_root, record.get("prerequisites") or [])
    return record


def _enrich_prerequisite_labels(wiki_root: Path, prerequisites: list[dict[str, str]]) -> list[dict[str, str]]:
    enriched: list[dict[str, str]] = []
    for item in prerequisites:
        code = item.get("courseNumber") or ""
        prereq_path = find_course_wiki_page(wiki_root, code)
        title_he = ""
        title_en = ""
        if prereq_path is not None:
            prereq_text = read_wiki_page(prereq_path)
            if prereq_text:
                parsed = parse_course_page(prereq_text, source_path=relative_wiki_path(prereq_path, wiki_root))
                title_he = str(parsed.get("titleHebrew") or "")
                title_en = str(parsed.get("title") or "")
        label_parts = [part for part in (title_he, title_en) if part]
        label = " — ".join(label_parts) if label_parts else item.get("label") or code
        enriched.append({"courseNumber": code, "label": label})
    return enriched


def course_prerequisites(course_number: str) -> list[dict[str, str]]:
    record = course_by_code(course_number)
    if not record:
        return []
    return list(record.get("prerequisites") or [])


def tracks_requiring_course(course_number: str) -> list[str]:
    record = course_by_code(course_number)
    if not record:
        return []
    return list(record.get("requiredTracks") or [])


def course_wiki_page_by_code(course_number: str) -> str | None:
    record = course_by_code(course_number)
    if not record:
        return None
    return record.get("sourceWikiPage")


def track_by_code_or_slug(identifier: str) -> dict[str, Any] | None:
    wiki_root = resolve_wiki_root_from_settings()
    if wiki_root is None:
        return None
    cleaned = identifier.strip().lower()
    slug: str | None = None
    if cleaned.startswith("track-"):
        slug = cleaned
    else:
        digits = re.sub(r"\D", "", cleaned)
        if digits:
            try:
                from app.agent.evaluation.wiki_eval_cache import cached_track_code_index

                index = cached_track_code_index(wiki_root)
            except Exception:  # noqa: BLE001
                index = _cached_track_code_index(str(wiki_root))
            slug = index.get(digits) or index.get(canonical_course_number(digits) or "")
    if not slug:
        return None
    try:
        from app.agent.evaluation.wiki_eval_cache import cached_track_by_slug, _course_path_index

        if str(wiki_root.resolve()) in _course_path_index:
            cached = cached_track_by_slug(wiki_root, slug)
            if cached is not None:
                return cached
    except Exception:  # noqa: BLE001
        pass
    path = find_track_wiki_page(wiki_root, slug)
    if path is None:
        return None
    text = read_wiki_page(path)
    if not text:
        return None
    return parse_track_page(text, source_path=relative_wiki_path(path, wiki_root))


def track_credit_breakdown(track_slug: str) -> dict[str, Any] | None:
    return track_by_code_or_slug(track_slug)


def regulation_concept_page() -> str | None:
    wiki_root = resolve_wiki_root_from_settings()
    if wiki_root is None:
        return None
    path = find_regulations_page(wiki_root)
    if path is None:
        return None
    return relative_wiki_path(path, wiki_root)


def classify_course_question_focus(user_message: str) -> str:
    text = (user_message or "").strip()
    wants_tracks = _matches(_TRACKS_REQUIRING_PATTERNS, text)
    wants_catalog_prereqs = _matches(_CATALOG_PREREQ_PATTERNS, text)
    wants_eligibility = _matches(_ELIGIBILITY_PATTERNS, text)

    if wants_tracks and wants_catalog_prereqs:
        return "compound_catalog"
    if wants_tracks:
        return "tracks_requiring"
    if wants_catalog_prereqs and not wants_eligibility:
        return "catalog_prerequisites"
    if wants_eligibility:
        return "eligibility"
    if _matches(_CATALOG_PREREQ_PATTERNS, text):
        return "catalog_prerequisites"
    return "general"


def detect_academic_query_kind(user_message: str) -> AcademicQueryKind:
    text = (user_message or "").strip()
    if not text:
        return "unknown"
    if _matches(_STANDING_LIST_PATTERNS, text):
        return "regulation_standing_list"
    if _matches(_MOED_GRADE_PATTERNS, text) and (
        re.search(r"\b\d{2,3}\b", text) or re.search(r"\bwhich grade counts\b", text, re.I)
    ):
        return "regulation_moed_grade"
    if _matches(_TRACK_STRUCTURE_PATTERNS, text):
        return "track_credit_breakdown"
    course_focus = classify_course_question_focus(text)
    if course_focus == "compound_catalog":
        return "course_compound_catalog"
    if course_focus == "tracks_requiring":
        return "course_tracks_requiring"
    if course_focus == "catalog_prerequisites":
        return "course_catalog_prerequisites"
    if course_focus == "eligibility":
        return "course_eligibility"
    return "unknown"


def resolve_track_identifier_from_message(message: str, entities: dict[str, Any]) -> str | None:
    if entities.get("trackSlug"):
        return str(entities["trackSlug"])
    if entities.get("trackCode"):
        return str(entities["trackCode"])
    text = message or ""
    code_match = _TRACK_CODE_NUMBER.search(text)
    if code_match:
        return code_match.group(1)
    if _GENERIC_TRACK_NAME.search(text):
        return "track-computer-science-general-4year"
    return None


def compose_course_catalog_answer(course_number: str, *, include_prerequisites: bool, include_tracks: bool) -> tuple[str, list[str]]:
    record = course_by_code(course_number)
    if not record:
        return f"Course {course_number} was not found in the catalog wiki.", []

    sources = [str(record.get("sourceWikiPage") or "")]
    title = str(record.get("title") or course_number)
    title_he = str(record.get("titleHebrew") or "")
    credits = record.get("credits")
    level = record.get("level") or "undergraduate"
    parts = [f"Course code: {course_number}"]
    if title_he:
        parts.append(f"Hebrew name: {title_he}")
    parts.append(
        f"{title} ({course_number}{f' / {title_he}' if title_he else ''}) is a {credits}-credit {level} course."
    )

    if include_prerequisites:
        prereqs = record.get("prerequisites") or []
        if prereqs:
            lines = []
            for index, item in enumerate(prereqs, start=1):
                code = item.get("courseNumber") or ""
                label = item.get("label") or ""
                lines.append(f"Prerequisite {index}: {code} — {label}" if label else f"Prerequisite {index}: {code}")
            parts.append("Prerequisites:\n" + "\n".join(lines))
        else:
            parts.append("Prerequisites: none listed in the catalog.")

    if include_tracks:
        tracks = record.get("requiredTracks") or []
        faculty = str(record.get("faculty") or "")
        if tracks:
            lines = [f"Required in track: {slug}" for slug in tracks]
            parts.append(
                f"It is required in {len(tracks)} tracks:\n" + "\n".join(lines)
            )
            parts.append(f"Total tracks requiring this course: {len(tracks)}")
            if faculty and faculty != "faculty-computer-science":
                has_cs = any(slug.startswith("track-computer-science") or slug == "track-cs-physics" for slug in tracks)
                has_education = any(slug.startswith("track-education-") for slug in tracks)
                if has_cs and has_education:
                    parts.append(
                        f"This course is filed under {faculty} but is also required by Computer Science and Education tracks."
                    )
        else:
            parts.append("No tracks list this course as required in the catalog wiki.")

    return "\n\n".join(parts), [source for source in sources if source]


def compose_tracks_requiring_answer(course_number: str) -> tuple[str, list[str]]:
    return compose_course_catalog_answer(course_number, include_prerequisites=False, include_tracks=True)


def compose_track_credit_breakdown_answer(track_identifier: str) -> tuple[str, list[str]]:
    record = track_by_code_or_slug(track_identifier)
    if not record:
        return f"I could not find track information for {track_identifier}.", []

    source = str(record.get("sourceWikiPage") or "")
    title = record.get("title") or record.get("trackSlug")
    total = record.get("totalCredits")
    required = record.get("requiredCourseCredits")
    faculty = record.get("facultyElectiveCredits")
    technion = record.get("technionWideElectiveCredits")
    enrichment = record.get("enrichmentMinimumCredits")
    pe = record.get("peMinimumCredits")
    duration = record.get("duration")
    degree = record.get("degree")
    faculty_slug = record.get("faculty")
    program_code = record.get("trackCode")

    if total is None:
        return f"I could not determine the total credit requirement for {title}.", [source] if source else []

    parts = [f"The {title} requires {total} credits:"]
    if required is not None:
        parts.append(f"- Required courses (מקצועות חובה): {required}")
    if faculty is not None:
        parts.append(f"- Faculty electives (מקצועות בחירה פקולטית): {faculty}")
    if technion is not None:
        parts.append(f"- Technion-wide electives (מקצועות בחירה כלל-טכניונית): {technion}")
    if required is not None and faculty is not None and technion is not None:
        parts.append(f"{required} + {faculty} + {technion} = {total}")
    if program_code:
        parts.append(f"Program code: {program_code}.")
    technion_bits = []
    if enrichment is not None:
        technion_bits.append(f"at least {int(enrichment)} enrichment credits")
    if pe is not None:
        technion_bits.append(f"at least {int(pe)} PE credits")
    if technion_bits:
        parts.append(
            "The Technion-wide block includes " + " and ".join(technion_bits) + "."
        )
    if duration:
        parts.append(f"Duration: {duration}.")
    if degree:
        parts.append(f"Degree: {degree}.")
    if faculty_slug:
        parts.append(f"Faculty: {faculty_slug}.")

    return "\n".join(parts), [source] if source else []


def compose_regulation_moed_answer(user_message: str) -> tuple[str, list[str]]:
    grades = [int(value) for value in re.findall(r"\b(\d{2,3})\b", user_message or "")]
    # Expect Moed A then Moed B when two grades present
    moed_a = grades[0] if grades else None
    moed_b = grades[1] if len(grades) > 1 else None
    final_grade = moed_b if moed_b is not None else moed_a
    if final_grade is None:
        return "", []

    source = regulation_concept_page() or "wiki/concepts/regulations-undergraduate.md"
    parts = [
        f"Your official final grade is {final_grade}.",
        (
            "Under the last-grade rule (Section 5.3 / תקנה 3.1.3), the last exam grade is the "
            "determining grade even when it is lower than an earlier attempt."
        ),
    ]
    if moed_a is not None and moed_b is not None and final_grade == moed_b:
        parts.append(f"The {moed_a} from Moed A no longer determines the official course grade.")
    if final_grade >= 55:
        parts.append(f"Since {final_grade} is at least 55, the course is still passing.")
    else:
        parts.append(f"Since {final_grade} is below 55, the course is not passing.")
    parts.append("Both Moed A and Moed B grades count in cumulative GPA calculations.")
    return " ".join(parts), [source]


def compose_non_regular_standing_answer() -> tuple[str, list[str]]:
    wiki_root = resolve_wiki_root_from_settings()
    if wiki_root is None:
        return "", []
    path = find_regulations_page(wiki_root)
    if path is None:
        return "", []
    text = read_wiki_page(path)
    if not text:
        return "", []
    conditions = parse_non_regular_standing_section(text)
    source = relative_wiki_path(path, wiki_root)
    if not conditions:
        return "", [source]

    lines = [
        "A student enters non-regular academic standing if any one of the following "
        f"{len(conditions)} conditions applies (OR logic — any single condition is sufficient):"
    ]
    for row in conditions:
        lines.append(f"{row['number']}. {row['text']}")
    lines.append("Regulation reference: Section 5.6 / תקנה 3.1.5.")
    lines.append(
        "Process after trigger: faculty advising invitation → faculty recommendation to Dean → student may appeal."
    )
    return "\n".join(lines), [source]


def try_compose_deterministic_answer(
    user_message: str,
    *,
    entities: dict[str, Any] | None = None,
) -> tuple[str, list[str]] | None:
    """Return (text, wiki_sources) when a deterministic wiki-grounded answer is available."""
    entities = dict(entities or {})
    kind = detect_academic_query_kind(user_message)

    if kind == "regulation_standing_list":
        text, sources = compose_non_regular_standing_answer()
        return (text, sources) if text else None
    if kind == "regulation_moed_grade":
        text, sources = compose_regulation_moed_answer(user_message)
        return (text, sources) if text else None
    if kind == "track_credit_breakdown":
        track_id = resolve_track_identifier_from_message(user_message, entities)
        if not track_id:
            return None
        text, sources = compose_track_credit_breakdown_answer(track_id)
        return (text, sources) if text else None

    course_number = str(entities.get("courseNumber") or "").strip()
    if not course_number:
        return None

    if kind == "course_compound_catalog":
        return compose_course_catalog_answer(course_number, include_prerequisites=True, include_tracks=True)
    if kind == "course_tracks_requiring":
        return compose_tracks_requiring_answer(course_number)
    if kind == "course_catalog_prerequisites":
        return compose_course_catalog_answer(course_number, include_prerequisites=True, include_tracks=False)
    return None
