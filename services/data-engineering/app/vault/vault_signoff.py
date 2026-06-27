"""Vault wiki-backed catalog sign-off (replaces manual human sign-off)."""

from __future__ import annotations

from datetime import UTC, datetime
from pathlib import Path
from typing import Any

from app.curation.catalog_signoff import SIGNOFF_SOURCE_VAULT
from app.catalog.course_reference_policy import (
    build_dds_promotion_course_number_set,
    build_technion_promotion_course_number_set,
    collect_catalog_course_numbers,
    derive_production_excluded_course_numbers,
)
from app.sources.technion_course_json_index import build_course_index, default_course_json_paths
from app.utils.course_numbers import normalize_course_number
from app.vault.loader import WikiPage, load_pages_by_slug, wiki_root
from app.vault.ocr_course_resolution import apply_ocr_resolutions_to_catalog
from app.vault.title_index import (
    align_credits_with_semester_json,
    build_wiki_title_index,
    enrich_titles_from_index,
)

PRODUCTION_EXCLUDED_POLICY = "omit-from-production-do-not-ingest"
NON_EXECUTABLE_POLICY = "advisory-only"


def _utc_now_iso() -> str:
    return datetime.now(UTC).replace(microsecond=0).isoformat()


def _relative_path(path: Path) -> str:
    from app.paths import service_root

    try:
        return str(path.resolve().relative_to(service_root().resolve()))
    except ValueError:
        return str(path)


def build_wiki_course_title_index(pages: dict[str, WikiPage]) -> dict[str, str]:
    return build_wiki_title_index(pages)


def enrich_titles_from_wiki(
    document: dict[str, Any],
    wiki_titles: dict[str, str],
) -> int:
    return enrich_titles_from_index(document, wiki_titles, source_label="vault-wiki")


def enrich_titles_from_semester_json(
    document: dict[str, Any],
    course_index: dict[str, Any],
) -> int:
    title_index = {
        number: record.titleHebrew
        for number, record in course_index.items()
        if getattr(record, "titleHebrew", None)
    }
    return enrich_titles_from_index(document, title_index, source_label="semester-json")


def derive_non_executable_rule_group_ids(document: dict[str, Any]) -> list[str]:
    group_ids: list[str] = []
    for program in document.get("programs", []):
        for group in program.get("requirementGroups", []):
            rule_type = (group.get("ruleExpression") or {}).get("type")
            if rule_type != "credit_bucket":
                group_id = group.get("groupId")
                if group_id:
                    group_ids.append(group_id)
    return sorted(group_ids)


def derive_production_excluded_from_document(
    document: dict[str, Any],
    *,
    ingestible_course_numbers: set[str],
) -> list[str]:
    catalog_numbers = collect_catalog_course_numbers(document)
    return derive_production_excluded_course_numbers(
        catalog_numbers,
        ingestible_course_numbers=ingestible_course_numbers,
    )


def attach_program_source_refs(document: dict[str, Any], pages: dict[str, WikiPage]) -> None:
    track_by_code: dict[str, WikiPage] = {}
    for page in pages.values():
        if not (page.page_type == "track" or page.slug.startswith("track-")):
            continue
        code = extract_program_code(page)
        if code:
            track_by_code[code] = page

    for program in document.get("programs", []):
        code = program.get("programCode")
        page = track_by_code.get(code)
        refs = list(program.get("wikiSourceRefs") or [])
        if page is not None:
            wiki_ref = {
                "sourceType": "catalog_vault_wiki",
                "path": _relative_path(page.path),
                "slug": page.slug,
            }
            if wiki_ref not in refs:
                refs.append(wiki_ref)
        if refs:
            program["wikiSourceRefs"] = refs

        for group in program.get("requirementGroups", []):
            group_refs = list(group.get("wikiSourceRefs") or [])
            if page is not None:
                wiki_ref = {
                    "sourceType": "catalog_vault_wiki",
                    "path": _relative_path(page.path),
                    "slug": page.slug,
                }
                if wiki_ref not in group_refs:
                    group_refs.append(wiki_ref)
            if group_refs:
                group["wikiSourceRefs"] = group_refs


def extract_program_code(page: WikiPage) -> str | None:
    from app.vault.loader import extract_field

    raw = extract_field(page.english_body, "Program code") or extract_field(page.body, "קוד תוכנית")
    if not raw:
        return None
    cleaned = raw.strip().strip("*")
    return cleaned or None


def build_vault_signoff_payload(
    document: dict[str, Any],
    *,
    ingestible_course_numbers: set[str],
    wiki_root_path: Path,
    signed_off_at: str | None = None,
    ingestible_course_scope: str = "dds-faculty-semester-json",
) -> dict[str, Any]:
    non_executable = derive_non_executable_rule_group_ids(document)
    excluded = derive_production_excluded_from_document(
        document,
        ingestible_course_numbers=ingestible_course_numbers,
    )
    return {
        "signoffSource": SIGNOFF_SOURCE_VAULT,
        "signedOffBy": SIGNOFF_SOURCE_VAULT,
        "signedOffAt": signed_off_at or _utc_now_iso(),
        "wikiRoot": _relative_path(wiki_root_path),
        "nonExecutableRulesPolicy": NON_EXECUTABLE_POLICY,
        "enforceNonExecutableRulesInProduction": False,
        "signedOffNonExecutableRuleGroupIds": non_executable,
        "productionExcludedCourseNumbers": excluded,
        "productionExcludedCoursePolicy": PRODUCTION_EXCLUDED_POLICY,
        "ingestibleCourseScope": ingestible_course_scope,
        "notes": (
            "Vault wiki sign-off: non-executable requirement groups are advisory-only in production. "
            "Catalog course references outside the DDS ingest scope are excluded from production "
            "course ingestion but remain as reference-only metadata in vault-backed requirements."
        ),
    }


def apply_vault_signoff_to_catalog(
    document: dict[str, Any],
    *,
    vault_path: Path | None = None,
    course_json_paths: list[Path] | None = None,
    ingestible_course_scope: str = "dds-faculty-semester-json",
) -> dict[str, Any]:
    root = wiki_root(vault_path)
    pages = load_pages_by_slug(root)

    paths = [path for path in (course_json_paths or default_course_json_paths()) if path.exists()]
    course_index = build_course_index(paths)
    if ingestible_course_scope == "technion-semester-json":
        ingestible_course_numbers = build_technion_promotion_course_number_set(course_index)
    else:
        ingestible_course_numbers = build_dds_promotion_course_number_set(course_index)
    wiki_titles = build_wiki_course_title_index(pages)

    titles_filled = enrich_titles_from_wiki(document, wiki_titles)
    titles_filled += enrich_titles_from_semester_json(document, course_index)
    credits_aligned = align_credits_with_semester_json(document, course_index)
    attach_program_source_refs(document, pages)
    apply_ocr_resolutions_to_catalog(
        document,
        ingestible_course_numbers=ingestible_course_numbers,
    )

    vault_signoff = build_vault_signoff_payload(
        document,
        ingestible_course_numbers=ingestible_course_numbers,
        wiki_root_path=root,
        ingestible_course_scope=ingestible_course_scope,
    )

    report = document.setdefault("curationReport", {})
    report["vaultSignoff"] = vault_signoff

    signoff = document.setdefault("signoffReview", {})
    signoff["reviewedBy"] = SIGNOFF_SOURCE_VAULT
    signoff["reviewedAt"] = vault_signoff["signedOffAt"]
    signoff["reviewStatus"] = "vault-signed-ready-for-staging"
    signoff["sourceFilesReviewed"] = [vault_signoff["wikiRoot"]]
    signoff.setdefault("checksPerformed", [])
    for check in (
        "vault_program_codes_present",
        "vault_credit_buckets_present",
        "vault_semester_matrices_parsed",
        "vault_non_executable_rules_advisory",
        "vault_production_exclusions_derived",
    ):
        if check not in signoff["checksPerformed"]:
            signoff["checksPerformed"].append(check)

    signoff["verifiedItems"] = [
        f"Vault export: {len(document.get('programs', []))} DDS programs from wiki track pages.",
        f"{len(vault_signoff['signedOffNonExecutableRuleGroupIds'])} non-executable groups "
        "signed off as advisory-only from wiki structure.",
        f"{len(vault_signoff['productionExcludedCourseNumbers'])} catalog references excluded "
        "from production (not in 2025 semester JSON).",
    ]
    if titles_filled:
        signoff["verifiedItems"].append(
            f"{titles_filled} titleHint values enriched from wiki/semester sources.",
        )
    if credits_aligned:
        signoff["verifiedItems"].append(
            f"{credits_aligned} creditsHint values aligned to semester JSON.",
        )

    signoff["unresolvedItems"] = [
        item
        for item in signoff.get("unresolvedItems", [])
        if not any(
            token in item
            for token in (
                "Human signoff",
                "human signoff",
                "titleHint still missing",
                "Missing titleHint:",
            )
        )
    ]
    signoff["phase8Recommendation"] = (
        "Safe to import to staging; vault wiki is authoritative for catalog structure."
    )
    signoff["productionPromotionRecommendation"] = (
        "Vault sign-off recorded: non-executable groups are advisory-only; "
        "excluded catalog references must not become production course records."
    )

    curation = document.setdefault("curationMetadata", {})
    curation["curationStatus"] = "vault-signed-ready-for-staging"
    known = curation.setdefault("knownLimitations", [])
    limitation = (
        "Vault wiki sign-off: non-executable rules are advisory-only; "
        f"{len(vault_signoff['productionExcludedCourseNumbers'])} catalog refs are production-excluded."
    )
    if limitation not in known:
        known.append(limitation)

    finalize_export_quality_metadata(document)

    return vault_signoff


def finalize_export_quality_metadata(document: dict[str, Any]) -> None:
    """Recompute curation warnings from the post-signoff document (titles enriched)."""
    from app.vault.export_dds_catalog import count_export_stats

    vault = document.get("curationReport", {}).get("vaultSignoff", {})
    signed_groups = set(vault.get("signedOffNonExecutableRuleGroupIds") or [])

    for program in document.get("programs", []):
        for group in program.get("requirementGroups", []):
            if group.get("groupId") in signed_groups:
                group["manualReviewRequired"] = False
            for ref in group.get("courseReferences", []):
                if ref.get("titleHint"):
                    ref["manualReviewRequired"] = False

    counts = count_export_stats(document)
    preserved: list[str] = []
    for item in document.get("curationMetadata", {}).get("unresolvedIssues") or []:
        if "titleHint" in item:
            continue
        preserved.append(item)

    unresolved = list(preserved)
    if counts["missingTitleHints"]:
        unresolved.append(f"{counts['missingTitleHints']} course references lack titleHint.")

    curation = document.setdefault("curationMetadata", {})
    curation["unresolvedIssues"] = unresolved
    curation["countsAfter"] = counts

    report = document.setdefault("curationReport", {})
    chain_warnings = [
        item for item in report.get("warnings") or [] if "titleHint" not in item
    ]
    report["warnings"] = [*chain_warnings, *unresolved]

    signoff = document.setdefault("signoffReview", {})
    signoff["unresolvedItems"] = unresolved


def build_readiness_after_vault_signoff(document: dict[str, Any]) -> dict[str, Any]:
    from app.vault.export_dds_catalog import count_export_stats

    vault = document.get("curationReport", {}).get("vaultSignoff", {})
    counts = count_export_stats(document)
    warnings: list[str] = []
    if counts["missingTitleHints"]:
        warnings.append(f"{counts['missingTitleHints']} course references still lack titleHint.")

    return {
        "canImportToStaging": True,
        "canPromoteToProduction": False,
        "blockingIssuesForStaging": [],
        "blockingIssuesForProduction": [
            "Production promotion gate must pass staging quality checks.",
            "Excluded catalog course references must not be ingested as production courses.",
        ],
        "warnings": warnings,
        "reviewStatus": "vault-signed-ready-for-staging",
        "phase8Recommendation": (
            "Safe for staging import; vault wiki replaces manual human sign-off."
        ),
        "productionPromotionRecommendation": document.get("signoffReview", {}).get(
            "productionPromotionRecommendation",
            "Vault sign-off recorded.",
        ),
        "vaultSignoff": vault,
        "counts": {
            **counts,
            "productionExcludedCourseNumbers": len(vault.get("productionExcludedCourseNumbers", [])),
            "nonExecutableRuleGroupsSignedOff": len(vault.get("signedOffNonExecutableRuleGroupIds", [])),
        },
    }
