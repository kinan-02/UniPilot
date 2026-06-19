"""CLI entry point for data-engineering ingestion tasks."""

import argparse
import json
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


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        description="UniPilot data-engineering CLI (staging ingestion foundation)",
    )
    parser.add_argument(
        "command",
        choices=["health", "validate-sample", "import-sample"],
        help="Task to execute",
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
    finally:
        close_mongo_client()

    parser.error(f"Unsupported command: {args.command}")
    return 2


if __name__ == "__main__":
    sys.exit(main())
