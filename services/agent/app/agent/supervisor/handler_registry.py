"""Handler resolution for the Supervisor Orchestrator Runtime (Phase 6/7/10)."""

from __future__ import annotations

from app.agent.supervisor.handlers import (
    ContextPreviewHandler,
    DryRunCapabilityHandler,
    SubtaskHandler,
    UnsupportedCapabilityHandler,
)
from app.agent.supervisor.workflow_adapters import ReadOnlyWorkflowAdapterHandler
from app.config import Settings, get_settings

# Capability types (`app.agent.capabilities.schemas.CapabilityType`) that get
# the context-preview-only handler by default, rather than the generic
# dry-run handler — these types describe inputs to other subtasks, not
# stand-alone "results".
_CONTEXT_PREVIEW_CAPABILITY_TYPES: tuple[str, ...] = ("retrieval", "validator", "composer")

# Phase 7: the only capability names ever registered with a real
# `ReadOnlyWorkflowAdapterHandler` by default — every one of these has been
# manually reviewed (see `capabilities/default_registry.py`'s
# `_READ_ONLY_WORKFLOW_EXECUTION`) and confirmed to never write to Mongo or
# create an `agent_action_proposals` document. `runtime.py` still
# independently re-checks `safety.can_shadow_execute_capability` before
# actually invoking the resolved handler — this list alone is not the
# safety boundary, just which names are even offered a real handler.
_READ_ONLY_WORKFLOW_CAPABILITY_NAMES: tuple[str, ...] = (
    "graduation_progress_workflow",
    "course_question_workflow",
    "requirement_explanation_workflow",
    "general_academic_workflow",
)

# Phase 10: the only capability names ever registered with a
# `SpecialistAgentHandler` by default — every one of these is a manually
# reviewed, read-only specialist agent (see `capabilities/default_registry.py`
# and `specialists.registry.build_default_specialist_agent_registry`).
# `SpecialistAgentHandler` still independently re-checks
# `specialists.safety.is_specialist_agent_safe` before ever calling one.
_SPECIALIST_AGENT_CAPABILITY_NAMES: tuple[str, ...] = (
    "graduation_progress_agent",
    "course_catalog_agent",
    "requirement_explanation_agent",
)

# Phase 15: dynamic agents are configuration-assembled sub-agents — shadow-only.
_DYNAMIC_AGENT_CAPABILITY_NAMES: tuple[str, ...] = ("dynamic_agent",)


class SubtaskHandlerRegistry:
    """Resolves a `SubtaskHandler` for a subtask, by capability name or type.

    Phase 6 registers only safe dry-run handlers. Phase 7 can register real
    workflow-adapter / specialist-agent handlers here (by capability name,
    taking priority over the type-level default) without changing this
    registry's interface.
    """

    def __init__(self, *, default_handler: SubtaskHandler | None = None) -> None:
        self._by_capability_name: dict[str, SubtaskHandler] = {}
        self._by_capability_type: dict[str, SubtaskHandler] = {}
        self._default_handler: SubtaskHandler = default_handler or DryRunCapabilityHandler()

    def register_for_capability_name(self, name: str, handler: SubtaskHandler) -> None:
        self._by_capability_name[name] = handler

    def register_for_capability_type(self, capability_type: str, handler: SubtaskHandler) -> None:
        self._by_capability_type[capability_type] = handler

    def resolve(self, *, capability_name: str, capability_type: str | None) -> SubtaskHandler:
        """Never raises — falls back to the registry's default handler."""
        if capability_name in self._by_capability_name:
            return self._by_capability_name[capability_name]
        if capability_type and capability_type in self._by_capability_type:
            return self._by_capability_type[capability_type]
        return self._default_handler


def build_default_handler_registry(
    *, enable_real_read_only_handlers: bool = False, settings: Settings | None = None
) -> SubtaskHandlerRegistry:
    """Build the default registry.

    When `enable_real_read_only_handlers` is `False` (the Phase 6 default),
    this is byte-for-byte the Phase 6 registry — no name is ever mapped to
    `ReadOnlyWorkflowAdapterHandler`, so behavior is identical to before
    Phase 7 existed. When `True`, the reviewed read-only workflow names
    additionally resolve to a real adapter — but `runtime.py` still
    independently re-validates safety and runtime-context availability
    before ever actually calling it (see `handlers.py` / `safety.py`).

    `settings`, when supplied, is threaded into the Phase 10
    `SpecialistAgentHandler` this builds — `run_supervisor_shadow` always
    passes its own resolved `cfg` here so a caller-supplied `Settings`
    object (e.g. in tests) actually controls specialist-agent behavior
    instead of that handler silently falling back to the process-wide
    cached `get_settings()` singleton.
    """
    registry = SubtaskHandlerRegistry(default_handler=DryRunCapabilityHandler())
    context_preview_handler = ContextPreviewHandler()
    for capability_type in _CONTEXT_PREVIEW_CAPABILITY_TYPES:
        registry.register_for_capability_type(capability_type, context_preview_handler)

    if enable_real_read_only_handlers:
        real_handler = ReadOnlyWorkflowAdapterHandler()
        for capability_name in _READ_ONLY_WORKFLOW_CAPABILITY_NAMES:
            registry.register_for_capability_name(capability_name, real_handler)

    # Phase 10: unlike the real workflow adapter above, the specialist-agent
    # handler is *always* registered for its three capability names —
    # `AGENT_SPECIALIST_AGENTS_ENABLED` is checked inside the handler itself
    # (returning a safe `"skipped"` `SubtaskResult`, never calling
    # `ReasoningBlock`, when off) rather than by conditionally registering a
    # different handler here. Imported lazily to avoid a circular import
    # (`specialists.supervisor_handler` imports `supervisor.blackboard`/
    # `supervisor.schemas`, which would otherwise trigger this very module
    # while `app.agent.supervisor`'s own package `__init__` is still loading).
    from app.agent.specialists.supervisor_handler import SpecialistAgentHandler

    specialist_handler = SpecialistAgentHandler(settings=settings or get_settings())
    for capability_name in _SPECIALIST_AGENT_CAPABILITY_NAMES:
        registry.register_for_capability_name(capability_name, specialist_handler)

    from app.agent.dynamic_agents.supervisor_handler import DynamicAgentHandler

    dynamic_agent_handler = DynamicAgentHandler(settings=settings or get_settings())
    for capability_name in _DYNAMIC_AGENT_CAPABILITY_NAMES:
        registry.register_for_capability_name(capability_name, dynamic_agent_handler)

    return registry


__all__ = [
    "SubtaskHandlerRegistry",
    "build_default_handler_registry",
    "UnsupportedCapabilityHandler",
]
