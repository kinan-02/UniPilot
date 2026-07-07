#!/usr/bin/env python3
"""Build a draft human-reviewed promotion activation manifest (Phase 25)."""

from __future__ import annotations

import argparse
import json
import sys
from datetime import datetime, timedelta, timezone
from pathlib import Path

_AGENT_ROOT = Path(__file__).resolve().parents[1]
if str(_AGENT_ROOT) not in sys.path:
    sys.path.insert(0, str(_AGENT_ROOT))


def _parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Build draft promotion activation manifest from readiness report.")
    parser.add_argument("--readiness-report", required=True)
    parser.add_argument("--candidate", required=True)
    parser.add_argument(
        "--level",
        choices=["ready_for_limited_promotion", "ready_for_broader_promotion"],
        default="ready_for_limited_promotion",
    )
    parser.add_argument("--reviewed-by", required=True)
    parser.add_argument("--expires-days", type=int, default=30)
    parser.add_argument("--output", required=True)
    return parser.parse_args()


def _candidate_scope(candidate_id: str) -> list[str]:
    if candidate_id.startswith("synthesis_text_promotion."):
        return [candidate_id.split(".", 1)[1]]
    if candidate_id.startswith("workflow_promotion."):
        return [candidate_id.split(".", 1)[1]]
    if candidate_id.startswith("specialist_text_promotion."):
        return ["graduation_progress_workflow"]
    return []


def main() -> None:
    args = _parse_args()
    report_path = Path(args.readiness_report)
    report = json.loads(report_path.read_text(encoding="utf-8"))
    candidates = report.get("candidates") or []
    matched = next((item for item in candidates if item.get("candidateId") == args.candidate), None)

    now = datetime.now(timezone.utc)
    expires = now + timedelta(days=max(1, int(args.expires_days)))

    manifest = {
        "schemaVersion": "1",
        "generatedAt": now.isoformat().replace("+00:00", "Z"),
        "reviewedAt": now.isoformat().replace("+00:00", "Z"),
        "reviewedBy": args.reviewed_by,
        "sourceReport": report_path.name,
        "suiteRunId": f"draft-{now.date().isoformat()}",
        "candidates": [
            {
                "candidateId": args.candidate,
                "level": args.level,
                "approved": True,
                "scope": _candidate_scope(args.candidate),
                "expiresAt": expires.isoformat().replace("+00:00", "Z"),
                "notes": "Draft manifest — requires human review before runtime use.",
            }
        ],
    }
    if matched:
        manifest["candidates"][0]["notes"] = (
            f"Draft from readiness report level={matched.get('level')} passRate={matched.get('passRate')}"
        )

    Path(args.output).write_text(json.dumps(manifest, indent=2), encoding="utf-8")
    print(json.dumps({"output": args.output, "candidateId": args.candidate, "draft": True}))


if __name__ == "__main__":
    main()
