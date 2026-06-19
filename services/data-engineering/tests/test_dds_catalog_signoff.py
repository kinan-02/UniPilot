"""Tests for Phase 7.6 DDS catalog signoff review."""

import json
from pathlib import Path

from app.curation.dds_catalog_signoff import (
    run_signoff,
    run_signoff_review,
)
from app.models.catalog import ReviewedCuratedCatalogDocument

FIXTURE_REVIEWED = Path(__file__).parent / "fixtures" / "dds_catalog_reviewed_sample.json"
FIXTURE_MD = Path(__file__).parent / "fixtures" / "dds_catalog_sample.md"
FIXTURE_201 = Path(__file__).parent / "fixtures" / "courses_sample_201.json"


def test_signoff_adds_signoff_review_metadata(tmp_path: Path) -> None:
    document, readiness = run_signoff_review(
        reviewed_path=FIXTURE_REVIEWED,
        markdown_path=FIXTURE_MD,
        course_json_paths=[FIXTURE_201],
    )
    assert document.signoffReview is not None
    assert document.signoffReview.reviewedBy == "cursor-agent-source-review"
    assert document.signoffReview.reviewStatus in {
        "ready-for-human-signoff",
        "ready-for-staging-with-review-flags",
        "needs-more-curation",
        "not-ready",
    }
    assert document.signoffReview.reviewStatus != "production-ready"
    assert readiness["canPromoteToProduction"] is False


def test_signoff_fills_titles_from_json_or_markdown() -> None:
    document, _readiness = run_signoff_review(
        reviewed_path=FIXTURE_REVIEWED,
        markdown_path=FIXTURE_MD,
        course_json_paths=[FIXTURE_201],
    )
    ds = next(p for p in document.programs if p.programCode == "009216-1-000")
    sem = next(g for g in ds.requirementGroups if g.groupId.endswith("semester-1-matrix"))
    titles = {ref.courseNumber: ref.titleHint for ref in sem.courseReferences}
    assert titles["00940345"] == "מתמטיקה דיסקרטית ת'"


def test_ie_chain_stays_non_mandatory() -> None:
    document, _ = run_signoff_review(
        reviewed_path=FIXTURE_REVIEWED,
        markdown_path=FIXTURE_MD,
        course_json_paths=[FIXTURE_201],
    )
    ie = next(p for p in document.programs if p.programCode == "009009-1-000")
    chain = next(g for g in ie.requirementGroups if "chain" in g.groupId)
    assert chain.ruleExpression.get("operator") == "choose_n"
    assert chain.courseReferences == []
    assert chain.manualReviewRequired is True


def test_readiness_check_counts(tmp_path: Path) -> None:
    document, readiness = run_signoff_review(
        reviewed_path=FIXTURE_REVIEWED,
        markdown_path=FIXTURE_MD,
        course_json_paths=[FIXTURE_201],
    )
    assert readiness["counts"]["programs"] == 3
    assert readiness["counts"]["executableRuleGroups"] >= 1
    assert readiness["counts"]["nonExecutableRuleGroups"] >= 1
    assert "canImportToStaging" in readiness


def test_curation_status_not_production_ready() -> None:
    document, _ = run_signoff_review(
        reviewed_path=FIXTURE_REVIEWED,
        markdown_path=FIXTURE_MD,
        course_json_paths=[FIXTURE_201],
    )
    assert document.curationMetadata.curationStatus != "production-ready"
    assert document.signoffReview is not None
    assert document.signoffReview.reviewStatus != "production-ready"


def test_no_requirements_inferred_from_course_json_only() -> None:
    """Signoff must not add course references from JSON alone."""
    before = json.loads(FIXTURE_REVIEWED.read_text(encoding="utf-8"))
    before_refs = {
        ref["courseNumber"]
        for program in before["programs"]
        for group in program["requirementGroups"]
        for ref in group.get("courseReferences", [])
    }
    document, _ = run_signoff_review(
        reviewed_path=FIXTURE_REVIEWED,
        markdown_path=FIXTURE_MD,
        course_json_paths=[FIXTURE_201],
    )
    after_refs = {
        ref.courseNumber
        for program in document.programs
        for group in program.requirementGroups
        for ref in group.courseReferences
    }
    assert after_refs == before_refs


def test_run_signoff_writes_outputs(tmp_path: Path) -> None:
    out = tmp_path / "reviewed.json"
    report = tmp_path / "signoff.md"
    readiness = tmp_path / "readiness.json"
    document, readiness_payload, reviewed_path, report_path, readiness_path = run_signoff(
        reviewed_path=FIXTURE_REVIEWED,
        markdown_path=FIXTURE_MD,
        course_json_paths=[FIXTURE_201],
        reviewed_output_path=out,
        signoff_report_path=report,
        readiness_path=readiness,
    )
    assert reviewed_path == out
    assert report_path == report
    assert readiness_path == readiness
    payload = json.loads(out.read_text(encoding="utf-8"))
    assert payload.get("signoffReview")
    assert readiness_payload["canPromoteToProduction"] is False
    ReviewedCuratedCatalogDocument.model_validate(payload)
