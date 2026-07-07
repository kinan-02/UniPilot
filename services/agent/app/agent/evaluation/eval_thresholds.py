"""Threshold evaluation for final-answer eval reports (Phase 28.1)."""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any

from pydantic import BaseModel, Field


class SuiteThresholds(BaseModel):
    min_pass_rate: float | None = Field(default=None, alias="minPassRate")
    min_average_fact_coverage: float | None = Field(default=None, alias="minAverageFactCoverage")
    max_contradictions: int | None = Field(default=None, alias="maxContradictions")
    max_source_warnings: int | None = Field(default=None, alias="maxSourceWarnings")

    model_config = {"populate_by_name": True}


class EvalThresholdsFile(BaseModel):
    golden: SuiteThresholds | None = None
    paraphrase: SuiteThresholds | None = None
    broader: SuiteThresholds | None = None
    default: SuiteThresholds | None = None


def load_eval_thresholds(path: str | Path | None) -> EvalThresholdsFile:
    if not path:
        return EvalThresholdsFile()
    payload = json.loads(Path(path).read_text(encoding="utf-8"))
    return EvalThresholdsFile.model_validate(payload)


def _suite_key_from_cases_path(cases_path: str) -> str:
    name = Path(cases_path).stem.lower()
    if "paraphrase" in name:
        return "paraphrase"
    if "broader" in name or name == "eval_cases":
        return "broader"
    if "golden" in name or name == "eval_cases":
        return "golden"
    return "default"


def resolve_suite_thresholds(
    thresholds: EvalThresholdsFile,
    *,
    cases_path: str,
) -> SuiteThresholds:
    key = _suite_key_from_cases_path(cases_path)
    selected = getattr(thresholds, key, None)
    if selected is not None:
        return selected
    return thresholds.default or SuiteThresholds()


def evaluate_thresholds(
    report: dict[str, Any],
    *,
    thresholds: SuiteThresholds,
) -> dict[str, Any]:
    summary = dict(report.get("summary") or {})
    total = int(summary.get("total_cases") or 0)
    passed = int(summary.get("passed_cases") or 0)
    pass_rate = (passed / total) if total else 0.0
    avg_coverage = float(summary.get("average_fact_coverage") or 0.0)
    contradictions = int(summary.get("total_facts_contradicted") or 0)
    source_warnings = sum(len(item.get("sourceWarnings") or []) for item in report.get("caseResults") or [])

    violations: list[str] = []
    if thresholds.min_pass_rate is not None and pass_rate < thresholds.min_pass_rate:
        violations.append("min_pass_rate")
    if thresholds.min_average_fact_coverage is not None and avg_coverage < thresholds.min_average_fact_coverage:
        violations.append("min_average_fact_coverage")
    if thresholds.max_contradictions is not None and contradictions > thresholds.max_contradictions:
        violations.append("max_contradictions")
    if thresholds.max_source_warnings is not None and source_warnings > thresholds.max_source_warnings:
        violations.append("max_source_warnings")

    return {
        "passed": not violations,
        "violations": violations,
        "observed": {
            "passRate": round(pass_rate, 4),
            "averageFactCoverage": round(avg_coverage, 4),
            "totalContradictions": contradictions,
            "totalSourceWarnings": source_warnings,
        },
        "policy": thresholds.model_dump(by_alias=True),
    }
