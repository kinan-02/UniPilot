"""CLI entry point for data-engineering ingestion tasks."""

import argparse
import json
import os
import sys

from app.config import get_settings
from app.db import check_mongo_connectivity, close_mongo_client, get_database
from app.importers.staging_importer import import_records_to_staging
from app.logging_config import configure_logging
from app.sources.sample_data import (
    INVALID_SAMPLE_COURSE,
    SAMPLE_COURSES,
    SAMPLE_DEGREE_REQUIREMENTS,
    SAMPLE_SOURCE_NAME,
    SAMPLE_SOURCE_TYPE,
)
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
            "degreeRequirements": settings.staging_degree_requirements_collection,
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
        help="Output path for draft curated catalog JSON",
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
    finally:
        close_mongo_client()

    parser.error(f"Unsupported command: {args.command}")
    return 2


if __name__ == "__main__":
    sys.exit(main())
