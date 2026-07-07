"""Markdown reporting for promotion readiness scorecards (Phase 24)."""

from __future__ import annotations

from typing import Any


def render_readiness_markdown_report(scorecard: dict[str, Any]) -> str:
    """Render a compact Markdown readiness report without raw payloads."""
    summary = scorecard.get("summary") or {}
    lines = [
        "# UniPilot Agent Promotion Readiness Report",
        "",
        "## Summary",
        "",
        f"- Candidates evaluated: {summary.get('candidateCount', 0)}",
        f"- Ready for limited promotion: {summary.get('readyForLimitedPromotion', 0)}",
        f"- Ready for broader promotion: {summary.get('readyForBroaderPromotion', 0)}",
        f"- Ready for shadow: {summary.get('readyForShadow', 0)}",
        f"- Not ready: {summary.get('notReady', 0)}",
        "",
    ]

    suite_coverage = scorecard.get("suiteCoverage") or []
    if suite_coverage:
        lines.extend(["## Suite Coverage", ""])
        for suite in suite_coverage:
            status = "ok" if suite.get("meetsMinimum") else "below minimum"
            lines.append(
                f"- `{suite.get('suiteId')}` ({suite.get('purpose')}): "
                f"{suite.get('caseCount')}/{suite.get('minimumCaseCount')} — {status}"
            )
        lines.append("")

    safety = scorecard.get("safetyFailures") or {}
    lines.extend(
        [
            "## Safety Failures",
            "",
            f"- Student write failures: {safety.get('studentWriteFailures', 0)}",
            f"- Action proposal failures: {safety.get('actionProposalFailures', 0)}",
            f"- Raw payload leaks: {safety.get('rawPayloadLeaks', 0)}",
            f"- Unexpected promotions: {safety.get('unexpectedPromotions', 0)}",
            "",
        ]
    )

    candidates = scorecard.get("candidates") or []
    if candidates:
        lines.extend(["## Candidate Readiness", ""])
        lines.append("| Candidate | Level | Pass Rate | Cases | Blocking |")
        lines.append("| --- | --- | --- | --- | --- |")
        for item in candidates:
            blocking = ", ".join(item.get("blockingReasons") or []) or "—"
            lines.append(
                f"| `{item.get('candidateId')}` | `{item.get('level')}` | "
                f"{item.get('passRate', 0)} | {item.get('passedCases', 0)}/{item.get('totalCases', 0)} | "
                f"{blocking} |"
            )
        lines.append("")

    recommendations = scorecard.get("recommendations") or []
    if recommendations:
        lines.extend(["## Recommendations", ""])
        for item in recommendations:
            lines.append(
                f"- **{item.get('target')}**: `{item.get('recommendation')}` — {item.get('reason')}"
            )
        lines.append("")

    return "\n".join(lines).strip() + "\n"
