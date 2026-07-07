"""JSON/Markdown reporting for offline eval runs (Phase 23)."""

from __future__ import annotations

from typing import Any

from app.agent.evaluation.metrics import compute_eval_run_summary
from app.agent.evaluation.replay_schemas import EvalCase, EvalCaseResult, EvalRunSummary
from app.agent.evaluation.sanitizer import assert_no_forbidden_eval_payload, sanitize_eval_payload


def build_eval_report(
    results: list[EvalCaseResult],
    *,
    cases: list[EvalCase] | None = None,
    mode: str = "gates_only",
    allow_real_llm: bool = False,
) -> dict[str, Any]:
    summary = compute_eval_run_summary(results, cases=cases)
    failed = [item for item in results if item.status != "passed"]
    report = {
        "mode": mode,
        "allowRealLlm": allow_real_llm,
        "deterministic": not allow_real_llm,
        "summary": summary.model_dump(),
        "failedCases": [
            {
                "caseId": item.case_id,
                "name": item.name,
                "status": item.status,
                "failures": item.failures[:20],
                "oracleFailures": item.oracle_failures[:10],
                "safetyFailures": item.safety_failures[:10],
                "gateFailures": [
                    {"name": gate.name, "reasonCodes": gate.reason_codes[:5]}
                    for gate in item.gates
                    if gate.status == "failed"
                ],
            }
            for item in failed
        ],
    }
    sanitized = sanitize_eval_payload(report, strict=False)
    assert_no_forbidden_eval_payload(sanitized if isinstance(sanitized, dict) else report)
    return sanitized if isinstance(sanitized, dict) else report


def render_markdown_eval_report(report: dict[str, Any]) -> str:
    summary = report.get("summary") or {}
    lines = [
        "# UniPilot Agent Offline Eval Report",
        "",
        f"- Mode: `{report.get('mode', 'gates_only')}`",
        f"- Deterministic: `{report.get('deterministic', True)}`",
        f"- Total cases: {summary.get('totalCases', summary.get('total_cases', 0))}",
        f"- Passed: {summary.get('passedCases', summary.get('passed_cases', 0))}",
        f"- Failed: {summary.get('failedCases', summary.get('failed_cases', 0))}",
        f"- Pass rate: {summary.get('passRate', summary.get('pass_rate', 0))}",
        "",
        "## Metrics",
        "",
        f"- Intent accuracy: {summary.get('intentAccuracy', summary.get('intent_accuracy'))}",
        f"- Workflow accuracy: {summary.get('workflowAccuracy', summary.get('workflow_accuracy'))}",
        f"- Synthesis promotions: {summary.get('synthesisPromotions', summary.get('synthesis_promotions', 0))}",
        f"- Synthesis blocks: {summary.get('synthesisBlocks', summary.get('synthesis_blocks', 0))}",
        f"- Unsafe cases blocked: {summary.get('unsafeCasesBlocked', summary.get('unsafe_cases_blocked', 0))}",
        "",
    ]

    failed_cases = report.get("failedCases") or []
    if failed_cases:
        lines.append("## Failed Cases")
        lines.append("")
        for item in failed_cases:
            lines.append(f"### {item.get('caseId')} — {item.get('name')}")
            for failure in item.get("failures") or []:
                lines.append(f"- failure: `{failure}`")
            for gate in item.get("gateFailures") or []:
                lines.append(f"- gate `{gate.get('name')}`: {gate.get('reasonCodes')}")
            lines.append("")
    return "\n".join(lines).strip() + "\n"
