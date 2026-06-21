"""Tests for app/main.py CLI — run_* functions and main() dispatcher."""

from __future__ import annotations

import json
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import MagicMock, patch

import pytest

from app.main import (
    build_parser,
    main,
    run_export_vault_catalog,
    run_health,
    run_import_dds_catalog_staging,
    run_import_sample,
    run_import_technion_courses_staging,
    run_plan_dds_production_promotion,
    run_promote_dds_to_production,
    run_rollback_dds_production_promotion,
    run_validate_dds_staging_quality,
    run_validate_sample,
    run_verify_vault_production_parity,
)


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _settings(**kwargs):
    defaults = dict(
        service_name="data-engineering",
        environment="test",
        staging_courses_collection="staging_courses",
        staging_course_offerings_collection="staging_course_offerings",
        staging_degree_requirements_collection="staging_degree_requirements",
        staging_degree_programs_collection="staging_degree_programs",
        staging_catalog_rules_collection="staging_catalog_rules",
        staging_data_quality_reports_collection="staging_data_quality_reports",
        staging_ingestion_runs_collection="staging_ingestion_runs",
        mongo_uri="mongodb://localhost/test",
        mongo_db_name="test",
        log_level="INFO",
    )
    defaults.update(kwargs)
    return SimpleNamespace(**defaults)


# ---------------------------------------------------------------------------
# run_health
# ---------------------------------------------------------------------------

class TestRunHealth:
    def test_connected_returns_0(self, capsys):
        with (
            patch("app.main.get_settings", return_value=_settings()),
            patch("app.main.check_mongo_connectivity", return_value="connected"),
        ):
            code = run_health()

        assert code == 0
        payload = json.loads(capsys.readouterr().out)
        assert payload["mongo"] == "connected"
        assert payload["service"] == "data-engineering"

    def test_disconnected_returns_1(self, capsys):
        with (
            patch("app.main.get_settings", return_value=_settings()),
            patch("app.main.check_mongo_connectivity", return_value="disconnected"),
        ):
            code = run_health()

        assert code == 1
        payload = json.loads(capsys.readouterr().out)
        assert payload["mongo"] == "disconnected"


# ---------------------------------------------------------------------------
# run_validate_sample
# ---------------------------------------------------------------------------

class TestRunValidateSample:
    def test_returns_1_when_invalid_records_present(self, capsys):
        code = run_validate_sample()
        out = json.loads(capsys.readouterr().out)
        assert out["itemsInvalid"] > 0
        assert code == 1

    def test_counts_match_total_records(self, capsys):
        run_validate_sample()
        out = json.loads(capsys.readouterr().out)
        assert out["itemsRead"] == out["itemsValid"] + out["itemsInvalid"]


# ---------------------------------------------------------------------------
# run_import_sample
# ---------------------------------------------------------------------------

class TestRunImportSample:
    def test_completed_status_returns_0(self, capsys):
        mock_run = SimpleNamespace(
            status="completed",
            itemsRead=2,
            itemsValid=2,
            itemsInvalid=0,
            errors=[],
        )
        with (
            patch("app.main.get_database", return_value=MagicMock()),
            patch("app.main.get_settings", return_value=_settings()),
            patch("app.main.import_records_to_staging", return_value=mock_run),
        ):
            code = run_import_sample()

        assert code == 0
        out = json.loads(capsys.readouterr().out)
        assert out["status"] == "completed"

    def test_partial_status_returns_0(self, capsys):
        mock_run = SimpleNamespace(
            status="partial",
            itemsRead=3,
            itemsValid=2,
            itemsInvalid=1,
            errors=["one error"],
        )
        with (
            patch("app.main.get_database", return_value=MagicMock()),
            patch("app.main.get_settings", return_value=_settings()),
            patch("app.main.import_records_to_staging", return_value=mock_run),
        ):
            code = run_import_sample()

        assert code == 0

    def test_failed_status_returns_1(self, capsys):
        mock_run = SimpleNamespace(
            status="failed",
            itemsRead=0,
            itemsValid=0,
            itemsInvalid=0,
            errors=["db error"],
        )
        with (
            patch("app.main.get_database", return_value=MagicMock()),
            patch("app.main.get_settings", return_value=_settings()),
            patch("app.main.import_records_to_staging", return_value=mock_run),
        ):
            code = run_import_sample()

        assert code == 1


# ---------------------------------------------------------------------------
# run_export_vault_catalog
# ---------------------------------------------------------------------------

class TestRunExportVaultCatalog:
    def _make_catalog_export(self, tmp_path):
        catalog_file = tmp_path / "catalog.json"
        readiness_file = tmp_path / "readiness.json"
        document = {
            "programs": [
                {"programCode": "P001"},
            ]
        }
        readiness = {"counts": {"programs": 1}, "canImportToStaging": True}
        return catalog_file, readiness_file, document, readiness

    def test_success_returns_0(self, tmp_path, capsys):
        export_result = self._make_catalog_export(tmp_path)
        with patch("app.main.write_vault_catalog_export", return_value=export_result):
            code = run_export_vault_catalog(None, "dds", None, None, None)

        assert code == 0
        out = json.loads(capsys.readouterr().out)
        assert out["status"] == "ok"
        assert "P001" in out["programs"]

    def test_exception_returns_1(self, capsys):
        with patch("app.main.write_vault_catalog_export", side_effect=RuntimeError("boom")):
            code = run_export_vault_catalog(None, "dds", None, None, None)

        assert code == 1
        out = json.loads(capsys.readouterr().out)
        assert "error" in out

    def test_with_explicit_paths(self, tmp_path, capsys):
        export_result = self._make_catalog_export(tmp_path)
        with patch("app.main.write_vault_catalog_export", return_value=export_result) as mock_fn:
            run_export_vault_catalog(
                str(tmp_path),
                "dds",
                str(tmp_path / "out.json"),
                str(tmp_path / "readiness.json"),
                [str(tmp_path / "courses.json")],
            )
        args, kwargs = mock_fn.call_args
        assert kwargs["vault_path"] == tmp_path
        assert kwargs["faculty"] == "dds"


# ---------------------------------------------------------------------------
# run_import_dds_catalog_staging
# ---------------------------------------------------------------------------

class TestRunImportDdsCatalogStaging:
    def _summary(self, **overrides):
        defaults = dict(
            dryRun=False,
            programsUpserted=3,
            requirementsUpserted=10,
            rulesUpserted=5,
            courseReferencesObserved=20,
            manualReviewRequiredItems=0,
            warningsPreserved=0,
            stagingCollections={},
            ingestionRunId="run-1",
            ingestionStatus="completed",
        )
        defaults.update(overrides)
        return SimpleNamespace(**defaults)

    def test_dry_run_returns_0(self, capsys):
        with (
            patch("app.main.get_settings", return_value=_settings()),
            patch("app.main.import_dds_catalog_to_staging", return_value=self._summary(dryRun=True)),
        ):
            code = run_import_dds_catalog_staging(None, None, dry_run=True)

        assert code == 0
        out = json.loads(capsys.readouterr().out)
        assert out["dryRun"] is True
        assert "Dry run only" in out["note"]

    def test_live_run_with_mongo_connected(self, capsys):
        with (
            patch("app.main.get_settings", return_value=_settings()),
            patch("app.main.check_mongo_connectivity", return_value="connected"),
            patch("app.main.get_database", return_value=MagicMock()),
            patch("app.main.import_dds_catalog_to_staging", return_value=self._summary()),
        ):
            code = run_import_dds_catalog_staging(None, None, dry_run=False)

        assert code == 0

    def test_live_run_mongo_disconnected_returns_1(self, capsys):
        with (
            patch("app.main.get_settings", return_value=_settings()),
            patch("app.main.check_mongo_connectivity", return_value="disconnected"),
        ):
            code = run_import_dds_catalog_staging(None, None, dry_run=False)

        assert code == 1

    def test_file_not_found_returns_1(self, capsys):
        with (
            patch("app.main.get_settings", return_value=_settings()),
            patch("app.main.import_dds_catalog_to_staging", side_effect=FileNotFoundError("missing")),
        ):
            code = run_import_dds_catalog_staging(None, None, dry_run=True)

        assert code == 1

    def test_generic_exception_returns_1(self, capsys):
        with (
            patch("app.main.get_settings", return_value=_settings()),
            patch("app.main.import_dds_catalog_to_staging", side_effect=ValueError("unexpected")),
        ):
            code = run_import_dds_catalog_staging(None, None, dry_run=True)

        assert code == 1


# ---------------------------------------------------------------------------
# run_import_technion_courses_staging
# ---------------------------------------------------------------------------

class TestRunImportTechnionCoursesStaging:
    def _summary(self, **overrides):
        defaults = dict(
            dryRun=False,
            ddsOnly=False,
            filesRead=2,
            rawRecordsRead=100,
            validCourses=95,
            invalidRecords=5,
            uniqueCourses=90,
            ddsFacultyCourses=20,
            offeringsObserved=190,
            warnings=[],
            stagingCollections={},
            ingestionRunId="run-2",
            ingestionStatus="completed",
        )
        defaults.update(overrides)
        return SimpleNamespace(**defaults)

    def test_dry_run_returns_0(self, capsys):
        with (
            patch("app.main.get_settings", return_value=_settings()),
            patch("app.main.import_technion_courses_to_staging", return_value=self._summary(dryRun=True)),
        ):
            code = run_import_technion_courses_staging(None, dry_run=True, dds_only=False)

        assert code == 0

    def test_live_run_connected(self, capsys):
        with (
            patch("app.main.get_settings", return_value=_settings()),
            patch("app.main.check_mongo_connectivity", return_value="connected"),
            patch("app.main.get_database", return_value=MagicMock()),
            patch("app.main.import_technion_courses_to_staging", return_value=self._summary()),
        ):
            code = run_import_technion_courses_staging(["path.json"], dry_run=False, dds_only=True)

        assert code == 0

    def test_disconnected_returns_1(self, capsys):
        with (
            patch("app.main.get_settings", return_value=_settings()),
            patch("app.main.check_mongo_connectivity", return_value="disconnected"),
        ):
            code = run_import_technion_courses_staging(None, dry_run=False, dds_only=False)

        assert code == 1

    def test_file_not_found_returns_1(self, capsys):
        with (
            patch("app.main.get_settings", return_value=_settings()),
            patch("app.main.import_technion_courses_to_staging", side_effect=FileNotFoundError("x")),
        ):
            code = run_import_technion_courses_staging(None, dry_run=True, dds_only=False)

        assert code == 1

    def test_generic_error_returns_1(self, capsys):
        with (
            patch("app.main.get_settings", return_value=_settings()),
            patch("app.main.import_technion_courses_to_staging", side_effect=RuntimeError("oops")),
        ):
            code = run_import_technion_courses_staging(None, dry_run=True, dds_only=False)

        assert code == 1


# ---------------------------------------------------------------------------
# run_validate_dds_staging_quality
# ---------------------------------------------------------------------------

class TestRunValidateDdsStagingQuality:
    def _report(self, status="pass"):
        return SimpleNamespace(
            status=status,
            recommendation="promote",
            summary={"courses": 10},
            counts={"total": 10},
            blockersForProduction=[],
            blockersForApiMigration=[],
            warnings=[],
        )

    def test_disconnected_returns_1(self, capsys):
        with patch("app.main.check_mongo_connectivity", return_value="disconnected"):
            code = run_validate_dds_staging_quality(None, None, False)

        assert code == 1

    def test_pass_status_returns_0(self, capsys, tmp_path):
        with (
            patch("app.main.check_mongo_connectivity", return_value="connected"),
            patch("app.main.get_settings", return_value=_settings()),
            patch("app.main.get_database", return_value=MagicMock()),
            patch("app.main.run_dds_staging_quality_review", return_value=self._report("pass")),
        ):
            code = run_validate_dds_staging_quality(
                str(tmp_path / "q.json"), str(tmp_path / "q.md"), False
            )

        assert code == 0

    def test_needs_fixes_returns_1(self, capsys, tmp_path):
        with (
            patch("app.main.check_mongo_connectivity", return_value="connected"),
            patch("app.main.get_settings", return_value=_settings()),
            patch("app.main.get_database", return_value=MagicMock()),
            patch("app.main.run_dds_staging_quality_review", return_value=self._report("needs-fixes")),
        ):
            code = run_validate_dds_staging_quality(None, None, False)

        assert code == 1

    def test_exception_returns_1(self, capsys):
        with (
            patch("app.main.check_mongo_connectivity", return_value="connected"),
            patch("app.main.get_settings", return_value=_settings()),
            patch("app.main.get_database", return_value=MagicMock()),
            patch("app.main.run_dds_staging_quality_review", side_effect=RuntimeError("db fail")),
        ):
            code = run_validate_dds_staging_quality(None, None, False)

        assert code == 1


# ---------------------------------------------------------------------------
# run_plan_dds_production_promotion
# ---------------------------------------------------------------------------

class TestRunPlanDdsProductionPromotion:
    def _gate(self, gate_status="pass"):
        planned = SimpleNamespace(counts={"programs": 3})
        gate = SimpleNamespace(
            gateStatus=gate_status,
            canPromote=gate_status != "fail",
            dryRun=True,
            plannedWrites=planned,
            blockers=[],
            warnings=[],
        )
        return SimpleNamespace(gate=gate)

    def test_disconnected_returns_1(self, capsys):
        with patch("app.main.check_mongo_connectivity", return_value="disconnected"):
            code = run_plan_dds_production_promotion(None, None, False, True)

        assert code == 1

    def test_pass_gate_returns_0(self, capsys, tmp_path):
        mock_db = MagicMock()
        mock_db.__getitem__.return_value.count_documents.return_value = 0
        with (
            patch("app.main.check_mongo_connectivity", return_value="connected"),
            patch("app.main.get_settings", return_value=_settings()),
            patch("app.main.get_database", return_value=mock_db),
            patch("app.main.PRODUCTION_COLLECTION_NAMES", ["degree_programs"]),
            patch("app.main.run_promotion_gate_plan", return_value=self._gate("pass")),
        ):
            code = run_plan_dds_production_promotion(
                str(tmp_path / "p.json"), str(tmp_path / "p.md"), False, True
            )

        assert code == 0

    def test_fail_gate_returns_1(self, capsys, tmp_path):
        mock_db = MagicMock()
        mock_db.__getitem__.return_value.count_documents.return_value = 0
        with (
            patch("app.main.check_mongo_connectivity", return_value="connected"),
            patch("app.main.get_settings", return_value=_settings()),
            patch("app.main.get_database", return_value=mock_db),
            patch("app.main.PRODUCTION_COLLECTION_NAMES", ["degree_programs"]),
            patch("app.main.run_promotion_gate_plan", return_value=self._gate("fail")),
        ):
            code = run_plan_dds_production_promotion(None, None, False, True)

        assert code == 1

    def test_exception_returns_1(self, capsys):
        mock_db = MagicMock()
        mock_db.__getitem__.return_value.count_documents.return_value = 0
        with (
            patch("app.main.check_mongo_connectivity", return_value="connected"),
            patch("app.main.get_settings", return_value=_settings()),
            patch("app.main.get_database", return_value=mock_db),
            patch("app.main.PRODUCTION_COLLECTION_NAMES", ["degree_programs"]),
            patch("app.main.run_promotion_gate_plan", side_effect=RuntimeError("boom")),
        ):
            code = run_plan_dds_production_promotion(None, None, False, True)

        assert code == 1


# ---------------------------------------------------------------------------
# run_promote_dds_to_production
# ---------------------------------------------------------------------------

class TestRunPromoteDdsToProduction:
    def _result(self, run_status="completed", gate_status="pass", writes_performed=True):
        run = SimpleNamespace(
            promotionRunId="promo-abc",
            status=run_status,
            countsPlanned={"programs": 3},
            countsWritten={"programs": 3},
            productionCollectionCountsBefore={},
            productionCollectionCountsAfter={},
            errors=[],
        )
        planned = SimpleNamespace(counts={"programs": 3})
        gate = SimpleNamespace(
            gateStatus=gate_status,
            canPromote=gate_status != "fail",
            dryRun=False,
            plannedWrites=planned,
        )
        return SimpleNamespace(
            promotionRun=run,
            gate=gate,
            productionWritesPerformed=writes_performed,
        )

    def test_disconnected_returns_1(self, capsys):
        with patch("app.main.check_mongo_connectivity", return_value="disconnected"):
            code = run_promote_dds_to_production(True, False, True, None, None)

        assert code == 1

    def test_dry_run_no_confirm_returns_2(self, capsys):
        mock_db = MagicMock()
        mock_db.__getitem__.return_value.count_documents.return_value = 0
        with (
            patch("app.main.check_mongo_connectivity", return_value="connected"),
            patch("app.main.get_settings", return_value=_settings()),
            patch("app.main.get_database", return_value=mock_db),
            patch("app.main.PRODUCTION_COLLECTION_NAMES", []),
            patch("app.main.run_dds_production_promotion", return_value=self._result()),
        ):
            code = run_promote_dds_to_production(False, False, True, None, None)

        assert code == 2

    def test_confirmed_and_succeeded_returns_0(self, capsys):
        mock_db = MagicMock()
        mock_db.__getitem__.return_value.count_documents.return_value = 0
        with (
            patch("app.main.check_mongo_connectivity", return_value="connected"),
            patch("app.main.get_settings", return_value=_settings()),
            patch("app.main.get_database", return_value=mock_db),
            patch("app.main.PRODUCTION_COLLECTION_NAMES", []),
            patch("app.main.run_dds_production_promotion", return_value=self._result("completed", "pass")),
        ):
            code = run_promote_dds_to_production(True, False, True, None, None)

        assert code == 0

    def test_failed_run_returns_1(self, capsys):
        mock_db = MagicMock()
        mock_db.__getitem__.return_value.count_documents.return_value = 0
        with (
            patch("app.main.check_mongo_connectivity", return_value="connected"),
            patch("app.main.get_settings", return_value=_settings()),
            patch("app.main.get_database", return_value=mock_db),
            patch("app.main.PRODUCTION_COLLECTION_NAMES", []),
            patch("app.main.run_dds_production_promotion", return_value=self._result("failed", "pass")),
        ):
            code = run_promote_dds_to_production(True, False, True, None, None)

        assert code == 1


# ---------------------------------------------------------------------------
# run_rollback_dds_production_promotion
# ---------------------------------------------------------------------------

class TestRunRollbackDdsProductionPromotion:
    def test_missing_run_id_returns_1(self, capsys):
        code = run_rollback_dds_production_promotion(None, False)
        assert code == 1

    def test_disconnected_returns_1(self, capsys):
        with patch("app.main.check_mongo_connectivity", return_value="disconnected"):
            code = run_rollback_dds_production_promotion("promo-abc", True)
        assert code == 1

    def test_success_returns_0(self, capsys):
        with (
            patch("app.main.check_mongo_connectivity", return_value="connected"),
            patch("app.main.get_database", return_value=MagicMock()),
            patch("app.main.run_dds_production_rollback", return_value={"status": "ok"}),
        ):
            code = run_rollback_dds_production_promotion("promo-abc", True)
        assert code == 0

    def test_error_without_confirm_returns_2(self, capsys):
        with (
            patch("app.main.check_mongo_connectivity", return_value="connected"),
            patch("app.main.get_database", return_value=MagicMock()),
            patch("app.main.run_dds_production_rollback", return_value={"error": "not found"}),
        ):
            code = run_rollback_dds_production_promotion("promo-abc", False)
        assert code == 2

    def test_error_with_confirm_returns_1(self, capsys):
        with (
            patch("app.main.check_mongo_connectivity", return_value="connected"),
            patch("app.main.get_database", return_value=MagicMock()),
            patch("app.main.run_dds_production_rollback", return_value={"error": "oops"}),
        ):
            code = run_rollback_dds_production_promotion("promo-abc", True)
        assert code == 1


# ---------------------------------------------------------------------------
# run_verify_vault_production_parity
# ---------------------------------------------------------------------------

class TestRunVerifyVaultProductionParity:
    def _parity_result(self, status="pass"):
        return SimpleNamespace(
            status=status,
            wiki_root="/wiki",
            exported_at="2025-01-01T00:00:00+00:00",
            expected_hard_count=5,
            expected_advisory_count=3,
            production_hard_count=5,
            production_advisory_count=3,
            missing_in_production=[],
            extra_in_production=[],
            classification_mismatches=[],
            field_mismatches=[],
            matched_groups=8,
            ok=status == "pass",
        )

    def test_disconnected_returns_1(self, capsys):
        with patch("app.main.check_mongo_connectivity", return_value="disconnected"):
            code = run_verify_vault_production_parity(None, "dds", None, None)
        assert code == 1

    def test_pass_returns_0(self, capsys, tmp_path):
        parity = self._parity_result("pass")
        with (
            patch("app.main.check_mongo_connectivity", return_value="connected"),
            patch("app.main.get_database", return_value=MagicMock()),
            patch(
                "app.vault.verify_vault_production_parity.verify_vault_production_parity",
                return_value=parity,
            ),
            patch(
                "app.vault.verify_vault_production_parity.write_parity_report",
                return_value=(tmp_path / "r.json", tmp_path / "r.md"),
            ),
        ):
            code = run_verify_vault_production_parity(None, "dds", None, None)

        assert code == 0

    def test_fail_returns_1(self, capsys, tmp_path):
        parity = self._parity_result("fail")
        with (
            patch("app.main.check_mongo_connectivity", return_value="connected"),
            patch("app.main.get_database", return_value=MagicMock()),
            patch(
                "app.vault.verify_vault_production_parity.verify_vault_production_parity",
                return_value=parity,
            ),
            patch(
                "app.vault.verify_vault_production_parity.write_parity_report",
                return_value=(tmp_path / "r.json", tmp_path / "r.md"),
            ),
        ):
            code = run_verify_vault_production_parity(None, "dds", None, None)

        assert code == 1


# ---------------------------------------------------------------------------
# build_parser
# ---------------------------------------------------------------------------

class TestBuildParser:
    def test_health_command(self):
        parser = build_parser()
        args = parser.parse_args(["health"])
        assert args.command == "health"

    def test_validate_sample_command(self):
        args = build_parser().parse_args(["validate-sample"])
        assert args.command == "validate-sample"

    def test_dry_run_flag(self):
        args = build_parser().parse_args(["import-dds-catalog-staging", "--dry-run"])
        assert args.dry_run is True

    def test_dds_only_flag(self):
        args = build_parser().parse_args(["import-technion-courses-staging", "--dds-only"])
        assert args.dds_only is True

    def test_confirm_dangerous_flag(self):
        args = build_parser().parse_args(
            ["promote-dds-to-production", "--i-confirm-dangerous-production-write"]
        )
        assert args.confirm_dangerous is True

    def test_promotion_run_id(self):
        args = build_parser().parse_args(
            ["rollback-dds-production-promotion", "--promotion-run-id", "abc123"]
        )
        assert args.promotion_run_id == "abc123"

    def test_course_json_repeatable(self):
        args = build_parser().parse_args(
            ["import-technion-courses-staging", "--course-json", "a.json", "--course-json", "b.json"]
        )
        assert args.course_json_paths == ["a.json", "b.json"]

    def test_no_allow_warnings(self):
        args = build_parser().parse_args(
            ["plan-dds-production-promotion", "--no-allow-warnings"]
        )
        assert args.allow_warnings is False

    def test_allow_warnings_default_true(self):
        args = build_parser().parse_args(["plan-dds-production-promotion"])
        assert args.allow_warnings is True


# ---------------------------------------------------------------------------
# main() dispatcher
# ---------------------------------------------------------------------------

class TestMain:
    def test_health_command_end_to_end(self, capsys):
        with (
            patch("app.main.configure_logging"),
            patch("app.main.check_mongo_connectivity", return_value="connected"),
            patch("app.main.get_settings", return_value=_settings()),
            patch("app.main.close_mongo_client"),
        ):
            code = main(["health"])

        assert code == 0

    def test_validate_sample_command(self, capsys):
        with (
            patch("app.main.configure_logging"),
            patch("app.main.close_mongo_client"),
        ):
            code = main(["validate-sample"])

        assert isinstance(code, int)

    def test_import_sample_command(self, capsys):
        mock_run = SimpleNamespace(
            status="completed",
            itemsRead=1,
            itemsValid=1,
            itemsInvalid=0,
            errors=[],
        )
        with (
            patch("app.main.configure_logging"),
            patch("app.main.get_database", return_value=MagicMock()),
            patch("app.main.get_settings", return_value=_settings()),
            patch("app.main.import_records_to_staging", return_value=mock_run),
            patch("app.main.close_mongo_client"),
        ):
            code = main(["import-sample"])

        assert code == 0

    def test_export_vault_catalog_command(self, tmp_path, capsys):
        document = {"programs": [{"programCode": "P001"}]}
        readiness = {"counts": {}, "canImportToStaging": True}
        with (
            patch("app.main.configure_logging"),
            patch(
                "app.main.write_vault_catalog_export",
                return_value=(tmp_path / "c.json", tmp_path / "r.json", document, readiness),
            ),
            patch("app.main.close_mongo_client"),
        ):
            code = main(["export-vault-catalog"])

        assert code == 0

    def test_import_dds_catalog_staging_dry_run(self, capsys):
        summary = SimpleNamespace(
            dryRun=True,
            programsUpserted=0,
            requirementsUpserted=0,
            rulesUpserted=0,
            courseReferencesObserved=0,
            manualReviewRequiredItems=0,
            warningsPreserved=0,
            stagingCollections={},
            ingestionRunId=None,
            ingestionStatus="dry-run",
        )
        with (
            patch("app.main.configure_logging"),
            patch("app.main.get_settings", return_value=_settings()),
            patch("app.main.import_dds_catalog_to_staging", return_value=summary),
            patch("app.main.close_mongo_client"),
        ):
            code = main(["import-dds-catalog-staging", "--dry-run"])

        assert code == 0

    def test_import_technion_courses_staging_dry_run(self, capsys):
        summary = SimpleNamespace(
            dryRun=True,
            ddsOnly=False,
            filesRead=0,
            rawRecordsRead=0,
            validCourses=0,
            invalidRecords=0,
            uniqueCourses=0,
            ddsFacultyCourses=0,
            offeringsObserved=0,
            warnings=[],
            stagingCollections={},
            ingestionRunId=None,
            ingestionStatus="dry-run",
        )
        with (
            patch("app.main.configure_logging"),
            patch("app.main.get_settings", return_value=_settings()),
            patch("app.main.import_technion_courses_to_staging", return_value=summary),
            patch("app.main.close_mongo_client"),
        ):
            code = main(["import-technion-courses-staging", "--dry-run"])

        assert code == 0

    def test_close_mongo_called_even_on_exception(self):
        close_mock = MagicMock()
        with (
            patch("app.main.configure_logging"),
            patch("app.main.check_mongo_connectivity", side_effect=RuntimeError("db error")),
            patch("app.main.get_settings", return_value=_settings()),
            patch("app.main.close_mongo_client", close_mock),
        ):
            with pytest.raises(RuntimeError):
                main(["health"])

        close_mock.assert_called_once()
