"""Local client-side mirror of `api`'s `GraduationAuditResult`.

The graduation audit computation (grading rules, pool/matrix evaluation)
stays exclusively in `api` — see `services/api/app/routes/internal_agent.py`
— to avoid duplicating that actively-evolving core engine. This module just
calls that endpoint and reconstructs the same typed result shape so the
workflows (`graduation_progress_workflow.py`,
`requirement_explanation_workflow.py`) barely change.

Note: the original in-process `run_graduation_audit` accepted an optional
`context: AgentContextPack` to fold in 1-2 extra context-derived warnings
(e.g. `profile_missing_in_context_pack`). That enrichment is intentionally
dropped here (documented simplification) — the endpoint always computes the
audit from the user's stored profile/completed-courses only.
"""

from __future__ import annotations

from typing import Any, Literal

from pydantic import BaseModel, Field

from app.clients.internal_api_client import fetch_graduation_audit

AuditStatus = Literal[
    "ok",
    "profile_not_found",
    "degree_not_selected",
    "degree_not_found",
    "audit_failed",
]


class GraduationAuditResult(BaseModel):
    status: AuditStatus
    progress: dict[str, Any] | None = None
    errors: list[str] = Field(default_factory=list)
    warnings: list[str] = Field(default_factory=list)
    assumptions: list[str] = Field(default_factory=list)
    blockers: list[str] = Field(default_factory=list)
    graduation_status: str = "missing_data"
    can_graduate: bool = False


async def run_graduation_audit(*, user_id: str) -> GraduationAuditResult:
    payload = await fetch_graduation_audit(user_id=user_id)
    return GraduationAuditResult.model_validate(payload)
