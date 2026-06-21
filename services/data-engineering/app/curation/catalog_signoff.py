"""Shared catalog sign-off extraction (vault wiki or legacy human)."""

from __future__ import annotations

from typing import Any

SIGNOFF_SOURCE_VAULT = "vault-wiki"
SIGNOFF_SOURCE_HUMAN = "human"


def extract_catalog_signoff(programs: list[dict[str, Any]]) -> dict[str, Any]:
    """Return vault or legacy human sign-off metadata from staged programs."""
    for program in programs:
        report = program.get("curationReport")
        if not isinstance(report, dict):
            continue
        vault = report.get("vaultSignoff")
        if isinstance(vault, dict) and vault.get("signedOffBy"):
            return vault
        human = report.get("humanSignoff")
        if isinstance(human, dict) and human.get("signedOffBy"):
            return human
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
