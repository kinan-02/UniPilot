"""Phase 12 — guarded staging → production DDS promotion."""

from __future__ import annotations

import json
import uuid
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

from pymongo import ReplaceOne
from pymongo.database import Database

from app.config import Settings, get_settings
from app.promotion.dds_promotion_gate import EXCLUDED_COURSE_SKIP_REASON
from app.importers.dds_catalog_staging_importer import (
    PROMOTION_WRITE_COLLECTIONS,
    SOURCE_NAME as DDS_CATALOG_SOURCE,
)
from app.models.promotion import (
    ProductionPromotionResult,
    ProductionPromotionRun,
    PromotionGateResult,
    SkippedPromotionItem,
)
from app.promotion.graduation_pool_links import linked_credit_bucket_for_pool
from app.promotion.dds_promotion_gate import (
    _is_hard_requirement,
    build_promotion_gate_result,
)
from app.paths import service_root
from app.sources.technion_course_json import SOURCE_NAME as COURSE_JSON_SOURCE

PROMOTION_COLLECTION_SOURCE_NAMES: dict[str, str] = {
    "degree_programs": DDS_CATALOG_SOURCE,
    "degree_requirements": DDS_CATALOG_SOURCE,
    "catalog_rules": DDS_CATALOG_SOURCE,
    "courses": COURSE_JSON_SOURCE,
    "course_offerings": COURSE_JSON_SOURCE,
}

STAGING_FIELDS_TO_STRIP = frozenset(
    {
        "isStaging",
        "productionEligible",
        "requiresHumanSignoff",
        "requiresHumanReview",
        "importRunId",
        "importedAt",
        "stagingKey",
        "_id",
    }
)

GENERAL_TECHNION_HARD_BUCKET_SUFFIXES = frozenset(
    {"enrichment", "free-elective", "physical-education"}
)


def _hard_requirement_is_mandatory(group_id: str) -> bool:
    suffix = group_id.split(":")[-1] if ":" in group_id else group_id
    if suffix == "core-mandatory":
        return True
    if suffix in GENERAL_TECHNION_HARD_BUCKET_SUFFIXES:
        return False
    return True


class ProductionPromotionError(Exception):
    """Raised when promotion must abort before writing production data."""


def default_production_promotion_json_path() -> Path:
    return service_root() / "data" / "reports" / "technion" / "dds_production_promotion_report.json"


def default_production_promotion_md_path() -> Path:
    return service_root() / "data" / "reports" / "technion" / "dds_production_promotion_report.md"


def _utc_now_iso() -> str:
    return datetime.now(UTC).replace(microsecond=0).isoformat()


def _new_promotion_run_id() -> str:
    return f"dds-promotion-{uuid.uuid4().hex[:12]}"


def production_program_key(program_code: str, catalog_version: str) -> str:
    return f"technion-dds:program:{program_code}:{catalog_version}"


def production_requirement_key(group_id: str, catalog_version: str) -> str:
    return f"technion-dds:requirement:{group_id}:{catalog_version}"


def production_advisory_requirement_key(group_id: str, catalog_version: str) -> str:
    return f"technion-dds:advisory-rule:req:{group_id}:{catalog_version}"


def production_course_key(course_number: str) -> str:
    return f"technion:course:{course_number}"


def production_offering_key(course_number: str, academic_year: int, semester_code: int) -> str:
    return f"technion:course-offering:{course_number}:{academic_year}:{semester_code}"


def _strip_staging_fields(document: dict[str, Any]) -> dict[str, Any]:
    return {key: value for key, value in document.items() if key not in STAGING_FIELDS_TO_STRIP}


def _source_refs(*paths: str) -> list[dict[str, str]]:
    return [{"type": "file", "path": path} for path in paths if path]


def _load_staging_by_key(
    database: Database,
    collection: str,
    staging_keys: set[str],
) -> dict[str, dict[str, Any]]:
    if not staging_keys:
        return {}
    documents = database[collection].find({"stagingKey": {"$in": list(staging_keys)}})
    return {doc["stagingKey"]: doc for doc in documents if doc.get("stagingKey")}


def _validate_document_safety(document: dict[str, Any], *, context: str) -> None:
    if document.get("isStaging") is True:
        raise ProductionPromotionError(f"{context}: refused to write document with isStaging=true.")
    if document.get("productionEligible") is not False and "productionEligible" in document:
        raise ProductionPromotionError(f"{context}: invalid productionEligible flag.")
    metadata = document.get("metadata", {})
    if metadata.get("degreeRequirementsInferred") is True:
        raise ProductionPromotionError(f"{context}: degree requirements must not be inferred from course JSON.")


def map_staging_program_to_production(
    staging: dict[str, Any],
    *,
    promotion_run_id: str,
    promoted_at: str,
    catalog_version: str,
) -> dict[str, Any]:
    program_code = staging.get("programCode", "")
    production_key = production_program_key(program_code, catalog_version)
    document = {
        "productionKey": production_key,
        "institutionId": staging.get("institutionId", "technion"),
        "programCode": program_code,
        "name": staging.get("name"),
        "nameEn": staging.get("nameEn"),
        "totalCredits": staging.get("totalCredits"),
        "catalogYear": staging.get("catalogYear"),
        "catalogVersion": catalog_version,
        "paths": staging.get("paths", []),
        "sourceName": DDS_CATALOG_SOURCE,
        "sourceType": staging.get("sourceType", "dds_catalog_curated_reviewed"),
        "sourceVersion": staging.get("sourceVersion", catalog_version),
        "sourceMetadata": {
            "curationStatus": staging.get("curationStatus"),
            "signoffReview": staging.get("signoffReview"),
            "curationReport": staging.get("curationReport"),
        },
        "sourceRefs": _source_refs(*(staging.get("sourceFiles") or [])),
        "status": "published",
        "promotedAt": promoted_at,
        "promotionRunId": promotion_run_id,
        "updatedAt": promoted_at,
    }
    _validate_document_safety(document, context=f"degree_program {program_code}")
    return document


def map_staging_requirement_to_production(
    staging: dict[str, Any],
    *,
    promotion_run_id: str,
    promoted_at: str,
    catalog_version: str,
) -> dict[str, Any]:
    group = staging.get("requirementGroup", {})
    group_id = group.get("groupId", "")
    if not _is_hard_requirement(staging):
        raise ProductionPromotionError(f"Refusing to promote non-executable requirement {group_id} as hard.")
    production_key = production_requirement_key(group_id, catalog_version)
    document = {
        "productionKey": production_key,
        "institutionId": staging.get("institutionId", "technion"),
        "programCode": staging.get("programCode"),
        "requirementGroupId": group_id,
        "title": group.get("title"),
        "requirementType": group.get("requirementType"),
        "minCredits": group.get("minCredits"),
        "courseReferences": group.get("courseReferences", []),
        "ruleExpression": group.get("ruleExpression"),
        "ruleIsExecutable": True,
        "isMandatory": _hard_requirement_is_mandatory(str(group_id)),
        "enforceInGraduationProgress": True,
        "advisoryOnly": False,
        "catalogYear": staging.get("catalogYear"),
        "catalogVersion": catalog_version,
        "sourceName": DDS_CATALOG_SOURCE,
        "sourceType": staging.get("sourceType", "dds_catalog_curated_reviewed"),
        "sourceMetadata": {
            "stagingKey": staging.get("stagingKey"),
            "manualReviewRequired": group.get("manualReviewRequired"),
            "confidence": group.get("confidence"),
        },
        "sourceRefs": _source_refs(*(staging.get("sourceFiles") or [])),
        "status": "published",
        "promotedAt": promoted_at,
        "promotionRunId": promotion_run_id,
        "updatedAt": promoted_at,
    }
    _validate_document_safety(document, context=f"degree_requirement {group_id}")
    return document


def map_staging_advisory_requirement_to_production(
    staging: dict[str, Any],
    *,
    promotion_run_id: str,
    promoted_at: str,
    catalog_version: str,
) -> dict[str, Any]:
    group = staging.get("requirementGroup", {})
    group_id = group.get("groupId", "")
    production_key = production_advisory_requirement_key(group_id, catalog_version)
    linked_credit_bucket_id = linked_credit_bucket_for_pool(group_id)
    source_metadata: dict[str, Any] = {
        "stagingKey": staging.get("stagingKey"),
        "nonExecutableRulesPolicy": "advisory-only",
    }
    if linked_credit_bucket_id:
        source_metadata["graduationPoolLinkPhase"] = "15.1"
        source_metadata["linkedCreditBucketId"] = linked_credit_bucket_id

    document = {
        "productionKey": production_key,
        "institutionId": staging.get("institutionId", "technion"),
        "programCode": staging.get("programCode"),
        "requirementGroupId": group_id,
        "recordType": "advisory_requirement_group",
        "title": group.get("title"),
        "requirementType": group.get("requirementType"),
        "courseReferences": group.get("courseReferences", []),
        "catalogDescription": group.get("catalogDescription"),
        "ruleExpression": group.get("ruleExpression"),
        "ruleIsExecutable": False,
        "advisoryOnly": True,
        "enforceInGraduationProgress": False,
        "manualReviewRequired": True,
        "isMandatory": False,
        "catalogYear": staging.get("catalogYear"),
        "catalogVersion": catalog_version,
        "sourceName": DDS_CATALOG_SOURCE,
        "sourceType": staging.get("sourceType", "dds_catalog_curated_reviewed"),
        "sourceMetadata": source_metadata,
        "sourceRefs": _source_refs(*(staging.get("sourceFiles") or [])),
        "status": "published",
        "promotedAt": promoted_at,
        "promotionRunId": promotion_run_id,
        "updatedAt": promoted_at,
    }
    if linked_credit_bucket_id:
        document["linkedCreditBucketId"] = linked_credit_bucket_id
    _validate_document_safety(document, context=f"advisory_requirement {group_id}")
    return document


def map_staging_course_to_production(
    staging: dict[str, Any],
    *,
    promotion_run_id: str,
    promoted_at: str,
    catalog_version: str,
    production_excluded_course_numbers: set[str] | None = None,
) -> dict[str, Any]:
    number = staging.get("courseNumber", "")
    excluded = production_excluded_course_numbers or set()
    if number in excluded:
        raise ProductionPromotionError(f"Refusing to promote excluded course {number}.")
    production_key = production_course_key(number)
    metadata = dict(staging.get("metadata") or {})
    metadata["degreeRequirementsInferred"] = False
    document = {
        "productionKey": production_key,
        "institutionId": staging.get("institutionId", "technion"),
        "courseNumber": number,
        "titleHebrew": staging.get("titleHebrew"),
        "title": staging.get("titleHebrew"),
        "credits": staging.get("credits"),
        "faculty": staging.get("faculty"),
        "studyFramework": staging.get("studyFramework"),
        "syllabus": staging.get("syllabus"),
        "prerequisitesText": staging.get("prerequisitesText"),
        "corequisitesText": staging.get("corequisitesText"),
        "noAdditionalCreditText": staging.get("noAdditionalCreditText"),
        "instructors": staging.get("instructors"),
        "notes": staging.get("notes"),
        "sourceFiles": staging.get("sourceFiles", []),
        "semestersOffered": staging.get("semestersOffered", []),
        "exams": staging.get("exams", {}),
        "scheduleSummary": staging.get("scheduleSummary"),
        "metadata": metadata,
        "catalogYear": staging.get("catalogYear", 2025),
        "catalogVersion": catalog_version,
        "sourceName": COURSE_JSON_SOURCE,
        "sourceType": staging.get("sourceType", "technion_course_json"),
        "status": "published",
        "promotedAt": promoted_at,
        "promotionRunId": promotion_run_id,
        "updatedAt": promoted_at,
    }
    _validate_document_safety(document, context=f"course {number}")
    return document


def map_staging_offering_to_production(
    staging: dict[str, Any],
    *,
    promotion_run_id: str,
    promoted_at: str,
    catalog_version: str,
    promoted_course_numbers: set[str],
    production_excluded_course_numbers: set[str] | None = None,
) -> dict[str, Any]:
    number = staging.get("courseNumber", "")
    excluded = production_excluded_course_numbers or set()
    if number in excluded:
        raise ProductionPromotionError(f"Refusing to promote offering for excluded course {number}.")
    if number not in promoted_course_numbers:
        raise ProductionPromotionError(f"Refusing offering for non-promoted course {number}.")
    academic_year = int(staging.get("academicYear", 0))
    semester_code = int(staging.get("semesterCode", 0))
    production_key = production_offering_key(number, academic_year, semester_code)
    document = {
        "productionKey": production_key,
        "courseNumber": number,
        "courseProductionKey": production_course_key(number),
        "academicYear": academic_year,
        "semesterCode": semester_code,
        "semesterName": staging.get("semesterName"),
        "scheduleGroups": staging.get("scheduleGroups", []),
        "examDates": staging.get("examDates", {}),
        "instructors": staging.get("instructors"),
        "sourceFile": staging.get("sourceFile"),
        "catalogVersion": catalog_version,
        "sourceName": COURSE_JSON_SOURCE,
        "sourceType": "technion_course_json",
        "status": "published",
        "promotedAt": promoted_at,
        "promotionRunId": promotion_run_id,
        "updatedAt": promoted_at,
    }
    _validate_document_safety(document, context=f"course_offering {production_key}")
    return document


def _collection_name_for_logical(logical: str, settings: Settings) -> str:
    mapping = {
        "degreePrograms": settings.production_degree_programs_collection,
        "hardDegreeRequirements": settings.production_degree_requirements_collection,
        "advisoryCatalogRules": settings.production_catalog_rules_collection,
        "courses": settings.production_courses_collection,
        "courseOfferings": settings.production_course_offerings_collection,
    }
    return mapping[logical]


def ensure_production_promotion_indexes(database: Database, settings: Settings) -> None:
    for collection in PROMOTION_WRITE_COLLECTIONS:
        database[collection].create_index(
            [("productionKey", 1)],
            unique=True,
            name=f"{collection}_production_key_unique",
        )
    database[settings.production_promotion_runs_collection].create_index(
        [("promotionRunId", 1)],
        unique=True,
        name="promotion_runs_unique_id",
    )


def validate_production_collections_for_promotion(
    database: Database,
    *,
    settings: Settings,
    planned_keys_by_collection: dict[str, set[str]],
    catalog_version: str,
    source_name: str,
) -> None:
    for collection in sorted(PROMOTION_WRITE_COLLECTIONS):
        planned_keys = planned_keys_by_collection.get(collection, set())
        existing_count = database[collection].count_documents({})
        if existing_count == 0:
            continue

        foreign_filter = {
            "$or": [
                {"productionKey": {"$exists": False}},
                {"productionKey": {"$nin": list(planned_keys)}},
            ]
        }
        foreign_count = database[collection].count_documents(foreign_filter)
        if foreign_count > 0:
            raise ProductionPromotionError(
                f"Production collection `{collection}` contains {foreign_count} document(s) "
                "outside this promotion plan. Phase 12 requires empty collections or idempotent "
                "re-promotion of the same stable keys."
            )

        expected_source = PROMOTION_COLLECTION_SOURCE_NAMES.get(collection, source_name)
        version_conflicts = database[collection].count_documents(
            {
                "productionKey": {"$in": list(planned_keys)},
                "$or": [
                    {"catalogVersion": {"$exists": True, "$ne": catalog_version}},
                    {"sourceName": {"$exists": True, "$ne": expected_source}},
                ],
            }
        )
        if version_conflicts > 0:
            raise ProductionPromotionError(
                f"Production collection `{collection}` has conflicting catalogVersion/sourceName "
                "for planned production keys."
            )


def _retire_superseded_catalog_rules(
    database: Database,
    *,
    settings: Settings,
    planned_production_keys: set[str],
    catalog_version: str,
) -> int:
    """Remove retired DDS advisory rules (e.g. renamed pool group ids) before re-promotion."""
    if not planned_production_keys:
        return 0
    result = database[settings.production_catalog_rules_collection].delete_many(
        {
            "catalogVersion": catalog_version,
            "sourceName": DDS_CATALOG_SOURCE,
            "productionKey": {"$nin": list(planned_production_keys)},
        }
    )
    return int(result.deleted_count)


def build_production_documents(
    database: Database,
    gate: PromotionGateResult,
    *,
    settings: Settings,
    promotion_run_id: str,
    promoted_at: str,
) -> tuple[dict[str, list[dict[str, Any]]], dict[str, set[str]]]:
    catalog_version = gate.catalogVersion or "2025-2026"
    plan = gate.plannedWrites

    program_keys = {item.stagingKey for item in plan.degreePrograms}
    requirement_keys = {item.stagingKey for item in plan.hardDegreeRequirements}
    advisory_req_keys = {
        item.stagingKey for item in plan.advisoryCatalogRules if item.itemType == "advisory_requirement_group"
    }
    course_keys = {item.stagingKey for item in plan.courses}
    offering_keys = {item.stagingKey for item in plan.courseOfferings}

    programs_by_key = _load_staging_by_key(
        database, settings.staging_degree_programs_collection, program_keys
    )
    requirements_by_key = _load_staging_by_key(
        database, settings.staging_degree_requirements_collection, requirement_keys
    )
    advisory_reqs_by_key = _load_staging_by_key(
        database, settings.staging_degree_requirements_collection, advisory_req_keys
    )
    courses_by_key = _load_staging_by_key(database, settings.staging_courses_collection, course_keys)
    offerings_by_key = _load_staging_by_key(
        database, settings.staging_course_offerings_collection, offering_keys
    )

    promoted_numbers = {item.identifier for item in plan.courses}
    excluded_numbers = set(gate.policiesApplied.productionExcludedCourseNumbers)
    documents: dict[str, list[dict[str, Any]]] = {
        settings.production_degree_programs_collection: [],
        settings.production_degree_requirements_collection: [],
        settings.production_catalog_rules_collection: [],
        settings.production_courses_collection: [],
        settings.production_course_offerings_collection: [],
    }
    planned_keys: dict[str, set[str]] = {name: set() for name in PROMOTION_WRITE_COLLECTIONS}

    for item in plan.degreePrograms:
        staging = programs_by_key.get(item.stagingKey)
        if not staging:
            raise ProductionPromotionError(f"Missing staging program for key {item.stagingKey}")
        doc = map_staging_program_to_production(
            staging,
            promotion_run_id=promotion_run_id,
            promoted_at=promoted_at,
            catalog_version=catalog_version,
        )
        documents[settings.production_degree_programs_collection].append(doc)
        planned_keys[settings.production_degree_programs_collection].add(doc["productionKey"])

    for item in plan.hardDegreeRequirements:
        staging = requirements_by_key.get(item.stagingKey)
        if not staging:
            raise ProductionPromotionError(f"Missing staging requirement for key {item.stagingKey}")
        doc = map_staging_requirement_to_production(
            staging,
            promotion_run_id=promotion_run_id,
            promoted_at=promoted_at,
            catalog_version=catalog_version,
        )
        documents[settings.production_degree_requirements_collection].append(doc)
        planned_keys[settings.production_degree_requirements_collection].add(doc["productionKey"])

    for item in plan.advisoryCatalogRules:
        if item.itemType != "advisory_requirement_group":
            raise ProductionPromotionError(
                f"Unsupported advisory promotion item type: {item.itemType!r}"
            )
        staging = advisory_reqs_by_key.get(item.stagingKey)
        if not staging:
            raise ProductionPromotionError(f"Missing advisory requirement staging key {item.stagingKey}")
        doc = map_staging_advisory_requirement_to_production(
            staging,
            promotion_run_id=promotion_run_id,
            promoted_at=promoted_at,
            catalog_version=catalog_version,
        )
        if doc.get("enforceInGraduationProgress") is not False:
            raise ProductionPromotionError(f"Advisory rule {doc['productionKey']} must not be enforced.")
        documents[settings.production_catalog_rules_collection].append(doc)
        planned_keys[settings.production_catalog_rules_collection].add(doc["productionKey"])

    for item in plan.courses:
        staging = courses_by_key.get(item.stagingKey)
        if not staging:
            raise ProductionPromotionError(f"Missing staging course for key {item.stagingKey}")
        doc = map_staging_course_to_production(
            staging,
            promotion_run_id=promotion_run_id,
            promoted_at=promoted_at,
            catalog_version=catalog_version,
            production_excluded_course_numbers=excluded_numbers,
        )
        documents[settings.production_courses_collection].append(doc)
        planned_keys[settings.production_courses_collection].add(doc["productionKey"])

    for item in plan.courseOfferings:
        staging = offerings_by_key.get(item.stagingKey)
        if not staging:
            raise ProductionPromotionError(f"Missing staging offering for key {item.stagingKey}")
        doc = map_staging_offering_to_production(
            staging,
            promotion_run_id=promotion_run_id,
            promoted_at=promoted_at,
            catalog_version=catalog_version,
            promoted_course_numbers=promoted_numbers,
            production_excluded_course_numbers=excluded_numbers,
        )
        documents[settings.production_course_offerings_collection].append(doc)
        planned_keys[settings.production_course_offerings_collection].add(doc["productionKey"])

    return documents, planned_keys


def _upsert_production_documents(
    database: Database,
    documents_by_collection: dict[str, list[dict[str, Any]]],
) -> dict[str, int]:
    counts_written: dict[str, int] = {}
    for collection, documents in documents_by_collection.items():
        if collection not in PROMOTION_WRITE_COLLECTIONS:
            raise ProductionPromotionError(f"Refusing to write unapproved collection `{collection}`.")
        if not documents:
            counts_written[collection] = 0
            continue
        operations = [
            ReplaceOne({"productionKey": doc["productionKey"]}, doc, upsert=True) for doc in documents
        ]
        result = database[collection].bulk_write(operations, ordered=False)
        counts_written[collection] = result.upserted_count + result.modified_count + result.matched_count
    return counts_written


def _production_counts(database: Database, settings: Settings) -> dict[str, int]:
    counts: dict[str, int] = {}
    for collection in sorted(PROMOTION_WRITE_COLLECTIONS):
        counts[collection] = database[collection].count_documents({})
    counts[settings.production_promotion_runs_collection] = database[
        settings.production_promotion_runs_collection
    ].count_documents({})
    return counts


def render_production_promotion_markdown(result: ProductionPromotionResult) -> str:
    run = result.promotionRun
    gate = result.gate
    lines = [
        "# DDS Production Promotion Report (Phase 12)",
        "",
        f"Promotion run: `{run.promotionRunId}`",
        f"Started: {run.startedAt}",
        f"Finished: {run.finishedAt}",
        f"Status: **{run.status}**",
        f"Gate status: **{run.gateStatus}**",
        f"Dry run: **{run.dryRun}**",
        f"Confirmation flag: **{run.confirmationFlagProvided}**",
        f"Production writes performed: **{result.productionWritesPerformed}**",
        "",
        "## Policies applied",
    ]
    if run.policiesApplied:
        policy = run.policiesApplied
        lines.extend(
            [
                f"- nonExecutableRulesPolicy: `{policy.nonExecutableRulesPolicy}`",
                f"- enforceNonExecutableRulesInProduction: `{policy.enforceNonExecutableRulesInProduction}`",
                f"- productionExcludedCoursePolicy: `{policy.productionExcludedCoursePolicy}`",
                f"- productionExcludedCourseNumbers: {len(policy.productionExcludedCourseNumbers)}",
            ]
        )
    lines.extend(["", "## Counts planned"])
    for key, value in run.countsPlanned.items():
        lines.append(f"- {key}: {value}")
    lines.extend(["", "## Counts written"])
    for key, value in run.countsWritten.items():
        lines.append(f"- {key}: {value}")
    lines.extend(["", "## Production collection counts"])
    lines.append("### Before")
    for key, value in run.productionCollectionCountsBefore.items():
        lines.append(f"- {key}: {value}")
    lines.append("### After")
    for key, value in run.productionCollectionCountsAfter.items():
        lines.append(f"- {key}: {value}")
    lines.extend(["", "## Skipped excluded courses"])
    excluded = [
        item for item in run.skippedItems if item.reason == EXCLUDED_COURSE_SKIP_REASON
    ]
    for item in excluded[:20]:
        lines.append(f"- `{item.identifier}` — {item.reason}")
    if len(excluded) > 20:
        lines.append(f"- ... and {len(excluded) - 20} more")
    lines.extend(["", "## Advisory rule handling"])
    lines.append(
        "- Non-executable groups promoted to `catalog_rules` with `enforceInGraduationProgress: false`."
    )
    lines.extend(["", "## Rollback notes"])
    for note in run.rollbackNotes:
        lines.append(f"- {note}")
    if run.errors:
        lines.extend(["", "## Errors"])
        for error in run.errors:
            lines.append(f"- {error}")
    if gate.blockers:
        lines.extend(["", "## Gate blockers"])
        for blocker in gate.blockers:
            lines.append(f"- {blocker}")
    lines.extend(
        [
            "",
            "## Safety",
            "- Staging collections were not modified.",
            "- Production promotion used stable `productionKey` upserts.",
            "- Roll back with `rollback-dds-production-promotion --promotion-run-id <id> "
            "--i-confirm-dangerous-production-write` (deletes only matching promotionRunId).",
        ]
    )
    return "\n".join(lines) + "\n"


def write_production_promotion_report(
    result: ProductionPromotionResult,
    *,
    json_path: Path,
    md_path: Path,
) -> None:
    json_path.parent.mkdir(parents=True, exist_ok=True)
    md_path.parent.mkdir(parents=True, exist_ok=True)
    json_path.write_text(
        json.dumps(result.model_dump(mode="json"), indent=2, ensure_ascii=False) + "\n",
        encoding="utf-8",
    )
    md_path.write_text(render_production_promotion_markdown(result), encoding="utf-8")


def run_dds_production_promotion(
    database: Database,
    *,
    settings: Settings | None = None,
    confirm_dangerous: bool = False,
    dry_run: bool = False,
    allow_warnings: bool = True,
    json_path: Path | None = None,
    md_path: Path | None = None,
) -> ProductionPromotionResult:
    settings = settings or get_settings()
    started_at = _utc_now_iso()
    promotion_run_id = _new_promotion_run_id()
    counts_before = _production_counts(database, settings)

    gate = build_promotion_gate_result(
        database,
        settings=settings,
        allow_warnings=allow_warnings,
        dry_run=dry_run,
    )

    skipped_items = list(gate.plannedWrites.skippedItems)
    run = ProductionPromotionRun(
        promotionRunId=promotion_run_id,
        sourceName=gate.sourceName,
        catalogYear=gate.catalogYear,
        catalogVersion=gate.catalogVersion,
        startedAt=started_at,
        status="planned",
        gateStatus=gate.gateStatus,
        dryRun=dry_run,
        confirmationFlagProvided=confirm_dangerous,
        countsPlanned=dict(gate.plannedWrites.counts),
        skippedItems=skipped_items,
        policiesApplied=gate.policiesApplied,
        productionCollectionCountsBefore=counts_before,
        rollbackNotes=[
            f"Delete production docs with promotionRunId={promotion_run_id} to roll back this run.",
            "Do not delete staging data.",
            "Advisory catalog rules remain non-enforced in graduation progress.",
        ],
    )

    if not dry_run and not confirm_dangerous:
        run.status = "failed"
        run.finishedAt = _utc_now_iso()
        run.errors.append(
            "Refusing production promotion without --i-confirm-dangerous-production-write."
        )
        result = ProductionPromotionResult(
            promotionRun=run,
            gate=gate,
            productionWritesPerformed=False,
        )
        out_json = json_path or default_production_promotion_json_path()
        out_md = md_path or default_production_promotion_md_path()
        write_production_promotion_report(result, json_path=out_json, md_path=out_md)
        return result

    if not gate.canPromote or gate.gateStatus == "fail":
        run.status = "failed"
        run.finishedAt = _utc_now_iso()
        run.errors.extend(gate.blockers or ["Promotion gate failed."])
        result = ProductionPromotionResult(
            promotionRun=run,
            gate=gate,
            productionWritesPerformed=False,
        )
        out_json = json_path or default_production_promotion_json_path()
        out_md = md_path or default_production_promotion_md_path()
        write_production_promotion_report(result, json_path=out_json, md_path=out_md)
        return result

    promoted_at = _utc_now_iso()
    try:
        documents_by_collection, planned_keys = build_production_documents(
            database,
            gate,
            settings=settings,
            promotion_run_id=promotion_run_id,
            promoted_at=promoted_at,
        )
        run.plannedProductionKeys = {name: sorted(keys) for name, keys in planned_keys.items()}
        run.productionCollectionsTouched = sorted(PROMOTION_WRITE_COLLECTIONS)

        if dry_run:
            run.status = "completed"
            run.finishedAt = _utc_now_iso()
            run.countsWritten = {name: 0 for name in PROMOTION_WRITE_COLLECTIONS}
            run.productionCollectionCountsAfter = dict(counts_before)
            result = ProductionPromotionResult(
                promotionRun=run,
                gate=gate,
                productionWritesPerformed=False,
            )
            out_json = json_path or default_production_promotion_json_path()
            out_md = md_path or default_production_promotion_md_path()
            write_production_promotion_report(result, json_path=out_json, md_path=out_md)
            return result

        _retire_superseded_catalog_rules(
            database,
            settings=settings,
            planned_production_keys=planned_keys.get(settings.production_catalog_rules_collection, set()),
            catalog_version=gate.catalogVersion or "2025-2026",
        )

        validate_production_collections_for_promotion(
            database,
            settings=settings,
            planned_keys_by_collection=planned_keys,
            catalog_version=gate.catalogVersion or "2025-2026",
            source_name=gate.sourceName,
        )
        ensure_production_promotion_indexes(database, settings)
        counts_written = _upsert_production_documents(database, documents_by_collection)
        run.countsWritten = {
            settings.production_degree_programs_collection: len(
                documents_by_collection[settings.production_degree_programs_collection]
            ),
            settings.production_degree_requirements_collection: len(
                documents_by_collection[settings.production_degree_requirements_collection]
            ),
            settings.production_catalog_rules_collection: len(
                documents_by_collection[settings.production_catalog_rules_collection]
            ),
            settings.production_courses_collection: len(
                documents_by_collection[settings.production_courses_collection]
            ),
            settings.production_course_offerings_collection: len(
                documents_by_collection[settings.production_course_offerings_collection]
            ),
        }
        run.status = "completed"
        run.finishedAt = _utc_now_iso()

        audit_doc = run.model_dump(mode="json")
        database[settings.production_promotion_runs_collection].replace_one(
            {"promotionRunId": promotion_run_id},
            audit_doc,
            upsert=True,
        )

        counts_after = _production_counts(database, settings)
        run.productionCollectionCountsAfter = counts_after

        result = ProductionPromotionResult(
            promotionRun=run,
            gate=gate,
            productionWritesPerformed=True,
            reportPaths={
                "json": str(json_path or default_production_promotion_json_path()),
                "md": str(md_path or default_production_promotion_md_path()),
            },
        )
        out_json = json_path or default_production_promotion_json_path()
        out_md = md_path or default_production_promotion_md_path()
        write_production_promotion_report(result, json_path=out_json, md_path=out_md)
        return result
    except Exception as exc:
        run.status = "failed"
        run.finishedAt = _utc_now_iso()
        run.errors.append(str(exc))
        run.productionCollectionCountsAfter = _production_counts(database, settings)
        result = ProductionPromotionResult(
            promotionRun=run,
            gate=gate,
            productionWritesPerformed=False,
        )
        out_json = json_path or default_production_promotion_json_path()
        out_md = md_path or default_production_promotion_md_path()
        write_production_promotion_report(result, json_path=out_json, md_path=out_md)
        return result


def run_dds_production_rollback(
    database: Database,
    *,
    promotion_run_id: str,
    confirm_dangerous: bool = False,
    settings: Settings | None = None,
) -> dict[str, Any]:
    settings = settings or get_settings()
    if not confirm_dangerous:
        return {
            "error": "Refusing rollback without --i-confirm-dangerous-production-write.",
            "promotionRunId": promotion_run_id,
            "deletedCounts": {},
        }

    audit = database[settings.production_promotion_runs_collection].find_one(
        {"promotionRunId": promotion_run_id}
    )
    if not audit:
        return {
            "error": f"Promotion run not found: {promotion_run_id}",
            "promotionRunId": promotion_run_id,
            "deletedCounts": {},
        }

    deleted: dict[str, int] = {}
    for collection in sorted(PROMOTION_WRITE_COLLECTIONS):
        result = database[collection].delete_many({"promotionRunId": promotion_run_id})
        deleted[collection] = result.deleted_count

    database[settings.production_promotion_runs_collection].update_one(
        {"promotionRunId": promotion_run_id},
        {"$set": {"status": "rolled_back", "finishedAt": _utc_now_iso()}},
    )
    return {
        "promotionRunId": promotion_run_id,
        "status": "rolled_back",
        "deletedCounts": deleted,
        "note": "Deleted only documents matching promotionRunId. Staging data untouched.",
    }
