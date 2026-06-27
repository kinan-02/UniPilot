"""Shared catalog sign-off extraction (vault wiki or legacy human)."""

from __future__ import annotations

from typing import Any

SIGNOFF_SOURCE_VAULT = "vault-wiki"
SIGNOFF_SOURCE_HUMAN = "human"


def _merge_signoff_lists(*lists: list[str] | None) -> list[str]:
    merged: list[str] = []
    seen: set[str] = set()
    for items in lists:
        for item in items or []:
            value = str(item)
            if value in seen:
                continue
            seen.add(value)
            merged.append(value)
    return merged


def _merge_catalog_signoffs(signoffs: list[dict[str, Any]]) -> dict[str, Any]:
    """Merge vault/human sign-offs from multiple staged programs (newest/most complete wins)."""
    if not signoffs:
        return {}

    def completeness(signoff: dict[str, Any]) -> tuple[int, int]:
        return (
            len(signoff.get("signedOffNonExecutableRuleGroupIds") or []),
            len(signoff.get("productionExcludedCourseNumbers") or []),
        )

    base = max(signoffs, key=completeness)
    merged = dict(base)
    signed_ids = _merge_signoff_lists(
        *(signoff.get("signedOffNonExecutableRuleGroupIds") for signoff in signoffs)
    )
    excluded_numbers = _merge_signoff_lists(
        *(signoff.get("productionExcludedCourseNumbers") for signoff in signoffs)
    )
    if signed_ids or any("signedOffNonExecutableRuleGroupIds" in signoff for signoff in signoffs):
        merged["signedOffNonExecutableRuleGroupIds"] = signed_ids
    if excluded_numbers or any("productionExcludedCourseNumbers" in signoff for signoff in signoffs):
        merged["productionExcludedCourseNumbers"] = excluded_numbers
    return merged


def extract_catalog_signoff(programs: list[dict[str, Any]]) -> dict[str, Any]:
    """Return vault or legacy human sign-off metadata from staged programs."""
    vault_signoffs: list[dict[str, Any]] = []
    human_signoffs: list[dict[str, Any]] = []
    for program in programs:
        report = program.get("curationReport")
        if not isinstance(report, dict):
            continue
        vault = report.get("vaultSignoff")
        if isinstance(vault, dict) and vault.get("signedOffBy"):
            vault_signoffs.append(vault)
            continue
        human = report.get("humanSignoff")
        if isinstance(human, dict) and human.get("signedOffBy"):
            human_signoffs.append(human)

    if vault_signoffs:
        return _merge_catalog_signoffs(vault_signoffs)
    if human_signoffs:
        return _merge_catalog_signoffs(human_signoffs)
    return {}


def extract_human_signoff_from_staged_programs(programs: list[dict[str, Any]]) -> dict[str, Any]:
    """Backward-compatible alias used by promotion gate and quality checks."""
    return extract_catalog_signoff(programs)


def signoff_source_label(signoff: dict[str, Any]) -> str:
    if signoff.get("signoffSource") == SIGNOFF_SOURCE_VAULT:
        return "vaultSignoff"
    if signoff.get("signedOffBy") == SIGNOFF_SOURCE_VAULT:
        return "vaultSignoff"
    return "humanSignoff"
