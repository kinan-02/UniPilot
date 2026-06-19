"""Phase 9 — import Technion semester course JSON into MongoDB staging only."""

from __future__ import annotations

import logging
from dataclasses import dataclass, field
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

from pymongo.database import Database

from app.config import Settings, get_settings
from app.importers.dds_catalog_staging_importer import assert_staging_collection_name
from app.models.ingestion_run import IngestionRun
from app.models.staging_course import TechnionCourseStagingImportSummary
from app.sources.technion_course_json import (
    SOURCE_NAME,
    SOURCE_TYPE,
    TechnionCourseParseResult,
    default_course_json_paths,
    read_and_normalize_course_json_files,
)
from app.validators.staging_course_validator import (
    validate_staged_technion_course,
    validate_staged_technion_offering,
)

logger = logging.getLogger(__name__)


class TechnionCourseStagingImportError(ValueError):
    """Raised when Technion course staging import preconditions fail."""


@dataclass
class TechnionCourseStagingImportPlan:
    course_documents: list[dict[str, Any]] = field(default_factory=list)
    offering_documents: list[dict[str, Any]] = field(default_factory=list)
    summary: TechnionCourseStagingImportSummary = field(default_factory=TechnionCourseStagingImportSummary)


def _utc_now() -> datetime:
    return datetime.now(UTC)


def _utc_now_iso() -> str:
    return _utc_now().replace(microsecond=0).isoformat()


def assert_course_staging_settings(settings: Settings) -> None:
    for name in (
        settings.staging_courses_collection,
        settings.staging_course_offerings_collection,
        settings.staging_ingestion_runs_collection,
    ):
        assert_staging_collection_name(name)


def build_technion_course_staging_plan(
    parse_result: TechnionCourseParseResult,
    *,
    settings: Settings,
    dds_only: bool,
    dry_run: bool,
) -> TechnionCourseStagingImportPlan:
    assert_course_staging_settings(settings)

    course_documents: list[dict[str, Any]] = []
    offering_documents: list[dict[str, Any]] = []
    warnings = list(parse_result.warnings)
    valid_courses = 0
    invalid_records = len(parse_result.invalid_records)

    for course in parse_result.courses:
        validation = validate_staged_technion_course(course)
        warnings.extend(validation.warnings)
        if not validation.is_valid:
            invalid_records += 1
            warnings.extend(validation.errors)
            continue

        document = course.model_dump(mode="json")
        document["importedAt"] = _utc_now_iso()
        document["importRunId"] = "dry-run" if dry_run else None
        course_documents.append(document)
        valid_courses += 1

    for offering in parse_result.offerings:
        validation = validate_staged_technion_offering(offering)
        warnings.extend(validation.warnings)
        if not validation.is_valid:
            invalid_records += 1
            warnings.extend(validation.errors)
            continue

        document = offering.model_dump(mode="json")
        document["importedAt"] = _utc_now_iso()
        document["importRunId"] = "dry-run" if dry_run else None
        offering_documents.append(document)

    for invalid in parse_result.invalid_records:
        warnings.append(f"invalid record {invalid.sourceFile}[{invalid.recordIndex}]: {invalid.reason}")

    summary = TechnionCourseStagingImportSummary(
        dryRun=dry_run,
        ddsOnly=dds_only,
        filesRead=parse_result.files_read,
        rawRecordsRead=parse_result.raw_records_read,
        validCourses=valid_courses,
        invalidRecords=invalid_records,
        uniqueCourses=len(course_documents),
        ddsFacultyCourses=parse_result.dds_faculty_course_count,
        offeringsObserved=len(offering_documents),
        warnings=sorted(set(warnings)),
        stagingCollections={
            "courses": settings.staging_courses_collection,
            "courseOfferings": settings.staging_course_offerings_collection,
            "ingestionRuns": settings.staging_ingestion_runs_collection,
        },
    )

    return TechnionCourseStagingImportPlan(
        course_documents=course_documents,
        offering_documents=offering_documents,
        summary=summary,
    )


def ensure_technion_course_staging_indexes(database: Database, settings: Settings) -> None:
    assert_course_staging_settings(settings)
    database[settings.staging_courses_collection].create_index(
        [("stagingKey", 1)],
        unique=True,
        name="staging_courses_unique_key",
    )
    database[settings.staging_course_offerings_collection].create_index(
        [("stagingKey", 1)],
        unique=True,
        name="staging_course_offerings_unique_key",
    )
    database[settings.staging_ingestion_runs_collection].create_index(
        [("startedAt", -1)],
        name="staging_ingestion_runs_started_at",
    )


def _start_ingestion_run(database: Database, settings: Settings) -> tuple[Any, IngestionRun]:
    started_at = _utc_now()
    run = IngestionRun(
        sourceName=SOURCE_NAME,
        sourceType=SOURCE_TYPE,
        status="running",
        startedAt=started_at,
    )
    insert_result = database[settings.staging_ingestion_runs_collection].insert_one(
        run.model_dump(mode="json")
    )
    return insert_result.inserted_id, run


def _finish_ingestion_run(
    database: Database,
    settings: Settings,
    run_id: Any,
    run: IngestionRun,
) -> IngestionRun:
    finished = run.model_copy(
        update={
            "finishedAt": _utc_now(),
            "status": "completed" if run.itemsInvalid == 0 else ("partial" if run.itemsValid else "failed"),
        }
    )
    database[settings.staging_ingestion_runs_collection].update_one(
        {"_id": run_id},
        {"$set": finished.model_dump(mode="json")},
    )
    return finished


def _upsert_documents(
    database: Database,
    collection_name: str,
    documents: list[dict[str, Any]],
) -> int:
    assert_staging_collection_name(collection_name)
    collection = database[collection_name]
    for document in documents:
        collection.update_one(
            {"stagingKey": document["stagingKey"]},
            {"$set": document},
            upsert=True,
        )
    return len(documents)


def import_technion_courses_to_staging(
    database: Database | None,
    *,
    course_json_paths: list[Path] | None = None,
    settings: Settings | None = None,
    dry_run: bool = False,
    dds_only: bool = False,
) -> TechnionCourseStagingImportSummary:
    settings = settings or get_settings()
    paths = course_json_paths if course_json_paths is not None else default_course_json_paths()
    existing_paths = [path for path in paths if path.exists()]
    if not existing_paths:
        raise FileNotFoundError("No course JSON source files found for staging import.")

    parse_result = read_and_normalize_course_json_files(existing_paths, dds_only=dds_only)
    plan = build_technion_course_staging_plan(
        parse_result,
        settings=settings,
        dds_only=dds_only,
        dry_run=dry_run,
    )

    if dry_run:
        logger.info("technion_course_staging_dry_run summary=%s", plan.summary.model_dump())
        return plan.summary

    if database is None:
        raise TechnionCourseStagingImportError("Database connection is required for staging import.")

    ensure_technion_course_staging_indexes(database, settings)
    run_id, run = _start_ingestion_run(database, settings)
    run_id_str = str(run_id)
    imported_at = _utc_now_iso()

    for document in plan.course_documents:
        document["importRunId"] = run_id_str
        document["importedAt"] = imported_at
    for document in plan.offering_documents:
        document["importRunId"] = run_id_str
        document["importedAt"] = imported_at

    items_total = len(plan.course_documents) + len(plan.offering_documents)
    run = run.model_copy(
        update={
            "itemsRead": parse_result.raw_records_read,
            "itemsValid": items_total,
            "itemsInvalid": plan.summary.invalidRecords,
            "metadata": {
                "importType": "technion_course_json_staging",
                "dryRun": False,
                "ddsOnly": dds_only,
                "sourceFiles": [path.name for path in existing_paths],
                "summary": plan.summary.model_dump(mode="json"),
            },
        }
    )

    _upsert_documents(database, settings.staging_courses_collection, plan.course_documents)
    _upsert_documents(
        database,
        settings.staging_course_offerings_collection,
        plan.offering_documents,
    )

    finished_run = _finish_ingestion_run(database, settings, run_id, run)

    plan.summary.ingestionRunId = run_id_str
    plan.summary.ingestionStatus = finished_run.status
    return plan.summary
