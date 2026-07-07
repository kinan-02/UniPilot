"""Typed models for Controlled Specialist Text Promotion (Phase 14).

Diagnostic/decision models only — mirrors `supervisor.promotion_schemas`
(Phase 9) but for a narrower decision: whether one specialist's
`answer_text` may replace `AgentResponse.text` for the current turn. Nothing
here executes anything, selects a workflow, or builds blocks/sources/actions.

As with every other specialist/supervisor model, no field here may carry raw
chain-of-thought or private model reasoning — `text_promotion.py` actively
scans for forbidden key shapes before a decision is ever built, and this
module's own fields are limited to compact codes/severities/counts.
"""

from __future__ import annotations

from typing import Any, Literal

from pydantic import BaseModel, Field

SpecialistTextPromotionMode = Literal[
    "off",
    "shadow_only",
    "promote_validated",
]

SpecialistTextPromotionStatus = Literal[
    "promoted",
    "blocked",
    "skipped",
    "failed",
]


class SpecialistTextPromotionReason(BaseModel):
    """One reason a text-promotion attempt was blocked (or, rarely, an info note).

    Deliberately has no `message` field (unlike `PromotionBlockReason`) —
    `code` alone is the stable, compact identifier stored in diagnostics;
    `details` is never persisted by `text_promotion_diagnostics.build_specialist_text_promotion_metadata`
    (only `code`/`severity` are), so it may safely carry small, non-sensitive
    counters (e.g. a confidence value) for programmatic callers without ever
    leaking into `agent_runs.retrievalMetadata`.
    """

    code: str
    severity: Literal["info", "warning", "error"] = "warning"
    details: dict[str, Any] = Field(default_factory=dict)


class SpecialistTextPromotionDecision(BaseModel):
    """Result of `text_promotion.evaluate_specialist_text_promotion`.

    `status="skipped"` means text promotion was never attempted (disabled,
    or mode isn't `"promote_validated"`). `status="blocked"` means it was
    attempted but at least one strict gate failed — including the Phase 14
    workflow-promotion-precedence rule (`workflow_promotion_already_selected_response`).
    `status="promoted"` means every gate passed and the caller should use
    `answer_text` in place of the live response's `text` only.
    `status="failed"` means the evaluation itself hit an unexpected internal
    error (never a raised exception — always degrades to this instead).
    """

    status: SpecialistTextPromotionStatus
    promoted: bool = False
    mode: SpecialistTextPromotionMode = "off"
    workflow_name: str | None = None
    specialist_agent_name: str | None = None
    reasons: list[SpecialistTextPromotionReason] = Field(default_factory=list)
    diagnostics: dict[str, Any] = Field(default_factory=dict)


__all__ = [
    "SpecialistTextPromotionMode",
    "SpecialistTextPromotionStatus",
    "SpecialistTextPromotionReason",
    "SpecialistTextPromotionDecision",
]
