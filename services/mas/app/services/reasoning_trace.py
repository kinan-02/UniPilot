"""Sanitized chain-of-thought traces for MAS agent turns."""

from __future__ import annotations

from typing import Any

_MAX_TEXT_LEN = 600
_MAX_BLOCKS_PER_STEP = 8


def _truncate(value: Any, *, limit: int = _MAX_TEXT_LEN) -> str:
    text = str(value or "").strip()
    if len(text) <= limit:
        return text
    return f"{text[: limit - 3]}..."


def sanitize_retrieved_block(block: dict[str, Any]) -> dict[str, Any]:
    """Keep grounding keys; drop bulky graph/wiki payloads."""
    return {
        "intent": block.get("intent"),
        "course_id": block.get("course_id"),
        "wiki_slug": block.get("wiki_slug"),
        "search_query": block.get("search_query"),
        "is_empty": block.get("is_empty"),
        "error": block.get("error"),
    }


def sanitize_planner_tool_steps(steps: list[dict[str, Any]]) -> list[dict[str, Any]]:
    """Persist planner tool-loop steps for transcript / UI without huge blobs."""
    sanitized: list[dict[str, Any]] = []
    for step in steps:
        blocks = step.get("retrieved_blocks") or []
        if isinstance(blocks, list):
            trimmed_blocks = [
                sanitize_retrieved_block(block)
                for block in blocks[:_MAX_BLOCKS_PER_STEP]
                if isinstance(block, dict)
            ]
        else:
            trimmed_blocks = []

        proposal = step.get("proposal")
        proposal_summary = None
        if isinstance(proposal, dict):
            proposal_summary = {
                "course_ids": list(proposal.get("course_ids") or []),
                "reasoning": _truncate(proposal.get("reasoning")),
                "notes": _truncate(proposal.get("notes")),
            }

        sanitized.append(
            {
                "iteration": step.get("iteration"),
                "content": _truncate(step.get("content")),
                "tool_calls": list(step.get("tool_calls") or []),
                "retrieved_blocks": trimmed_blocks,
                "tool_cache_hits": step.get("tool_cache_hits"),
                "tool_cache_misses": step.get("tool_cache_misses"),
                "proposal": proposal_summary,
            }
        )
    return sanitized


def build_planner_tool_loop_trace(
    *,
    status: str,
    reasoning: str,
    notes: str,
    steps: list[dict[str, Any]],
) -> dict[str, Any]:
    return {
        "kind": "planner_tool_loop",
        "status": status,
        "reasoning": _truncate(reasoning),
        "notes": _truncate(notes),
        "steps": sanitize_planner_tool_steps(steps),
    }


def build_planner_repair_trace(
    *,
    course_ids: list[str],
    reasoning: str,
    violations: list[str],
) -> dict[str, Any]:
    return {
        "kind": "planner_repair",
        "course_ids": list(course_ids),
        "reasoning": _truncate(reasoning),
        "violations": violations[:12],
    }


def build_goal_analysis_trace(*, goal_spec: dict[str, Any]) -> dict[str, Any]:
    return {
        "kind": "goal_analysis",
        "intent": goal_spec.get("intent"),
        "confidence": goal_spec.get("confidence"),
        "analysis_source": goal_spec.get("analysis_source"),
        "explicit_course_ids": list(goal_spec.get("explicit_course_ids") or []),
        "ambiguity_note": goal_spec.get("ambiguity_note"),
        "clarification_question": goal_spec.get("clarification_question"),
        "what_if_scenario": goal_spec.get("what_if_scenario"),
    }


def build_arbitration_trace(*, arbitration: dict[str, Any]) -> dict[str, Any]:
    return {
        "kind": "arbitration",
        "chosen_variant": arbitration.get("chosen_variant"),
        "utility": arbitration.get("utility"),
        "breakdown": arbitration.get("breakdown"),
        "considered_variants": list(arbitration.get("considered_variants") or []),
        "rejected_alternatives": list(arbitration.get("rejected_alternatives") or []),
    }


def build_explainer_trace(
    *,
    summary: dict[str, Any],
    transcript_roles: list[str],
) -> dict[str, Any]:
    return {
        "kind": "explainer_summary",
        "source": summary.get("source"),
        "headline": _truncate(summary.get("headline")),
        "rationale": _truncate(summary.get("rationale")),
        "trade_offs": list(summary.get("trade_offs") or [])[:5],
        "transcript_roles": transcript_roles[-8:],
    }


def _sanitize_critique_list(critiques: list[Any]) -> list[dict[str, Any]]:
    sanitized: list[dict[str, Any]] = []
    for critique in critiques[:6]:
        if not isinstance(critique, dict):
            continue
        sanitized.append(
            {
                "type": critique.get("type"),
                "message": _truncate(critique.get("message")),
                "courseId": critique.get("courseId"),
            }
        )
    return sanitized


def _sanitize_violations(violations: list[Any]) -> list[dict[str, Any]]:
    sanitized: list[dict[str, Any]] = []
    for violation in violations[:8]:
        if isinstance(violation, dict):
            sanitized.append(
                {
                    "type": violation.get("type"),
                    "message": _truncate(violation.get("message")),
                    "course_ids": list(violation.get("course_ids") or violation.get("courseIds") or [])[:6],
                    "hard": violation.get("hard"),
                }
            )
        else:
            sanitized.append({"message": _truncate(violation)})
    return sanitized


def _sanitize_risk_evidence(evidence: dict[str, Any] | None) -> dict[str, Any]:
    if not isinstance(evidence, dict):
        return {}
    summary: dict[str, Any] = {}
    for key in ("totalCredits", "maxCredits", "excessCredits", "probationPressured"):
        if key in evidence:
            summary[key] = evidence[key]
    probation = evidence.get("probation")
    if isinstance(probation, dict):
        summary["probation"] = {
            field: probation.get(field)
            for field in ("pressured", "gpa", "threshold", "message")
            if field in probation
        }
    return summary


def build_feasibility_trace(
    *,
    approved: bool,
    violations: list[Any] | None = None,
) -> dict[str, Any]:
    sanitized = _sanitize_violations(list(violations or []))
    return {
        "kind": "feasibility_review",
        "approved": approved,
        "violations": sanitized,
        "violationCount": len(sanitized),
    }


def build_risk_trace(
    *,
    approved: bool,
    violations: list[Any] | None = None,
    evidence: dict[str, Any] | None = None,
    probation_pressured: bool = False,
) -> dict[str, Any]:
    sanitized = _sanitize_violations(list(violations or []))
    return {
        "kind": "risk_review",
        "approved": approved,
        "violations": sanitized,
        "violationCount": len(sanitized),
        "evidence": _sanitize_risk_evidence(evidence),
        "probationPressured": probation_pressured,
    }


def build_progress_scout_trace(
    *,
    progress_score: float | None = None,
    unlock_count: int | None = None,
    critiques: list[dict[str, Any]] | None = None,
    variants: list[dict[str, Any]] | None = None,
) -> dict[str, Any]:
    trace: dict[str, Any] = {"kind": "progress_review"}
    if variants:
        trace["variants"] = [
            {
                "variant": entry.get("variant"),
                "progressScore": entry.get("progressScore"),
                "unlockCount": entry.get("unlockCount"),
                "critiques": _sanitize_critique_list(list(entry.get("critiques") or [])),
            }
            for entry in variants[:4]
            if isinstance(entry, dict)
        ]
        trace["variantCount"] = len(trace["variants"])
    else:
        if progress_score is not None:
            trace["progressScore"] = progress_score
        if unlock_count is not None:
            trace["unlockCount"] = unlock_count
        trace["critiques"] = _sanitize_critique_list(list(critiques or []))
    return trace


def build_advocate_trace(
    *,
    critiques: list[dict[str, Any]] | None = None,
    trade_offs: list[dict[str, Any]] | None = None,
    critique_count: int | None = None,
    variants: list[dict[str, Any]] | None = None,
) -> dict[str, Any]:
    trace: dict[str, Any] = {"kind": "preference_review"}
    if variants:
        trace["variants"] = [
            {
                "variant": entry.get("variant"),
                "critiques": _sanitize_critique_list(list(entry.get("critiques") or [])),
                "tradeOffs": [
                    {
                        "action": trade.get("action"),
                        "courseId": trade.get("courseId"),
                        "message": _truncate(trade.get("message")),
                    }
                    for trade in list(entry.get("tradeOffs") or [])[:4]
                    if isinstance(trade, dict)
                ],
            }
            for entry in variants[:4]
            if isinstance(entry, dict)
        ]
        trace["critiqueCount"] = sum(
            len(list(entry.get("critiques") or [])) for entry in trace["variants"]
        )
    else:
        trace["critiques"] = _sanitize_critique_list(list(critiques or []))
        trace["tradeOffs"] = [
            {
                "action": trade.get("action"),
                "courseId": trade.get("courseId"),
                "message": _truncate(trade.get("message")),
            }
            for trade in list(trade_offs or [])[:4]
            if isinstance(trade, dict)
        ]
        if critique_count is not None:
            trace["critiqueCount"] = critique_count
        else:
            trace["critiqueCount"] = len(trace["critiques"])
    return trace


def build_red_team_trace(
    *,
    attacks: list[dict[str, Any]],
    severity: str,
    chosen_variant: str,
) -> dict[str, Any]:
    return {
        "kind": "red_team_review",
        "severity": severity,
        "chosen_variant": chosen_variant,
        "attacks": [
            {
                "type": attack.get("type"),
                "severity": attack.get("severity"),
                "message": _truncate(attack.get("message")),
            }
            for attack in attacks[:6]
            if isinstance(attack, dict)
        ],
    }
