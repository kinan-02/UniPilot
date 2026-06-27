"""Export profile-selectable academic path options from the catalog wiki vault."""

from __future__ import annotations

import re
from pathlib import Path
from typing import Any

from app.vault.loader import WikiPage, extract_wikilinks, load_pages_by_slug, wiki_root

GRADUATE_SECTION_PATTERN = re.compile(
    r"^##\s+(?:\d+\.\s+)?(.+?)(?:\s*\(([^)]+)\))?\s*$",
    re.MULTILINE,
)
PROGRAM_CODE_PATTERN = re.compile(r"\b(0\d{6}-\d-\d{3})\b")

SPECIALIZATION_KIND = "dne_specialization"
GRADUATE_KIND = "graduate_program"
FACULTY_PREFIX = "faculty-"

GRADUATE_SKIP_TITLES = frozenset(
    {
        "overview",
        "sources",
        "ph.d. requirements",
        "ph.d. requirements (standard)",
    }
)


def _option_key(institution_id: str, faculty_id: str, wiki_slug: str) -> str:
    faculty_short = faculty_id.removeprefix(FACULTY_PREFIX)
    return f"{institution_id}:{faculty_short}:{wiki_slug}"


def _study_levels_from_text(text: str) -> list[str]:
    lowered = text.lower()
    levels: list[str] = []
    if "b.sc" in lowered or "bsc" in lowered or "תואר ראשון" in text or "בוגר" in text:
        levels.append("BSc")
    if "m.sc" in lowered or "msc" in lowered or "מוסמך" in text or 'מ"א' in text:
        levels.append("MSc")
    if "ph.d" in lowered or "phd" in lowered or "דוקטורט" in text:
        levels.append("PhD")
    if "mba" in lowered:
        levels.append("MBA")
    if "m.d" in lowered or " md " in f" {lowered} " or "דוקטור לרפואה" in text:
        levels.append("MD")
    return levels or ["BSc"]


_TRACK_PREREQUISITE_PATTERN = re.compile(
    r"\*\*Prerequisites?:\*\*[^\n]*",
    re.IGNORECASE,
)


def _track_study_levels(page: WikiPage) -> list[str]:
    body = f"{page.english_body}\n{page.body}"
    return _study_levels_from_text(body)


def _track_selectable_as_primary(page: WikiPage) -> bool:
    """Admission paths only — exclude clinical/continuation tracks with upstream prerequisites."""
    body = f"{page.english_body}\n{page.body}"
    prerequisite_line = _TRACK_PREREQUISITE_PATTERN.search(body)
    if not prerequisite_line:
        return True
    prereq_text = prerequisite_line.group(0).lower()
    if "completion of" not in prereq_text and "requires" not in prereq_text:
        return True
    for link in extract_wikilinks(prerequisite_line.group(0)):
        if link.startswith("track-"):
            return False
    return True


def _graduate_study_levels(title: str, section_text: str) -> list[str]:
    combined = f"{title}\n{section_text}"
    lowered = combined.lower()
    if "mba" in lowered:
        return ["MBA"]
    levels: list[str] = []
    if "ph.d" in lowered or "phd" in lowered or "דוקטורט" in combined:
        levels.append("PhD")
    if (
        "m.sc" in lowered
        or "msc" in lowered
        or "מוסמך" in combined
        or 'מ"א' in combined
        or "master" in lowered
    ):
        levels.append("MSc")
    return levels or ["MSc", "PhD"]


def _graduate_slug_from_title(title: str) -> str:
    slug = re.sub(r"[^a-z0-9]+", "-", title.lower()).strip("-")
    return f"grad-{slug}" if slug else "grad-program"


def _faculty_entry(page: WikiPage, institution_id: str) -> dict[str, Any]:
    return {
        "facultyId": page.slug,
        "institutionId": institution_id,
        "wikiSlug": page.slug,
        "name": page.title,
        "nameHe": page.title_he or page.title,
        "nameEn": page.title,
        "aliases": list(page.frontmatter.get("aliases") or []),
        "catalogPrefix": _extract_field(page.english_body, "Catalog prefix"),
    }


def _extract_field(body: str, label: str) -> str | None:
    match = re.search(
        rf"^\*\*{re.escape(label)}:\*\*\s*(.+)$",
        body,
        flags=re.IGNORECASE | re.MULTILINE,
    )
    if not match:
        return None
    value = match.group(1).strip()
    value = re.split(r"\s*\*\*", value, maxsplit=1)[0].strip()
    return value or None


def _normalize_credits_value(raw: str | None) -> str | None:
    if not raw:
        return None
    number = re.search(r"([\d.]+)", raw)
    return number.group(1) if number else raw.strip()


def _page_catalog_meta(page: WikiPage) -> tuple[str | None, str | None]:
    body = page.english_body
    duration = _extract_field(body, "Duration")
    credits_raw = _extract_field(body, "Total credits required") or _extract_field(
        body, "Total credits"
    )
    return duration, _normalize_credits_value(credits_raw)


def _section_catalog_meta(section_text: str) -> tuple[str | None, str | None]:
    duration = _extract_field(section_text, "Duration")
    if not duration:
        bullet = re.search(
            r"[-*]\s*\*\*Duration:\*\*\s*(.+)$",
            section_text,
            flags=re.IGNORECASE | re.MULTILINE,
        )
        if bullet:
            duration = bullet.group(1).strip()
    credits_raw = _extract_field(section_text, "Total credits required") or _extract_field(
        section_text, "Total credits"
    )
    return duration, _normalize_credits_value(credits_raw)


def _resolve_page_faculty_id(page: WikiPage) -> str | None:
    body = f"{page.english_body}\n{page.body}"
    for label in ("Faculty", "Offered by"):
        raw = _extract_field(body, label)
        if not raw:
            continue
        for link in extract_wikilinks(raw):
            if link.startswith(FACULTY_PREFIX):
                return link
    return None


def _is_metadata_line(stripped: str) -> bool:
    if re.match(r"^\*\*[^*]+:\*\*", stripped):
        return True
    return stripped.startswith("**") and stripped.endswith("**")


def _page_description(page: WikiPage, *, max_len: int = 280) -> str | None:
    text = page.english_body.strip()
    if not text:
        return None
    lines: list[str] = []
    for line in text.splitlines():
        stripped = line.strip()
        if not stripped or stripped.startswith("#") or stripped.startswith("|"):
            continue
        if _is_metadata_line(stripped):
            continue
        if stripped.startswith("---"):
            break
        lines.append(stripped)
        if len(" ".join(lines)) >= max_len:
            break
    description = " ".join(lines).strip()
    if not description:
        return None
    return description[:max_len]


def _in_scope(page_faculty_id: str | None, scope_faculty_id: str | None, fallback_faculty_id: str) -> bool:
    if scope_faculty_id is None:
        return True
    resolved = page_faculty_id or fallback_faculty_id
    return resolved == scope_faculty_id


def _path_option(
    *,
    institution_id: str,
    faculty_id: str,
    wiki_slug: str,
    kind: str,
    name: str,
    name_he: str | None,
    name_en: str | None,
    study_levels: list[str],
    selectable_as_primary: bool,
    linked_program_code: str | None = None,
    description: str | None = None,
    duration: str | None = None,
    total_credits_required: str | None = None,
) -> dict[str, Any]:
    option: dict[str, Any] = {
        "optionKey": _option_key(institution_id, faculty_id, wiki_slug),
        "institutionId": institution_id,
        "facultyId": faculty_id,
        "wikiSlug": wiki_slug,
        "kind": kind,
        "name": name_he or name,
        "nameHe": name_he or name,
        "nameEn": name_en or name,
        "studyLevels": study_levels,
        "selectableAsPrimary": selectable_as_primary,
        "linkedProgramCode": linked_program_code,
        "description": description,
        "status": "published",
    }
    if duration:
        option["duration"] = duration
    if total_credits_required:
        option["totalCreditsRequired"] = total_credits_required
    return option


def _track_options(
    pages: dict[str, WikiPage],
    *,
    institution_id: str,
    fallback_faculty_id: str,
    track_program_codes: dict[str, str],
    scope_faculty_id: str | None,
) -> list[dict[str, Any]]:
    options: list[dict[str, Any]] = []
    for wiki_slug, program_code in sorted(track_program_codes.items()):
        page = pages.get(wiki_slug)
        if page is None:
            continue
        page_faculty = _resolve_page_faculty_id(page) or fallback_faculty_id
        if not _in_scope(page_faculty, scope_faculty_id, fallback_faculty_id):
            continue
        duration, total_credits = _page_catalog_meta(page)
        options.append(
            _path_option(
                institution_id=institution_id,
                faculty_id=page_faculty,
                wiki_slug=wiki_slug,
                kind="bsc_track",
                name=page.title,
                name_he=page.title_he,
                name_en=page.title,
                study_levels=_track_study_levels(page),
                selectable_as_primary=_track_selectable_as_primary(page),
                linked_program_code=program_code,
                description=_page_description(page),
                duration=duration,
                total_credits_required=total_credits,
            )
        )
    return options


def _entity_prefix_options(
    pages: dict[str, WikiPage],
    *,
    institution_id: str,
    fallback_faculty_id: str,
    prefix: str,
    kind: str,
    scope_faculty_id: str | None,
    study_levels: list[str] | None = None,
) -> list[dict[str, Any]]:
    options: list[dict[str, Any]] = []
    for slug, page in sorted(pages.items()):
        if not slug.startswith(prefix):
            continue
        page_faculty = _resolve_page_faculty_id(page) or fallback_faculty_id
        if not _in_scope(page_faculty, scope_faculty_id, fallback_faculty_id):
            continue
        body = f"{page.english_body}\n{page.body}"
        levels = study_levels or _study_levels_from_text(body)
        duration, total_credits = _page_catalog_meta(page)
        options.append(
            _path_option(
                institution_id=institution_id,
                faculty_id=page_faculty,
                wiki_slug=slug,
                kind=kind,
                name=page.title,
                name_he=page.title_he,
                name_en=page.title,
                study_levels=levels,
                selectable_as_primary=False,
                description=_page_description(page),
                duration=duration,
                total_credits_required=total_credits,
            )
        )
    return options


def _should_skip_graduate_section(title: str) -> bool:
    normalized = title.strip().lower()
    if normalized in GRADUATE_SKIP_TITLES:
        return True
    return normalized.startswith("ph.d. requirements")


def _graduate_options(
    page: WikiPage | None,
    *,
    institution_id: str,
    fallback_faculty_id: str,
    scope_faculty_id: str | None,
) -> list[dict[str, Any]]:
    if page is None:
        return []

    page_faculty = _resolve_page_faculty_id(page) or fallback_faculty_id
    if not _in_scope(page_faculty, scope_faculty_id, fallback_faculty_id):
        return []

    options: list[dict[str, Any]] = []
    for match in GRADUATE_SECTION_PATTERN.finditer(page.english_body):
        title = match.group(1).strip()
        if _should_skip_graduate_section(title):
            continue
        section_start = match.end()
        next_heading = page.english_body.find("\n## ", section_start)
        section_text = (
            page.english_body[section_start:next_heading]
            if next_heading >= 0
            else page.english_body[section_start:]
        )
        levels = _graduate_study_levels(title, section_text)
        if "mba" in title.lower():
            levels = ["MBA"]
        wiki_slug = _graduate_slug_from_title(title)
        duration, total_credits = _section_catalog_meta(section_text)
        if page is not None and not duration:
            page_duration, _ = _page_catalog_meta(page)
            duration = page_duration
        options.append(
            _path_option(
                institution_id=institution_id,
                faculty_id=page_faculty,
                wiki_slug=wiki_slug,
                kind=GRADUATE_KIND,
                name=title,
                name_he=match.group(2).strip() if match.group(2) else title,
                name_en=title,
                study_levels=levels,
                selectable_as_primary=True,
                description=section_text.strip()[:500] or None,
                duration=duration,
                total_credits_required=total_credits,
            )
        )
    return options


def _specialization_options(
    pages: dict[str, WikiPage],
    *,
    institution_id: str,
    fallback_faculty_id: str,
    scope_faculty_id: str | None,
) -> list[dict[str, Any]]:
    options: list[dict[str, Any]] = []
    for slug, page in sorted(pages.items()):
        if not slug.startswith("specialization-"):
            continue
        page_faculty = _resolve_page_faculty_id(page) or fallback_faculty_id
        if not _in_scope(page_faculty, scope_faculty_id, fallback_faculty_id):
            continue
        duration, total_credits = _page_catalog_meta(page)
        options.append(
            _path_option(
                institution_id=institution_id,
                faculty_id=page_faculty,
                wiki_slug=slug,
                kind=SPECIALIZATION_KIND,
                name=page.title,
                name_he=page.title_he,
                name_en=page.title,
                study_levels=["BSc"],
                selectable_as_primary=False,
                description=_page_description(page),
                duration=duration,
                total_credits_required=total_credits,
            )
        )
    return options


def build_wiki_path_catalog(
    *,
    wiki_path: Path | None = None,
    institution_id: str = "technion",
    faculty_id: str = "faculty-dds",
    track_program_codes: dict[str, str],
    catalog_year: int,
    catalog_version: str,
    scope_faculty_id: str | None = None,
) -> dict[str, Any]:
    """Build faculty registry and path options from wiki pages (Technion-scalable)."""
    root = wiki_root(wiki_path) if wiki_path is None else wiki_path
    pages = load_pages_by_slug(root)
    effective_scope = scope_faculty_id or faculty_id

    faculties: list[dict[str, Any]] = []
    for slug, page in sorted(pages.items()):
        if slug.startswith(FACULTY_PREFIX) and page.page_type in {None, "entity", "organization"}:
            entry = _faculty_entry(page, institution_id)
            entry["catalogYear"] = catalog_year
            entry["catalogVersion"] = catalog_version
            entry["status"] = "published"
            faculties.append(entry)

    if not faculties:
        faculties.append(
            {
                "facultyId": faculty_id,
                "institutionId": institution_id,
                "wikiSlug": faculty_id,
                "name": faculty_id,
                "nameHe": faculty_id,
                "nameEn": faculty_id,
                "aliases": [],
                "catalogYear": catalog_year,
                "catalogVersion": catalog_version,
                "status": "published",
            }
        )

    path_options: list[dict[str, Any]] = []
    path_options.extend(
        _track_options(
            pages,
            institution_id=institution_id,
            fallback_faculty_id=faculty_id,
            track_program_codes=track_program_codes,
            scope_faculty_id=effective_scope,
        )
    )
    path_options.extend(
        _entity_prefix_options(
            pages,
            institution_id=institution_id,
            fallback_faculty_id=faculty_id,
            prefix="program-",
            kind="special_program",
            scope_faculty_id=effective_scope,
        )
    )
    path_options.extend(
        _entity_prefix_options(
            pages,
            institution_id=institution_id,
            fallback_faculty_id=faculty_id,
            prefix="minor-",
            kind="minor",
            scope_faculty_id=effective_scope,
            study_levels=["BSc"],
        )
    )
    path_options.extend(
        _graduate_options(
            pages.get("graduate-programs"),
            institution_id=institution_id,
            fallback_faculty_id=faculty_id,
            scope_faculty_id=effective_scope,
        )
    )
    path_options.extend(
        _specialization_options(
            pages,
            institution_id=institution_id,
            fallback_faculty_id=faculty_id,
            scope_faculty_id=effective_scope,
        )
    )

    for option in path_options:
        option["catalogYear"] = catalog_year
        option["catalogVersion"] = catalog_version

    return {
        "faculties": faculties,
        "pathOptions": path_options,
    }
