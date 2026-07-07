"""Synthesis output validation (Phase 21)."""

from __future__ import annotations

import re

from app.agent.synthesis.schemas import SynthesisInput, SynthesisOutput
from app.agent.synthesis.trust_policy import monitor_blocks_promotion, unresolved_high_severity_conflicts
from app.config import Settings

_WRITE_CLAIM_RE = re.compile(
    r"\b(saved|updated|imported|wrote|created|confirmed action|proposed action)\b",
    re.IGNORECASE,
)
_COT_MARKERS = ("chain_of_thought", "hidden_reasoning", "scratchpad", "thoughts:")
_RAW_PAYLOAD_MARKERS = ("```json", "AgentContextPack", "retrievalMetadata", "proposedActions")


def validate_synthesis_output(
    output: SynthesisOutput,
    input: SynthesisInput,
    settings: Settings,
) -> SynthesisOutput:
    warnings = list(output.warnings)
    candidate = (output.candidate_answer_text or "").strip()
    max_chars = max(1, int(settings.agent_synthesis_max_candidate_chars))
    safe_to_show = output.safe_to_show
    status = output.status

    if status in {"candidate_ready", "candidate_ready_with_warnings"} and not candidate:
        status = "insufficient_evidence"
        safe_to_show = False
        warnings.append("empty_candidate_downgraded")

    if len(candidate) > max_chars:
        candidate = candidate[:max_chars]
        warnings.append("candidate_truncated")
        if status == "candidate_ready":
            status = "candidate_ready_with_warnings"

    if candidate and _WRITE_CLAIM_RE.search(candidate):
        safe_to_show = False
        status = "unsafe"
        warnings.append("write_claim_rejected")

    if candidate and any(marker.lower() in candidate.lower() for marker in _COT_MARKERS):
        safe_to_show = False
        status = "failed"
        warnings.append("chain_of_thought_rejected")

    if candidate and any(marker in candidate for marker in _RAW_PAYLOAD_MARKERS):
        safe_to_show = False
        warnings.append("raw_payload_marker_rejected")

    if monitor_blocks_promotion(input.monitor_summary) and safe_to_show:
        safe_to_show = False
        status = "unsafe"
        warnings.append("monitor_unsafe_blocks_show")

    if unresolved_high_severity_conflicts(output.conflicts) and status == "candidate_ready":
        status = "needs_clarification"
        safe_to_show = False
        warnings.append("high_severity_conflict_blocks_ready")

    safe_to_promote = False
    if settings.is_agent_synthesis_text_promotion_enabled() and candidate and safe_to_show:
        from app.agent.synthesis.promotion_policy import synthesis_output_promotion_ready
        from app.agent.synthesis.candidate_safety import check_synthesis_candidate_safety

        ready = synthesis_output_promotion_ready(
            output.model_copy(update={"status": status, "safe_to_show": safe_to_show, "candidate_answer_text": candidate}),
            settings=settings,
            monitor_summary=input.monitor_summary,
            plan_repair_summary=input.plan_repair_summary,
        )
        safety_ok = not check_synthesis_candidate_safety(
            candidate,
            max_chars=settings.resolved_agent_synthesis_text_promotion_max_chars(),
            uncertainty_notes=output.uncertainty_notes,
        )
        safe_to_promote = ready and safety_ok

    return output.model_copy(
        update={
            "status": status,
            "candidate_answer_text": candidate or None,
            "safe_to_show": safe_to_show,
            "safe_to_promote": safe_to_promote,
            "warnings": warnings,
        }
    )
