"""Shared LLM reasoning runtime for the UniPilot agent (Phase 1 foundation).

This package provides `ReasoningBlock`, a reusable multi-pass reasoning
runtime intended to become the single call path for all future LLM-powered
agent components. It is not wired into the live orchestrator/workflows in
Phase 1 — importing this package has no side effects and does not change any
existing production behavior.
"""

from __future__ import annotations

from app.agent.reasoning.llm_adapter import ChatLLMAdapter, LLMAdapter, LLMAdapterError
from app.agent.reasoning.prompt_registry import (
    GENERIC_REASONING_BLOCK_V1,
    SCHEMA_REPAIR_V1,
    PromptContract,
    PromptContractNotFoundError,
    PromptRegistry,
    build_default_prompt_registry,
)
from app.agent.reasoning.reasoning_block import ReasoningBlock
from app.agent.reasoning.schema_validator import validate_against_schema
from app.agent.reasoning.schemas import (
    ReasoningBlockInput,
    ReasoningBlockOutput,
    ReasoningPassPayload,
    ReasoningRiskLevel,
    ReasoningStatus,
    ReasoningTrace,
    ReasoningToolRequest,
    ReasoningToolSpec,
    SchemaRepairOutcome,
    SchemaValidationResult,
)

__all__ = [
    "ChatLLMAdapter",
    "LLMAdapter",
    "LLMAdapterError",
    "GENERIC_REASONING_BLOCK_V1",
    "SCHEMA_REPAIR_V1",
    "PromptContract",
    "PromptContractNotFoundError",
    "PromptRegistry",
    "build_default_prompt_registry",
    "ReasoningBlock",
    "validate_against_schema",
    "ReasoningBlockInput",
    "ReasoningBlockOutput",
    "ReasoningPassPayload",
    "ReasoningRiskLevel",
    "ReasoningStatus",
    "ReasoningTrace",
    "ReasoningToolRequest",
    "ReasoningToolSpec",
    "SchemaRepairOutcome",
    "SchemaValidationResult",
]
