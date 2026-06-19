"""Tests for DDS catalog markdown parser."""

from pathlib import Path

import pytest

from app.models.catalog import CuratedCatalogDocument
from app.parsers.dds_catalog_markdown_parser import (
    parse_curated_catalog_draft,
    preprocess_markdown,
    split_program_sections,
    write_curated_catalog_draft,
)

FIXTURE_PATH = Path(__file__).parent / "fixtures" / "dds_catalog_sample.md"


def test_split_program_sections() -> None:
    text = FIXTURE_PATH.read_text(encoding="utf-8")
    sections = split_program_sections(preprocess_markdown(text))
    assert set(sections) == {"009216-1-000", "009009-1-000", "009118-1-000"}


def test_parse_curated_catalog_draft_from_fixture(tmp_path: Path) -> None:
    document, report = parse_curated_catalog_draft(str(FIXTURE_PATH))
    assert isinstance(document, CuratedCatalogDocument)
    assert len(document.programs) == 3
    assert report.normalizedCourseNumbers > 0
    assert report.to_dict()["manualReviewRequired"] is True

    ds_program = next(p for p in document.programs if p.programCode == "009216-1-000")
    assert ds_program.totalCredits == 155.0
    assert len(ds_program.paths) >= 1

    all_numbers = {
        ref.courseNumber
        for group in ds_program.requirementGroups
        for ref in group.courseReferences
    }
    assert "00940700" in all_numbers
    assert "00940345" in all_numbers
    assert "00940139" in all_numbers


def test_write_curated_catalog_draft(tmp_path: Path) -> None:
    output = tmp_path / "draft.json"
    document, target = write_curated_catalog_draft(
        str(FIXTURE_PATH),
        output_path=str(output),
    )
    assert target == output
    assert output.exists()
    assert document.parserReport["courseReferences"] > 0


def test_parse_missing_markdown_raises() -> None:
    with pytest.raises(FileNotFoundError):
        parse_curated_catalog_draft("/tmp/does-not-exist-dds.md")
