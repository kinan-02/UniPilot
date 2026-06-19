from pathlib import Path

import pytest

from app.main import main
from app.sources.technion_dds_catalog_pdf import (
    ExtractedPage,
    default_output_directory,
    detect_candidate_sections,
    detect_course_numbers,
    detect_program_codes,
    extract_dds_catalog,
    resolve_pdf_path,
    service_root,
)

FIXTURE_TEXT = Path(__file__).parent / "fixtures" / "dds_catalog_sample_text.txt"


def test_detect_program_codes_finds_known_ids():
    text = "Programs 009216-1-000 and 009118-1-000 in catalog"
    hits = detect_program_codes(text)
    codes = {item["programCode"] for item in hits}
    assert codes == {"009216-1-000", "009118-1-000"}


def test_detect_course_numbers_normalizes_to_eight_digits():
    text = "Courses 0960401 and 00960412 on same line"
    hits = detect_course_numbers(text, page_number=3)
    numbers = {item["courseNumber"] for item in hits}
    assert "00960401" in numbers
    assert "00960412" in numbers
    assert all(len(item["courseNumber"]) == 8 for item in hits)


def test_detect_candidate_sections_from_fixture_text():
    text = FIXTURE_TEXT.read_text(encoding="utf-8")
    pages = [
        ExtractedPage(
            page_number=1,
            raw_text=text,
            processed_text=text,
            character_count=len(text),
        )
    ]
    result = detect_candidate_sections(pages)

    section_types = {section["sectionType"] for section in result["sections"]}
    assert "program_data_science_engineering" in section_types
    assert "mandatory_courses" in section_types
    assert "elective_courses" in section_types
    assert "credit_requirements" in section_types
    assert "semester_tables" in section_types
    assert "course_lists" in section_types
    assert len(result["courseNumberHits"]) >= 2


def test_resolve_pdf_path_raises_for_missing_file():
    with pytest.raises(FileNotFoundError, match="DDS catalog PDF path is required"):
        resolve_pdf_path(None, None)

    with pytest.raises(FileNotFoundError, match="not found"):
        resolve_pdf_path("/tmp/does-not-exist-dds-catalog.pdf", None)


def test_cli_missing_pdf_path_returns_error(capsys):
    exit_code = main(["inspect-dds-catalog"])
    captured = capsys.readouterr().out
    assert exit_code == 1
    assert "DDS catalog PDF path is required" in captured


def test_default_output_directory_is_under_generated_not_raw():
    output_dir = default_output_directory()
    assert "generated" in output_dir.parts
    assert "raw" not in output_dir.parts
    assert output_dir.is_relative_to(service_root())


def test_extract_dds_catalog_writes_generated_artifacts(tmp_path, monkeypatch):
    pdf_path = tmp_path / "sample.pdf"
    pdf_path.write_bytes(_minimal_pdf_bytes())

    output_dir = tmp_path / "generated" / "dds_catalog"
    artifacts = extract_dds_catalog(
        str(pdf_path),
        output_directory=output_dir,
    )

    assert artifacts.output_directory == output_dir.resolve()
    assert (output_dir / "extracted_pages.json").exists()
    assert (output_dir / "extracted_pages.txt").exists()
    assert (output_dir / "extraction_report.json").exists()
    assert (output_dir / "candidate_sections.json").exists()
    assert "generated" in str(output_dir)
    assert "raw" not in str(output_dir)


def _minimal_pdf_bytes() -> bytes:
  return (
      b"%PDF-1.1\n"
      b"1 0 obj<<>>endobj\n"
      b"2 0 obj<</Length 44>>stream\n"
      b"BT /F1 12 Tf 100 700 Td (Hello DDS) Tj ET\n"
      b"endstream\nendobj\n"
      b"3 0 obj<</Type/Page/Parent 4 0 R/Contents 2 0 R>>endobj\n"
      b"4 0 obj<</Type/Pages/Count 1/Kids[3 0 R]>>endobj\n"
      b"5 0 obj<</Type/Catalog/Pages 4 0 R>>endobj\n"
      b"xref\n0 6\n0000000000 65535 f \n"
      b"0000000009 00000 n \n"
      b"0000000020 00000 n \n"
      b"0000000105 00000 n \n"
      b"0000000170 00000 n \n"
      b"0000000224 00000 n \n"
      b"trailer<</Size 6/Root 5 0 R>>\n"
      b"startxref\n280\n%%EOF\n"
  )
