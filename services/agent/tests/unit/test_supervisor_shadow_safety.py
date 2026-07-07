"""Unit tests for Phase 7 shadow-execution safety gating (`supervisor/safety.py`).

Includes the dedicated static source scan for the whole `supervisor`
package (no Mongo writes, no proposal creation, no confirm/reject calls, no
direct LLM calls) — deliberately more targeted than a blanket import ban,
since Phase 7's `workflow_adapters.py` legitimately imports the real
`workflows.registry` to execute reviewed read-only workflows.
"""

from __future__ import annotations

from pathlib import Path

import pytest

from app.agent.capabilities.default_registry import build_default_capability_registry
from app.agent.capabilities.schemas import (
    CapabilityDescriptor,
    CapabilityExecutionMetadata,
    CapabilityPermissionScope,
)
from app.agent.supervisor.handler_registry import build_default_handler_registry
from app.agent.supervisor.runtime import _select_handler
from app.agent.supervisor.safety import (
    can_execute_capability_for_real_with_proposals,
    can_shadow_execute_capability,
    shadow_execution_blocked_warning,
)
from app.agent.supervisor.schemas import SupervisorRuntimeContext
from app.agent.supervisor.workflow_adapters import ReadOnlyWorkflowAdapterHandler


def _capability(**overrides) -> CapabilityDescriptor:
    defaults = dict(
        name="test_capability",
        type="workflow",
        description="test",
        execution=CapabilityExecutionMetadata(
            execution_supported=True,
            shadow_execution_supported=True,
            handler_name="read_only_workflow_adapter",
            side_effect_level="none",
            safe_for_shadow_execution=True,
        ),
        permissions=CapabilityPermissionScope(),
    )
    defaults.update(overrides)
    return CapabilityDescriptor(**defaults)


# ---------------------------------------------------------------------------
# 1. Read-only workflow capability can shadow execute.
# ---------------------------------------------------------------------------


def test_read_only_workflow_capability_can_shadow_execute() -> None:
    assert can_shadow_execute_capability(_capability()) is True


def test_real_default_registry_read_only_workflows_can_shadow_execute() -> None:
    registry = build_default_capability_registry()
    for name in (
        "graduation_progress_workflow",
        "course_question_workflow",
        "requirement_explanation_workflow",
        "general_academic_workflow",
    ):
        assert can_shadow_execute_capability(registry.require(name)) is True, name


# ---------------------------------------------------------------------------
# 2. Proposal workflow cannot shadow execute.
# ---------------------------------------------------------------------------


def test_real_default_registry_proposal_workflows_cannot_shadow_execute() -> None:
    registry = build_default_capability_registry()
    for name in ("transcript_import_workflow", "semester_planning_workflow"):
        assert can_shadow_execute_capability(registry.require(name)) is False, name


# ---------------------------------------------------------------------------
# 3. write_scope="proposal_only" blocks real shadow execution.
# ---------------------------------------------------------------------------


def test_write_scope_proposal_only_blocks_shadow_execution() -> None:
    capability = _capability(permissions=CapabilityPermissionScope(write_scope="proposal_only"))
    assert can_shadow_execute_capability(capability) is False


def test_write_scope_direct_write_blocks_shadow_execution() -> None:
    capability = _capability(permissions=CapabilityPermissionScope(write_scope="direct_write"))
    assert can_shadow_execute_capability(capability) is False


# ---------------------------------------------------------------------------
# 4. can_create_action_proposals blocks real shadow execution.
# ---------------------------------------------------------------------------


def test_can_create_action_proposals_blocks_shadow_execution() -> None:
    capability = _capability(permissions=CapabilityPermissionScope(can_create_action_proposals=True))
    assert can_shadow_execute_capability(capability) is False


# ---------------------------------------------------------------------------
# 5. can_execute_writes blocks real shadow execution.
# ---------------------------------------------------------------------------


def test_can_execute_writes_blocks_shadow_execution() -> None:
    capability = _capability(permissions=CapabilityPermissionScope(can_execute_writes=True))
    assert can_shadow_execute_capability(capability) is False


# ---------------------------------------------------------------------------
# 6. Unknown side_effect_level blocks execution.
# ---------------------------------------------------------------------------


@pytest.mark.parametrize("side_effect_level", ["unknown", "proposal", "write"])
def test_non_none_side_effect_level_blocks_execution(side_effect_level: str) -> None:
    capability = _capability(
        execution=CapabilityExecutionMetadata(
            execution_supported=True,
            shadow_execution_supported=True,
            side_effect_level=side_effect_level,
            safe_for_shadow_execution=True,
        )
    )
    assert can_shadow_execute_capability(capability) is False


def test_shadow_execution_not_supported_blocks_execution() -> None:
    capability = _capability(
        execution=CapabilityExecutionMetadata(
            execution_supported=True,
            shadow_execution_supported=False,
            side_effect_level="none",
            safe_for_shadow_execution=True,
        )
    )
    assert can_shadow_execute_capability(capability) is False


def test_not_safe_for_shadow_execution_blocks_execution() -> None:
    capability = _capability(
        execution=CapabilityExecutionMetadata(
            execution_supported=True,
            shadow_execution_supported=True,
            side_effect_level="none",
            safe_for_shadow_execution=False,
        )
    )
    assert can_shadow_execute_capability(capability) is False


def test_default_execution_metadata_is_conservative_and_blocks_execution() -> None:
    capability = _capability(execution=CapabilityExecutionMetadata())
    assert capability.execution.side_effect_level == "unknown"
    assert can_shadow_execute_capability(capability) is False


# ---------------------------------------------------------------------------
# 7. Disabled capability blocks execution.
# ---------------------------------------------------------------------------


def test_disabled_capability_blocks_shadow_execution() -> None:
    capability = _capability(enabled=False)
    assert can_shadow_execute_capability(capability) is False


# ---------------------------------------------------------------------------
# 8. Missing runtime context blocks real handler and falls back safely.
# ---------------------------------------------------------------------------


def test_missing_runtime_context_falls_back_to_dry_run_handler() -> None:
    capability = build_default_capability_registry().require("graduation_progress_workflow")
    handlers = build_default_handler_registry(enable_real_read_only_handlers=True)

    handler, warning = _select_handler(capability, handlers=handlers, real_handlers_enabled=True, runtime_context=None)

    assert handler is not None
    assert not isinstance(handler, ReadOnlyWorkflowAdapterHandler)
    assert warning == "real_shadow_execution_unavailable_missing_runtime_context"


def test_runtime_context_missing_database_falls_back_to_dry_run_handler() -> None:
    capability = build_default_capability_registry().require("graduation_progress_workflow")
    handlers = build_default_handler_registry(enable_real_read_only_handlers=True)
    context = SupervisorRuntimeContext(database=None, agent_context_pack=object(), user_message="hi")

    handler, warning = _select_handler(capability, handlers=handlers, real_handlers_enabled=True, runtime_context=context)

    assert not isinstance(handler, ReadOnlyWorkflowAdapterHandler)
    assert warning == "real_shadow_execution_unavailable_missing_runtime_context"


def test_populated_runtime_context_allows_real_handler_when_safe() -> None:
    capability = build_default_capability_registry().require("graduation_progress_workflow")
    handlers = build_default_handler_registry(enable_real_read_only_handlers=True)
    context = SupervisorRuntimeContext(database=object(), agent_context_pack=object(), user_message="hi")

    handler, warning = _select_handler(capability, handlers=handlers, real_handlers_enabled=True, runtime_context=context)

    assert isinstance(handler, ReadOnlyWorkflowAdapterHandler)
    assert warning is None


def test_unsafe_capability_never_gets_real_handler_even_with_runtime_context() -> None:
    """Defense in depth: even a caller-supplied registry mapping an unsafe
    capability to the real adapter must still be refused by `_select_handler`."""
    from app.agent.supervisor.handler_registry import SubtaskHandlerRegistry
    from app.agent.supervisor.handlers import DryRunCapabilityHandler

    unsafe_capability = _capability(
        permissions=CapabilityPermissionScope(can_create_action_proposals=True)
    )
    registry = SubtaskHandlerRegistry(default_handler=DryRunCapabilityHandler())
    registry.register_for_capability_name(unsafe_capability.name, ReadOnlyWorkflowAdapterHandler())
    context = SupervisorRuntimeContext(database=object(), agent_context_pack=object(), user_message="hi")

    handler, warning = _select_handler(unsafe_capability, handlers=registry, real_handlers_enabled=True, runtime_context=context)

    assert handler is None
    assert warning == shadow_execution_blocked_warning(unsafe_capability.name)


# ---------------------------------------------------------------------------
# Post-Phase-9: `can_execute_capability_for_real_with_proposals` -- wholly
# separate from `can_shadow_execute_capability` above, and never consulted
# by it. Proposal-creating workflows must still always fail
# `can_shadow_execute_capability` (item 2 above already covers that); these
# tests cover the new, independent predicate.
# ---------------------------------------------------------------------------


def _proposal_capability(**overrides) -> CapabilityDescriptor:
    defaults = dict(
        name="test_proposal_capability",
        type="workflow",
        description="test",
        execution=CapabilityExecutionMetadata(
            execution_supported=True,
            shadow_execution_supported=False,
            handler_name="proposal_capable_workflow_adapter",
            side_effect_level="proposal",
            safe_for_shadow_execution=False,
            real_execution_supported_with_proposals=True,
        ),
        permissions=CapabilityPermissionScope(can_create_action_proposals=True, write_scope="proposal_only"),
    )
    defaults.update(overrides)
    return CapabilityDescriptor(**defaults)


def test_proposal_capable_capability_can_execute_for_real_with_proposals() -> None:
    assert can_execute_capability_for_real_with_proposals(_proposal_capability()) is True


def test_real_default_registry_proposal_workflows_can_execute_for_real_with_proposals() -> None:
    registry = build_default_capability_registry()
    for name in ("transcript_import_workflow", "semester_planning_workflow"):
        assert can_execute_capability_for_real_with_proposals(registry.require(name)) is True, name


def test_real_default_registry_read_only_workflows_cannot_execute_for_real_with_proposals() -> None:
    """The new predicate is not a superset -- read-only workflows never
    have `real_execution_supported_with_proposals=True`, so they never pass
    this check either (they pass `can_shadow_execute_capability` instead)."""
    registry = build_default_capability_registry()
    for name in (
        "graduation_progress_workflow",
        "course_question_workflow",
        "requirement_explanation_workflow",
        "general_academic_workflow",
    ):
        assert can_execute_capability_for_real_with_proposals(registry.require(name)) is False, name


def test_direct_write_permission_blocks_proposal_capable_execution() -> None:
    capability = _proposal_capability(
        permissions=CapabilityPermissionScope(can_create_action_proposals=True, can_execute_writes=True)
    )
    assert can_execute_capability_for_real_with_proposals(capability) is False


def test_non_proposal_only_write_scope_blocks_proposal_capable_execution() -> None:
    capability = _proposal_capability(
        permissions=CapabilityPermissionScope(can_create_action_proposals=True, write_scope="direct_write")
    )
    assert can_execute_capability_for_real_with_proposals(capability) is False


def test_missing_can_create_action_proposals_blocks_proposal_capable_execution() -> None:
    capability = _proposal_capability(permissions=CapabilityPermissionScope(write_scope="proposal_only"))
    assert can_execute_capability_for_real_with_proposals(capability) is False


def test_missing_execution_flag_blocks_proposal_capable_execution_even_with_right_permissions() -> None:
    capability = _proposal_capability(
        execution=CapabilityExecutionMetadata(
            execution_supported=True,
            side_effect_level="proposal",
            real_execution_supported_with_proposals=False,
        )
    )
    assert can_execute_capability_for_real_with_proposals(capability) is False


def test_disabled_capability_blocks_proposal_capable_execution() -> None:
    capability = _proposal_capability(enabled=False)
    assert can_execute_capability_for_real_with_proposals(capability) is False


# ---------------------------------------------------------------------------
# Post-Phase-9: `_select_handler`'s `allow_proposal_capable_execution` opt-in.
# ---------------------------------------------------------------------------


def test_select_handler_blocks_proposal_capability_without_opt_in() -> None:
    """Without `allow_proposal_capable_execution`, a proposal-capable
    capability is refused exactly like any other unsafe capability -- the
    opt-in must be explicit."""
    capability = build_default_capability_registry().require("transcript_import_workflow")
    handlers = build_default_handler_registry(enable_real_read_only_handlers=True)
    context = SupervisorRuntimeContext(database=object(), agent_context_pack=object(), user_message="hi")

    handler, warning = _select_handler(
        capability, handlers=handlers, real_handlers_enabled=True, runtime_context=context
    )

    assert handler is None
    assert warning == shadow_execution_blocked_warning(capability.name)


def test_select_handler_allows_proposal_capability_with_explicit_opt_in() -> None:
    capability = build_default_capability_registry().require("transcript_import_workflow")
    from app.agent.supervisor.handler_registry import SubtaskHandlerRegistry
    from app.agent.supervisor.handlers import DryRunCapabilityHandler

    pre_registered = ReadOnlyWorkflowAdapterHandler(allow_single_proposed_action=True)
    registry = SubtaskHandlerRegistry(default_handler=DryRunCapabilityHandler())
    registry.register_for_capability_name(capability.name, pre_registered)
    context = SupervisorRuntimeContext(database=object(), agent_context_pack=object(), user_message="hi")

    handler, warning = _select_handler(
        capability,
        handlers=registry,
        real_handlers_enabled=True,
        runtime_context=context,
        allow_proposal_capable_execution=True,
    )

    assert handler is pre_registered
    assert warning is None


def test_select_handler_fresh_fallback_never_tolerates_proposed_actions() -> None:
    """Defense in depth: even with the opt-in, a *fresh* default handler
    instance (no caller pre-registration) must never itself be configured
    to tolerate a proposed action -- only an explicitly configured,
    pre-registered instance ever can."""
    capability = build_default_capability_registry().require("transcript_import_workflow")
    from app.agent.supervisor.handler_registry import SubtaskHandlerRegistry
    from app.agent.supervisor.handlers import DryRunCapabilityHandler

    registry = SubtaskHandlerRegistry(default_handler=DryRunCapabilityHandler())
    context = SupervisorRuntimeContext(database=object(), agent_context_pack=object(), user_message="hi")

    handler, warning = _select_handler(
        capability,
        handlers=registry,
        real_handlers_enabled=True,
        runtime_context=context,
        allow_proposal_capable_execution=True,
    )

    assert isinstance(handler, ReadOnlyWorkflowAdapterHandler)
    assert handler._allow_single_proposed_action is False
    assert warning is None


def test_select_handler_read_only_capability_unaffected_by_proposal_opt_in() -> None:
    """`allow_proposal_capable_execution=True` never widens eligibility for
    a capability that isn't itself marked `real_execution_supported_with_proposals`."""
    unsafe_capability = _capability(permissions=CapabilityPermissionScope(can_create_action_proposals=True))
    handlers = build_default_handler_registry(enable_real_read_only_handlers=True)
    context = SupervisorRuntimeContext(database=object(), agent_context_pack=object(), user_message="hi")

    handler, warning = _select_handler(
        unsafe_capability,
        handlers=handlers,
        real_handlers_enabled=True,
        runtime_context=context,
        allow_proposal_capable_execution=True,
    )

    assert handler is None
    assert warning == shadow_execution_blocked_warning(unsafe_capability.name)


# ---------------------------------------------------------------------------
# Static safety scan: no Mongo writes, no proposal creation, no
# confirm/reject calls, no direct LLM calls anywhere in the supervisor
# package (including the new Phase 7 files).
# ---------------------------------------------------------------------------

_FORBIDDEN_TOKENS: tuple[str, ...] = (
    "create_agent_action_proposal(",
    ".insert_one(",
    ".update_one(",
    ".update_many(",
    ".delete_one(",
    ".delete_many(",
    "confirm_action(",
    "reject_action(",
    "/confirm",
    "/reject",
    "internal_api_client",
    "ChatOpenAI",
    "llm.ainvoke",
    "llm.invoke",
    "build_chat_llm(",
)


def test_static_scan_no_writes_proposals_confirm_reject_or_direct_llm_calls() -> None:
    supervisor_dir = Path(__file__).resolve().parents[2] / "app" / "agent" / "supervisor"
    assert supervisor_dir.is_dir()

    violations: dict[str, list[str]] = {}
    for path in supervisor_dir.glob("*.py"):
        text = path.read_text(encoding="utf-8")
        hits = [token for token in _FORBIDDEN_TOKENS if token in text]
        if hits:
            violations[path.name] = hits

    assert not violations, (
        "Forbidden write/proposal/confirm-reject/direct-LLM patterns found in "
        f"the supervisor package: {violations}"
    )


def test_workflow_adapters_module_only_imports_workflow_registry_for_lookup() -> None:
    """`workflow_adapters.py` is the one supervisor file allowed to reference
    the real workflow registry -- confirm no *other* supervisor file does."""
    supervisor_dir = Path(__file__).resolve().parents[2] / "app" / "agent" / "supervisor"
    for path in supervisor_dir.glob("*.py"):
        if path.name == "workflow_adapters.py":
            continue
        text = path.read_text(encoding="utf-8")
        assert "workflows.registry" not in text, f"{path.name} must not import the workflow registry"


# ---------------------------------------------------------------------------
# Phase 8: extended static safety scan for the new validation/compare/
# post-context files (also covered by the whole-package scan above, but
# listed explicitly here per the Phase 8 spec's own forbidden-token list).
# ---------------------------------------------------------------------------

_PHASE8_FORBIDDEN_TOKENS: tuple[str, ...] = (
    ".insert_one(",
    ".update_one(",
    ".delete_one(",
    "create_agent_action_proposal(",
    "confirm_action(",
    "reject_action(",
    "chat.completions",
    "ChatOpenAI",
    "OpenAI(",
    "llm.invoke",
    "llm.ainvoke",
)

_PHASE8_SUPERVISOR_FILES: tuple[str, ...] = (
    "validation.py",
    "validation_schemas.py",
    "shadow_compare.py",
    "compare_diagnostics.py",
    "post_context_runner.py",
)


def test_phase8_files_contain_no_writes_proposals_confirm_reject_or_direct_llm_calls() -> None:
    supervisor_dir = Path(__file__).resolve().parents[2] / "app" / "agent" / "supervisor"

    violations: dict[str, list[str]] = {}
    for filename in _PHASE8_SUPERVISOR_FILES:
        path = supervisor_dir / filename
        assert path.is_file(), f"expected Phase 8 file missing: {filename}"
        text = path.read_text(encoding="utf-8")
        hits = [token for token in _PHASE8_FORBIDDEN_TOKENS if token in text]
        if hits:
            violations[filename] = hits

    assert not violations, f"Forbidden patterns found in Phase 8 supervisor files: {violations}"


# ---------------------------------------------------------------------------
# Phase 9: extended static safety scan for the promotion files.
# ---------------------------------------------------------------------------

_PHASE9_SUPERVISOR_FILES: tuple[str, ...] = (
    "promotion.py",
    "promotion_schemas.py",
    "promotion_diagnostics.py",
)


def test_phase9_promotion_files_contain_no_writes_proposals_confirm_reject_or_direct_llm_calls() -> None:
    supervisor_dir = Path(__file__).resolve().parents[2] / "app" / "agent" / "supervisor"

    violations: dict[str, list[str]] = {}
    for filename in _PHASE9_SUPERVISOR_FILES:
        path = supervisor_dir / filename
        assert path.is_file(), f"expected Phase 9 file missing: {filename}"
        text = path.read_text(encoding="utf-8")
        hits = [token for token in _PHASE8_FORBIDDEN_TOKENS if token in text]
        if hits:
            violations[filename] = hits

    assert not violations, f"Forbidden patterns found in Phase 9 promotion files: {violations}"


# ---------------------------------------------------------------------------
# Phase 10: static safety scan for the whole `specialists` package (also
# covered independently in `test_specialist_agent_safety.py`, duplicated
# here so the supervisor package's own safety test suite stays a complete
# one-stop check across every phase's shadow-execution surface).
# ---------------------------------------------------------------------------


def test_phase10_specialists_package_contains_no_writes_proposals_confirm_reject_or_direct_llm_calls() -> None:
    specialists_dir = Path(__file__).resolve().parents[2] / "app" / "agent" / "specialists"
    assert specialists_dir.is_dir()

    violations: dict[str, list[str]] = {}
    for path in specialists_dir.glob("*.py"):
        text = path.read_text(encoding="utf-8")
        hits = [token for token in _PHASE8_FORBIDDEN_TOKENS if token in text]
        if hits:
            violations[path.name] = hits

    assert not violations, f"Forbidden patterns found in the specialists package: {violations}"
