"""Computer Science elective-chain enrichment (general 4-year track)."""

from __future__ import annotations

import re
from typing import Any

from app.utils.course_numbers import collect_course_numbers_from_text
from app.vault.export_dds_catalog import _course_pool_group, build_course_reference
from app.vault.loader import WikiPage

GENERAL_4YEAR_SLUG = "track-computer-science-general-4year"
GENERAL_4YEAR_PROGRAM_CODE = "023023-1-000"

_SPECIALIZATION_HEADER = re.compile(r"^\*\*(\d+)\.\s+(.+?)\*\*\s*$", re.MULTILINE)
_MANDATORY_LINE = re.compile(r"Mandatory:\s*(.+)$", re.IGNORECASE | re.MULTILINE)

_SCIENCE_CHAIN_SPECS: tuple[tuple[str, str, tuple[str, ...], int, str], ...] = (
    (
        "cs-science-chain-physics-mm",
        "CS science elective chain: Physics 2MM",
        ("01140075",),
        1,
        "Complete Physics 2MM (01140075, 5.0 credits) as the science chain.",
    ),
    (
        "cs-science-chain-physics-23",
        "CS science elective chain: Physics 2 + Physics 3",
        ("01140052", "01140054"),
        2,
        "Complete Physics 2 (01140052) and Physics 3 (01140054).",
    ),
    (
        "cs-science-chain-biology",
        "CS science elective chain: Biology",
        ("01340058", "01340020"),
        2,
        "Complete Biology 1 (01340058) and General Genetics (01340020).",
    ),
    (
        "cs-science-chain-chemistry",
        "CS science elective chain: Chemistry",
        ("01240120", "01250801", "01240510"),
        2,
        "Complete Foundations of Chemistry (01240120) plus Organic Chemistry (01250801) "
        "or Physical Chemistry (01240510).",
    ),
    (
        "cs-science-chain-physics-chemistry",
        "CS science elective chain: Physics + Chemistry",
        ("01240120", "01140052"),
        2,
        "Complete Foundations of Chemistry (01240120) and Physics 2 (01140052).",
    ),
)


def _refs_for_numbers(numbers: tuple[str, ...], *, source_page: str) -> list[dict[str, Any]]:
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


def _science_chain_groups(page: WikiPage, program_code: str) -> list[dict[str, Any]]:
    groups: list[dict[str, Any]] = []
    for suffix, title, numbers, choose_count, description in _SCIENCE_CHAIN_SPECS:
        refs = _refs_for_numbers(numbers, source_page=page.path)
        groups.append(
            _course_pool_group(
                program_code=program_code,
                group_suffix=suffix,
                title=title,
                course_refs=refs,
                rule_expression={
                    "type": "course_pool",
                    "operator": "choose_chain",
                    "chooseCount": choose_count,
                    "chain": suffix.removeprefix("cs-science-chain-"),
                },
                catalog_description=description,
                notes=["Semester 4 science requirement: complete one chain (min 8 science credits)."],
            )
        )
    return groups


def _specialization_section(english: str) -> str:
    marker = "### Specialization Groups"
    start = english.find(marker)
    if start < 0:
        return ""
    end = english.find("## Special Rules", start)
    if end < 0:
        end = english.find("## נתונים בעברית", start)
    if end < 0:
        return english[start:]
    return english[start:end]


def _parse_specialization_groups(section: str) -> list[tuple[int, str, list[str], str | None]]:
    matches = list(_SPECIALIZATION_HEADER.finditer(section))
    parsed: list[tuple[int, str, list[str], str | None]] = []
    for index, match in enumerate(matches):
        group_number = int(match.group(1))
        title = match.group(2).strip()
        block_start = match.end()
        block_end = matches[index + 1].start() if index + 1 < len(matches) else len(section)
        block = section[block_start:block_end]
        mandatory_match = _MANDATORY_LINE.search(block)
        mandatory_note = mandatory_match.group(1).strip() if mandatory_match else None
        numbers = collect_course_numbers_from_text(block)
        parsed.append((group_number, title, numbers, mandatory_note))
    return parsed


def _specialization_groups(page: WikiPage, program_code: str) -> list[dict[str, Any]]:
    section = _specialization_section(page.english_body)
    if not section:
        return []

    groups: list[dict[str, Any]] = []
    for group_number, title, numbers, mandatory_note in _parse_specialization_groups(section):
        refs = _refs_for_numbers(tuple(numbers), source_page=page.path)
        notes = [
            "Faculty elective specialization group; choose 3 distinct courses including mandatory courses.",
        ]
        if mandatory_note:
            notes.append(f"Mandatory: {mandatory_note}")
        description = (
            f"Specialization group {group_number} — {title}. "
            "Complete 3 different courses from this pool, including any mandatory courses."
        )
        if mandatory_note:
            description += f" Mandatory: {mandatory_note}."
        groups.append(
            _course_pool_group(
                program_code=program_code,
                group_suffix=f"cs-spec-group-{group_number:02d}",
                title=f"CS specialization group {group_number}: {title}",
                course_refs=refs,
                rule_expression={
                    "type": "course_pool",
                    "operator": "choose_n",
                    "chooseCount": 3,
                    "group": group_number,
                },
                catalog_description=description,
                notes=notes,
            )
        )
    return groups


def cs_elective_groups(page: WikiPage, program_code: str) -> list[dict[str, Any]]:
    """Return elective-chain pools for the CS general 4-year track."""
    if page.slug != GENERAL_4YEAR_SLUG or program_code != GENERAL_4YEAR_PROGRAM_CODE:
        return []

    groups = _science_chain_groups(page, program_code)
    groups.extend(_specialization_groups(page, program_code))
    return groups
