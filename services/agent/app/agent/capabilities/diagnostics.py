"""Optional diagnostic integration: capability registry + context compiler (Phase 4).

Diagnostic only, mirroring `app.agent.task_understanding.integration`. Runs
after the (already diagnostic-only) `TaskUnderstandingAgent` dry-run and
produces a small, compact summary meant to be attached to
`agent_runs.retrievalMetadata.capabilityDiagnostics`.

Hard constraints:
- Never selects a workflow or changes routing.
- Never changes the final response or emits new SSE events.
- Never raises into a live turn — any failure degrades to `None`.
- No LLM calls, no database access — `CapabilityRegistry` and
  `ContextCompiler` are both purely deterministic/in-memory.
"""

from __future__ import annotations

import logging
from typing import Any

from app.agent.capabilities.default_registry import build_default_capability_registry
from app.agent.context_compiler.compiler import compile_context_for_capability
from app.agent.context_compiler.schemas import ContextCompilationRequest

logger = logging.getLogger(__name__)

# Phase 5's planner is the natural "next layer" to preview context for,
# regardless of what `TaskUnderstandingAgent` suggests today — none of the
# suggestions map to an already-implemented specialist agent yet.
_DEFAULT_TARGET_CAPABILITY = "planner_agent"

_MAX_OMITTED_SECTIONS_LOGGED = 12
_MAX_WARNINGS_LOGGED = 8


def build_capability_diagnostics(
    *,
    task_understanding_summary: dict[str, Any],
    user_message: str,
    deterministic_intent: str | None,
    deterministic_entities: dict[str, Any] | None,
) -> dict[str, Any] | None:
    """Build a compact, storage-safe capability/context diagnostic summary.

    Returns `None` on any failure — this must never break a live agent turn.
    """
    try:
        registry = build_default_capability_registry()
        primary_intent = task_understanding_summary.get("primaryIntent")
        matched = registry.find_by_intent(primary_intent) if primary_intent else []

        target_capability_name = _DEFAULT_TARGET_CAPABILITY
        if not registry.has(target_capability_name):
            return None

        request = ContextCompilationRequest(
            capability_name=target_capability_name,
            objective="phase4_diagnostic_capability_context_compilation",
            user_message=user_message,
            task_understanding=task_understanding_summary,
            deterministic_intent=deterministic_intent,
            deterministic_entities=deterministic_entities or {},
        )
        compiled = compile_context_for_capability(request, registry=registry)

        return {
            "matchedCapabilities": [capability.name for capability in matched],
            "targetCapability": compiled.capability_name,
            "includedSections": compiled.included_sections,
            "omittedSections": compiled.omitted_sections[:_MAX_OMITTED_SECTIONS_LOGGED],
            "warnings": compiled.warnings[:_MAX_WARNINGS_LOGGED],
            "estimatedItems": compiled.estimated_items,
        }
    except Exception:  # noqa: BLE001 — diagnostic-only path, must never break a live turn
        logger.exception("capability_diagnostics_failed")
        return None
