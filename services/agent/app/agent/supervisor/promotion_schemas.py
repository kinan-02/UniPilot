"""Typed models for the Controlled Supervisor Promotion experiment (Phase 9).

Diagnostic/decision models only — nothing here executes anything. As with
every other Phase 6/7/8 supervisor model, no field may carry raw
chain-of-thought or private model reasoning; `promotion.py` actively scans
for forbidden key shapes (via `validation_schemas.scan_for_forbidden_keys`)
before a `PromotionDecision` is ever built.
"""

from __future__ import annotations

from typing import Any, Literal

from pydantic import BaseModel, ConfigDict, Field

from app.agent.schemas import AgentResponse
from app.agent.supervisor.schemas import SupervisorRunOutput

PromotionMode = Literal["off", "shadow_only", "promote_validated"]
PromotionDecisionStatus = Literal["promoted", "blocked", "skipped", "failed"]


class PromotionBlockReason(BaseModel):
    """One reason a promotion attempt was blocked (or, rarely, an info note)."""

    code: str
    message: str
    severity: Literal["info", "warning", "error"] = "warning"
    details: dict[str, Any] = Field(default_factory=dict)


class PromotionDecision(BaseModel):
    """Result of `promotion.evaluate_promotion_decision`.

    `status="skipped"` means promotion was never attempted at all (disabled,
    or `AGENT_SUPERVISOR_PROMOTION_MODE` isn't `"promote_validated"`).
    `status="blocked"` means promotion was attempted but at least one gate
    failed — `reasons` explains which. `status="promoted"` means every
    strict gate passed and the caller should use the supervisor candidate
    response. `status="failed"` means the evaluation itself hit an
    unexpected internal error (never a raised exception — always degrades
    to this instead).
    """

    status: PromotionDecisionStatus
    promoted: bool = False
    workflow_name: str | None = None
    mode: PromotionMode = "off"
    reasons: list[PromotionBlockReason] = Field(default_factory=list)
    diagnostics: dict[str, Any] = Field(default_factory=dict)


class ShadowCandidateBundle(BaseModel):
    """In-memory-only pairing of a diagnostic `SupervisorRunOutput` and the
    full candidate `AgentResponse` captured for promotion consideration.

    Never persisted: `candidate_response` must never be written into
    `SupervisorRunOutput.diagnostics`/`blackboard_summary`,
    `agent_runs.retrievalMetadata`, or any other stored document — this
    bundle exists only to hand both back to `post_context_runner` together,
    for the current turn, in local Python memory.
    """

    model_config = ConfigDict(arbitrary_types_allowed=True)

    supervisor_output: SupervisorRunOutput
    candidate_response: AgentResponse | None = None
