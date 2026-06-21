"""Phase 8 — import reviewed DDS curated catalog into MongoDB staging only."""

from __future__ import annotations

import json
import logging
import re
from dataclasses import dataclass, field
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

from pymongo.database import Database

from app.config import Settings, get_settings
from app.models.catalog import ReviewedCuratedCatalogDocument
from app.models.ingestion_run import IngestionRun
from app.models.staging_catalog import (
    CatalogStagingImportSummary,
    Phase8ReadinessCheck,
    StagingCatalogImportMetadata,
)
from app.paths import default_catalog_reviewed_path, default_readiness_path as vault_default_readiness_path

logger = logging.getLogger(__name__)

SOURCE_NAME = "technion-dds-catalog"
SOURCE_TYPE = "dds_catalog_curated_reviewed"

EXPECTED_PROGRAM_CODES = ["009216-1-000", "009009-1-000", "009118-1-000"]
EXPECTED_TOTAL_CREDITS = 155.0

ALLOWED_CURATION_STATUSES = {
    "ready-for-staging-with-review-flags",
    "ready-for-human-signoff",
    "vault-signed-ready-for-staging",
}
BLOCKED_CURATION_STATUSES = {
    "production-ready",
}

EXECUTABLE_RULE_TYPES = {"credit_bucket"}
NON_MANDATORY_RULE_TYPES = {
    "course_pool",
    "semester_matrix",
    "track_requirement",
    "prefix_pool",
}

PRODUCTION_COLLECTION_NAMES = frozenset(
    {
        "courses",
        "degree_requirements",
        "degree_programs",
        "degrees",
        "catalog",
        "catalog_rules",
        "course_offerings",
        "completed_courses",
        "semester_plans",
        "promotion_runs",
    }
)

PROMOTION_WRITE_COLLECTIONS = frozenset(
    {
        "degree_programs",
        "degree_requirements",
        "catalog_rules",
        "courses",
        "course_offerings",
    }
)

COURSE_NUMBER_PATTERN = re.compile(r"^0\d{7}$")


class CatalogStagingImportError(ValueError):
    """Raised when catalog staging import preconditions fail."""


@dataclass
class CatalogStagingImportPlan:
    program_documents: list[dict[str, Any]] = field(default_factory=list)
    requirement_documents: list[dict[str, Any]] = field(default_factory=list)
    rule_documents: list[dict[str, Any]] = field(default_factory=list)
    summary: CatalogStagingImportSummary = field(default_factory=CatalogStagingImportSummary)


def default_catalog_path() -> Path:
    return default_catalog_reviewed_path()


def default_readiness_path() -> Path:
    return vault_default_readiness_path()


def _utc_now() -> datetime:
    return datetime.now(UTC)


def _utc_now_iso() -> str:
    return _utc_now().replace(microsecond=0).isoformat()


def program_staging_key(catalog_version: str, program_code: str) -> str:
    return f"technion-dds:catalog:{catalog_version}:program:{program_code}"


def requirement_staging_key(catalog_version: str, group_id: str) -> str:
    return f"technion-dds:catalog:{catalog_version}:requirement:{group_id}"


def assert_staging_collection_name(collection_name: str) -> None:
    if collection_name in PRODUCTION_COLLECTION_NAMES:
        raise CatalogStagingImportError(
            f"Refusing production collection name: {collection_name}",
        )
    if not collection_name.startswith("staging_"):
        raise CatalogStagingImportError(
            f"Collection name must start with staging_: {collection_name}",
        )


def assert_staging_settings(settings: Settings) -> None:
    for name in (
        settings.staging_degree_programs_collection,
        settings.staging_degree_requirements_collection,
        settings.staging_catalog_rules_collection,
        settings.staging_ingestion_runs_collection,
    ):
        assert_staging_collection_name(name)


def load_reviewed_catalog(path: Path) -> ReviewedCuratedCatalogDocument:
    if not path.exists():
        raise FileNotFoundError(f"Reviewed catalog not found: {path}")
    payload = json.loads(path.read_text(encoding="utf-8"))
    return ReviewedCuratedCatalogDocument.model_validate(payload)


def load_phase8_readiness(path: Path) -> Phase8ReadinessCheck:
    if not path.exists():
        raise FileNotFoundError(f"Phase 8 readiness check not found: {path}")
    payload = json.loads(path.read_text(encoding="utf-8"))
    return Phase8ReadinessCheck.model_validate(payload)


def validate_readiness_gate(readiness: Phase8ReadinessCheck) -> None:
    if not readiness.canImportToStaging:
        issues = "; ".join(readiness.blockingIssuesForStaging) or "canImportToStaging is false"
        raise CatalogStagingImportError(f"Staging import blocked by readiness check: {issues}")
    if readiness.canPromoteToProduction:
        raise CatalogStagingImportError(
            "Readiness check reports canPromoteToProduction=true; "
            "Phase 8 must not promote to production.",
        )


def validate_curation_status(document: ReviewedCuratedCatalogDocument) -> None:
    status = document.curationMetadata.curationStatus
    if status in BLOCKED_CURATION_STATUSES:
        raise CatalogStagingImportError(
            f"Refusing import for curationStatus={status!r}",
        )
    if status not in ALLOWED_CURATION_STATUSES:
        raise CatalogStagingImportError(
            f"Unsupported curationStatus={status!r}; "
            f"expected one of {sorted(ALLOWED_CURATION_STATUSES)}",
        )
    if document.signoffReview is None:
        raise CatalogStagingImportError("signoffReview metadata is required for Phase 8 import.")


def is_rule_executable(rule_expression: dict[str, Any]) -> bool:
    return rule_expression.get("type") in EXECUTABLE_RULE_TYPES


def treats_courses_as_mandatory(rule_expression: dict[str, Any]) -> bool:
    rule_type = rule_expression.get("type")
    if rule_type in NON_MANDATORY_RULE_TYPES:
        return False
    if rule_type == "course_pool" and rule_expression.get("operator") == "choose_n":
        return False
    return False


def _count_manual_review_items(document: ReviewedCuratedCatalogDocument) -> int:
    count = 0
    if document.source.manualReviewRequired:
        count += 1
    for program in document.programs:
        if program.manualReviewRequired:
            count += 1
        for group in program.requirementGroups:
            if group.manualReviewRequired:
                count += 1
            for ref in group.courseReferences:
                if ref.manualReviewRequired:
                    count += 1
    return count


def validate_catalog_structure(document: ReviewedCuratedCatalogDocument) -> None:
    programs = document.programs
    if len(programs) != 3:
        raise CatalogStagingImportError(f"Expected exactly 3 programs, found {len(programs)}")

    codes = [program.programCode for program in programs]
    if codes != EXPECTED_PROGRAM_CODES:
        raise CatalogStagingImportError(
            f"Unexpected program codes: {codes}; expected {EXPECTED_PROGRAM_CODES}",
        )

    for program in programs:
        if program.totalCredits != EXPECTED_TOTAL_CREDITS:
            raise CatalogStagingImportError(
                f"{program.programCode}: totalCredits must be {EXPECTED_TOTAL_CREDITS}, "
                f"found {program.totalCredits}",
            )
        if not program.programCode:
            raise CatalogStagingImportError("Program missing programCode.")
        for group in program.requirementGroups:
            if not group.groupId:
                raise CatalogStagingImportError(
                    f"{program.programCode}: requirement group missing groupId.",
                )
            rule_expression = group.ruleExpression
            if (
                rule_expression.get("type") == "course_pool"
                and rule_expression.get("operator") == "choose_n"
                and group.courseReferences
            ):
                raise CatalogStagingImportError(
                    f"{group.groupId}: choose-N chain rule must not flatten mandatory courses.",
                )
            for ref in group.courseReferences:
                if not COURSE_NUMBER_PATTERN.fullmatch(ref.courseNumber):
                    raise CatalogStagingImportError(
                        f"{group.groupId}: invalid course number {ref.courseNumber!r}",
                    )


def build_import_metadata(
    *,
    staging_key: str,
    document: ReviewedCuratedCatalogDocument,
    import_run_id: str,
    catalog_path: Path,
    readiness_path: Path,
) -> StagingCatalogImportMetadata:
    signoff = document.signoffReview
    source_files = [str(catalog_path), str(readiness_path)]
    if signoff:
        source_files.extend(signoff.sourceFilesReviewed)

    return StagingCatalogImportMetadata(
        stagingKey=staging_key,
        sourceName=SOURCE_NAME,
        sourceType=SOURCE_TYPE,
        sourceVersion=document.source.catalogVersion,
        catalogYear=document.source.catalogYear,
        importedAt=_utc_now_iso(),
        importRunId=import_run_id,
        isStaging=True,
        productionEligible=False,
        requiresHumanSignoff=True,
        curationStatus=document.curationMetadata.curationStatus,
        signoffReviewStatus=signoff.reviewStatus if signoff else None,
        sourceFiles=sorted(set(source_files)),
    )


def build_catalog_staging_plan(
    document: ReviewedCuratedCatalogDocument,
    *,
    readiness: Phase8ReadinessCheck,
    catalog_path: Path,
    readiness_path: Path,
    settings: Settings,
    dry_run: bool = False,
) -> CatalogStagingImportPlan:
    assert_staging_settings(settings)
    validate_readiness_gate(readiness)
    validate_curation_status(document)
    validate_catalog_structure(document)

    catalog_version = document.source.catalogVersion
    dry_run_run_id = "dry-run"
    course_refs_observed = 0
    manual_review_items = _count_manual_review_items(document)

    program_documents: list[dict[str, Any]] = []
    requirement_documents: list[dict[str, Any]] = []
    rule_documents: list[dict[str, Any]] = []

    shared_catalog_context = {
        "catalogSource": document.source.model_dump(mode="json"),
        "curationMetadata": document.curationMetadata.model_dump(mode="json"),
        "curationReport": document.curationReport,
        "parserReport": document.parserReport,
        "signoffReview": (
            document.signoffReview.model_dump(mode="json")
            if document.signoffReview
            else None
        ),
        "readinessCheck": readiness.model_dump(mode="json"),
        "importWarnings": list(readiness.warnings),
        "unresolvedIssues": list(document.curationMetadata.unresolvedIssues),
    }

    for program in document.programs:
        program_key = program_staging_key(catalog_version, program.programCode)
        import_meta = build_import_metadata(
            staging_key=program_key,
            document=document,
            import_run_id=dry_run_run_id,
            catalog_path=catalog_path,
            readiness_path=readiness_path,
        )
        program_documents.append(
            {
                **import_meta.model_dump(mode="json"),
                **program.model_dump(mode="json"),
                **shared_catalog_context,
                "recordType": "degree_program",
            }
        )

        for group in program.requirementGroups:
            group_key = requirement_staging_key(catalog_version, group.groupId)
            rule_expression = group.ruleExpression
            executable = is_rule_executable(rule_expression)
            requirement_import_meta = build_import_metadata(
                staging_key=group_key,
                document=document,
                import_run_id=dry_run_run_id,
                catalog_path=catalog_path,
                readiness_path=readiness_path,
            )
            course_refs_observed += len(group.courseReferences)
            requirement_documents.append(
                {
                    **requirement_import_meta.model_dump(mode="json"),
                    "recordType": "degree_requirement_group",
                    "programCode": program.programCode,
                    "institutionId": program.institutionId,
                    "requirementGroup": group.model_dump(mode="json"),
                    "ruleIsExecutable": executable,
                    "treatsCoursesAsMandatory": treats_courses_as_mandatory(rule_expression),
                    "importWarnings": list(readiness.warnings),
                }
            )

    summary = CatalogStagingImportSummary(
        dryRun=dry_run,
        programsUpserted=len(program_documents),
        requirementsUpserted=len(requirement_documents),
        rulesUpserted=len(rule_documents),
        courseReferencesObserved=course_refs_observed,
        manualReviewRequiredItems=manual_review_items,
        warningsPreserved=list(readiness.warnings),
        stagingCollections={
            "degreePrograms": settings.staging_degree_programs_collection,
            "degreeRequirements": settings.staging_degree_requirements_collection,
            "catalogRules": settings.staging_catalog_rules_collection,
            "ingestionRuns": settings.staging_ingestion_runs_collection,
        },
    )

    return CatalogStagingImportPlan(
        program_documents=program_documents,
        requirement_documents=requirement_documents,
        rule_documents=rule_documents,
        summary=summary,
    )


def ensure_dds_catalog_staging_indexes(database: Database, settings: Settings) -> None:
    assert_staging_settings(settings)
    database[settings.staging_degree_programs_collection].create_index(
        [("stagingKey", 1)],
        unique=True,
        name="staging_degree_programs_unique_key",
    )
    database[settings.staging_degree_requirements_collection].create_index(
        [("stagingKey", 1)],
        unique=True,
        name="staging_degree_requirements_unique_key",
    )
    database[settings.staging_catalog_rules_collection].create_index(
        [("stagingKey", 1)],
        unique=True,
        name="staging_catalog_rules_unique_key",
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
            "status": "completed" if run.itemsInvalid == 0 else "failed",
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


def import_dds_catalog_to_staging(
    database: Database | None,
    *,
    catalog_path: Path | None = None,
    readiness_path: Path | None = None,
    settings: Settings | None = None,
    dry_run: bool = False,
) -> CatalogStagingImportSummary:
    settings = settings or get_settings()
    catalog_file = catalog_path or default_catalog_path()
    readiness_file = readiness_path or default_readiness_path()

    document = load_reviewed_catalog(catalog_file)
    readiness = load_phase8_readiness(readiness_file)

    plan = build_catalog_staging_plan(
        document,
        readiness=readiness,
        catalog_path=catalog_file,
        readiness_path=readiness_file,
        settings=settings,
        dry_run=dry_run,
    )

    if dry_run:
        logger.info("dds_catalog_staging_dry_run summary=%s", plan.summary.model_dump())
        return plan.summary

    if database is None:
        raise CatalogStagingImportError("Database connection is required for staging import.")
    ensure_dds_catalog_staging_indexes(database, settings)

    run_id, run = _start_ingestion_run(database, settings)
    run_id_str = str(run_id)

    for doc in plan.program_documents:
        doc["importRunId"] = run_id_str
        doc["importedAt"] = _utc_now_iso()
    for doc in plan.requirement_documents:
        doc["importRunId"] = run_id_str
        doc["importedAt"] = _utc_now_iso()
    for doc in plan.rule_documents:
        doc["importRunId"] = run_id_str
        doc["importedAt"] = _utc_now_iso()

    items_total = (
        len(plan.program_documents)
        + len(plan.requirement_documents)
        + len(plan.rule_documents)
    )
    run = run.model_copy(update={"itemsRead": items_total})

    _upsert_documents(
        database,
        settings.staging_degree_programs_collection,
        plan.program_documents,
    )
    _upsert_documents(
        database,
        settings.staging_degree_requirements_collection,
        plan.requirement_documents,
    )
    _upsert_documents(
        database,
        settings.staging_catalog_rules_collection,
        plan.rule_documents,
    )

    run = run.model_copy(
        update={
            "itemsValid": items_total,
            "metadata": {
                "importType": "dds_catalog_staging",
                "dryRun": False,
                "catalogPath": str(catalog_file),
                "readinessPath": str(readiness_file),
                "summary": plan.summary.model_dump(mode="json"),
            },
        }
    )
    finished_run = _finish_ingestion_run(database, settings, run_id, run)

    plan.summary.ingestionRunId = run_id_str
    plan.summary.ingestionStatus = finished_run.status
    return plan.summary
