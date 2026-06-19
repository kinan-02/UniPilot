"""CLI entry point for data-engineering ingestion tasks."""

import argparse
import json
import os
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
from app.curation.dds_catalog_blocker_cleanup import run_blocker_cleanup
from app.curation.dds_catalog_human_signoff import run_record_human_signoff
from app.promotion.dds_promotion_gate import (
    default_promotion_json_path,
    default_promotion_md_path,
    run_promotion_gate_plan,
)
from app.importers.dds_catalog_staging_importer import PRODUCTION_COLLECTION_NAMES
from app.quality.dds_staging_quality import (
    default_json_report_path,
    default_md_report_path,
    run_dds_staging_quality_review,
)
from app.curation.dds_catalog_signoff import run_signoff
from app.parsers.dds_catalog_markdown_parser import write_curated_catalog_draft
from app.sources.technion_dds_catalog_pdf import extract_dds_catalog, inspect_dds_catalog
from app.validators.course_validator import validate_normalized_course
from app.validators.degree_requirement_validator import validate_normalized_degree_requirement


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
        "note": "Real Technion DDS ingestion is not implemented in Phase 4.",
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


def run_extract_dds_catalog(pdf_path: str | None, output_dir: str | None) -> int:
    settings = get_settings()
    env_path = os.environ.get("DDS_CATALOG_PDF_PATH") or settings.dds_catalog_pdf_path

    try:
        artifacts = extract_dds_catalog(
            pdf_path,
            env_path=env_path,
            output_directory=output_dir or settings.dds_catalog_output_dir,
        )
    except FileNotFoundError as exc:
        print(json.dumps({"error": str(exc)}, indent=2))
        return 1

    print(
        json.dumps(
            {
                "status": "completed",
                "outputDirectory": str(artifacts.output_directory),
                "pageCount": artifacts.report.pageCount,
                "totalCharacters": artifacts.report.totalCharacters,
                "detectedProgramCodes": [
                    item["programCode"] for item in artifacts.candidate_sections["programCodes"]
                ],
                "detectedCourseNumbersCount": len(
                    artifacts.candidate_sections["courseNumberHits"]
                ),
                "candidateSectionsCount": len(artifacts.candidate_sections["sections"]),
                "artifacts": [
                    "extracted_pages.json",
                    "extracted_pages.txt",
                    "extraction_report.json",
                    "candidate_sections.json",
                ],
                "note": "Local extraction only — no MongoDB or staging writes.",
            },
            indent=2,
        )
    )
    return 0


def run_parse_dds_catalog_md(md_path: str | None, output_path: str | None) -> int:
    settings = get_settings()
    env_path = os.environ.get("DDS_CATALOG_MD_PATH") or settings.dds_catalog_md_path

    try:
        document, target = write_curated_catalog_draft(
            md_path,
            env_path=env_path,
            output_path=output_path,
        )
    except FileNotFoundError as exc:
        print(json.dumps({"error": str(exc)}, indent=2))
        return 1

    print(
        json.dumps(
            {
                "status": "ok",
                "outputPath": str(target),
                "programs": [program.programCode for program in document.programs],
                "parserReport": document.parserReport,
                "note": "Draft curated JSON only — no MongoDB or staging writes.",
            },
            indent=2,
            ensure_ascii=False,
        )
    )
    return 0


def run_curate_dds_catalog(
    draft_path: str | None,
    markdown_path: str | None,
    output_path: str | None,
    report_path: str | None,
) -> int:
    try:
        document, reviewed_path, report_file = run_curation(
            draft_path=Path(draft_path) if draft_path else None,
            markdown_path=Path(markdown_path) if markdown_path else None,
            output_path=Path(output_path) if output_path else None,
            report_path=Path(report_path) if report_path else None,
        )
    except FileNotFoundError as exc:
        print(json.dumps({"error": str(exc)}, indent=2))
        return 1

    print(
        json.dumps(
            {
                "status": "ok",
                "reviewedPath": str(reviewed_path),
                "reportPath": str(report_file),
                "curationStatus": document.curationMetadata.curationStatus,
                "countsAfter": document.curationMetadata.countsAfter,
                "curationReport": document.curationReport,
                "note": "Reviewed curated JSON only — no MongoDB or staging writes.",
            },
            indent=2,
            ensure_ascii=False,
        )
    )
    return 0


def run_signoff_dds_catalog(
    reviewed_path: str | None,
    md_path: str | None,
    output_path: str | None,
    report_path: str | None,
    readiness_path: str | None,
) -> int:
    try:
        document, readiness, reviewed_out, signoff_report, readiness_out = run_signoff(
            reviewed_path=Path(reviewed_path) if reviewed_path else None,
            markdown_path=Path(md_path) if md_path else None,
            reviewed_output_path=Path(output_path) if output_path else None,
            signoff_report_path=Path(report_path) if report_path else None,
            readiness_path=Path(readiness_path) if readiness_path else None,
        )
    except FileNotFoundError as exc:
        print(json.dumps({"error": str(exc)}, indent=2))
        return 1

    print(
        json.dumps(
            {
                "status": "ok",
                "reviewStatus": document.signoffReview.reviewStatus if document.signoffReview else None,
                "reviewedPath": str(reviewed_out),
                "signoffReportPath": str(signoff_report),
                "phase8ReadinessPath": str(readiness_out),
                "phase8Readiness": readiness,
                "note": "Signoff review only — no MongoDB or staging writes.",
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


def run_record_dds_human_signoff(
    catalog_path: str | None,
    readiness_path: str | None,
    signed_off_by: str,
    dry_run: bool,
) -> int:
    try:
        summary = run_record_human_signoff(
            catalog_path=Path(catalog_path) if catalog_path else None,
            readiness_path=Path(readiness_path) if readiness_path else None,
            signed_off_by=signed_off_by,
            dry_run=dry_run,
        )
    except Exception as exc:
        print(json.dumps({"error": str(exc)}, indent=2))
        return 1

    print(json.dumps(summary, indent=2, ensure_ascii=False))
    return 0


def run_cleanup_dds_staging_blockers(
    catalog_path: str | None,
    readiness_path: str | None,
    cleanup_report_path: str | None,
    dry_run: bool,
) -> int:
    try:
        summary = run_blocker_cleanup(
            catalog_path=Path(catalog_path) if catalog_path else None,
            readiness_path=Path(readiness_path) if readiness_path else None,
            cleanup_report_path=Path(cleanup_report_path) if cleanup_report_path else None,
            dry_run=dry_run,
        )
    except Exception as exc:
        print(json.dumps({"error": str(exc)}, indent=2))
        return 1

    print(json.dumps(summary, indent=2, ensure_ascii=False))
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


def run_promote_dds_to_production() -> int:
    """Phase 11 stub — real production promotion belongs in Phase 12."""
    database = get_database()
    production_counts_before = {
        name: database[name].count_documents({}) for name in sorted(PRODUCTION_COLLECTION_NAMES)
    }

    message = (
        "Production promotion is not implemented in Phase 11. "
        "Run plan-dds-production-promotion first and implement Phase 12 only after explicit approval."
    )
    print(
        json.dumps(
            {
                "error": message,
                "phase": 11,
                "productionWritesPerformed": False,
                "productionCollectionCounts": production_counts_before,
            },
            indent=2,
            ensure_ascii=False,
        )
    )
    return 2


def run_inspect_dds_catalog(pdf_path: str | None) -> int:
    settings = get_settings()
    env_path = os.environ.get("DDS_CATALOG_PDF_PATH") or settings.dds_catalog_pdf_path

    try:
        summary = inspect_dds_catalog(pdf_path, env_path=env_path)
    except FileNotFoundError as exc:
        print(json.dumps({"error": str(exc)}, indent=2))
        return 1

    print(json.dumps(summary, indent=2, ensure_ascii=False))
    return 0


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
            "extract-dds-catalog",
            "inspect-dds-catalog",
            "parse-dds-catalog-md",
            "curate-dds-catalog",
            "signoff-dds-catalog",
            "import-dds-catalog-staging",
            "import-technion-courses-staging",
            "validate-dds-staging-quality",
            "cleanup-dds-staging-blockers",
            "record-dds-human-signoff",
            "plan-dds-production-promotion",
            "promote-dds-to-production",
        ],
        help="Task to execute",
    )
    parser.add_argument(
        "--pdf-path",
        dest="pdf_path",
        default=None,
        help="Path to local Technion DDS catalog PDF",
    )
    parser.add_argument(
        "--output-dir",
        dest="output_dir",
        default=None,
        help="Output directory for generated DDS catalog extraction artifacts",
    )
    parser.add_argument(
        "--md-path",
        dest="md_path",
        default=None,
        help="Path to Technion DDS catalog markdown (docx export)",
    )
    parser.add_argument(
        "--output",
        dest="output",
        default=None,
        help="Output path for draft/reviewed curated catalog JSON",
    )
    parser.add_argument(
        "--draft-path",
        dest="draft_path",
        default=None,
        help="Path to parser draft curated catalog JSON",
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
        "--signed-off-by",
        dest="signed_off_by",
        default="project-owner",
        help="Human sign-off identity for record-dds-human-signoff",
    )
    parser.add_argument(
        "--cleanup-report-path",
        dest="cleanup_report_path",
        default=None,
        help="Output path for Phase 10.5 blocker cleanup markdown report",
    )
    parser.add_argument(
        "--catalog-path",
        dest="catalog_path",
        default=None,
        help="Path to Phase 7.6 reviewed curated catalog JSON",
    )
    parser.add_argument(
        "--dry-run",
        dest="dry_run",
        action="store_true",
        help="Validate and summarize without writing to MongoDB",
    )
    parser.add_argument(
        "--reviewed-path",
        dest="reviewed_path",
        default=None,
        help="Path to Phase 7.5 reviewed curated catalog JSON",
    )
    parser.add_argument(
        "--readiness-path",
        dest="readiness_path",
        default=None,
        help="Output path for Phase 8 readiness check JSON",
    )
    parser.add_argument(
        "--report-path",
        dest="report_path",
        default=None,
        help="Output path for signoff or curation review report markdown",
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
        if args.command == "extract-dds-catalog":
            return run_extract_dds_catalog(args.pdf_path, args.output_dir)
        if args.command == "inspect-dds-catalog":
            return run_inspect_dds_catalog(args.pdf_path)
        if args.command == "parse-dds-catalog-md":
            return run_parse_dds_catalog_md(args.md_path, args.output)
        if args.command == "curate-dds-catalog":
            return run_curate_dds_catalog(
                args.draft_path,
                args.md_path,
                args.output,
                args.report_path,
            )
        if args.command == "signoff-dds-catalog":
            return run_signoff_dds_catalog(
                args.reviewed_path,
                args.md_path,
                args.output,
                args.report_path,
                args.readiness_path,
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
        if args.command == "cleanup-dds-staging-blockers":
            return run_cleanup_dds_staging_blockers(
                args.catalog_path,
                args.readiness_path,
                args.cleanup_report_path,
                args.dry_run,
            )
        if args.command == "record-dds-human-signoff":
            return run_record_dds_human_signoff(
                args.catalog_path,
                args.readiness_path,
                args.signed_off_by,
                args.dry_run,
            )
        if args.command == "plan-dds-production-promotion":
            return run_plan_dds_production_promotion(
                args.output_json,
                args.output_md,
                args.strict,
                args.allow_warnings,
            )
        if args.command == "promote-dds-to-production":
            return run_promote_dds_to_production()
    finally:
        close_mongo_client()

    parser.error(f"Unsupported command: {args.command}")
    return 2


if __name__ == "__main__":
    sys.exit(main())
