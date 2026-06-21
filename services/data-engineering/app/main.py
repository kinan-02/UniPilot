"""CLI entry point for data-engineering ingestion tasks."""

import argparse
import json
import sys
from pathlib import Path

from app.config import get_settings
from app.db import check_mongo_connectivity, close_mongo_client, get_database
from app.importers.dds_catalog_staging_importer import import_dds_catalog_to_staging
from app.importers.technion_course_staging_importer import import_technion_courses_to_staging
from app.importers.staging_importer import import_records_to_staging
from app.logging_config import configure_logging
from app.sources.sample_data import (
    INVALID_SAMPLE_COURSE,
    SAMPLE_COURSES,
    SAMPLE_DEGREE_REQUIREMENTS,
    SAMPLE_SOURCE_NAME,
    SAMPLE_SOURCE_TYPE,
)
from app.promotion.dds_promotion_gate import (
    default_promotion_json_path,
    default_promotion_md_path,
    run_promotion_gate_plan,
)
from app.promotion.dds_production_promoter import (
    default_production_promotion_json_path,
    default_production_promotion_md_path,
    run_dds_production_promotion,
    run_dds_production_rollback,
)
from app.importers.dds_catalog_staging_importer import PRODUCTION_COLLECTION_NAMES
from app.quality.dds_staging_quality import (
    default_json_report_path,
    default_md_report_path,
    run_dds_staging_quality_review,
)
from app.validators.course_validator import validate_normalized_course
from app.validators.degree_requirement_validator import validate_normalized_degree_requirement
from app.vault.export_dds_catalog import write_vault_catalog_export


def run_health() -> int:
    settings = get_settings()
    mongo_status = check_mongo_connectivity()

    payload = {
        "service": settings.service_name,
        "environment": settings.environment,
        "mongo": mongo_status,
        "stagingCollections": {
            "courses": settings.staging_courses_collection,
            "courseOfferings": settings.staging_course_offerings_collection,
            "degreeRequirements": settings.staging_degree_requirements_collection,
            "degreePrograms": settings.staging_degree_programs_collection,
            "catalogRules": settings.staging_catalog_rules_collection,
            "dataQualityReports": settings.staging_data_quality_reports_collection,
            "ingestionRuns": settings.staging_ingestion_runs_collection,
        },
        "note": "Catalog data is sourced from catalog_valut wiki export; semester offerings from Technion JSON.",
    }

    print(json.dumps(payload, indent=2))

    if mongo_status != "connected":
        return 1
    return 0


def run_validate_sample() -> int:
    records = [
        *SAMPLE_COURSES,
        INVALID_SAMPLE_COURSE,
        *SAMPLE_DEGREE_REQUIREMENTS,
    ]

    valid_count = 0
    invalid_count = 0
    errors: list[str] = []

    for index, record in enumerate(records):
        if "requirementType" in record:
            result = validate_normalized_degree_requirement(record)
            label = f"degree_requirement[{index}]"
        else:
            result = validate_normalized_course(record)
            label = f"course[{index}]"

        if result.is_valid:
            valid_count += 1
        else:
            invalid_count += 1
            errors.append(f"{label}: {'; '.join(result.errors)}")

    summary = {
        "itemsRead": len(records),
        "itemsValid": valid_count,
        "itemsInvalid": invalid_count,
        "errors": errors,
        "note": "Sample data only — not real Technion DDS imports.",
    }
    print(json.dumps(summary, indent=2))

    return 0 if invalid_count == 0 else 1


def run_import_sample() -> int:
    database = get_database()
    settings = get_settings()

    finished_run = import_records_to_staging(
        database,
        source_name=SAMPLE_SOURCE_NAME,
        source_type=SAMPLE_SOURCE_TYPE,
        courses=SAMPLE_COURSES,
        degree_requirements=SAMPLE_DEGREE_REQUIREMENTS,
        settings=settings,
    )

    print(
        json.dumps(
            {
                "status": finished_run.status,
                "itemsRead": finished_run.itemsRead,
                "itemsValid": finished_run.itemsValid,
                "itemsInvalid": finished_run.itemsInvalid,
                "errors": finished_run.errors,
                "stagingCollections": {
                    "courses": settings.staging_courses_collection,
                    "degreeRequirements": settings.staging_degree_requirements_collection,
                    "ingestionRuns": settings.staging_ingestion_runs_collection,
                },
                "note": "Imported synthetic sample records to staging only.",
            },
            indent=2,
        )
    )

    return 0 if finished_run.status in {"completed", "partial"} else 1


def run_export_vault_catalog(
    vault_path: str | None,
    faculty: str,
    output_path: str | None,
    readiness_path: str | None,
    course_json_paths: list[str] | None,
) -> int:
    try:
        catalog_file, readiness_file, document, readiness = write_vault_catalog_export(
            vault_path=Path(vault_path) if vault_path else None,
            faculty=faculty,
            output_path=Path(output_path) if output_path else None,
            readiness_path=Path(readiness_path) if readiness_path else None,
            course_json_paths=[Path(path) for path in course_json_paths] if course_json_paths else None,
        )
    except Exception as exc:
        print(json.dumps({"error": str(exc)}, indent=2))
        return 1

    print(
        json.dumps(
            {
                "status": "ok",
                "catalogPath": str(catalog_file),
                "readinessPath": str(readiness_file),
                "programs": [program["programCode"] for program in document["programs"]],
                "counts": readiness.get("counts"),
                "canImportToStaging": readiness.get("canImportToStaging"),
                "note": "Vault export only — run import-dds-catalog-staging to load MongoDB staging.",
            },
            indent=2,
            ensure_ascii=False,
        )
    )
    return 0


def run_import_dds_catalog_staging(
    catalog_path: str | None,
    readiness_path: str | None,
    dry_run: bool,
) -> int:
    settings = get_settings()
    catalog_file = Path(catalog_path) if catalog_path else None
    readiness_file = Path(readiness_path) if readiness_path else None

    try:
        if dry_run:
            summary = import_dds_catalog_to_staging(
                None,
                catalog_path=catalog_file,
                readiness_path=readiness_file,
                settings=settings,
                dry_run=True,
            )
        else:
            if check_mongo_connectivity() != "connected":
                print(json.dumps({"error": "MongoDB is not connected"}, indent=2))
                return 1
            database = get_database()
            summary = import_dds_catalog_to_staging(
                database,
                catalog_path=catalog_file,
                readiness_path=readiness_file,
                settings=settings,
                dry_run=False,
            )
    except FileNotFoundError as exc:
        print(json.dumps({"error": str(exc)}, indent=2))
        return 1
    except Exception as exc:
        print(json.dumps({"error": str(exc)}, indent=2))
        return 1

    print(
        json.dumps(
            {
                "status": "ok",
                "dryRun": summary.dryRun,
                "programsUpserted": summary.programsUpserted,
                "requirementsUpserted": summary.requirementsUpserted,
                "rulesUpserted": summary.rulesUpserted,
                "courseReferencesObserved": summary.courseReferencesObserved,
                "manualReviewRequiredItems": summary.manualReviewRequiredItems,
                "warningsPreserved": summary.warningsPreserved,
                "stagingCollections": summary.stagingCollections,
                "ingestionRunId": summary.ingestionRunId,
                "ingestionStatus": summary.ingestionStatus,
                "note": (
                    "Dry run only — no MongoDB writes."
                    if summary.dryRun
                    else "Staging import only — no production collections written."
                ),
            },
            indent=2,
            ensure_ascii=False,
        )
    )
    return 0


def run_import_technion_courses_staging(
    course_json_paths: list[str] | None,
    dry_run: bool,
    dds_only: bool,
) -> int:
    settings = get_settings()
    paths = [Path(path) for path in course_json_paths] if course_json_paths else None

    try:
        if dry_run:
            summary = import_technion_courses_to_staging(
                None,
                course_json_paths=paths,
                settings=settings,
                dry_run=True,
                dds_only=dds_only,
            )
        else:
            if check_mongo_connectivity() != "connected":
                print(json.dumps({"error": "MongoDB is not connected"}, indent=2))
                return 1
            database = get_database()
            summary = import_technion_courses_to_staging(
                database,
                course_json_paths=paths,
                settings=settings,
                dry_run=False,
                dds_only=dds_only,
            )
    except FileNotFoundError as exc:
        print(json.dumps({"error": str(exc)}, indent=2))
        return 1
    except Exception as exc:
        print(json.dumps({"error": str(exc)}, indent=2))
        return 1

    print(
        json.dumps(
            {
                "status": "ok",
                "dryRun": summary.dryRun,
                "ddsOnly": summary.ddsOnly,
                "filesRead": summary.filesRead,
                "rawRecordsRead": summary.rawRecordsRead,
                "validCourses": summary.validCourses,
                "invalidRecords": summary.invalidRecords,
                "uniqueCourses": summary.uniqueCourses,
                "ddsFacultyCourses": summary.ddsFacultyCourses,
                "offeringsObserved": summary.offeringsObserved,
                "warnings": summary.warnings[:25],
                "warningsCount": len(summary.warnings),
                "stagingCollections": summary.stagingCollections,
                "ingestionRunId": summary.ingestionRunId,
                "ingestionStatus": summary.ingestionStatus,
                "note": (
                    "Dry run only — no MongoDB writes."
                    if summary.dryRun
                    else "Technion course JSON staging import only — no production collections written."
                ),
            },
            indent=2,
            ensure_ascii=False,
        )
    )
    return 0


def run_validate_dds_staging_quality(
    output_json: str | None,
    output_md: str | None,
    write_staging_audit: bool,
) -> int:
    if check_mongo_connectivity() != "connected":
        print(json.dumps({"error": "MongoDB is not connected"}, indent=2))
        return 1

    settings = get_settings()
    database = get_database()
    json_path = Path(output_json) if output_json else default_json_report_path()
    md_path = Path(output_md) if output_md else default_md_report_path()

    try:
        report = run_dds_staging_quality_review(
            database,
            settings=settings,
            json_path=json_path,
            md_path=md_path,
            write_staging_audit=write_staging_audit,
        )
    except Exception as exc:
        print(json.dumps({"error": str(exc)}, indent=2))
        return 1

    print(
        json.dumps(
            {
                "status": report.status,
                "recommendation": report.recommendation,
                "summary": report.summary,
                "counts": report.counts,
                "blockersForProduction": report.blockersForProduction[:15],
                "blockersForApiMigration": report.blockersForApiMigration[:15],
                "warningsCount": len(report.warnings),
                "jsonReportPath": str(json_path),
                "mdReportPath": str(md_path),
                "stagingAuditWritten": write_staging_audit,
                "note": "Quality review only — no production writes; staged records not modified.",
            },
            indent=2,
            ensure_ascii=False,
        )
    )
    return 0 if report.status != "needs-fixes" else 1


def run_plan_dds_production_promotion(
    output_json: str | None,
    output_md: str | None,
    strict: bool,
    allow_warnings: bool,
) -> int:
    if check_mongo_connectivity() != "connected":
        print(json.dumps({"error": "MongoDB is not connected"}, indent=2))
        return 1

    settings = get_settings()
    database = get_database()
    json_path = Path(output_json) if output_json else default_promotion_json_path()
    md_path = Path(output_md) if output_md else default_promotion_md_path()

    production_counts_before = {
        name: database[name].count_documents({}) for name in sorted(PRODUCTION_COLLECTION_NAMES)
    }

    try:
        report = run_promotion_gate_plan(
            database,
            settings=settings,
            json_path=json_path,
            md_path=md_path,
            strict=strict,
            allow_warnings=allow_warnings,
        )
    except Exception as exc:
        print(json.dumps({"error": str(exc)}, indent=2))
        return 1

    production_counts_after = {
        name: database[name].count_documents({}) for name in sorted(PRODUCTION_COLLECTION_NAMES)
    }
    production_unchanged = production_counts_before == production_counts_after

    gate = report.gate
    print(
        json.dumps(
            {
                "gateStatus": gate.gateStatus,
                "canPromote": gate.canPromote,
                "dryRun": gate.dryRun,
                "plannedCounts": gate.plannedWrites.counts,
                "blockers": gate.blockers[:10],
                "warnings": gate.warnings[:10],
                "jsonReportPath": str(json_path),
                "mdReportPath": str(md_path),
                "productionCollectionsUnchanged": production_unchanged,
                "note": "Phase 11 dry-run only — no production collections were written.",
            },
            indent=2,
            ensure_ascii=False,
        )
    )
    if gate.gateStatus == "fail":
        return 1
    return 0


def run_promote_dds_to_production(
    confirm_dangerous: bool,
    dry_run: bool,
    allow_warnings: bool,
    output_json: str | None,
    output_md: str | None,
) -> int:
    if check_mongo_connectivity() != "connected":
        print(json.dumps({"error": "MongoDB is not connected"}, indent=2))
        return 1

    settings = get_settings()
    database = get_database()
    json_path = Path(output_json) if output_json else default_production_promotion_json_path()
    md_path = Path(output_md) if output_md else default_production_promotion_md_path()

    counts_before = {
        name: database[name].count_documents({}) for name in sorted(PRODUCTION_COLLECTION_NAMES)
    }

    result = run_dds_production_promotion(
        database,
        settings=settings,
        confirm_dangerous=confirm_dangerous,
        dry_run=dry_run,
        allow_warnings=allow_warnings,
        json_path=json_path,
        md_path=md_path,
    )

    counts_after = {
        name: database[name].count_documents({}) for name in sorted(PRODUCTION_COLLECTION_NAMES)
    }

    run = result.promotionRun
    gate = result.gate
    payload = {
        "promotionRunId": run.promotionRunId,
        "status": run.status,
        "gateStatus": gate.gateStatus,
        "canPromote": gate.canPromote,
        "dryRun": dry_run,
        "confirmationFlagProvided": confirm_dangerous,
        "productionWritesPerformed": result.productionWritesPerformed,
        "countsPlanned": run.countsPlanned,
        "countsWritten": run.countsWritten,
        "productionCollectionCountsBefore": run.productionCollectionCountsBefore,
        "productionCollectionCountsAfter": run.productionCollectionCountsAfter,
        "errors": run.errors,
        "jsonReportPath": str(json_path),
        "mdReportPath": str(md_path),
        "productionCollectionsUnchanged": counts_before == counts_after
        if dry_run or not result.productionWritesPerformed
        else None,
    }
    print(json.dumps(payload, indent=2, ensure_ascii=False))

    if not confirm_dangerous and not dry_run:
        return 2
    if run.status == "failed" or gate.gateStatus == "fail":
        return 1
    return 0


def run_rollback_dds_production_promotion(
    promotion_run_id: str | None,
    confirm_dangerous: bool,
) -> int:
    if not promotion_run_id:
        print(json.dumps({"error": "--promotion-run-id is required"}, indent=2))
        return 1
    if check_mongo_connectivity() != "connected":
        print(json.dumps({"error": "MongoDB is not connected"}, indent=2))
        return 1

    database = get_database()
    summary = run_dds_production_rollback(
        database,
        promotion_run_id=promotion_run_id,
        confirm_dangerous=confirm_dangerous,
    )
    print(json.dumps(summary, indent=2, ensure_ascii=False))
    if summary.get("error"):
        return 2 if not confirm_dangerous else 1
    return 0


def run_verify_vault_production_parity(
    vault_path: str | None,
    faculty: str,
    output_json: str | None,
    output_md: str | None,
) -> int:
    if check_mongo_connectivity() != "connected":
        print(json.dumps({"error": "MongoDB is not connected"}, indent=2))
        return 1

    from app.vault.verify_vault_production_parity import (
        default_parity_report_json_path,
        default_parity_report_md_path,
        verify_vault_production_parity,
        write_parity_report,
    )

    database = get_database()
    result = verify_vault_production_parity(
        database,
        faculty=faculty,
        vault_path=Path(vault_path) if vault_path else None,
    )
    json_path, md_path = write_parity_report(
        result,
        json_path=Path(output_json) if output_json else default_parity_report_json_path(),
        md_path=Path(output_md) if output_md else default_parity_report_md_path(),
    )
    payload = {
        "status": result.status,
        "wikiRoot": result.wiki_root,
        "exportedAt": result.exported_at,
        "counts": {
            "expectedHard": result.expected_hard_count,
            "expectedAdvisory": result.expected_advisory_count,
            "productionHard": result.production_hard_count,
            "productionAdvisory": result.production_advisory_count,
            "matchedGroups": result.matched_groups,
        },
        "missingInProduction": result.missing_in_production,
        "extraInProduction": result.extra_in_production,
        "classificationMismatches": result.classification_mismatches,
        "fieldMismatchCount": len(result.field_mismatches),
        "jsonReportPath": str(json_path),
        "mdReportPath": str(md_path),
    }
    print(json.dumps(payload, indent=2, ensure_ascii=False))
    return 0 if result.ok else 1


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        description="UniPilot data-engineering CLI (staging ingestion foundation)",
    )
    parser.add_argument(
        "command",
        choices=[
            "health",
            "validate-sample",
            "import-sample",
            "export-vault-catalog",
            "import-dds-catalog-staging",
            "import-technion-courses-staging",
            "validate-dds-staging-quality",
            "plan-dds-production-promotion",
            "promote-dds-to-production",
            "rollback-dds-production-promotion",
            "verify-vault-production-parity",
        ],
        help="Task to execute",
    )
    parser.add_argument(
        "--vault-path",
        dest="vault_path",
        default=None,
        help="Path to catalog_valut root (defaults to data/catalog_valut)",
    )
    parser.add_argument(
        "--faculty",
        dest="faculty",
        default="dds",
        help="Faculty slug to export (currently only dds)",
    )
    parser.add_argument(
        "--output",
        dest="output",
        default=None,
        help="Output path for vault-exported catalog_reviewed.json",
    )
    parser.add_argument(
        "--course-json",
        dest="course_json_paths",
        action="append",
        default=None,
        help="Path to Technion semester course JSON (repeatable)",
    )
    parser.add_argument(
        "--dds-only",
        dest="dds_only",
        action="store_true",
        help="Import only DDS faculty courses (הפקולטה למדעי הנתונים וההחלטות)",
    )
    parser.add_argument(
        "--output-json",
        dest="output_json",
        default=None,
        help="Output path for staging quality JSON report",
    )
    parser.add_argument(
        "--output-md",
        dest="output_md",
        default=None,
        help="Output path for staging quality markdown report",
    )
    parser.add_argument(
        "--write-staging-audit",
        dest="write_staging_audit",
        action="store_true",
        help="Write report snapshot to staging_data_quality_reports (staging only)",
    )
    parser.add_argument(
        "--catalog-path",
        dest="catalog_path",
        default=None,
        help="Path to vault-exported reviewed catalog JSON (see export-vault-catalog)",
    )
    parser.add_argument(
        "--dry-run",
        dest="dry_run",
        action="store_true",
        help="Validate and summarize without writing to MongoDB",
    )
    parser.add_argument(
        "--readiness-path",
        dest="readiness_path",
        default=None,
        help="Path to Phase 8 readiness check JSON",
    )
    parser.add_argument(
        "--strict",
        dest="strict",
        action="store_true",
        help="Fail promotion gate when warnings are present",
    )
    parser.add_argument(
        "--allow-warnings",
        dest="allow_warnings",
        action="store_true",
        default=True,
        help="Allow pass-with-warnings gate status (default: true)",
    )
    parser.add_argument(
        "--no-allow-warnings",
        dest="allow_warnings",
        action="store_false",
        help="Treat warnings as gate failure unless resolved",
    )
    parser.add_argument(
        "--i-confirm-dangerous-production-write",
        dest="confirm_dangerous",
        action="store_true",
        help="Required for real production promotion or rollback (Phase 12)",
    )
    parser.add_argument(
        "--promotion-run-id",
        dest="promotion_run_id",
        default=None,
        help="Promotion run id for rollback-dds-production-promotion",
    )
    return parser


def main(argv: list[str] | None = None) -> int:
    configure_logging()
    parser = build_parser()
    args = parser.parse_args(argv)

    try:
        if args.command == "health":
            return run_health()
        if args.command == "validate-sample":
            return run_validate_sample()
        if args.command == "import-sample":
            return run_import_sample()
        if args.command == "export-vault-catalog":
            return run_export_vault_catalog(
                args.vault_path,
                args.faculty,
                args.output,
                args.readiness_path,
                args.course_json_paths,
            )
        if args.command == "import-dds-catalog-staging":
            return run_import_dds_catalog_staging(
                args.catalog_path,
                args.readiness_path,
                args.dry_run,
            )
        if args.command == "import-technion-courses-staging":
            return run_import_technion_courses_staging(
                args.course_json_paths,
                args.dry_run,
                args.dds_only,
            )
        if args.command == "validate-dds-staging-quality":
            return run_validate_dds_staging_quality(
                args.output_json,
                args.output_md,
                args.write_staging_audit,
            )
        if args.command == "plan-dds-production-promotion":
            return run_plan_dds_production_promotion(
                args.output_json,
                args.output_md,
                args.strict,
                args.allow_warnings,
            )
        if args.command == "promote-dds-to-production":
            return run_promote_dds_to_production(
                args.confirm_dangerous,
                args.dry_run,
                args.allow_warnings,
                args.output_json,
                args.output_md,
            )
        if args.command == "rollback-dds-production-promotion":
            return run_rollback_dds_production_promotion(
                args.promotion_run_id,
                args.confirm_dangerous,
            )
        if args.command == "verify-vault-production-parity":
            return run_verify_vault_production_parity(
                args.vault_path,
                args.faculty,
                args.output_json,
                args.output_md,
            )
    finally:
        close_mongo_client()

    parser.error(f"Unsupported command: {args.command}")
    return 2


if __name__ == "__main__":
    sys.exit(main())
