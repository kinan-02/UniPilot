"""Additional Phase D coverage for faculty export and context helpers."""

from __future__ import annotations

from pathlib import Path
from unittest.mock import MagicMock

import pytest

from app.catalog.faculty_catalog_context import (
    FacultyCatalogContext,
    faculty_catalog_context_from_document,
    faculty_catalog_context_from_staging_program,
    faculty_id_from_document,
    production_advisory_requirement_key,
    production_requirement_key,
)
from app.importers.dds_catalog_staging_importer import (
    CatalogStagingImportError,
    validate_catalog_structure,
)
from app.paths import faculty_catalog_export_dir
from app.quality.dds_staging_quality import build_dds_staging_quality_report
from app.vault.export_faculty_vault_catalog import (
    _bucket_requirement_type,
    _canonical_bucket_slug,
    _dedupe_requirement_groups,
    _missing_standard_technion_bucket_slugs,
    _slugify_bucket_label,
    build_generic_program,
    export_faculty_vault_catalog,
    should_export_degree_program,
    parse_credit_buckets_from_page,
)
from app.vault.loader import WikiPage


def test_faculty_id_from_document_fallback_paths() -> None:
    assert faculty_id_from_document({}) == "dds"
    assert faculty_id_from_document({"parserReport": {"faculty": "math"}}) == "math"
    assert faculty_id_from_document(
        {"programs": [{"metadata": {"facultyId": "faculty-physics"}}]}
    ) == "physics"
    assert faculty_id_from_document(
        {"programs": [{"metadata": {"faculty": "chemistry"}}]}
    ) == "chemistry"


def test_faculty_context_from_staging_program_variants() -> None:
    assert faculty_catalog_context_from_staging_program({}) is None
    context = faculty_catalog_context_from_staging_program(
        {"sourceName": "technion-math-catalog", "programCode": "010001-1-000"}
    )
    assert context is not None
    assert context.faculty_id == "math"
    context2 = faculty_catalog_context_from_staging_program(
        {
            "metadata": {"facultyId": "faculty-biology"},
            "sourceName": "technion-biology-catalog",
            "programCode": "010002-1-000",
            "sourceMetadata": {"exportMode": "specialized"},
        }
    )
    assert context2 is not None
    assert context2.faculty_id == "biology"
    assert context2.export_mode == "specialized"


def test_faculty_context_production_key_prefix() -> None:
    context = faculty_catalog_context_from_document(
        {"source": {"facultyId": "dds"}, "programs": []}
    )
    assert context.production_key_prefix == "technion-dds"
    assert production_requirement_key("dds", "G1", "2025-2026") == "technion-dds:requirement:G1:2025-2026"
    assert (
        production_advisory_requirement_key("dds", "G1", "2025-2026")
        == "technion-dds:advisory-rule:req:G1:2025-2026"
    )


def test_faculty_catalog_export_dir_non_dds() -> None:
    path = faculty_catalog_export_dir("computer-science")
    assert path.name == "computer-science"


def test_validate_catalog_structure_generic_faculty_paths() -> None:
    program = MagicMock()
    program.programCode = "023023-1-000"
    program.totalCredits = 0
    program.requirementGroups = []
    doc = MagicMock()
    doc.programs = [program]
    doc.model_dump.return_value = {
        "source": {
            "facultyId": "computer-science",
            "expectedProgramCodes": ["023023-1-000"],
        },
        "programs": [{"programCode": "023023-1-000"}],
    }
    context = FacultyCatalogContext(
        faculty_id="computer-science",
        source_name="technion-computer-science-catalog",
        source_type="computer-science_catalog_curated_reviewed",
        expected_program_codes=("023023-1-000",),
        export_mode="specialized",
    )
    with pytest.raises(CatalogStagingImportError, match="totalCredits must be a positive"):
        validate_catalog_structure(doc, context=context)

    empty_doc = MagicMock()
    empty_doc.programs = []
    empty_doc.model_dump.return_value = {"source": {"facultyId": "computer-science"}, "programs": []}
    with pytest.raises(CatalogStagingImportError, match="at least one program"):
        validate_catalog_structure(empty_doc, context=context)


def test_generic_bucket_helpers() -> None:
    assert _slugify_bucket_label("מקצועות חובה") == "required-courses"
    assert _slugify_bucket_label("מקצועות העשרה") == "enrichment"
    assert _slugify_bucket_label("Free electives") == "free-elective"
    assert _canonical_bucket_slug("free-electives") == "free-elective"
    assert _missing_standard_technion_bucket_slugs({"enrichment", "physical-education", "free-electives"}) == set()
    assert _bucket_requirement_type("Physical education") == "enrichment"
    assert _bucket_requirement_type("Faculty electives") == "elective"
    assert _bucket_requirement_type("Core required") == "core"


def test_dedupe_requirement_groups_merges_course_refs_and_skips_blank_ids() -> None:
    merged = _dedupe_requirement_groups(
        [
            {"groupId": "", "courseReferences": [{"courseNumber": "01040001"}]},
            {
                "groupId": "010040-1-000:semester-1-matrix",
                "courseReferences": [{"courseNumber": "01040001"}],
            },
            {
                "groupId": "010040-1-000:semester-1-matrix",
                "courseReferences": [{"courseNumber": "01040002"}],
            },
        ]
    )
    assert len(merged) == 1
    assert {ref["courseNumber"] for ref in merged[0]["courseReferences"]} == {
        "01040001",
        "01040002",
    }


def test_slugify_bucket_label_falls_back_to_hash_for_unknown_hebrew() -> None:
    slug = _slugify_bucket_label("קטגוריה לא מוכרת")
    assert slug.startswith("bucket-")


def test_build_generic_program_without_program_code() -> None:
    page = WikiPage(
        slug="track-test",
        path=Path("/tmp/track-test.md"),
        frontmatter={},
        body="",
        english_body="**Track code:** TBD\n",
    )
    assert build_generic_program(page, faculty_id="math", pages={}) is None


def test_parse_credit_buckets_skips_invalid_rows() -> None:
    page = WikiPage(
        slug="track-test",
        path=Path("/tmp/track-test.md"),
        frontmatter={},
        body="",
        english_body=(
            "| Category | Credits |\n"
            "|---|---|\n"
            "| **Total** | 155.0 |\n"
            "| Required | not-a-number |\n"
            "| Electives | 12.0 |\n"
        ),
    )
    buckets = parse_credit_buckets_from_page(page)
    assert len(buckets) == 1


def test_export_faculty_vault_catalog_raises_when_no_programs(monkeypatch) -> None:
    monkeypatch.setattr(
        "app.vault.export_faculty_vault_catalog.discover_faculty_track_slugs",
        lambda pages, faculty_id: ["track-empty"],
    )
    monkeypatch.setattr(
        "app.vault.export_faculty_vault_catalog.build_generic_program",
        lambda page, faculty_id, pages: None,
    )
    with pytest.raises(ValueError, match="No exportable BSc track programs"):
        export_faculty_vault_catalog(faculty_id="math")


def test_build_quality_report_for_generic_faculty(mongo_database) -> None:
    from app.config import get_settings

    settings = get_settings()
    mongo_database[settings.staging_degree_programs_collection].insert_one(
        {
            "sourceName": "technion-math-catalog",
            "programCode": "010001-1-000",
            "totalCredits": 155.0,
            "signoffReview": {"reviewStatus": "ok"},
        }
    )
    mongo_database[settings.staging_degree_requirements_collection].insert_one(
        {
            "sourceName": "technion-math-catalog",
            "requirementGroup": {"groupId": "010001-1-000:core", "courseReferences": []},
        }
    )
    report = build_dds_staging_quality_report(mongo_database, settings=settings, faculty_id="math")
    assert report.counts.get("programs") == 1


def test_normalize_faculty_id_empty() -> None:
    from app.catalog.faculty_catalog_context import _normalize_faculty_id

    assert _normalize_faculty_id(None) == "unknown"
    assert _normalize_faculty_id("") == "unknown"


def test_discover_faculty_tracks_from_tags() -> None:
    from app.vault.export_faculty_vault_catalog import discover_faculty_track_slugs
    from app.vault.loader import WikiPage

    pages = {
        "track-tagged-only": WikiPage(
            slug="track-tagged-only",
            path=Path("/tmp/tagged.md"),
            frontmatter={"tags": ["faculty-math"]},
            body="",
            english_body="",
        )
    }
    assert discover_faculty_track_slugs(pages, "math") == ["track-tagged-only"]


def test_extract_program_code_multiline_pattern() -> None:
    from app.vault.export_faculty_vault_catalog import extract_program_code
    from app.vault.loader import WikiPage

    page = WikiPage(
        slug="track-test",
        path=Path("/tmp/track-test.md"),
        frontmatter={},
        body="",
        english_body="**Program code:** 010001-1-000\n",
    )
    assert extract_program_code(page) == "010001-1-000"


def test_parse_credit_buckets_skips_short_rows() -> None:
    from app.vault.export_faculty_vault_catalog import parse_credit_buckets_from_page
    from app.vault.loader import WikiPage

    page = WikiPage(
        slug="track-test",
        path=Path("/tmp/track-test.md"),
        frontmatter={},
        body="",
        english_body="| Category | Credits |\n|---|---|\n| Required |\n",
    )
    assert parse_credit_buckets_from_page(page) == []


def test_promotion_gate_filters_path_options_and_faculties_by_scope(mongo_database) -> None:
    from app.config import get_settings
    from app.promotion.dds_promotion_gate import build_promotion_gate_result

    settings = get_settings()
    source = "technion-math-catalog"
    mongo_database[settings.staging_degree_programs_collection].insert_one(
        {
            "sourceName": source,
            "programCode": "010001-1-000",
            "totalCredits": 155.0,
            "catalogVersion": "2025-2026",
            "isStaging": True,
            "productionEligible": False,
            "signoffReview": {"reviewStatus": "ok"},
            "curationReport": {"vaultSignoff": {"signoffSource": "manual"}},
        }
    )
    mongo_database[settings.staging_catalog_path_options_collection].insert_many(
        [
            {
                "sourceName": source,
                "optionKey": "track-math-a",
                "facultyId": "faculty-math",
                "stagingKey": "math:path:a",
            },
            {
                "sourceName": source,
                "optionKey": "track-physics-a",
                "facultyId": "faculty-physics",
                "stagingKey": "math:path:physics",
            },
        ]
    )
    mongo_database[settings.staging_catalog_faculties_collection].insert_many(
        [
            {"sourceName": source, "facultyId": "faculty-math", "stagingKey": "math:faculty"},
            {"sourceName": source, "facultyId": "faculty-physics", "stagingKey": "physics:faculty"},
        ]
    )
    mongo_database[settings.staging_courses_collection].insert_one(
        {"sourceName": "technion-course-json", "courseNumber": "01000101"}
    )
    mongo_database[settings.staging_course_offerings_collection].insert_one(
        {"courseNumber": "01000101", "stagingKey": "technion:offering:01000101"}
    )
    gate = build_promotion_gate_result(
        mongo_database,
        settings=settings,
        faculty_id="math",
        allow_warnings=True,
    )
    assert len(gate.plannedWrites.catalogPathOptions) == 1
    assert gate.plannedWrites.catalogPathOptions[0].identifier == "track-math-a"
    assert len(gate.plannedWrites.catalogFaculties) == 1
    assert gate.plannedWrites.catalogFaculties[0].identifier == "faculty-math"


def test_build_track_program_code_map_skips_missing_pages(monkeypatch) -> None:
    from app.vault.export_faculty_vault_catalog import build_track_program_code_map

    monkeypatch.setattr(
        "app.vault.export_faculty_vault_catalog.discover_faculty_track_slugs",
        lambda pages, faculty_id: ["missing-track"],
    )
    assert build_track_program_code_map({}, "math") == {}


def test_extract_program_code_falls_back_to_body_pattern(monkeypatch) -> None:
    from app.vault.export_faculty_vault_catalog import extract_program_code
    from app.vault.loader import WikiPage

    monkeypatch.setattr(
        "app.vault.export_faculty_vault_catalog.extract_field",
        lambda text, label: None,
    )
    page = WikiPage(
        slug="track-test",
        path=Path("/tmp/track-test.md"),
        frontmatter={},
        body="",
        english_body="**Program code:** 010001-1-000\n",
    )
    assert extract_program_code(page) == "010001-1-000"


def test_extract_program_code_falls_back_to_body_pattern_when_english_body_empty(monkeypatch) -> None:
    from app.vault.export_faculty_vault_catalog import extract_program_code
    from app.vault.loader import WikiPage

    monkeypatch.setattr(
        "app.vault.export_faculty_vault_catalog.extract_field",
        lambda text, label: None,
    )
    page = WikiPage(
        slug="track-test",
        path=Path("/tmp/track-test.md"),
        frontmatter={},
        body="**Program code:** 010002-1-000\n",
        english_body="",
    )
    assert extract_program_code(page) == "010002-1-000"


def test_build_generic_program_splits_technion_wide_electives_into_standard_buckets() -> None:
    from app.paths import catalog_vault_root
    from app.vault.loader import load_pages_by_slug, wiki_root

    pages = load_pages_by_slug(wiki_root(catalog_vault_root()))
    page = pages["track-computer-science-general-4year"]
    program = build_generic_program(page, faculty_id="computer-science", pages=pages)
    assert program is not None
    group_ids = {group["groupId"] for group in program["requirementGroups"]}
    code = program["programCode"]
    assert f"{code}:technion-wide-electives" not in group_ids
    assert f"{code}:enrichment" in group_ids
    assert f"{code}:free-elective" in group_ids
    assert f"{code}:physical-education" in group_ids
    assert f"{code}:enrichment-pool" in group_ids

    from app.vault.export_dds_catalog import technion_wide_elective_credit_split

    assert technion_wide_elective_credit_split(12.0) == (6.0, 4.0, 2.0)
    assert technion_wide_elective_credit_split(10.0) == (6.0, 2.0, 2.0)


def _assert_no_duplicate_group_ids(program: dict) -> None:
    from collections import Counter

    group_ids = [group["groupId"] for group in program["requirementGroups"]]
    duplicates = [group_id for group_id, count in Counter(group_ids).items() if count > 1]
    assert duplicates == []


def test_build_generic_program_dedupes_hebrew_credit_buckets_and_standard_technion_buckets() -> None:
    from app.paths import catalog_vault_root
    from app.vault.loader import load_pages_by_slug, wiki_root

    pages = load_pages_by_slug(wiki_root(catalog_vault_root()))
    education = build_generic_program(
        pages["track-education-computer-science"],
        faculty_id="education-science-technology",
        pages=pages,
    )
    mathematics = build_generic_program(
        pages["track-mathematics-bsc"],
        faculty_id="mathematics",
        pages=pages,
    )
    assert education is not None and mathematics is not None
    _assert_no_duplicate_group_ids(education)
    _assert_no_duplicate_group_ids(mathematics)
    assert any(
        group["groupId"].endswith(":required-courses")
        for group in education["requirementGroups"]
    )


def test_should_export_degree_program_skips_specializations_and_canonical_mirrors() -> None:
    from app.paths import catalog_vault_root
    from app.vault.export_faculty_vault_catalog import discover_faculty_track_slugs
    from app.vault.loader import load_pages_by_slug, wiki_root

    pages = load_pages_by_slug(wiki_root(catalog_vault_root()))
    assert should_export_degree_program(pages["track-biology-general"]) is True
    assert should_export_degree_program(pages["track-biology-human-development"]) is True
    assert should_export_degree_program(pages["track-computer-science-cyber"]) is False
    assert should_export_degree_program(pages["track-medicine-dual-computer-science"]) is False

    medicine_slugs = frozenset(discover_faculty_track_slugs(pages, "medicine"))
    assert should_export_degree_program(
        pages["track-medicine-dual-computer-science"],
        faculty_track_slugs=medicine_slugs,
    ) is False
    assert should_export_degree_program(
        pages["track-medicine-dual-biomedical-engineering"],
        faculty_track_slugs=medicine_slugs,
    ) is True

    chemistry_slugs = frozenset(discover_faculty_track_slugs(pages, "chemistry"))
    assert should_export_degree_program(
        pages["track-chemistry-materials-combined"],
        faculty_track_slugs=chemistry_slugs,
    ) is True


def test_should_export_degree_program_skips_non_primary_canonical_with_faculty_slugs(
    monkeypatch,
) -> None:
    page = WikiPage(
        slug="track-mirror",
        path=Path("/tmp/mirror.md"),
        frontmatter={"canonicalSlug": "track-canonical"},
        body="",
        english_body="",
    )
    monkeypatch.setattr(
        "app.vault.export_faculty_vault_catalog._track_selectable_as_primary",
        lambda candidate: False,
    )
    assert should_export_degree_program(
        page,
        faculty_track_slugs=frozenset({"track-mirror"}),
    ) is False


def test_export_biology_expected_program_codes_match_per_track_programs() -> None:
    biology_doc, _ = export_faculty_vault_catalog(faculty_id="biology")
    program_codes = [program["programCode"] for program in biology_doc["programs"]]
    assert biology_doc["source"]["expectedProgramCodes"] == sorted(program_codes)
    assert program_codes.count("013043-1-000") > 1


def test_export_cross_faculty_canonical_mirrors_have_elective_pools() -> None:
    chemistry_doc, _ = export_faculty_vault_catalog(faculty_id="chemistry")
    chemistry_program = next(
        program
        for program in chemistry_doc["programs"]
        if (program.get("metadata") or {}).get("wikiPage") == "track-chemistry-materials-combined"
    )
    chemistry_pools = [
        group
        for group in chemistry_program.get("requirementGroups") or []
        if (group.get("ruleExpression") or {}).get("operator") in {"choose_n", "choose_chain"}
        and (group.get("courseReferences") or [])
    ]
    assert chemistry_pools

    medicine_doc, _ = export_faculty_vault_catalog(faculty_id="medicine")
    medicine_program = next(
        program
        for program in medicine_doc["programs"]
        if (program.get("metadata") or {}).get("wikiPage")
        == "track-medicine-dual-biomedical-engineering"
    )
    medicine_pools = [
        group
        for group in medicine_program.get("requirementGroups") or []
        if (group.get("ruleExpression") or {}).get("operator") in {"choose_n", "choose_chain"}
        and (group.get("courseReferences") or [])
    ]
    assert medicine_pools


def test_export_faculty_vault_catalog_exports_each_primary_track_slug(
    monkeypatch,
) -> None:
    """Each exportable track slug gets its own program document (codes may repeat)."""
    program_code = "099999-1-000"
    pages = {
        "track-dup-a": WikiPage(
            slug="track-dup-a",
            path=Path("/tmp/track-dup-a.md"),
            frontmatter={"faculty": "faculty-test"},
            body="",
            english_body=f"**Track code:** {program_code}\n",
        ),
        "track-dup-b": WikiPage(
            slug="track-dup-b",
            path=Path("/tmp/track-dup-b.md"),
            frontmatter={"faculty": "faculty-test"},
            body="",
            english_body=f"**Track code:** {program_code}\n",
        ),
    }
    monkeypatch.setattr(
        "app.vault.export_faculty_vault_catalog.load_pages_by_slug",
        lambda root: pages,
    )
    monkeypatch.setattr(
        "app.vault.export_faculty_vault_catalog.discover_faculty_track_slugs",
        lambda loaded_pages, faculty_id: ["track-dup-a", "track-dup-b"],
    )
    monkeypatch.setattr(
        "app.vault.export_faculty_vault_catalog.build_generic_program",
        lambda page, faculty_id, pages: {
            "programCode": program_code,
            "metadata": {"wikiPage": page.slug},
            "requirementGroups": [],
            "totalCredits": 155.0,
        },
    )
    monkeypatch.setattr(
        "app.vault.export_faculty_vault_catalog.build_wiki_path_catalog",
        lambda **kwargs: {"faculties": [], "pathOptions": []},
    )
    monkeypatch.setattr(
        "app.vault.export_faculty_vault_catalog.apply_vault_signoff_to_catalog",
        lambda *args, **kwargs: None,
    )
    monkeypatch.setattr(
        "app.vault.export_faculty_vault_catalog.build_readiness_after_vault_signoff",
        lambda doc: {
            "counts": {},
            "blockingIssuesForStaging": [],
            "canImportToStaging": True,
        },
    )
    monkeypatch.setattr(
        "app.vault.export_faculty_vault_catalog.ReviewedCuratedCatalogDocument.model_validate",
        lambda doc: doc,
    )
    monkeypatch.setattr(
        "app.vault.export_faculty_vault_catalog.Phase8ReadinessCheck.model_validate",
        lambda readiness: readiness,
    )
    doc, _ = export_faculty_vault_catalog(faculty_id="test")
    assert len(doc["programs"]) == 2
    assert {program["metadata"]["wikiPage"] for program in doc["programs"]} == {
        "track-dup-a",
        "track-dup-b",
    }


def test_export_faculty_vault_catalog_exports_shared_code_per_track_slug() -> None:
    biology_doc, _ = export_faculty_vault_catalog(faculty_id="biology")
    biology_slugs = {(program["programCode"], program["metadata"]["wikiPage"]) for program in biology_doc["programs"]}
    assert ("013043-1-000", "track-biology-general") in biology_slugs
    assert ("013043-1-000", "track-biology-human-development") in biology_slugs
    assert len(biology_doc["programs"]) >= 4

    cs_doc, _ = export_faculty_vault_catalog(faculty_id="computer-science")
    cs_slugs = [program["metadata"]["wikiPage"] for program in cs_doc["programs"]]
    assert "track-computer-science-general-3year" in cs_slugs
    assert "track-computer-science-general-4year" in cs_slugs
    assert len(cs_doc["programs"]) >= 8


def test_export_faculty_vault_catalog_skips_duplicate_slug(monkeypatch) -> None:
    program_code = "099998-1-000"
    page = WikiPage(
        slug="track-once",
        path=Path("/tmp/track-once.md"),
        frontmatter={"faculty": "faculty-test"},
        body="",
        english_body=f"**Track code:** {program_code}\n",
    )
    monkeypatch.setattr(
        "app.vault.export_faculty_vault_catalog.load_pages_by_slug",
        lambda root: {"track-once": page},
    )
    monkeypatch.setattr(
        "app.vault.export_faculty_vault_catalog.discover_faculty_track_slugs",
        lambda loaded_pages, faculty_id: ["track-once", "track-once"],
    )
    monkeypatch.setattr(
        "app.vault.export_faculty_vault_catalog.build_wiki_path_catalog",
        lambda **kwargs: {"faculties": [], "pathOptions": []},
    )
    monkeypatch.setattr(
        "app.vault.export_faculty_vault_catalog.apply_vault_signoff_to_catalog",
        lambda *args, **kwargs: None,
    )
    monkeypatch.setattr(
        "app.vault.export_faculty_vault_catalog.build_readiness_after_vault_signoff",
        lambda doc: {
            "counts": {},
            "blockingIssuesForStaging": [],
            "canImportToStaging": True,
        },
    )
    monkeypatch.setattr(
        "app.vault.export_faculty_vault_catalog.ReviewedCuratedCatalogDocument.model_validate",
        lambda doc: doc,
    )
    monkeypatch.setattr(
        "app.vault.export_faculty_vault_catalog.Phase8ReadinessCheck.model_validate",
        lambda readiness: readiness,
    )
    doc, _ = export_faculty_vault_catalog(faculty_id="test")
    assert len(doc["programs"]) == 1


def test_semester_matrix_groups_merge_variant_headings() -> None:
    from app.paths import catalog_vault_root
    from app.vault.export_dds_catalog import _semester_matrix_groups
    from app.vault.loader import load_pages_by_slug, wiki_root

    pages = load_pages_by_slug(wiki_root(catalog_vault_root()))
    page = pages["track-electrical-engineering-physics"]
    groups = _semester_matrix_groups(page, "004141-1-000")
    semester_six = [group for group in groups if group["groupId"].endswith("semester-6-matrix")]
    assert len(semester_six) == 1
    assert len(semester_six[0]["courseReferences"]) > 0
