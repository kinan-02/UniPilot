"""Wiki-driven elective-chain enrichment for non-DDS faculties (Phase D specialized export)."""

from __future__ import annotations

import re
from typing import Any

from app.utils.course_numbers import collect_course_numbers_from_text
from app.vault.export_dds_catalog import (
    _course_pool_group,
    _table_course_refs,
    build_course_reference,
    parse_credits_value,
)
from app.vault.loader import WikiPage
from app.vault.markdown_tables import find_table_with_header, parse_markdown_tables

_SPECIALIZATION_MARKERS: tuple[str, ...] = (
    "### Specialization Groups",
    "## Specialization Groups",
    "Specialization Groups (",
)

_SPEC_HEADER = re.compile(
    r"^(?:###\s+|\*\*)(\d+)\.\s+(.+?)(?:\*\*)?\s*$",
    re.MULTILINE,
)
_MANDATORY_LINE = re.compile(r"Mandatory[^:]*:\s*(.+)$", re.IGNORECASE | re.MULTILINE)
_MINIMUM_COURSES_LINE = re.compile(
    r"(?:Minimum courses|Single group):\s*(\d+)",
    re.IGNORECASE,
)
_GROUP_HEADER = re.compile(r"^(?:###\s+)?Group\s+(\d+)\b", re.IGNORECASE | re.MULTILINE)
_HEBREW_LIST_HEADER = re.compile(
    r"^#{2,4}\s+.*רשימה\s+([א-ה]|\d+)\b",
    re.MULTILINE,
)
_HEBREW_GROUP_HEADER = re.compile(r"^####\s+קבוצה\s+([א-ה]|\d+)\b", re.MULTILINE)
_CLUSTER_HEADER = re.compile(r"^###\s+Cluster\s+(\d+)\s*:", re.MULTILINE | re.IGNORECASE)
_NAMED_GROUP_HEADER = re.compile(r"^\*\*Group\s+(\d+)\s+—", re.MULTILINE | re.IGNORECASE)
_BOLD_NUMBERED_LIST_HEADER = re.compile(
    r"^\*\*List\s+(\d+)\s+—",
    re.MULTILINE | re.IGNORECASE,
)
_TRACK_COLON_HEADER = re.compile(r"^###\s+Track:\s+(.+)$", re.MULTILINE)
_TRACK_LETTER_HEADER = re.compile(r"^###\s+Track\s+([A-Z])\s+—", re.MULTILINE)
_BIOTECH_CLUSTER_MARKER = re.compile(
    r"^\*\*(Theory Cluster|Experience and Research Cluster)[^*]*\*\*",
    re.MULTILINE | re.IGNORECASE,
)
_HEBREW_ELECTIVE_SECTION_MARKERS: tuple[str, ...] = (
    "## מקצועות בחירה",
    "## מקצועות בחירה מומלצים",
)
_HEBREW_SUBSECTION_HEADER = re.compile(r"^###\s+(.+)$", re.MULTILINE)
_SPECIALIZATION_TRACK_HEADER = re.compile(
    r"^###\s+Specialization\s+(\d+)\s+—\s+(.+)$",
    re.MULTILINE,
)
_ELECTIVES_SECTION_MARKER = re.compile(r"\*\*Electives\b", re.IGNORECASE)
_BOLD_LIST_HEADER = re.compile(
    r"^\s*(?:-\s+)?\*\*List\s+([A-Z]\d?)\s+\(רשימה",
    re.MULTILINE | re.IGNORECASE,
)
_CHOOSE_N_TABLE_SUFFIXES = frozenset(
    {
        "lab-courses-pool",
        "faculty-elective-list-pool",
        "required-elective-list-pool",
    }
)

_FACULTY_POOL_PREFIX: dict[str, str] = {
    "electrical-computer-engineering": "ece",
    "civil-environmental-engineering": "civil",
    "mechanical-engineering": "mech",
    "chemical-engineering": "chem",
    "aerospace-engineering": "aero",
    "biomedical-engineering": "bme",
    "biotechnology-food-engineering": "biotech",
    "materials-science-engineering": "matsci",
    "mathematics": "math",
    "physics": "physics",
    "chemistry": "chemistry",
    "biology": "biology",
    "medicine": "medicine",
    "education-science-technology": "edu",
    "architecture-town-planning": "arch",
}

_TABLE_SECTION_MARKERS: tuple[tuple[str, str, str], ...] = (
    ("## Lab Courses", "lab-courses-pool", "Lab courses elective pool"),
    (
        "## Faculty Elective Courses",
        "faculty-elective-list-pool",
        "Faculty elective courses pool",
    ),
    (
        "## Faculty Elective Requirements",
        "faculty-elective-list-pool",
        "Faculty elective requirements pool",
    ),
    (
        "## Elective Requirements",
        "faculty-elective-list-pool",
        "Elective requirements pool",
    ),
    (
        "### רשימת מקצועות חובה/בחירה",
        "required-elective-list-pool",
        "Required/elective course list pool",
    ),
    (
        "## Scientific Course Requirements",
        "science-elective-chain",
        "Scientific course requirement chain",
    ),
)


def faculty_pool_prefix(faculty_id: str) -> str:
    return _FACULTY_POOL_PREFIX.get(faculty_id, faculty_id.split("-")[0][:12])


def _refs_for_numbers(numbers: tuple[str, ...], *, source_page) -> list[dict[str, Any]]:
    refs: list[dict[str, Any]] = []
    seen: set[str] = set()
    for number in numbers:
        ref = build_course_reference(number, source_page=source_page)
        if ref is None:
            continue
        course_number = str(ref.get("courseNumber") or "")
        if course_number in seen:
            continue
        seen.add(course_number)
        refs.append(ref)
    return refs


def _specialization_section(english: str) -> str:
    start = -1
    for marker in _SPECIALIZATION_MARKERS:
        pos = english.find(marker)
        if pos >= 0 and (start < 0 or pos < start):
            start = pos
    if start < 0:
        return ""

    for end_marker in ("## Faculty Elective", "## Lab Courses", "## Special Rules", "## נתונים בעברית"):
        end = english.find(end_marker, start + 1)
        if end >= 0:
            return english[start:end]
    return english[start:]


def _parse_choose_count(block: str, *, default: int = 3) -> int:
    match = _MINIMUM_COURSES_LINE.search(block)
    if match:
        return int(match.group(1))
    return default


def _parse_specialization_groups(
    section: str,
    *,
    program_code: str,
    page: WikiPage,
    faculty_id: str,
) -> list[dict[str, Any]]:
    matches = list(_SPEC_HEADER.finditer(section))
    if not matches:
        return []

    prefix = faculty_pool_prefix(faculty_id)
    groups: list[dict[str, Any]] = []
    for index, match in enumerate(matches):
        group_number = int(match.group(1))
        title = match.group(2).strip()
        block_start = match.end()
        block_end = matches[index + 1].start() if index + 1 < len(matches) else len(section)
        block = section[block_start:block_end]
        mandatory_match = _MANDATORY_LINE.search(block)
        mandatory_note = mandatory_match.group(1).strip() if mandatory_match else None
        numbers = collect_course_numbers_from_text(block)
        refs = _refs_for_numbers(tuple(numbers), source_page=page.path)
        choose_count = _parse_choose_count(block)
        notes = [
            "Faculty specialization group; choose-N semantics encoded as non-executable pool.",
        ]
        if mandatory_note:
            notes.append(f"Mandatory: {mandatory_note}")
        description = (
            f"Specialization group {group_number} — {title}. "
            f"Complete {choose_count} distinct courses from this pool."
        )
        if mandatory_note:
            description += f" Mandatory: {mandatory_note}."
        groups.append(
            _course_pool_group(
                program_code=program_code,
                group_suffix=f"{prefix}-spec-group-{group_number:02d}",
                title=f"{prefix.upper()} specialization group {group_number}: {title}",
                course_refs=refs,
                rule_expression={
                    "type": "course_pool",
                    "operator": "choose_n",
                    "chooseCount": choose_count,
                    "group": group_number,
                },
                catalog_description=description,
                notes=notes,
            )
        )
    return groups


def _section_slice(english: str, marker: str) -> str:
    start = english.find(marker)
    if start < 0:
        return ""
    end_candidates = [
        english.find(other, start + len(marker))
        for other in (
            "## Faculty Elective",
            "## Lab Courses",
            "## Special Rules",
            "## Credit",
            "## נתונים בעברית",
            "## Continuation",
        )
        if english.find(other, start + len(marker)) >= 0
    ]
    end = min(end_candidates) if end_candidates else len(english)
    return english[start:end]


def _table_pool_from_section(
    section: str,
    *,
    page: WikiPage,
    program_code: str,
    group_suffix: str,
    title: str,
    operator: str,
    choose_count: int | None = None,
    catalog_description: str | None = None,
) -> dict[str, Any] | None:
    if not section.strip():
        return None

    refs: list[dict[str, Any]] = []
    for table in parse_markdown_tables(section):
        refs.extend(_table_course_refs(page, table))
    if not refs:
        numbers = collect_course_numbers_from_text(section)
        refs = _refs_for_numbers(tuple(numbers), source_page=page.path)
    if not refs:
        return None

    rule_expression: dict[str, Any] = {"type": "course_pool", "operator": operator}
    if operator == "choose_chain":
        rule_expression["chooseCount"] = choose_count or 1
        rule_expression["chain"] = group_suffix
    elif operator == "choose_n":
        rule_expression["chooseCount"] = choose_count or 3

    return _course_pool_group(
        program_code=program_code,
        group_suffix=group_suffix,
        title=title,
        course_refs=refs,
        rule_expression=rule_expression,
        catalog_description=catalog_description or title,
        notes=["Parsed deterministically from wiki elective section."],
    )


def _table_section_pools(
    page: WikiPage,
    program_code: str,
    *,
    faculty_id: str,
) -> list[dict[str, Any]]:
    english = page.english_body
    prefix = faculty_pool_prefix(faculty_id)
    groups: list[dict[str, Any]] = []

    for marker, suffix_tail, title in _TABLE_SECTION_MARKERS:
        section = _section_slice(english, marker)
        if not section:
            continue
        operator = "choose_chain" if "science" in suffix_tail else "min_credits"
        choose_count: int | None = 1 if operator == "choose_chain" else None
        if suffix_tail in _CHOOSE_N_TABLE_SUFFIXES:
            operator = "choose_n"
            choose_count = 1
        pool = _table_pool_from_section(
            section,
            page=page,
            program_code=program_code,
            group_suffix=f"{prefix}-{suffix_tail}",
            title=title,
            operator=operator,
            choose_count=choose_count,
            catalog_description=title,
        )
        if pool is not None:
            groups.append(pool)
    return groups


def _hebrew_list_source(page: WikiPage) -> str:
    """Use one wiki body slice — english_body is a prefix of body and must not be doubled."""
    if _HEBREW_LIST_HEADER.search(page.english_body or ""):
        return page.english_body
    return page.body


def _wiki_elective_body(page: WikiPage, header_pattern: re.Pattern[str]) -> str:
    if header_pattern.search(page.english_body or ""):
        return page.english_body
    return page.body


def _dedupe_pool_groups(groups: list[dict[str, Any]]) -> list[dict[str, Any]]:
    best: dict[str, dict[str, Any]] = {}
    for group in groups:
        group_id = str(group.get("groupId") or "")
        if not group_id:
            continue
        existing = best.get(group_id)
        if existing is None or len(group.get("courseReferences") or []) > len(
            existing.get("courseReferences") or []
        ):
            best[group_id] = group
    return list(best.values())


def _slugify_label(label: str) -> str:
    slug = re.sub(r"[^a-z0-9]+", "-", label.lower()).strip("-")
    return slug[:48] or "section"


def _elective_subsection_slug(title: str, *, index: int) -> str:
    paren_match = re.match(r"^\(([א-הa-z0-9]+)\)", title.strip())
    if paren_match:
        return paren_match.group(1).lower()
    slug = _slugify_label(title.split("—")[0].split("(")[0])
    if slug and slug != "section":
        return slug
    return f"subsection-{index + 1:02d}"


def _hebrew_list_pools(page: WikiPage, program_code: str, *, faculty_id: str) -> list[dict[str, Any]]:
    body = _hebrew_list_source(page)
    prefix = faculty_pool_prefix(faculty_id)
    groups: list[dict[str, Any]] = []
    matches = list(_HEBREW_LIST_HEADER.finditer(body))
    for index, match in enumerate(matches):
        letter = match.group(1)
        slice_start = match.start()
        slice_end = matches[index + 1].start() if index + 1 < len(matches) else len(body)
        section = body[slice_start:slice_end]
        pool = _table_pool_from_section(
            section,
            page=page,
            program_code=program_code,
            group_suffix=f"{prefix}-elective-list-{letter}-pool",
            title=f"{prefix.upper()} elective list {letter}",
            operator="choose_n",
            choose_count=1,
            catalog_description=f"Faculty elective list {letter} from the track catalog.",
        )
        if pool is not None:
            groups.append(pool)
    return groups


def _hebrew_group_pools(page: WikiPage, program_code: str, *, faculty_id: str) -> list[dict[str, Any]]:
    body = _wiki_elective_body(page, _HEBREW_GROUP_HEADER)
    prefix = faculty_pool_prefix(faculty_id)
    groups: list[dict[str, Any]] = []
    matches = list(_HEBREW_GROUP_HEADER.finditer(body))
    for index, match in enumerate(matches):
        label = match.group(1)
        slice_start = match.start()
        slice_end = matches[index + 1].start() if index + 1 < len(matches) else len(body)
        section = body[slice_start:slice_end]
        pool = _table_pool_from_section(
            section,
            page=page,
            program_code=program_code,
            group_suffix=f"{prefix}-hebrew-group-{label}-pool",
            title=f"{prefix.upper()} Hebrew elective group {label}",
            operator="choose_n",
            choose_count=1,
            catalog_description=f"Hebrew elective group {label} from the track catalog.",
        )
        if pool is not None:
            groups.append(pool)
    return groups


def _specialization_track_elective_pools(
    page: WikiPage,
    program_code: str,
    *,
    faculty_id: str,
) -> list[dict[str, Any]]:
    body = page.english_body
    prefix = faculty_pool_prefix(faculty_id)
    groups: list[dict[str, Any]] = []
    matches = list(_SPECIALIZATION_TRACK_HEADER.finditer(body))
    for index, match in enumerate(matches):
        spec_number = int(match.group(1))
        title = match.group(2).strip()
        slice_start = match.start()
        slice_end = matches[index + 1].start() if index + 1 < len(matches) else len(body)
        section = body[slice_start:slice_end]
        elective_marker = _ELECTIVES_SECTION_MARKER.search(section)
        if elective_marker is None:
            continue
        elective_section = section[elective_marker.start() :]
        next_break = re.search(
            r"^###\s+|^##\s+|\*\*Mandatory|\*\*Projects",
            elective_section[10:],
            re.MULTILINE,
        )
        if next_break is not None:
            elective_section = elective_section[: 10 + next_break.start()]
        pool = _table_pool_from_section(
            elective_section,
            page=page,
            program_code=program_code,
            group_suffix=f"{prefix}-spec-{spec_number}-elective-pool",
            title=f"{prefix.upper()} specialization {spec_number} electives",
            operator="choose_n",
            choose_count=2,
            catalog_description=f"Elective pool for specialization {spec_number} ({title}).",
        )
        if pool is not None:
            groups.append(pool)
    return groups


def _bold_list_pools(page: WikiPage, program_code: str, *, faculty_id: str) -> list[dict[str, Any]]:
    body = page.english_body
    prefix = faculty_pool_prefix(faculty_id)
    groups: list[dict[str, Any]] = []
    matches = list(_BOLD_LIST_HEADER.finditer(body))
    for index, match in enumerate(matches):
        label = match.group(1).lower()
        slice_start = match.start()
        slice_end = matches[index + 1].start() if index + 1 < len(matches) else len(body)
        section = body[slice_start:slice_end]
        pool = _table_pool_from_section(
            section,
            page=page,
            program_code=program_code,
            group_suffix=f"{prefix}-list-{label}-pool",
            title=f"{prefix.upper()} elective list {label.upper()}",
            operator="choose_n",
            choose_count=1,
            catalog_description=f"Faculty elective list {label.upper()} from the track catalog.",
        )
        if pool is not None:
            groups.append(pool)
    return groups


def _cluster_elective_pools(
    page: WikiPage,
    program_code: str,
    *,
    faculty_id: str,
) -> list[dict[str, Any]]:
    body = page.english_body
    prefix = faculty_pool_prefix(faculty_id)
    groups: list[dict[str, Any]] = []
    matches = list(_CLUSTER_HEADER.finditer(body))
    for index, match in enumerate(matches):
        cluster_number = int(match.group(1))
        slice_start = match.start()
        slice_end = matches[index + 1].start() if index + 1 < len(matches) else len(body)
        section = body[slice_start:slice_end]
        pool = _table_pool_from_section(
            section,
            page=page,
            program_code=program_code,
            group_suffix=f"{prefix}-cluster-{cluster_number}-elective-pool",
            title=f"{prefix.upper()} elective cluster {cluster_number}",
            operator="choose_n",
            choose_count=1,
            catalog_description=f"Faculty elective cluster {cluster_number} from the track catalog.",
        )
        if pool is not None:
            groups.append(pool)
    return groups


def _named_group_pools(page: WikiPage, program_code: str, *, faculty_id: str) -> list[dict[str, Any]]:
    body = page.english_body
    prefix = faculty_pool_prefix(faculty_id)
    groups: list[dict[str, Any]] = []
    matches = list(_NAMED_GROUP_HEADER.finditer(body))
    for index, match in enumerate(matches):
        group_number = int(match.group(1))
        slice_start = match.start()
        slice_end = matches[index + 1].start() if index + 1 < len(matches) else len(body)
        section = body[slice_start:slice_end]
        pool = _table_pool_from_section(
            section,
            page=page,
            program_code=program_code,
            group_suffix=f"{prefix}-elective-group-{group_number}-pool",
            title=f"{prefix.upper()} elective group {group_number}",
            operator="choose_n",
            choose_count=2,
            catalog_description=f"Faculty elective group {group_number} from the track catalog.",
        )
        if pool is not None:
            groups.append(pool)
    return groups


def _bold_numbered_list_pools(
    page: WikiPage,
    program_code: str,
    *,
    faculty_id: str,
) -> list[dict[str, Any]]:
    body = page.english_body
    prefix = faculty_pool_prefix(faculty_id)
    groups: list[dict[str, Any]] = []
    track_matches = list(_TRACK_COLON_HEADER.finditer(body))
    if track_matches:
        for track_index, track_match in enumerate(track_matches):
            track_title = track_match.group(1).strip()
            track_slug = _slugify_label(track_title)
            track_start = track_match.start()
            track_end = (
                track_matches[track_index + 1].start()
                if track_index + 1 < len(track_matches)
                else len(body)
            )
            track_section = body[track_start:track_end]
            list_matches = list(_BOLD_NUMBERED_LIST_HEADER.finditer(track_section))
            for list_index, list_match in enumerate(list_matches):
                list_number = int(list_match.group(1))
                slice_start = list_match.start()
                slice_end = (
                    list_matches[list_index + 1].start()
                    if list_index + 1 < len(list_matches)
                    else len(track_section)
                )
                section = track_section[slice_start:slice_end]
                pool = _table_pool_from_section(
                    section,
                    page=page,
                    program_code=program_code,
                    group_suffix=f"{prefix}-track-{track_slug}-list-{list_number}-pool",
                    title=f"{prefix.upper()} {track_title} list {list_number}",
                    operator="choose_n",
                    choose_count=1,
                    catalog_description=(
                        f"Faculty elective list {list_number} for track {track_title}."
                    ),
                )
                if pool is not None:
                    groups.append(pool)
        return groups

    matches = list(_BOLD_NUMBERED_LIST_HEADER.finditer(body))
    for index, match in enumerate(matches):
        list_number = int(match.group(1))
        slice_start = match.start()
        slice_end = matches[index + 1].start() if index + 1 < len(matches) else len(body)
        section = body[slice_start:slice_end]
        pool = _table_pool_from_section(
            section,
            page=page,
            program_code=program_code,
            group_suffix=f"{prefix}-list-{list_number}-pool",
            title=f"{prefix.upper()} elective list {list_number}",
            operator="choose_n",
            choose_count=1,
            catalog_description=f"Faculty elective list {list_number} from the track catalog.",
        )
        if pool is not None:
            groups.append(pool)
    return groups


def _elective_subsection_pools(
    page: WikiPage,
    program_code: str,
    *,
    faculty_id: str,
) -> list[dict[str, Any]]:
    """Parse ### subsections under ## Elective Requirements (architecture-style)."""
    english = page.english_body
    section = _section_slice(english, "## Elective Requirements")
    if not section:
        return []

    prefix = faculty_pool_prefix(faculty_id)
    groups: list[dict[str, Any]] = []
    matches = list(_HEBREW_SUBSECTION_HEADER.finditer(section))
    for index, match in enumerate(matches):
        title = match.group(1).strip()
        subsection_slug = _elective_subsection_slug(title, index=index)
        slice_start = match.start()
        slice_end = matches[index + 1].start() if index + 1 < len(matches) else len(section)
        subsection = section[slice_start:slice_end]
        pool = _table_pool_from_section(
            subsection,
            page=page,
            program_code=program_code,
            group_suffix=f"{prefix}-elective-{subsection_slug}-pool",
            title=f"{prefix.upper()} {title}",
            operator="choose_n",
            choose_count=1,
            catalog_description=f"Elective subsection: {title}.",
        )
        if pool is not None:
            groups.append(pool)
    return groups


def _hebrew_elective_section_pools(
    page: WikiPage,
    program_code: str,
    *,
    faculty_id: str,
) -> list[dict[str, Any]]:
    """Parse Hebrew ## מקצועות בחירה subsections (chemistry-style)."""
    body = page.body
    prefix = faculty_pool_prefix(faculty_id)
    groups: list[dict[str, Any]] = []

    for marker in _HEBREW_ELECTIVE_SECTION_MARKERS:
        start = body.find(marker)
        if start < 0:
            continue
        end_candidates = [
            body.find(other, start + len(marker))
            for other in ("## Special Rules", "## נתונים בעברית", "## Credit Summary")
            if body.find(other, start + len(marker)) >= 0
        ]
        end = min(end_candidates) if end_candidates else len(body)
        section = body[start:end]
        matches = list(_HEBREW_SUBSECTION_HEADER.finditer(section))
        for index, match in enumerate(matches):
            title = match.group(1).strip()
            subsection_slug = _elective_subsection_slug(title, index=index)
            slice_start = match.start()
            slice_end = matches[index + 1].start() if index + 1 < len(matches) else len(section)
            subsection = section[slice_start:slice_end]
            pool = _table_pool_from_section(
                subsection,
                page=page,
                program_code=program_code,
                group_suffix=f"{prefix}-hebrew-elective-{subsection_slug}-pool",
                title=f"{prefix.upper()} {title}",
                operator="choose_n",
                choose_count=1,
                catalog_description=f"Hebrew elective subsection: {title}.",
            )
            if pool is not None:
                groups.append(pool)
    return groups


def _biotech_track_cluster_pools(
    page: WikiPage,
    program_code: str,
    *,
    faculty_id: str,
) -> list[dict[str, Any]]:
    body = page.english_body
    prefix = faculty_pool_prefix(faculty_id)
    groups: list[dict[str, Any]] = []
    track_matches = list(_TRACK_LETTER_HEADER.finditer(body))
    for track_index, track_match in enumerate(track_matches):
        track_letter = track_match.group(1).lower()
        track_start = track_match.start()
        track_end = (
            track_matches[track_index + 1].start()
            if track_index + 1 < len(track_matches)
            else len(body)
        )
        track_section = body[track_start:track_end]
        cluster_matches = list(_BIOTECH_CLUSTER_MARKER.finditer(track_section))
        for cluster_index, cluster_match in enumerate(cluster_matches):
            cluster_name = cluster_match.group(1).lower().replace(" ", "-")
            slice_start = cluster_match.start()
            slice_end = (
                cluster_matches[cluster_index + 1].start()
                if cluster_index + 1 < len(cluster_matches)
                else len(track_section)
            )
            subsection = track_section[slice_start:slice_end]
            choose_count = 3 if "theory" in cluster_name else 2
            pool = _table_pool_from_section(
                subsection,
                page=page,
                program_code=program_code,
                group_suffix=f"{prefix}-track-{track_letter}-{cluster_name}-pool",
                title=f"{prefix.upper()} track {track_letter.upper()} {cluster_match.group(1)}",
                operator="choose_n",
                choose_count=choose_count,
                catalog_description=(
                    f"Biotech track {track_letter.upper()} {cluster_match.group(1)} elective pool."
                ),
            )
            if pool is not None:
                groups.append(pool)
    return groups


def _group_n_pools(page: WikiPage, program_code: str, *, faculty_id: str) -> list[dict[str, Any]]:
    english = page.english_body
    prefix = faculty_pool_prefix(faculty_id)
    groups: list[dict[str, Any]] = []

    for match in _GROUP_HEADER.finditer(english):
        group_number = int(match.group(1))
        slice_start = match.start()
        next_group = _GROUP_HEADER.search(english, match.end())
        slice_end = next_group.start() if next_group else len(english)
        section = english[slice_start:slice_end]
        table = find_table_with_header(section, "Code")
        if table is None:
            continue
        refs = _table_course_refs(page, table)
        if not refs:
            continue
        groups.append(
            _course_pool_group(
                program_code=program_code,
                group_suffix=f"{prefix}-group-{group_number}-elective-chain",
                title=f"{prefix.upper()} elective group {group_number}",
                course_refs=refs,
                rule_expression={
                    "type": "course_pool",
                    "operator": "choose_n",
                    "chooseCount": 1,
                    "chain": f"group_{group_number}",
                },
                catalog_description=(
                    f"Elective group {group_number} from the faculty catalog; "
                    "complete the chain requirements from the wiki track page."
                ),
                notes=["Group-N choose chain semantics preserved as advisory pool."],
            )
        )
    return groups


def wiki_elective_groups(
    page: WikiPage,
    program_code: str,
    faculty_id: str,
) -> list[dict[str, Any]]:
    """Return wiki-parsed elective pools for any BSc track page."""
    groups: list[dict[str, Any]] = []
    section = _specialization_section(page.english_body)
    groups.extend(
        _parse_specialization_groups(
            section,
            program_code=program_code,
            page=page,
            faculty_id=faculty_id,
        )
    )
    groups.extend(_table_section_pools(page, program_code, faculty_id=faculty_id))
    groups.extend(_hebrew_list_pools(page, program_code, faculty_id=faculty_id))
    groups.extend(_hebrew_group_pools(page, program_code, faculty_id=faculty_id))
    groups.extend(_specialization_track_elective_pools(page, program_code, faculty_id=faculty_id))
    groups.extend(_bold_list_pools(page, program_code, faculty_id=faculty_id))
    groups.extend(_cluster_elective_pools(page, program_code, faculty_id=faculty_id))
    groups.extend(_named_group_pools(page, program_code, faculty_id=faculty_id))
    groups.extend(_bold_numbered_list_pools(page, program_code, faculty_id=faculty_id))
    groups.extend(_elective_subsection_pools(page, program_code, faculty_id=faculty_id))
    groups.extend(_hebrew_elective_section_pools(page, program_code, faculty_id=faculty_id))
    groups.extend(_biotech_track_cluster_pools(page, program_code, faculty_id=faculty_id))
    groups.extend(_group_n_pools(page, program_code, faculty_id=faculty_id))
    return _dedupe_pool_groups(groups)


def collect_contract_pool_entries(
    document: dict[str, Any],
    *,
    faculty_id: str,
) -> list[dict[str, Any]]:
    """Derive elective-chain contract entries from an exported catalog document."""
    entries_by_key: dict[tuple[str, str], dict[str, Any]] = {}
    for program in document.get("programs") or []:
        program_code = str(program.get("programCode") or "")
        track_slug = str((program.get("metadata") or {}).get("wikiPage") or "")
        for group in program.get("requirementGroups") or []:
            rule = group.get("ruleExpression") or {}
            operator = rule.get("operator")
            if operator not in {"choose_n", "choose_chain"}:
                continue
            group_id = str(group.get("groupId") or "")
            suffix = group_id.split(":", 1)[-1] if ":" in group_id else group_id
            refs = group.get("courseReferences") or []
            ref_count = len(refs)
            entry: dict[str, Any] = {
                "programCode": program_code,
                "trackSlug": track_slug,
                "suffix": suffix,
                "operator": operator,
                "minCourseRefs": ref_count,
                "maxCourseRefs": ref_count,
                "requiresCatalogDescription": True,
            }
            mandatory_numbers: list[str] = []
            for note in group.get("notes") or []:
                if not str(note).lower().startswith("mandatory:"):
                    continue
                mandatory_numbers.extend(collect_course_numbers_from_text(str(note)))
            if mandatory_numbers:
                entry["mustIncludeCourseNumbers"] = sorted(set(mandatory_numbers))
            key = (program_code, suffix)
            existing = entries_by_key.get(key)
            if existing is None or ref_count > int(existing.get("maxCourseRefs") or 0):
                entries_by_key[key] = entry
    return list(entries_by_key.values())
