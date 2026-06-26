"""Tests for faculty-scoped catalog context helpers (Phase D)."""

from __future__ import annotations

from app.catalog.faculty_catalog_context import (
    faculty_catalog_context_from_document,
    production_program_key,
)


def test_faculty_context_from_generic_export_document() -> None:
    document = {
        "source": {
            "facultyId": "computer-science",
            "sourceName": "technion-computer-science-catalog",
            "sourceType": "computer-science_catalog_curated_reviewed",
            "exportMode": "generic",
            "expectedProgramCodes": ["023023-1-000"],
        },
        "programs": [{"programCode": "023023-1-000", "metadata": {"wikiPage": "track-computer-science-general-4year"}}],
    }
    context = faculty_catalog_context_from_document(document)
    assert context.faculty_id == "computer-science"
    assert context.source_name == "technion-computer-science-catalog"
    assert context.expected_program_codes == ("023023-1-000",)
    assert production_program_key("computer-science", "023023-1-000", "2025-2026") == (
        "technion-computer-science:program:023023-1-000:2025-2026"
    )
