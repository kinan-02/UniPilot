"""Verify production MongoDB degree requirements and catalog rules match the wiki vault export."""

from __future__ import annotations

import json
from dataclasses import dataclass, field
from datetime import UTC, datetime
from pathlib import Path
from typing import Any, Literal

from pymongo.database import Database

from app.config import Settings, get_settings
from app.curation.catalog_signoff import extract_catalog_signoff
from app.importers.dds_catalog_staging_importer import is_rule_executable
from app.paths import service_root
from app.promotion.dds_promotion_gate import _is_advisory_requirement, _is_hard_requirement
from app.vault.export_dds_catalog import export_vault_catalog
from app.vault.vault_signoff import apply_vault_signoff_to_catalog, derive_non_executable_rule_group_ids

Classification = Literal["hard", "advisory"]


@dataclass
class GroupSnapshot:
    group_id: str
    program_code: str
    classification: Classification
    title: str | None
    requirement_type: str | None
    min_credits: float | None
    rule_type: str | None
    rule_operator: str | None
    rule_min_credits: float | None
    rule_semester: int | None
    course_numbers: tuple[str, ...]
    course_refs: tuple[tuple[str, float | None], ...]

    def to_compare_dict(self) -> dict[str, Any]:
        return {
            "groupId": self.group_id,
            "programCode": self.program_code,
            "classification": self.classification,
            "title": self.title,
            "requirementType": self.requirement_type,
            "minCredits": self.min_credits,
            "ruleExpression": {
                "type": self.rule_type,
                "operator": self.rule_operator,
                "minCredits": self.rule_min_credits,
                "semester": self.rule_semester,
            },
            "courseNumbers": list(self.course_numbers),
            "courseRefs": [{"courseNumber": n, "creditsHint": c} for n, c in self.course_refs],
        }


@dataclass
class ParityMismatch:
    group_id: str
    field: str
    expected: Any
    actual: Any
    program_code: str | None = None


@dataclass
class VaultProductionParityResult:
    status: Literal["pass", "fail"]
    wiki_root: str
    exported_at: str
    expected_hard_count: int
    expected_advisory_count: int
    production_hard_count: int
    production_advisory_count: int
    missing_in_production: list[str] = field(default_factory=list)
    extra_in_production: list[str] = field(default_factory=list)
    classification_mismatches: list[str] = field(default_factory=list)
    field_mismatches: list[ParityMismatch] = field(default_factory=list)
    matched_groups: int = 0

    @property
    def ok(self) -> bool:
        return self.status == "pass"


def _normalize_credits(value: Any) -> float | None:
    if value is None:
        return None
    try:
        return round(float(value), 2)
    except (TypeError, ValueError):
        return None


def _course_refs_from_group(group: dict[str, Any]) -> tuple[tuple[str, float | None], ...]:
    refs: list[tuple[str, float | None]] = []
    for ref in group.get("courseReferences") or []:
        number = ref.get("courseNumber")
        if not number:
            continue
        refs.append((str(number), _normalize_credits(ref.get("creditsHint"))))
    refs.sort(key=lambda item: item[0])
    return tuple(refs)


def _course_refs_from_production(doc: dict[str, Any]) -> tuple[tuple[str, float | None], ...]:
    refs: list[tuple[str, float | None]] = []
    for ref in doc.get("courseReferences") or []:
        number = ref.get("courseNumber")
        if not number:
            continue
        refs.append((str(number), _normalize_credits(ref.get("creditsHint"))))
    refs.sort(key=lambda item: item[0])
    return tuple(refs)


def _snapshot_from_vault_group(
    group: dict[str, Any],
    program_code: str,
    classification: Classification,
) -> GroupSnapshot:
    rule = group.get("ruleExpression") or {}
    course_refs = _course_refs_from_group(group)
    top_min = _normalize_credits(group.get("minCredits"))
    rule_min = _normalize_credits(rule.get("minCredits"))
    effective_min = top_min if top_min is not None else rule_min
    return GroupSnapshot(
        group_id=str(group.get("groupId") or ""),
        program_code=program_code,
        classification=classification,
        title=group.get("title"),
        requirement_type=group.get("requirementType"),
        min_credits=effective_min,
        rule_type=rule.get("type"),
        rule_operator=rule.get("operator"),
        rule_min_credits=rule_min,
        rule_semester=rule.get("semester"),
        course_numbers=tuple(number for number, _ in course_refs),
        course_refs=course_refs,
    )


def _staging_document_from_group(group: dict[str, Any], program_code: str) -> dict[str, Any]:
    rule_expression = group.get("ruleExpression") or {}
    return {
        "programCode": program_code,
        "requirementGroup": group,
        "ruleIsExecutable": is_rule_executable(rule_expression),
    }


def _classify_vault_group(
    group: dict[str, Any],
    program_code: str,
    advisory_group_ids: set[str],
) -> Classification:
    staging = _staging_document_from_group(group, program_code)
    if _is_hard_requirement(staging):
        return "hard"
    if _is_advisory_requirement(staging, advisory_group_ids):
        return "advisory"
    return "advisory"


def build_expected_groups_from_vault_document(document: dict[str, Any]) -> dict[str, GroupSnapshot]:
    signoff = extract_catalog_signoff_from_document(document)
    advisory_group_ids = set(signoff.get("signedOffNonExecutableRuleGroupIds") or [])
    advisory_group_ids |= set(derive_non_executable_rule_group_ids(document))

    expected: dict[str, GroupSnapshot] = {}
    for program in document.get("programs") or []:
        program_code = str(program.get("programCode") or "")
        for group in program.get("requirementGroups") or []:
            group_id = str(group.get("groupId") or "")
            if not group_id:
                continue
            classification = _classify_vault_group(group, program_code, advisory_group_ids)
            expected[group_id] = _snapshot_from_vault_group(group, program_code, classification)
    return expected


def extract_catalog_signoff_from_document(document: dict[str, Any]) -> dict[str, Any]:
    report = document.get("curationReport") or {}
    if report.get("vaultSignoff"):
        return dict(report["vaultSignoff"])
    return extract_catalog_signoff([])


def _snapshot_from_production_doc(
    doc: dict[str, Any],
    classification: Classification,
) -> GroupSnapshot:
    rule = doc.get("ruleExpression") or {}
    course_refs = _course_refs_from_production(doc)
    top_min = _normalize_credits(doc.get("minCredits"))
    rule_min = _normalize_credits(rule.get("minCredits"))
    effective_min = top_min if top_min is not None else rule_min
    return GroupSnapshot(
        group_id=str(doc.get("requirementGroupId") or ""),
        program_code=str(doc.get("programCode") or ""),
        classification=classification,
        title=doc.get("title"),
        requirement_type=doc.get("requirementType"),
        min_credits=effective_min,
        rule_type=rule.get("type"),
        rule_operator=rule.get("operator"),
        rule_min_credits=rule_min,
        rule_semester=rule.get("semester"),
        course_numbers=tuple(number for number, _ in course_refs),
        course_refs=course_refs,
    )


def load_production_groups(database: Database, settings: Settings | None = None) -> dict[str, GroupSnapshot]:
    resolved = settings or get_settings()
    production: dict[str, GroupSnapshot] = {}

    for doc in database[resolved.production_degree_requirements_collection].find({}):
        group_id = str(doc.get("requirementGroupId") or "")
        if not group_id:
            continue
        production[group_id] = _snapshot_from_production_doc(doc, "hard")

    for doc in database[resolved.production_catalog_rules_collection].find({}):
        group_id = str(doc.get("requirementGroupId") or "")
        if not group_id:
            continue
        record_type = doc.get("recordType", "catalog_rule")
        if record_type == "catalog_rule":
            continue
        if group_id in production:
            continue
        production[group_id] = _snapshot_from_production_doc(doc, "advisory")

    return production


def compare_group_snapshots(
    expected: GroupSnapshot,
    actual: GroupSnapshot,
    *,
    expected_all: dict[str, GroupSnapshot] | None = None,
) -> list[ParityMismatch]:
    mismatches: list[ParityMismatch] = []
    pairs = [
        ("classification", expected.classification, actual.classification),
        ("programCode", expected.program_code, actual.program_code),
        ("title", expected.title, actual.title),
        ("requirementType", expected.requirement_type, actual.requirement_type),
        ("minCredits", expected.min_credits, actual.min_credits),
        ("ruleExpression.type", expected.rule_type, actual.rule_type),
        ("ruleExpression.operator", expected.rule_operator, actual.rule_operator),
        ("ruleExpression.minCredits", expected.rule_min_credits, actual.rule_min_credits),
        ("ruleExpression.semester", expected.rule_semester, actual.rule_semester),
        ("courseNumbers", list(expected.course_numbers), list(actual.course_numbers)),
        ("courseRefs", list(expected.course_refs), list(actual.course_refs)),
    ]
    for field_name, exp, act in pairs:
        if field_name == "minCredits" and exp != act:
            from app.promotion.graduation_pool_links import linked_credit_bucket_for_pool

            linked_id = linked_credit_bucket_for_pool(expected.group_id)
            if (
                expected.classification == "advisory"
                and act is None
                and linked_id
                and expected_all
                and linked_id in expected_all
                and expected_all[linked_id].min_credits == exp
            ):
                continue
        if exp != act:
            mismatches.append(
                ParityMismatch(
                    group_id=expected.group_id,
                    program_code=expected.program_code,
                    field=field_name,
                    expected=exp,
                    actual=act,
                )
            )
    return mismatches


def verify_vault_production_parity(
    database: Database,
    *,
    settings: Settings | None = None,
    faculty: str = "dds",
    vault_path: Path | None = None,
) -> VaultProductionParityResult:
    settings = settings or get_settings()
    document, _readiness = export_vault_catalog(faculty=faculty, vault_path=vault_path)
    apply_vault_signoff_to_catalog(document, vault_path=vault_path)

    expected = build_expected_groups_from_vault_document(document)
    production = load_production_groups(database, settings)

    expected_hard = {gid for gid, snap in expected.items() if snap.classification == "hard"}
    expected_advisory = {gid for gid, snap in expected.items() if snap.classification == "advisory"}
    production_hard = {gid for gid, snap in production.items() if snap.classification == "hard"}
    production_advisory = {gid for gid, snap in production.items() if snap.classification == "advisory"}

    missing = sorted(set(expected) - set(production))
    extra = sorted(set(production) - set(expected))
    classification_mismatches = sorted(
        gid
        for gid in set(expected) & set(production)
        if expected[gid].classification != production[gid].classification
    )

    field_mismatches: list[ParityMismatch] = []
    matched = 0
    for group_id in sorted(set(expected) & set(production)):
        if group_id in classification_mismatches:
            continue
        diffs = compare_group_snapshots(expected[group_id], production[group_id], expected_all=expected)
        if diffs:
            field_mismatches.extend(diffs)
        else:
            matched += 1

    wiki_root = (
        (document.get("curationReport") or {}).get("vaultSignoff", {}).get("wikiRoot")
        or document.get("source", {}).get("sourceFile")
        or ""
    )
    exported_at = (
        (document.get("parserReport") or {}).get("exportedAt")
        or datetime.now(UTC).replace(microsecond=0).isoformat()
    )

    status: Literal["pass", "fail"] = "pass"
    if missing or extra or classification_mismatches or field_mismatches:
        status = "fail"

    return VaultProductionParityResult(
        status=status,
        wiki_root=str(wiki_root),
        exported_at=str(exported_at),
        expected_hard_count=len(expected_hard),
        expected_advisory_count=len(expected_advisory),
        production_hard_count=len(production_hard),
        production_advisory_count=len(production_advisory),
        missing_in_production=missing,
        extra_in_production=extra,
        classification_mismatches=classification_mismatches,
        field_mismatches=field_mismatches,
        matched_groups=matched,
    )


def default_parity_report_json_path() -> Path:
    return service_root() / "data" / "reports" / "technion" / "vault_production_parity_report.json"


def default_parity_report_md_path() -> Path:
    return service_root() / "data" / "reports" / "technion" / "vault_production_parity_report.md"


def render_parity_markdown(result: VaultProductionParityResult) -> str:
    lines = [
        "# Vault Wiki ↔ Production Parity Report",
        "",
        f"Status: **{result.status.upper()}**",
        f"Wiki root: `{result.wiki_root}`",
        f"Vault export time: {result.exported_at}",
        "",
        "## Counts",
        "",
        "| Bucket | Vault (expected) | Production |",
        "|--------|------------------|------------|",
        f"| Hard requirements | {result.expected_hard_count} | {result.production_hard_count} |",
        f"| Advisory rules | {result.expected_advisory_count} | {result.production_advisory_count} |",
        f"| Fully matched groups | — | {result.matched_groups} |",
        "",
    ]
    if result.missing_in_production:
        lines.extend(["## Missing in production", ""])
        for group_id in result.missing_in_production:
            lines.append(f"- `{group_id}`")
        lines.append("")
    if result.extra_in_production:
        lines.extend(["## Extra in production (not in vault export)", ""])
        for group_id in result.extra_in_production:
            lines.append(f"- `{group_id}`")
        lines.append("")
    if result.classification_mismatches:
        lines.extend(["## Classification mismatches (hard vs advisory)", ""])
        for group_id in result.classification_mismatches:
            lines.append(f"- `{group_id}`")
        lines.append("")
    if result.field_mismatches:
        lines.extend(["## Field mismatches", ""])
        for item in result.field_mismatches[:50]:
            lines.append(
                f"- `{item.group_id}` ({item.program_code}) **{item.field}**: "
                f"vault={item.expected!r} production={item.actual!r}"
            )
        if len(result.field_mismatches) > 50:
            lines.append(f"- ... and {len(result.field_mismatches) - 50} more")
        lines.append("")
    if result.ok:
        lines.append("All requirement groups and advisory rules in production match the wiki vault export.")
    return "\n".join(lines)


def write_parity_report(
    result: VaultProductionParityResult,
    *,
    json_path: Path | None = None,
    md_path: Path | None = None,
) -> tuple[Path, Path]:
    out_json = json_path or default_parity_report_json_path()
    out_md = md_path or default_parity_report_md_path()
    out_json.parent.mkdir(parents=True, exist_ok=True)
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
        "fieldMismatches": [
            {
                "groupId": item.group_id,
                "programCode": item.program_code,
                "field": item.field,
                "expected": item.expected,
                "actual": item.actual,
            }
            for item in result.field_mismatches
        ],
    }
    out_json.write_text(json.dumps(payload, indent=2, ensure_ascii=False), encoding="utf-8")
    out_md.write_text(render_parity_markdown(result), encoding="utf-8")
    return out_json, out_md
