"""Typed request/result models for the Context Compiler (Phase 4)."""

from __future__ import annotations

from typing import Any

from pydantic import BaseModel, Field


class ContextCompilationRequest(BaseModel):
    """Everything potentially available to compile context from.

    The compiler never sees more than this — it only ever *removes*
    sections, it never fetches additional data (no DB/LLM access).
    """

    capability_name: str
    objective: str
    user_message: str
    task_understanding: dict[str, Any] | None = None
    deterministic_intent: str | None = None
    deterministic_entities: dict[str, Any] = Field(default_factory=dict)
    conversation_summary: str | None = None
    recent_messages: list[dict[str, Any]] = Field(default_factory=list)
    conversation_entities: dict[str, Any] = Field(default_factory=dict)
    conversation_assumptions: dict[str, Any] = Field(default_factory=dict)
    profile_summary: dict[str, Any] = Field(default_factory=dict)
    attachment_metadata: list[dict[str, Any]] = Field(default_factory=list)
    agent_context_pack_summary: dict[str, Any] = Field(default_factory=dict)
    wiki_snippets: list[dict[str, Any]] = Field(default_factory=list)
    previous_results: dict[str, Any] = Field(default_factory=dict)
    extra_context: dict[str, Any] = Field(default_factory=dict)
    max_context_items: int | None = None


class CompiledContext(BaseModel):
    """Minimal, capability-specific context produced by the compiler."""

    capability_name: str
    objective: str
    context: dict[str, Any]
    included_sections: list[str] = Field(default_factory=list)
    omitted_sections: list[str] = Field(default_factory=list)
    warnings: list[str] = Field(default_factory=list)
    estimated_items: int | None = None
