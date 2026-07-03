"""DDS track slug ↔ program code registry (mirrors API vault export)."""

from __future__ import annotations

from typing import Any

DDS_TRACK_BY_SLUG: dict[str, dict[str, Any]] = {
    "track-data-information-engineering": {
        "programCode": "009216-1-000",
        "nameEn": "Data and Information Engineering",
    },
    "track-industrial-engineering-management": {
        "programCode": "009009-1-000",
        "nameEn": "Industrial Engineering and Management",
    },
    "track-information-systems-engineering": {
        "programCode": "009118-1-000",
        "nameEn": "Information Systems Engineering",
    },
}

DDS_TRACK_BY_PROGRAM_CODE: dict[str, str] = {
    config["programCode"]: slug for slug, config in DDS_TRACK_BY_SLUG.items()
}


def resolve_track_slug_from_program(
    program_document: dict[str, Any] | None,
) -> str | None:
    if not program_document:
        return None

    metadata = program_document.get("metadata") or {}
    wiki_page = metadata.get("wikiPage")
    if isinstance(wiki_page, str) and wiki_page.startswith("track-"):
        return wiki_page

    program_code = program_document.get("programCode")
    if isinstance(program_code, str):
        return DDS_TRACK_BY_PROGRAM_CODE.get(program_code)

    return None
