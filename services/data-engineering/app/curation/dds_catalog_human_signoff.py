"""Record human sign-off policy for DDS catalog promotion gate design."""

from __future__ import annotations

import json
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

from app.curation.dds_catalog_curator import default_reviewed_output_path
from app.importers.dds_catalog_staging_importer import default_readiness_path

NON_EXECUTABLE_RULE_GROUP_IDS: tuple[str, ...] = (
    "009216-1-000:semester-1-matrix",
    "009216-1-000:semester-2-matrix",
    "009216-1-000:semester-3-matrix",
    "009216-1-000:semester-4-matrix",
    "009216-1-000:elective-ds-pool",
    "009216-1-000:elective-faculty-pool",
    "009216-1-000:math-analytics-track:requirements",
    "009216-1-000:cognition-track:requirements",
    "009009-1-000:semester-2-matrix",
    "009009-1-000:semester-3-matrix",
    "009009-1-000:semester-4-matrix",
    "009009-1-000:semester-5-matrix",
    "009009-1-000:ie-statistics-elective-chain",
    "009009-1-000:ie-behavior-science-chain",
    "009009-1-000:ie-focus-chain",
    "009009-1-000:ie-additional-faculty-electives",
    "009118-1-000:semester-3-matrix",
    "009118-1-000:is-behavior-science-chain",
    "009118-1-000:is-focus-chain-performance",
    "009118-1-000:is-focus-chain-ml",
    "009118-1-000:is-focus-chain-game-theory",
    "009118-1-000:is-additional-faculty-electives",
)

PRODUCTION_EXCLUDED_COURSE_NUMBERS: tuple[str, ...] = (
    "00960226",
    "00960244",
    "00960251",
    "00960293",
    "00960311",
    "00960335",
    "00960351",
    "00960470",
    "00970211",
    "00970280",
    "00970329",
    "00980312",
    "00980455",
    "02740300",
)


def _utc_now_iso() -> str:
    return datetime.now(UTC).replace(microsecond=0).isoformat()


def build_human_signoff_payload(*, signed_off_by: str = "project-owner") -> dict[str, Any]:
    return {
        "signedOffBy": signed_off_by,
        "signedOffAt": _utc_now_iso(),
        "nonExecutableRulesPolicy": "advisory-only",
        "enforceNonExecutableRulesInProduction": False,
        "signedOffNonExecutableRuleGroupIds": list(NON_EXECUTABLE_RULE_GROUP_IDS),
        "productionExcludedCourseNumbers": list(PRODUCTION_EXCLUDED_COURSE_NUMBERS),
        "productionExcludedCoursePolicy": "omit-from-production-do-not-ingest",
        "notes": (
            "Human sign-off: 22 non-executable requirement groups may be used for display, "
            "planning, and manual review but must not be mandatory auto-enforcement in production. "
            "Phase 15.1: DS and faculty elective pools carry linkedCreditBucketId for graduation "
            "eligibility while remaining advisory in catalog APIs. "
            "14 catalog course references absent from 2025 semester JSON are excluded from "
            "production promotion and must not be ingested as production course records."
        ),
    }


def apply_human_signoff_to_catalog(
    document: dict[str, Any],
    *,
    signed_off_by: str = "project-owner",
) -> dict[str, Any]:
    human_signoff = build_human_signoff_payload(signed_off_by=signed_off_by)
    report = document.setdefault("curationReport", {})
    report["humanSignoff"] = human_signoff

    signoff = document.setdefault("signoffReview", {})
    signoff["reviewedAt"] = human_signoff["signedOffAt"]
    signoff["productionPromotionRecommendation"] = (
        "Non-executable groups signed off as advisory-only. "
        "Excluded cross-link gap courses must not be added to production."
    )
    signoff.setdefault("verifiedItems", [])
    verified = [
        "Human sign-off: 22 non-executable rule groups are advisory-only (not mandatory enforcement).",
        "Human sign-off: 14 catalog courses excluded from production (not in 2025 semester JSON).",
    ]
    for item in verified:
        if item not in signoff["verifiedItems"]:
            signoff["verifiedItems"].append(item)

    signoff["unresolvedItems"] = [
        item
        for item in signoff.get("unresolvedItems", [])
        if not any(
            token in item
            for token in (
                "Missing titleHint:",
                "titleHint still missing",
                "ie-additional-faculty-electives: could not locate",
                "is-additional-faculty-electives: could not locate",
            )
        )
    ]

    curation = document.setdefault("curationMetadata", {})
    curation.setdefault("knownLimitations", [])
    limitation = (
        "Human sign-off recorded: non-executable rules are advisory-only; "
        f"{len(PRODUCTION_EXCLUDED_COURSE_NUMBERS)} catalog course refs are production-excluded."
    )
    if limitation not in curation["knownLimitations"]:
        curation["knownLimitations"].append(limitation)

    return human_signoff


def build_readiness_after_human_signoff(document: dict[str, Any]) -> dict[str, Any]:
    human = document.get("curationReport", {}).get("humanSignoff", {})
    counts_after = document.get("curationMetadata", {}).get("countsAfter", {})
    return {
        "canImportToStaging": True,
        "canPromoteToProduction": False,
        "blockingIssuesForStaging": [],
        "blockingIssuesForProduction": [
            "Production promotion gate not implemented yet (Phase 11+).",
            "Excluded catalog course references must not be ingested as production courses.",
        ],
        "warnings": [
            f"{len(human.get('signedOffNonExecutableRuleGroupIds', []))} non-executable groups "
            "signed off as advisory-only (not mandatory enforcement).",
            f"{len(human.get('productionExcludedCourseNumbers', []))} catalog course numbers "
            "excluded from production (2025 JSON cross-link gaps).",
        ],
        "reviewStatus": document.get("curationMetadata", {}).get(
            "curationStatus",
            "ready-for-staging-with-review-flags",
        ),
        "phase8Recommendation": (
            "Safe for staging and promotion-gate design; non-executable rules are advisory-only."
        ),
        "productionPromotionRecommendation": signoff_recommendation(document),
        "humanSignoff": human,
        "counts": {
            "programs": len(document.get("programs", [])),
            "requirementGroups": sum(
                len(program.get("requirementGroups", []))
                for program in document.get("programs", [])
            ),
            "uniqueCourseNumbers": counts_after.get("uniqueCourseNumbers", 0),
            "missingTitleHints": counts_after.get("missingTitleHints", 0),
            "manualReviewRequiredItems": counts_after.get("manualReviewRequiredItems", 0),
            "executableRuleGroups": counts_after.get("executableRuleGroups", 19),
            "nonExecutableRuleGroups": counts_after.get("nonExecutableRuleGroups", 22),
            "productionExcludedCourseNumbers": len(PRODUCTION_EXCLUDED_COURSE_NUMBERS),
        },
    }


def signoff_recommendation(document: dict[str, Any]) -> str:
    human = document.get("curationReport", {}).get("humanSignoff")
    if human and human.get("enforceNonExecutableRulesInProduction") is False:
        return (
            "Human sign-off recorded: use non-executable groups advisedly; "
            "do not add excluded catalog course numbers to production."
        )
    return "Awaiting human sign-off on non-executable rules and production exclusions."


def extract_human_signoff_from_staged_programs(programs: list[dict[str, Any]]) -> dict[str, Any]:
    for program in programs:
        report = program.get("curationReport")
        if isinstance(report, dict) and isinstance(report.get("humanSignoff"), dict):
            return report["humanSignoff"]
    return {}


def run_record_human_signoff(
    *,
    catalog_path: Path | None = None,
    readiness_path: Path | None = None,
    signed_off_by: str = "project-owner",
    dry_run: bool = False,
) -> dict[str, Any]:
    catalog_file = catalog_path or default_reviewed_output_path()
    readiness_file = readiness_path or default_readiness_path()
    if not catalog_file.exists():
        raise FileNotFoundError(f"Curated catalog not found: {catalog_file}")

    document = json.loads(catalog_file.read_text(encoding="utf-8"))
    human_signoff = apply_human_signoff_to_catalog(document, signed_off_by=signed_off_by)
    readiness = build_readiness_after_human_signoff(document)

    if not dry_run:
        catalog_file.write_text(json.dumps(document, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
        readiness_file.write_text(json.dumps(readiness, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")

    return {
        "dryRun": dry_run,
        "catalogPath": str(catalog_file),
        "readinessPath": str(readiness_file),
        "humanSignoff": human_signoff,
        "canPromoteToProduction": False,
        "nonExecutableRuleGroupsSignedOff": len(NON_EXECUTABLE_RULE_GROUP_IDS),
        "productionExcludedCourseNumbers": list(PRODUCTION_EXCLUDED_COURSE_NUMBERS),
        "note": "Re-import staging catalog to propagate sign-off metadata, then re-run quality validation.",
    }
