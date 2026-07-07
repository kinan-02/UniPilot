#!/usr/bin/env python3
"""Audit whether promotion would be allowed right now (Phase 28.2).

Report-only — does not enable promotion or mutate runtime state.
"""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

_AGENT_ROOT = Path(__file__).resolve().parents[1]
if str(_AGENT_ROOT) not in sys.path:
    sys.path.insert(0, str(_AGENT_ROOT))

from app.agent.readiness.promotion_audit import audit_promotion_readiness
from app.config import Settings


def _parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Audit promotion readiness for a workflow candidate.")
    parser.add_argument("--workflow", required=True, help="Workflow name, e.g. graduation_progress_workflow")
    parser.add_argument(
        "--candidate",
        help="Promotion candidate id (default: synthesis_text_promotion.<workflow>)",
    )
    parser.add_argument(
        "--manifest",
        help="Path to promotion readiness manifest (overrides AGENT_RUNTIME_READINESS_MANIFEST_PATH)",
    )
    parser.add_argument("--output", help="Optional JSON report output path")
    parser.add_argument("--markdown", help="Optional markdown report output path")
    return parser.parse_args()


def _render_markdown(report: dict[str, object]) -> str:
    lines = [
        "# Promotion Readiness Audit",
        "",
        f"- **Workflow:** `{report.get('workflowName')}`",
        f"- **Candidate:** `{report.get('candidateId')}`",
        f"- **Final decision:** `{report.get('finalDecision')}`",
        "",
        "## Checks",
        "",
        f"- Hard workflow ceiling passed: `{report.get('hardWorkflowCeilingPassed')}`",
        f"- Manifest exists: `{report.get('manifestExists')}`",
        f"- Manifest stale: `{report.get('manifestStale')}`",
        f"- Candidate approval exists: `{report.get('candidateApprovalExists')}`",
        f"- Candidate approved: `{report.get('candidateApproved')}`",
        f"- Candidate expired: `{report.get('candidateExpired')}`",
        f"- Scope match: `{report.get('scopeMatch')}`",
        f"- Readiness level: `{report.get('readinessLevel')}`",
        f"- Human reviewed: `{report.get('humanReviewed')}`",
        f"- Runtime gate allowed: `{report.get('runtimeGateAllowed')}`",
        f"- Normal promotion gate still required: `{report.get('normalPromotionGateStillRequired')}`",
        "",
        "## Block reasons",
        "",
    ]
    reasons = report.get("blockReasons") or []
    if reasons:
        lines.extend(f"- `{reason}`" for reason in reasons)
    else:
        lines.append("- _(none)_")
    lines.append("")
    return "\n".join(lines)


def main() -> None:
    args = _parse_args()
    workflow = args.workflow.strip()
    candidate = (args.candidate or f"synthesis_text_promotion.{workflow}").strip()

    settings = Settings()
    report = audit_promotion_readiness(
        workflow_name=workflow,
        candidate_id=candidate,
        settings=settings,
        manifest_path=args.manifest,
    )

    payload = json.dumps(report, indent=2)
    print(payload)

    if args.output:
        Path(args.output).write_text(payload + "\n", encoding="utf-8")
    if args.markdown:
        Path(args.markdown).write_text(_render_markdown(report), encoding="utf-8")


if __name__ == "__main__":
    main()
