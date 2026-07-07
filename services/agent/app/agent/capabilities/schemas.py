"""Typed models describing what the agent system can do (Phase 4).

`CapabilityDescriptor` is metadata only in Phase 4 — it does not execute
anything and nothing in the live orchestrator reads it to select a
workflow. It exists so a future planner (Phase 5) can reason over available
capabilities (workflows, specialist agents, tools, internal APIs, retrieval,
validators, composers) instead of the current hardcoded
`intent -> workflow` mapping in `task_planner.py`.
"""

from __future__ import annotations

from typing import Any, Literal

from pydantic import BaseModel, Field

CapabilityType = Literal[
    "workflow",
    "specialist_agent",
    "tool",
    "internal_api",
    "retrieval",
    "validator",
    "composer",
]

CapabilityRiskLevel = Literal["low", "medium", "high"]

# "proposal_only" is the only write mode any capability except the explicit
# api-side action executor should ever declare — see
# `default_registry.py`'s `action_proposal_creator` and the api-side
# confirm/reject flow, which stays the sole `direct_write` path.
CapabilityWriteScope = Literal["none", "proposal_only", "direct_write"]


class CapabilityIOContract(BaseModel):
    """Optional documented input/output shape for a capability."""

    input_schema_name: str | None = None
    output_schema_name: str | None = None
    input_schema: dict[str, Any] = Field(default_factory=dict)
    output_schema: dict[str, Any] = Field(default_factory=dict)


class CapabilityPermissionScope(BaseModel):
    """What a capability is allowed to read/write/call."""

    can_read_student_data: bool = False
    can_read_catalog: bool = False
    can_read_offerings: bool = False
    can_read_wiki: bool = False
    can_create_action_proposals: bool = False
    can_execute_writes: bool = False
    write_scope: CapabilityWriteScope = "none"
    allowed_collections: list[str] = Field(default_factory=list)
    allowed_internal_endpoints: list[str] = Field(default_factory=list)
    allowed_tools: list[str] = Field(default_factory=list)


class CapabilityContextContract(BaseModel):
    """What context a capability may receive from the Context Compiler.

    `allowed_context_sections` names must match
    `app.agent.context_compiler.context_sections.ContextSection` values.
    """

    allowed_context_sections: list[str] = Field(default_factory=list)
    forbidden_context_sections: list[str] = Field(default_factory=list)
    max_recent_messages: int = 6
    max_wiki_snippets: int = 8
    include_attachment_metadata: bool = True
    include_attachment_contents: bool = False
    include_full_catalog: bool = False
    include_full_transcript_rows: bool = False


CapabilitySideEffectLevel = Literal["none", "proposal", "write", "unknown"]


class CapabilityExecutionMetadata(BaseModel):
    """Whether/how a capability may actually be *executed* (Phase 7+).

    Metadata only through Phase 6 — every capability defaulted to
    non-executable. Phase 7 adds real execution for a small, explicitly
    reviewed set of provably read-only workflows via
    `app.agent.supervisor.workflow_adapters.ReadOnlyWorkflowAdapterHandler`,
    gated by `app.agent.supervisor.safety.can_shadow_execute_capability`.

    Defaults are deliberately conservative (nothing executable, unknown
    side effects, unsafe for shadow execution) — a capability must be
    explicitly marked safe in `default_registry.py` after code review, it
    is never safe by omission.

    `operationally_expensive_for_shadow_execution` (Phase 8) is orthogonal to
    `safe_for_shadow_execution`: a capability can be perfectly safe (never
    writes, never proposes) yet still expensive/noisy to actually
    shadow-execute for real on every turn (e.g. it may call an LLM through
    the existing `ReasoningBlock` path). `app.agent.supervisor.runtime`
    treats this as an independent gate — such a capability still passes
    `safety.can_shadow_execute_capability`, but the runtime falls back to
    the safe dry-run handler instead of actually invoking it for real, by
    default, wherever real handlers are considered.

    `real_execution_supported_with_proposals` (post-Phase-9) is a wholly
    separate, narrower gate from `safe_for_shadow_execution` — it marks a
    capability whose real execution is expected to (optionally) create an
    action proposal, never a direct write. `safety.can_shadow_execute_capability`
    always hard-fails such a capability (proposal creation is never safe
    for the shadow-compare/promotion/diagnostic pipeline, regardless of this
    flag); only `safety.can_execute_capability_for_real_with_proposals`, and
    only when explicitly requested by an already-gated live-execution caller
    (`app.agent.planner_first_live`), ever allows it to dispatch for real.
    """

    execution_supported: bool = False
    shadow_execution_supported: bool = False
    handler_name: str | None = None
    side_effect_level: CapabilitySideEffectLevel = "unknown"
    safe_for_shadow_execution: bool = False
    operationally_expensive_for_shadow_execution: bool = False
    real_execution_supported_with_proposals: bool = False


class CapabilityDescriptor(BaseModel):
    """Metadata describing one thing the agent system can do.

    Phase 4: descriptive only. Registering a `specialist_agent` here does
    not create an executable agent — it documents what Phase 5+ intends to
    build, so the future planner has something to reason over today.
    """

    name: str
    type: CapabilityType
    description: str
    owner: str | None = None
    version: str = "1.0.0"
    supported_intents: list[str] = Field(default_factory=list)
    supported_task_categories: list[str] = Field(default_factory=list)
    risk_level: CapabilityRiskLevel = "medium"
    io: CapabilityIOContract = Field(default_factory=CapabilityIOContract)
    permissions: CapabilityPermissionScope = Field(default_factory=CapabilityPermissionScope)
    context: CapabilityContextContract = Field(default_factory=CapabilityContextContract)
    execution: CapabilityExecutionMetadata = Field(default_factory=CapabilityExecutionMetadata)
    source_of_truth_rank: int | None = None
    enabled: bool = True
    notes: list[str] = Field(default_factory=list)
