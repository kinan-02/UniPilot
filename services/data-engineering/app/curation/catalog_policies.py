"""Shared DDS catalog promotion policies (vault-aligned)."""

from __future__ import annotations

from datetime import UTC, datetime
from typing import Any

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


def build_catalog_signoff_payload(
    *,
    signed_off_by: str = "vault-wiki",
    signoff_source: str = "vault-wiki",
    non_executable_group_ids: list[str] | None = None,
    excluded_course_numbers: list[str] | None = None,
) -> dict[str, Any]:
    """Build vault-compatible sign-off metadata for tests and fixtures."""
    return {
        "signedOffBy": signed_off_by,
        "signedOffAt": _utc_now_iso(),
        "signoffSource": signoff_source,
        "nonExecutableRulesPolicy": "advisory-only",
        "enforceNonExecutableRulesInProduction": False,
        "signedOffNonExecutableRuleGroupIds": list(non_executable_group_ids or []),
        "productionExcludedCourseNumbers": list(
            excluded_course_numbers or PRODUCTION_EXCLUDED_COURSE_NUMBERS
        ),
        "productionExcludedCoursePolicy": "omit-from-production-do-not-ingest",
    }
