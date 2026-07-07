"""Clarification as a first-class capability (Phase 17)."""

from app.agent.clarification.capability import run_clarification_capability, run_clarification_from_shadow_context
from app.agent.clarification.diagnostics import build_clarification_metadata, build_clarification_output_diagnostics
from app.agent.clarification.detector import dedupe_clarification_needs, needs_from_missing_context, needs_from_monitor_output
from app.agent.clarification.fallbacks import build_assumed_answer, build_assumption_record
from app.agent.clarification.policy import decide_clarification_action
from app.agent.clarification.question_builder import batch_clarification_questions, build_clarification_question
from app.agent.clarification.schemas import (
    ClarificationAnswer,
    ClarificationCapabilityOutput,
    ClarificationDecision,
    ClarificationNeed,
    ClarificationQuestion,
)

__all__ = [
    "ClarificationAnswer",
    "ClarificationCapabilityOutput",
    "ClarificationDecision",
    "ClarificationNeed",
    "ClarificationQuestion",
    "batch_clarification_questions",
    "build_assumed_answer",
    "build_assumption_record",
    "build_clarification_metadata",
    "build_clarification_output_diagnostics",
    "build_clarification_question",
    "decide_clarification_action",
    "dedupe_clarification_needs",
    "needs_from_missing_context",
    "needs_from_monitor_output",
    "run_clarification_capability",
    "run_clarification_from_shadow_context",
]
