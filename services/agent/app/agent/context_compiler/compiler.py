"""Context Compiler (Phase 4).

Takes a large, global `ContextCompilationRequest` and a capability's
`CapabilityContextContract` and produces a minimal `CompiledContext`
containing only what that capability is allowed to see. Purely
deterministic — no database access, no LLM calls, no randomness.

Not yet wired into the live orchestrator/workflow path: workflows still
receive the full `AgentContextPack` as before. This exists so a future
planner (Phase 5+) can hand each subagent/subtask only the context it needs.
"""

from __future__ import annotations

from app.agent.capabilities.registry import CapabilityRegistry
from app.agent.capabilities.schemas import CapabilityContextContract, CapabilityDescriptor
from app.agent.context_compiler import context_sections as sections
from app.agent.context_compiler.reducers import (
    reduce_agent_context_pack_summary,
    reduce_attachment_metadata,
    reduce_profile,
    reduce_recent_messages,
    reduce_wiki_snippets,
    sanitize_context_value,
)
from app.agent.context_compiler.schemas import CompiledContext, ContextCompilationRequest


def _is_allowed(section: str, contract: CapabilityContextContract) -> bool:
    if section in contract.forbidden_context_sections:
        return False
    if not contract.allowed_context_sections:
        # Fail-closed by default: an unconfigured contract grants no
        # sections rather than silently defaulting to "everything".
        return False
    return section in contract.allowed_context_sections


def _forbidden_extra_context_overrides(contract: CapabilityContextContract) -> dict[str, bool]:
    """Map forbidden-by-default `extra_context` keys to whether this capability opts back in."""
    return {
        "full_catalog": contract.include_full_catalog,
        "full_transcript_rows": contract.include_full_transcript_rows,
        "attachment_contents": contract.include_attachment_contents,
        # No contract field opts back into these two — always stripped.
        "raw_pdf_bytes": False,
        "raw_mongo_document": False,
    }


def _compile_extra_context(
    extra_context: dict[str, object],
    *,
    contract: CapabilityContextContract,
    warnings: list[str],
) -> dict[str, object]:
    overrides = _forbidden_extra_context_overrides(contract)
    compiled: dict[str, object] = {}
    for key, value in extra_context.items():
        if key in sections.FORBIDDEN_BY_DEFAULT_CONTEXT_KEYS:
            if overrides.get(key, False):
                compiled[key] = sanitize_context_value(value)
            else:
                warnings.append(f"omitted_forbidden_context: {key}")
            continue
        compiled[key] = sanitize_context_value(value)
    return compiled


def _count_items(value: object) -> int:
    if isinstance(value, dict):
        return sum(_count_items(item) for item in value.values()) or 1
    if isinstance(value, list):
        return sum(_count_items(item) for item in value) or 1
    return 1


def compile_context(
    request: ContextCompilationRequest,
    *,
    capability: CapabilityDescriptor,
) -> CompiledContext:
    """Compile `request` down to only what `capability` is allowed to see.

    A disabled capability still gets a compiled context (compiling context
    is a pure data-shaping operation, not an execution decision) — a
    `capability_disabled` warning is added so callers can decide whether to
    actually invoke it.
    """
    contract = capability.context
    warnings: list[str] = []
    included: dict[str, object] = {}
    included_sections: list[str] = []
    omitted_sections: list[str] = []

    if not capability.enabled:
        warnings.append(f"capability_disabled: {capability.name}")

    candidates: dict[str, object | None] = {
        sections.USER_MESSAGE: request.user_message,
        sections.TASK_UNDERSTANDING: request.task_understanding,
        sections.DETERMINISTIC_INTENT: request.deterministic_intent,
        sections.DETERMINISTIC_ENTITIES: request.deterministic_entities,
        sections.CONVERSATION_SUMMARY: request.conversation_summary,
        sections.RECENT_MESSAGES: request.recent_messages,
        sections.CONVERSATION_ENTITIES: request.conversation_entities,
        sections.CONVERSATION_ASSUMPTIONS: request.conversation_assumptions,
        sections.PROFILE_SUMMARY: request.profile_summary,
        sections.ATTACHMENT_METADATA: request.attachment_metadata,
        sections.AGENT_CONTEXT_PACK_SUMMARY: request.agent_context_pack_summary,
        sections.WIKI_SNIPPETS: request.wiki_snippets,
        sections.PREVIOUS_RESULTS: request.previous_results,
        sections.EXTRA_CONTEXT: request.extra_context,
    }

    for section in sorted(sections.ALL_CONTEXT_SECTIONS):
        if not _is_allowed(section, contract):
            omitted_sections.append(section)
            continue

        value = candidates[section]
        if value is None:
            omitted_sections.append(section)
            continue

        if section == sections.ATTACHMENT_METADATA and not contract.include_attachment_metadata:
            omitted_sections.append(section)
            continue

        if section == sections.RECENT_MESSAGES:
            compiled_value = reduce_recent_messages(value, contract.max_recent_messages)  # type: ignore[arg-type]
        elif section == sections.WIKI_SNIPPETS:
            compiled_value = reduce_wiki_snippets(value, contract.max_wiki_snippets)  # type: ignore[arg-type]
        elif section == sections.PROFILE_SUMMARY:
            compiled_value = reduce_profile(value)  # type: ignore[arg-type]
        elif section == sections.AGENT_CONTEXT_PACK_SUMMARY:
            compiled_value = reduce_agent_context_pack_summary(value)  # type: ignore[arg-type]
        elif section == sections.ATTACHMENT_METADATA:
            compiled_value = reduce_attachment_metadata(value)  # type: ignore[arg-type]
        elif section == sections.EXTRA_CONTEXT:
            compiled_value = _compile_extra_context(value, contract=contract, warnings=warnings)  # type: ignore[arg-type]
        else:
            compiled_value = sanitize_context_value(value)

        included[section] = compiled_value
        included_sections.append(section)

    if request.max_context_items is not None and len(included_sections) > request.max_context_items:
        # Deterministic priority: keep sections in the fixed order they were
        # evaluated (sorted section name), drop the rest.
        keep = included_sections[: request.max_context_items]
        dropped = included_sections[request.max_context_items :]
        for section in dropped:
            included.pop(section, None)
            omitted_sections.append(section)
            warnings.append(f"omitted_over_budget: {section}")
        included_sections = keep

    estimated_items = sum(_count_items(value) for value in included.values())

    return CompiledContext(
        capability_name=capability.name,
        objective=request.objective,
        context=included,
        included_sections=included_sections,
        omitted_sections=sorted(set(omitted_sections)),
        warnings=warnings,
        estimated_items=estimated_items,
    )


def compile_context_for_capability(
    request: ContextCompilationRequest,
    *,
    registry: CapabilityRegistry,
) -> CompiledContext:
    """Look up `request.capability_name` in `registry`, then compile context for it.

    Raises `CapabilityNotFoundError` (from `app.agent.capabilities.registry`)
    for an unknown capability name — a clear, typed error rather than a
    silent empty context.
    """
    capability = registry.require(request.capability_name)
    return compile_context(request, capability=capability)
