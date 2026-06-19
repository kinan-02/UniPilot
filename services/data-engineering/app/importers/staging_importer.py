import logging
from datetime import datetime, timezone
from typing import Any

from pymongo.database import Database

from app.config import Settings, get_settings
from app.models.ingestion_run import IngestionRun, IngestionStatus
from app.models.normalized_course import NormalizedCourse
from app.models.normalized_degree_requirement import NormalizedDegreeRequirement
from app.validators.course_validator import validate_normalized_course
from app.validators.degree_requirement_validator import validate_normalized_degree_requirement

logger = logging.getLogger(__name__)


def _utc_now() -> datetime:
    return datetime.now(timezone.utc)


def ensure_staging_indexes(database: Database, settings: Settings) -> None:
    database[settings.staging_courses_collection].create_index(
        [("stagingKey", 1)],
        unique=True,
        name="staging_courses_unique_key",
    )
    database[settings.staging_degree_requirements_collection].create_index(
        [("stagingKey", 1)],
        unique=True,
        name="staging_degree_requirements_unique_key",
    )
    database[settings.staging_ingestion_runs_collection].create_index(
        [("startedAt", -1)],
        name="staging_ingestion_runs_started_at",
    )


def _start_ingestion_run(
    database: Database,
    settings: Settings,
    *,
    source_name: str,
    source_type: str,
) -> tuple[Any, IngestionRun]:
    started_at = _utc_now()
    run = IngestionRun(
        sourceName=source_name,
        sourceType=source_type,
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
            "status": _resolve_final_status(run),
        }
    )
    database[settings.staging_ingestion_runs_collection].update_one(
        {"_id": run_id},
        {"$set": finished.model_dump(mode="json")},
    )
    return finished


def _resolve_final_status(run: IngestionRun) -> IngestionStatus:
    if run.itemsInvalid > 0 and run.itemsValid > 0:
        return "partial"
    if run.itemsInvalid > 0 and run.itemsValid == 0:
        return "failed"
    return "completed"


def import_records_to_staging(
    database: Database,
    *,
    source_name: str,
    source_type: str,
    courses: list[dict],
    degree_requirements: list[dict],
    settings: Settings | None = None,
) -> IngestionRun:
    settings = settings or get_settings()
    ensure_staging_indexes(database, settings)

    run_id, run = _start_ingestion_run(
        database,
        settings,
        source_name=source_name,
        source_type=source_type,
    )

    logger.info(
        "ingestion_started sourceName=%s sourceType=%s runId=%s",
        source_name,
        source_type,
        str(run_id),
    )

    for raw_course in courses:
        run = _process_course_record(
            database,
            settings,
            run_id,
            run,
            raw_course,
        )

    for raw_requirement in degree_requirements:
        run = _process_requirement_record(
            database,
            settings,
            run_id,
            run,
            raw_requirement,
        )

    finished_run = _finish_ingestion_run(database, settings, run_id, run)

    logger.info(
        "ingestion_finished sourceName=%s status=%s itemsRead=%s itemsValid=%s itemsInvalid=%s",
        source_name,
        finished_run.status,
        finished_run.itemsRead,
        finished_run.itemsValid,
        finished_run.itemsInvalid,
    )

    return finished_run


def _process_course_record(
    database: Database,
    settings: Settings,
    run_id: Any,
    run: IngestionRun,
    raw_course: dict,
) -> IngestionRun:
    run = run.model_copy(update={"itemsRead": run.itemsRead + 1})
    validation = validate_normalized_course(raw_course)

    if not validation.is_valid:
        error_message = f"course validation failed: {'; '.join(validation.errors)}"
        logger.warning(error_message)
        return _record_invalid(database, settings, run_id, run, error_message)

    course = NormalizedCourse.model_validate(raw_course)
    document = {
        **course.model_dump(mode="json"),
        "stagingKey": course.staging_key(),
        "ingestionRunId": str(run_id),
        "importedAt": _utc_now().isoformat(),
    }

    database[settings.staging_courses_collection].update_one(
        {"stagingKey": document["stagingKey"]},
        {"$set": document},
        upsert=True,
    )

    updated_run = run.model_copy(update={"itemsValid": run.itemsValid + 1})
    _persist_run_progress(database, settings, run_id, updated_run)
    return updated_run


def _process_requirement_record(
    database: Database,
    settings: Settings,
    run_id: Any,
    run: IngestionRun,
    raw_requirement: dict,
) -> IngestionRun:
    run = run.model_copy(update={"itemsRead": run.itemsRead + 1})
    validation = validate_normalized_degree_requirement(raw_requirement)

    if not validation.is_valid:
        error_message = f"degree requirement validation failed: {'; '.join(validation.errors)}"
        logger.warning(error_message)
        return _record_invalid(database, settings, run_id, run, error_message)

    requirement = NormalizedDegreeRequirement.model_validate(raw_requirement)
    document = {
        **requirement.model_dump(mode="json"),
        "stagingKey": requirement.staging_key(),
        "ingestionRunId": str(run_id),
        "importedAt": _utc_now().isoformat(),
    }

    database[settings.staging_degree_requirements_collection].update_one(
        {"stagingKey": document["stagingKey"]},
        {"$set": document},
        upsert=True,
    )

    updated_run = run.model_copy(update={"itemsValid": run.itemsValid + 1})
    _persist_run_progress(database, settings, run_id, updated_run)
    return updated_run


def _record_invalid(
    database: Database,
    settings: Settings,
    run_id: Any,
    run: IngestionRun,
    error_message: str,
) -> IngestionRun:
    updated_run = run.model_copy(
        update={
            "itemsInvalid": run.itemsInvalid + 1,
            "errors": [*run.errors, error_message],
        }
    )
    _persist_run_progress(database, settings, run_id, updated_run)
    return updated_run


def _persist_run_progress(
    database: Database,
    settings: Settings,
    run_id: Any,
    run: IngestionRun,
) -> None:
    database[settings.staging_ingestion_runs_collection].update_one(
        {"_id": run_id},
        {"$set": run.model_dump(mode="json")},
    )
