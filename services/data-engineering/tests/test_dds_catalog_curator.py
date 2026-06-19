"""Tests for Phase 7.5 DDS catalog curation."""

import json
from pathlib import Path

from app.curation.dds_catalog_curator import curate_dds_catalog, run_curation

FIXTURE_DRAFT = Path(__file__).parent / "fixtures" / "dds_catalog_draft_sample.json"
FIXTURE_MD = Path(__file__).parent / "fixtures" / "dds_catalog_sample.md"
FIXTURE_201 = Path(__file__).parent / "fixtures" / "courses_sample_201.json"
EXTRA_JSON_ONLY_COURSE = Path(__file__).parent / "fixtures" / "courses_sample_json_only.json"


def test_title_enrichment_from_course_json(tmp_path: Path) -> None:
    document, _warnings = curate_dds_catalog(
        draft_path=FIXTURE_DRAFT,
        markdown_path=FIXTURE_MD,
        course_json_paths=[FIXTURE_201],
    )
    ds = next(program for program in document.programs if program.programCode == "009216-1-000")
    sem_group = next(
        group for group in ds.requirementGroups if group.groupId.endswith("semester-1-matrix")
    )
    ref = sem_group.courseReferences[0]
    assert ref.titleHint == "מתמטיקה דיסקרטית ת'"
    assert ref.creditsHint == 4.0
    assert 201 in ref.semestersOffered
    assert any("titleHint:" in item for item in ref.sourceEvidence)


def test_no_requirement_added_from_course_json_only(tmp_path: Path) -> None:
    json_only = tmp_path / "courses_only.json"
    json_only.write_text(
        json.dumps(
            [
                {
                    "general": {
                        "מספר מקצוע": "09999999",
                        "שם מקצוע": "קורס שלא בקטלוג",
                        "נקודות": "3",
                    },
                    "schedule": [],
                }
            ]
        ),
        encoding="utf-8",
    )
    document, _warnings = curate_dds_catalog(
        draft_path=FIXTURE_DRAFT,
        markdown_path=FIXTURE_MD,
        course_json_paths=[json_only],
    )
    all_numbers = {
        ref.courseNumber
        for program in document.programs
        for group in program.requirementGroups
        for ref in group.courseReferences
    }
    assert "09999999" not in all_numbers


def test_curation_report_counts(tmp_path: Path) -> None:
    document, _warnings = curate_dds_catalog(
        draft_path=FIXTURE_DRAFT,
        markdown_path=FIXTURE_MD,
        course_json_paths=[FIXTURE_201],
    )
    report = document.curationReport
    assert report["totalPrograms"] == 1
    assert report["titleHintsFilledFromCourseJson"] >= 1
    assert document.curationMetadata.countsBefore["courseReferences"] == 2
    assert document.curationMetadata.countsAfter["courseReferences"] >= 2
    assert document.curationMetadata.curationStatus == "draft-reviewed-needs-human-signoff"


def test_run_curation_writes_outputs(tmp_path: Path) -> None:
    output = tmp_path / "reviewed.json"
    report = tmp_path / "report.md"
    document, reviewed_path, report_path = run_curation(
        draft_path=FIXTURE_DRAFT,
        markdown_path=FIXTURE_MD,
        course_json_paths=[FIXTURE_201],
        output_path=output,
        report_path=report,
    )
    assert reviewed_path == output
    assert report_path == report
    assert output.exists()
    assert report.exists()
    assert "No MongoDB writes occurred" in report.read_text(encoding="utf-8")
    assert document.curationMetadata.curatedBy == "cursor-assisted"
