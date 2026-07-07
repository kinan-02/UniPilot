"""Context Compiler (Phase 4).

Produces a minimal, capability-specific context pack from a large global
context, respecting each capability's `CapabilityContextContract`. Purely
deterministic — no database access, no LLM calls. Importing this package
has no side effects.
"""

from __future__ import annotations

# Import order matters here: `compiler` imports `context_sections` back via
# `from app.agent.context_compiler import context_sections`, so
# `context_sections` (and the other leaf modules) must already be bound as
# package attributes before `compiler` is imported, to avoid relying on
# Python's submodule-import fallback for a self-referential import.
from app.agent.context_compiler import context_sections, reducers
from app.agent.context_compiler.compiler import compile_context, compile_context_for_capability
from app.agent.context_compiler.schemas import CompiledContext, ContextCompilationRequest

__all__ = [
    "context_sections",
    "reducers",
    "compile_context",
    "compile_context_for_capability",
    "CompiledContext",
    "ContextCompilationRequest",
]
