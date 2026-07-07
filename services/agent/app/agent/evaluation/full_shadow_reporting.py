"""Reporting extensions for full LLM shadow replay (Phase 26)."""

from __future__ import annotations

from typing import Any

from app.agent.evaluation.replay_schemas import EvalCase, EvalCaseResult
from app.agent.evaluation.reporting import build_eval_report, render_markdown_eval_report
from app.agent.evaluation.sanitizer import assert_no_forbidden_eval_payload, sanitize_eval_payload


def _build_case_results(results: list[EvalCaseResult]) -> list[dict[str, Any]]:
    case_results: list[dict[str, Any]] = []
    for item in results:
        calls = list(item.reasoning_call_summaries or [])
        failed_calls = [call for call in calls if isinstance(call, dict) and call.get("status") != "completed"]
        case_results.append(
            {
                "caseId": item.case_id,
                "name": item.name,
                "status": item.status,
                "reasoningCalls": calls,
                "schemaValidationFailures": [
                    {
                        "contractName": call.get("contractName"),
                        "status": call.get("status"),
                        "schemaValid": call.get("schemaValid"),
                        "reasoningStatus": call.get("reasoningStatus"),
                        "outputSchemaName": call.get("outputSchemaName"),
                        "validationRetryCount": call.get("validationRetryCount"),
                        "validationNotes": (call.get("validationNotes") or [])[:8],
                        "warnings": (call.get("warnings") or [])[:8],
                    }
                    for call in failed_calls
                ],
            }
        )
    return case_results


def _aggregate_full_shadow(results: list[EvalCaseResult]) -> dict[str, Any]:
    total_calls = 0
    contract_counts: dict[str, int] = {}
    schema_validation_failures: dict[str, int] = {}
    side_effect_violations = 0
    would_promote = 0
    clarification_cases = 0
    dynamic_specs = 0
    synthesis_candidates = 0
    latencies: list[int] = []
    total_cost = 0.0
    cost_items = 0

    for item in results:
        shadow = item.full_shadow if hasattr(item, "full_shadow") else {}
        trace = shadow.get("traceSummary") or {}
        total_calls += int(trace.get("totalReasoningCalls") or 0)
        for name, count in (trace.get("contractCallCounts") or {}).items():
            contract_counts[str(name)] = contract_counts.get(str(name), 0) + int(count)
        for name, count in (trace.get("schemaValidationFailures") or {}).items():
            schema_validation_failures[str(name)] = schema_validation_failures.get(str(name), 0) + int(count)
        side_effect_violations += len(item.side_effect_violations if hasattr(item, "side_effect_violations") else [])
        if shadow.get("promotionWouldPromote"):
            would_promote += 1
        clarification_cases += int(shadow.get("casesRequiringClarification") or 0)
        if item.actual_synthesis_status in {"candidate_ready", "candidate_ready_with_warnings"}:
            synthesis_candidates += 1
        if trace.get("averageLatencyMs") is not None:
            latencies.append(int(trace["averageLatencyMs"]))
        if trace.get("totalEstimatedCostUsd") is not None:
            total_cost += float(trace["totalEstimatedCostUsd"])
            cost_items += 1
        for summary in item.reasoning_call_summaries if hasattr(item, "reasoning_call_summaries") else []:
            if isinstance(summary, dict) and str(summary.get("contractName", "")).endswith("dynamic_spec"):
                dynamic_specs += 1
        if not trace.get("schemaValidationFailures"):
            for call in item.reasoning_call_summaries or []:
                if isinstance(call, dict) and call.get("status") != "completed":
                    name = str(call.get("contractName") or "unknown")
                    schema_validation_failures[name] = schema_validation_failures.get(name, 0) + 1

    return {
        "realLlmUsed": True,
        "totalReasoningCalls": total_calls,
        "contractCallCounts": contract_counts,
        "schemaValidationFailures": schema_validation_failures,
        "totalEstimatedCostUsd": round(total_cost, 6) if cost_items else None,
        "averageLatencyMs": round(sum(latencies) / len(latencies), 2) if latencies else None,
        "sideEffectViolations": side_effect_violations,
        "casesRequiringClarification": clarification_cases,
        "dynamicSpecsGenerated": dynamic_specs,
        "synthesisCandidates": synthesis_candidates,
        "promotionWouldPromoteCount": would_promote,
        "fullLlmShadowCases": len(results),
        "fullLlmShadowPassRate": round(
            sum(1 for item in results if item.status == "passed") / max(1, len(results)),
            4,
        ),
    }


def build_full_shadow_eval_report(
    results: list[EvalCaseResult],
    *,
    cases: list[EvalCase] | None = None,
    allow_real_llm: bool = False,
) -> dict[str, Any]:
    base = build_eval_report(
        results,
        cases=cases,
        mode="full_llm_shadow_replay",
        allow_real_llm=allow_real_llm,
    )
    base["fullShadow"] = _aggregate_full_shadow(results)
    base["caseResults"] = _build_case_results(results)
    sanitized = sanitize_eval_payload(base, strict=False)
    assert_no_forbidden_eval_payload(sanitized if isinstance(sanitized, dict) else base)
    return sanitized if isinstance(sanitized, dict) else base


def render_full_shadow_markdown_report(report: dict[str, Any]) -> str:
    lines = [render_markdown_eval_report(report).rstrip(), "", "## Full LLM Shadow Lab", ""]
    shadow = report.get("fullShadow") or {}
    lines.extend(
        [
            f"- Real LLM used: `{shadow.get('realLlmUsed', report.get('allowRealLlm'))}`",
            f"- Total reasoning calls: {shadow.get('totalReasoningCalls', 0)}",
            f"- Side-effect violations: {shadow.get('sideEffectViolations', 0)}",
            f"- Promotion would-promote count: {shadow.get('promotionWouldPromoteCount', 0)}",
            f"- Synthesis candidates: {shadow.get('synthesisCandidates', 0)}",
            f"- Full LLM shadow pass rate: {shadow.get('fullLlmShadowPassRate')}",
            "",
        ]
    )
    counts = shadow.get("contractCallCounts") or {}
    if counts:
        lines.append("### Contract call counts")
        lines.append("")
        for name, count in sorted(counts.items()):
            lines.append(f"- `{name}`: {count}")
        lines.append("")

    schema_failures = shadow.get("schemaValidationFailures") or {}
    if schema_failures:
        lines.append("### Schema validation failures by contract")
        lines.append("")
        for name, count in sorted(schema_failures.items()):
            lines.append(f"- `{name}`: {count}")
        lines.append("")

    case_results = report.get("caseResults") or []
    cases_with_failures = [item for item in case_results if item.get("schemaValidationFailures")]
    if cases_with_failures:
        lines.append("### Per-case schema validation failures")
        lines.append("")
        for item in cases_with_failures:
            lines.append(f"#### {item.get('caseId')} — {item.get('name')}")
            for failure in item.get("schemaValidationFailures") or []:
                notes = failure.get("validationNotes") or []
                warnings = failure.get("warnings") or []
                lines.append(
                    f"- `{failure.get('contractName')}`: status=`{failure.get('status')}`, "
                    f"schemaValid=`{failure.get('schemaValid')}`, "
                    f"reasoningStatus=`{failure.get('reasoningStatus')}`, "
                    f"retries=`{failure.get('validationRetryCount')}`"
                )
                for note in notes[:3]:
                    lines.append(f"  - note: {note}")
                for warning in warnings[:3]:
                    lines.append(f"  - warning: {warning}")
            lines.append("")

    return "\n".join(lines)
