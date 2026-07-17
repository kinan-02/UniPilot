"""Request Understanding's own `BaseReasoningBlock` shapes (docs/agent/AGENT_VISION.md §3, §6.2).

Deliberately just what this layer's three jobs actually need: resolving
conversation-history references into a self-contained goal, preserving
every distinct ask, and gating scope as its own explicit field -- never
inferred from `user_goal` being empty (the same "explicit status, never
inferred" discipline already used for the Planner's `plan_status`).
"""

from __future__ import annotations

from pydantic import BaseModel, Field

from app.agent_core.reasoning_blocks.schemas import BaseReasoningBlockInput, BaseReasoningBlockOutput


class ConversationTurn(BaseModel):
    """One prior turn -- bounded, not the full plan-execution state (§7.2's
    "deliberately bounded package" philosophy applied here too). Currently
    always passed as an empty list: nothing upstream persists turn history
    yet, so sourcing it is separate follow-up work -- this type exists so
    that plumbing doesn't need to be redesigned once it does.
    """

    user_message: str
    final_answer: str


class RequestUnderstandingReasoningBlockInput(BaseReasoningBlockInput):
    original_user_message: str
    conversation_history: list[ConversationTurn] = Field(default_factory=list)


class RequestUnderstandingReasoningBlockOutput(BaseReasoningBlockOutput):
    """`status`/`schema_valid`/`confidence`/`warnings`/`total_llm_calls_used`
    come from the base. `in_scope` is always explicit. When `in_scope` is
    `True`: `sub_asks` (every distinct thing asked), `constraints` (boundary
    conditions on the answer), `open_questions` (genuine ambiguities noticed
    but not resolved -- RU still never asks the user directly), and
    `implies_action_request` are populated; `decline_reason` is `None`.
    When `False`: only `decline_reason` is populated, everything else
    resets to empty/`False`.

    `user_goal` is **not** LLM output -- it's deterministically rendered
    from `sub_asks` (see `request_understanding._render_user_goal`), so it
    can never independently drift from the structured fields it summarizes.
    Kept only because `PlannerInvocationInput.user_goal: str` and other
    existing callers still want a flat string -- `sub_asks` is the actual
    source of truth.
    """

    in_scope: bool
    user_goal: str | None = None
    decline_reason: str | None = None
    sub_asks: list[str] = Field(default_factory=list)
    constraints: list[str] = Field(default_factory=list)
    open_questions: list[str] = Field(default_factory=list)
    # Claims the question takes for granted about the student's OWN state, which
    # it cannot be answered honestly without checking. A non-empty list
    # deterministically adds a verification sub-ask (see
    # `_PRESUPPOSITION_SUB_ASK`), so this is not merely descriptive -- it changes
    # the plan.
    presuppositions: list[str] = Field(default_factory=list)
    implies_action_request: bool = False


__all__ = [
    "ConversationTurn",
    "RequestUnderstandingReasoningBlockInput",
    "RequestUnderstandingReasoningBlockOutput",
]
