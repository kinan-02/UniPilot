"""Compact clarification diagnostics metadata (Phase 17)."""

from __future__ import annotations

from typing import Any

from app.agent.clarification.schemas import ClarificationCapabilityOutput
from app.agent.clarification.state_schemas import PendingClarificationState, ResolvedClarificationState

_MAX_WARNINGS = 8
_MAX_QUESTION_SUMMARIES = 5


def build_clarification_metadata(output: ClarificationCapabilityOutput) -> dict[str, Any]:
    """Compact dict for `retrievalMetadata.clarificationDiagnostics`."""
    return {
        "status": output.status,
        "needCount": output.diagnostics.get("needCount", 0),
        "questionCount": output.diagnostics.get("questionCount", len(output.questions)),
        "assumedAnswerCount": output.diagnostics.get("assumedAnswerCount", len(output.answers)),
        "questions": [
            {
                "ambiguityType": question.ambiguity_type,
                "consequence": question.consequence,
                "optionCount": len(question.options),
            }
            for question in output.questions[:_MAX_QUESTION_SUMMARIES]
        ],
        "assumptionsCreated": len(output.assumptions_created),
        "warnings": list(output.warnings[:_MAX_WARNINGS]),
    }


def build_clarification_output_diagnostics(output: ClarificationCapabilityOutput) -> dict[str, Any]:
    return {
        "resolvedEpistemicCount": output.diagnostics.get("resolvedEpistemicCount", 0),
        "skippedCount": output.diagnostics.get("skippedCount", 0),
    }


def build_clarification_state_metadata(
    *,
    pending: PendingClarificationState | None = None,
    resolved: ResolvedClarificationState | None = None,
    status: str | None = None,
    question_count: int | None = None,
    deferred_question_count: int | None = None,
    batching_enabled: bool | None = None,
    expired: bool = False,
    warnings: list[str] | None = None,
) -> dict[str, Any]:
    """Compact dict for `retrievalMetadata.clarificationState`."""
    from app.agent.clarification.state_schemas import PendingClarificationState, ResolvedClarificationState

    provenance: list[str] = []
    answer_count = 0
    clarification_id = None
    resume_mode = "resume_original_request"
    state_status = status or "skipped"

    if resolved is not None:
        clarification_id = resolved.clarification_id
        state_status = resolved.status
        answer_count = len(resolved.answers)
        provenance = sorted({str(answer.get("provenance") or "") for answer in resolved.answers if answer.get("provenance")})
        resume_mode = str((resolved.resume_payload or {}).get("resumeMode") or "resume_original_request")
    elif pending is not None:
        clarification_id = pending.clarification_id
        state_status = pending.status if status is None else status
        question_count = question_count if question_count is not None else len(pending.questions)
        resume_mode = pending.resume_mode

    return {
        "status": state_status,
        "clarificationId": clarification_id,
        "questionCount": question_count if question_count is not None else 0,
        "deferredQuestionCount": deferred_question_count if deferred_question_count is not None else 0,
        "batchingEnabled": batching_enabled if batching_enabled is not None else False,
        "answerCount": answer_count,
        "provenance": provenance,
        "resumeMode": resume_mode,
        "expired": expired,
        "warnings": list((warnings or [])[:8]),
    }
