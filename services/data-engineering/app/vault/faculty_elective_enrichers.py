"""Per-faculty elective enrichment registry for specialized vault export."""

from __future__ import annotations

from typing import Any

from app.vault.export_cs_electives import cs_elective_groups
from app.vault.export_wiki_elective_groups import wiki_elective_groups
from app.vault.loader import WikiPage


def faculty_elective_groups(
    page: WikiPage,
    program_code: str,
    faculty_id: str,
    *,
    pages: dict[str, WikiPage] | None = None,
) -> list[dict[str, Any]]:
    """Apply faculty-specific elective-chain enrichment on top of generic export."""
    _ = pages
    groups: list[dict[str, Any]] = []
    if faculty_id == "computer-science":
        groups.extend(cs_elective_groups(page, program_code))
    else:
        groups.extend(wiki_elective_groups(page, program_code, faculty_id))
    return groups
