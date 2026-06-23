"""Additional coverage for wiki path catalog, promotion mappers, and OCR resolution."""

from __future__ import annotations

from pathlib import Path
from types import SimpleNamespace
from unittest.mock import MagicMock, patch

import pytest

from app.config import get_settings
from app.promotion.dds_production_promoter import (
    ProductionPromotionError,
    build_production_documents,
    map_staging_faculty_to_production,
    map_staging_path_option_to_production,
)
from app.promotion.dds_promotion_gate import _bounded_message, build_promotion_gate_result
from app.vault.loader import WikiPage
from app.vault.ocr_course_resolution import apply_ocr_resolutions_to_catalog, suggest_ocr_correction
from app.vault.verify_vault_path_catalog_parity import verify_vault_path_catalog_parity
from app.vault.wiki_path_catalog import (
    _entity_prefix_options,
    _graduate_options,
    _graduate_study_levels,
    _page_description,
    _section_catalog_meta,
    _specialization_options,
    _study_levels_from_text,
    _track_options,
    build_wiki_path_catalog,
)
from tests.test_dds_promotion_gate import _seed_signed_off_promotion_staging

VAULT_ROOT = Path(__file__).resolve().parents[1] / "data" / "catalog_valut"


class TestPromotionMappers:
    def test_map_staging_path_option_to_production(self):
        doc = map_staging_path_option_to_production(
            {
                "optionKey": "technion:dds:track-dne",
                "institutionId": "technion",
                "facultyId": "faculty-dds",
                "wikiSlug": "track-data-information-engineering",
                "kind": "bsc_track",
                "nameHe": "הנדסת נתונים ומידע",
                "selectableAsPrimary": True,
                "duration": "4 years (8 semesters)",
                "totalCreditsRequired": "155",
                "catalogYear": 2025,
            },
            promotion_run_id="run-1",
            promoted_at="2025-01-01T00:00:00+00:00",
            catalog_version="2025-2026",
        )
        assert doc["duration"] == "4 years (8 semesters)"
        assert doc["totalCreditsRequired"] == "155"
        assert "path-option" in doc["productionKey"]

    def test_map_staging_faculty_to_production(self):
        doc = map_staging_faculty_to_production(
            {
                "facultyId": "faculty-dds",
                "institutionId": "technion",
                "wikiSlug": "faculty-dds",
                "nameHe": "הנדסת נתונים",
                "aliases": ["dds"],
                "catalogYear": 2025,
            },
            promotion_run_id="run-1",
            promoted_at="2025-01-01T00:00:00+00:00",
            catalog_version="2025-2026",
        )
        assert doc["facultyId"] == "faculty-dds"
        assert "faculty" in doc["productionKey"]


class TestPromotionGatePathCatalog:
    def test_gate_truncated_check_stores_full_message(self, mongo_database):
        settings = get_settings()
        for index in range(5):
            mongo_database[settings.staging_degree_requirements_collection].insert_one(
                {
                    "stagingKey": f"req-long-{index}",
                    "sourceName": "technion-dds-catalog",
                    "requirementGroup": {
                        "groupId": f"unsigned-group-{index}-" + ("x" * 150),
                        "ruleExpression": {"type": "semester_matrix"},
                    },
                    "ruleIsExecutable": False,
                }
            )
        result = build_promotion_gate_result(mongo_database, settings=settings, allow_warnings=True)
        check = next(
            item for item in result.checks if item.checkId == "policy.non_executable_groups_signed_off"
        )
        assert "fullMessage" in check.details

    def test_gate_plan_includes_path_options_and_faculties(self, mongo_database):
        _seed_signed_off_promotion_staging(mongo_database)
        settings = get_settings()
        mongo_database[settings.staging_catalog_path_options_collection].insert_one(
            {
                "sourceName": "technion-dds-catalog",
                "stagingKey": "path-opt-1",
                "optionKey": "technion:dds:track-dne",
                "facultyId": "faculty-dds",
            }
        )
        mongo_database[settings.staging_catalog_faculties_collection].insert_one(
            {
                "sourceName": "technion-dds-catalog",
                "stagingKey": "faculty-1",
                "facultyId": "faculty-dds",
            }
        )
        result = build_promotion_gate_result(mongo_database, settings=settings, allow_warnings=True)
        plan = result.plannedWrites
        assert any(item.itemType == "catalog_path_option" for item in plan.catalogPathOptions)
        assert any(item.itemType == "catalog_faculty" for item in plan.catalogFaculties)


class TestBoundedMessage:
    def test_truncates_overlong_messages(self):
        long_message = "x" * 600
        bounded = _bounded_message(long_message, max_length=500)
        assert len(bounded) <= 500
        assert bounded.endswith("…")


class TestOcrCourseResolutionExtras:
    def test_known_ocr_removal_reason(self):
        target, reason = suggest_ocr_correction("02300401", ingestible_course_numbers=set())
        assert target is None
        assert reason == "known-ocr-removal"

    def test_deduplicates_corrected_references(self):
        document = {
            "programs": [
                {
                    "programCode": "009216-1-000",
                    "requirementGroups": [
                        {
                            "groupId": "g1",
                            "courseReferences": [
                                {"courseNumber": "00906292"},
                                {"courseNumber": "00906292"},
                            ],
                        }
                    ],
                }
            ],
            "curationReport": {},
        }
        apply_ocr_resolutions_to_catalog(
            document,
            ingestible_course_numbers={"00960292"},
        )
        refs = document["programs"][0]["requirementGroups"][0]["courseReferences"]
        assert len(refs) == 1
        assert refs[0]["courseNumber"] == "00960292"

    def test_skips_empty_course_numbers(self):
        document = {
            "programs": [
                {
                    "programCode": "009216-1-000",
                    "requirementGroups": [
                        {
                            "groupId": "g1",
                            "courseReferences": [{"courseNumber": ""}, {"courseNumber": "00940345"}],
                        }
                    ],
                }
            ],
            "curationReport": {},
        }
        apply_ocr_resolutions_to_catalog(document, ingestible_course_numbers={"00940345"})
        refs = document["programs"][0]["requirementGroups"][0]["courseReferences"]
        assert len(refs) == 1


class TestWikiPathCatalogHelpers:
    def test_study_levels_detect_phd_and_mba(self):
        assert "PhD" in _study_levels_from_text("Ph.D program requirements")
        assert "MBA" in _study_levels_from_text("MBA track overview")

    def test_graduate_study_levels_default(self):
        assert _graduate_study_levels("Generic title", "overview") == ["MSc", "PhD"]

    def test_page_description_skips_metadata_lines(self):
        page = WikiPage(
            slug="program-test",
            path=Path("program-test.md"),
            frontmatter={"title": "Test", "title_he": "בדיקה"},
            body="",
            english_body="**Duration:** 4 years\nReal description line.",
        )
        assert _page_description(page) == "Real description line."

    def test_section_catalog_meta_from_bullet_duration(self):
        duration, credits = _section_catalog_meta("- **Duration:** 2 years\n**Total credits:** 30")
        assert duration == "2 years"
        assert credits == "30"

    def test_page_description_returns_none_for_empty_body(self):
        page = WikiPage(
            slug="program-empty",
            path=Path("program-empty.md"),
            frontmatter={"title": "Empty"},
            body="",
            english_body="   ",
        )
        assert _page_description(page) is None

    def test_page_description_stops_at_horizontal_rule(self):
        page = WikiPage(
            slug="program-hr",
            path=Path("program-hr.md"),
            frontmatter={"title": "HR"},
            body="",
            english_body="Intro line.\n---\nIgnored tail.",
        )
        assert _page_description(page) == "Intro line."

    def test_scoped_catalog_excludes_other_faculties(self):
        catalog = build_wiki_path_catalog(
            wiki_path=VAULT_ROOT / "wiki",
            track_program_codes={"track-data-information-engineering": "009216-1-000"},
            catalog_year=2025,
            catalog_version="2025-2026",
            scope_faculty_id="faculty-chemistry",
        )
        assert catalog["pathOptions"] == []

    def test_track_options_skips_missing_pages(self):
        options = _track_options(
            {},
            institution_id="technion",
            fallback_faculty_id="faculty-dds",
            track_program_codes={"missing-track": "009216-1-000"},
            scope_faculty_id=None,
        )
        assert options == []

    def test_track_options_includes_page_when_scope_unset(self):
        page = WikiPage(
            slug="track-data-information-engineering",
            path=Path("track-data-information-engineering.md"),
            frontmatter={"title": "Data Engineering", "title_he": "הנדסת נתונים"},
            body="",
            english_body="Program overview.",
        )
        options = _track_options(
            {"track-data-information-engineering": page},
            institution_id="technion",
            fallback_faculty_id="faculty-dds",
            track_program_codes={"track-data-information-engineering": "009216-1-000"},
            scope_faculty_id=None,
        )
        assert len(options) == 1
        assert options[0]["kind"] == "bsc_track"


class TestPathCatalogParityMismatch:
    def test_reports_field_mismatch(self, mongo_database, monkeypatch):
        from app.vault.export_dds_catalog import export_vault_catalog

        document, _ = export_vault_catalog(vault_path=VAULT_ROOT, faculty="dds")
        settings = get_settings()
        option = document["pathOptions"][0].copy()
        option["duration"] = "wrong-duration"
        mongo_database[settings.production_catalog_path_options_collection].delete_many({})
        mongo_database[settings.production_catalog_path_options_collection].insert_many(
            document["pathOptions"]
        )
        mongo_database[settings.production_catalog_path_options_collection].update_one(
            {"optionKey": option["optionKey"]},
            {"$set": {"duration": "wrong-duration"}},
        )
        if document.get("faculties"):
            mongo_database[settings.production_catalog_faculties_collection].delete_many({})
            mongo_database[settings.production_catalog_faculties_collection].insert_many(
                document["faculties"]
            )

        result = verify_vault_path_catalog_parity(
            mongo_database,
            settings=settings,
            vault_path=VAULT_ROOT,
            faculty="dds",
        )
        assert result.ok is False
        assert result.field_mismatches

    def test_skips_field_compare_for_missing_production_options(self, mongo_database):
        from app.vault.export_dds_catalog import export_vault_catalog

        document, _ = export_vault_catalog(vault_path=VAULT_ROOT, faculty="dds")
        settings = get_settings()
        if document.get("faculties"):
            mongo_database[settings.production_catalog_faculties_collection].delete_many({})
            mongo_database[settings.production_catalog_faculties_collection].insert_many(
                document["faculties"]
            )
        mongo_database[settings.production_catalog_path_options_collection].delete_many({})

        result = verify_vault_path_catalog_parity(
            mongo_database,
            settings=settings,
            vault_path=VAULT_ROOT,
            faculty="dds",
        )
        assert result.ok is False
        assert result.missing_path_options


class TestBuildProductionDocumentPathCatalog:
    def _make_gate_with_items(self, plan_override):
        from app.models.promotion import PromotionGateResult, PromotionPolicy

        gate = MagicMock(spec=PromotionGateResult)
        gate.catalogVersion = "2025-2026"
        gate.plannedWrites = plan_override
        gate.policiesApplied = PromotionPolicy(
            nonExecutableRulesPolicy="advisory-only",
            productionExcludedCoursePolicy="omit-from-production-do-not-ingest",
            productionExcludedCourseNumbers=[],
        )
        return gate

    def test_missing_staging_path_option(self):
        plan = MagicMock()
        plan.degreePrograms = []
        plan.hardDegreeRequirements = []
        plan.advisoryCatalogRules = []
        plan.courses = []
        plan.courseOfferings = []
        plan.catalogPathOptions = [SimpleNamespace(stagingKey="missing-path")]
        plan.catalogFaculties = []
        plan.skippedItems = []
        gate = self._make_gate_with_items(plan)
        settings = get_settings()

        with patch(
            "app.promotion.dds_production_promoter._load_staging_by_key",
            side_effect=[{}, {}, {}, {}, {}, {}, {}],
        ):
            with pytest.raises(ProductionPromotionError, match="Missing staging path option"):
                build_production_documents(
                    MagicMock(),
                    gate,
                    settings=settings,
                    promotion_run_id="r1",
                    promoted_at="ts",
                )

    def test_missing_staging_faculty(self):
        plan = MagicMock()
        plan.degreePrograms = []
        plan.hardDegreeRequirements = []
        plan.advisoryCatalogRules = []
        plan.courses = []
        plan.courseOfferings = []
        plan.catalogPathOptions = []
        plan.catalogFaculties = [SimpleNamespace(stagingKey="missing-faculty")]
        plan.skippedItems = []
        gate = self._make_gate_with_items(plan)
        settings = get_settings()

        with patch(
            "app.promotion.dds_production_promoter._load_staging_by_key",
            side_effect=[{}, {}, {}, {}, {}, {}, {}],
        ):
            with pytest.raises(ProductionPromotionError, match="Missing staging faculty"):
                build_production_documents(
                    MagicMock(),
                    gate,
                    settings=settings,
                    promotion_run_id="r1",
                    promoted_at="ts",
                )

    def test_build_production_includes_path_option_and_faculty(self):
        staging_path = {
            "stagingKey": "path-1",
            "optionKey": "technion:dds:track-dne",
            "institutionId": "technion",
            "facultyId": "faculty-dds",
            "wikiSlug": "track-data-information-engineering",
            "kind": "bsc_track",
            "nameHe": "הנדסת נתונים ומידע",
            "selectableAsPrimary": True,
            "catalogYear": 2025,
        }
        staging_faculty = {
            "stagingKey": "fac-1",
            "facultyId": "faculty-dds",
            "institutionId": "technion",
            "wikiSlug": "faculty-dds",
            "nameHe": "הנדסת נתונים",
            "aliases": ["dds"],
            "catalogYear": 2025,
        }
        plan = MagicMock()
        plan.degreePrograms = []
        plan.hardDegreeRequirements = []
        plan.advisoryCatalogRules = []
        plan.courses = []
        plan.courseOfferings = []
        plan.catalogPathOptions = [SimpleNamespace(stagingKey="path-1")]
        plan.catalogFaculties = [SimpleNamespace(stagingKey="fac-1")]
        plan.skippedItems = []
        gate = self._make_gate_with_items(plan)
        settings = get_settings()

        with patch(
            "app.promotion.dds_production_promoter._load_staging_by_key",
            side_effect=[
                {},
                {},
                {},
                {},
                {},
                {"path-1": staging_path},
                {"fac-1": staging_faculty},
            ],
        ):
            documents, _planned_keys = build_production_documents(
                MagicMock(),
                gate,
                settings=settings,
                promotion_run_id="r1",
                promoted_at="ts",
            )

        assert len(documents[settings.production_catalog_path_options_collection]) == 1
        assert len(documents[settings.production_catalog_faculties_collection]) == 1
