"""Unit tests for the Phase 6 built-in subtask handlers and handler registry."""

from __future__ import annotations

from app.agent.context_compiler.schemas import CompiledContext
from app.agent.planner.schemas import PlannerSubtask
from app.agent.supervisor.blackboard import SupervisorBlackboard
from app.agent.supervisor.handler_registry import SubtaskHandlerRegistry, build_default_handler_registry
from app.agent.supervisor.handlers import (
    ContextPreviewHandler,
    DryRunCapabilityHandler,
    UnsupportedCapabilityHandler,
)


def _subtask(**overrides) -> PlannerSubtask:
    defaults = dict(
        id="check",
        title="Check something",
        kind="analyze",
        capability_name="graduation_progress_workflow",
        objective="test objective",
    )
    defaults.update(overrides)
    return PlannerSubtask(**defaults)


def _compiled_context(**overrides) -> CompiledContext:
    defaults = dict(
        capability_name="graduation_progress_workflow",
        objective="test",
        context={"user_message": "hi"},
        included_sections=["user_message"],
        omitted_sections=["wiki_snippets"],
        warnings=[],
        estimated_items=1,
    )
    defaults.update(overrides)
    return CompiledContext(**defaults)


def _blackboard() -> SupervisorBlackboard:
    return SupervisorBlackboard(original_user_message="hello")


# ---------------------------------------------------------------------------
# 1. DryRunCapabilityHandler
# ---------------------------------------------------------------------------


async def test_dry_run_capability_handler_returns_completed_result() -> None:
    handler = DryRunCapabilityHandler()
    subtask = _subtask()
    compiled = _compiled_context()

    result = await handler.run(
        subtask=subtask, compiled_context=compiled, blackboard=_blackboard(), dry_run=True
    )

    assert result.status == "completed"
    assert result.subtask_id == "check"
    assert result.capability_name == "graduation_progress_workflow"
    assert result.output_summary["dryRun"] is True
    assert "Phase 7" in result.output_summary["message"]
    assert result.confidence == 1.0


async def test_dry_run_capability_handler_lowers_confidence_when_context_had_warnings() -> None:
    handler = DryRunCapabilityHandler()
    compiled = _compiled_context(warnings=["omitted_forbidden_context: full_catalog"])

    result = await handler.run(
        subtask=_subtask(), compiled_context=compiled, blackboard=_blackboard(), dry_run=True
    )

    assert result.status == "completed"
    assert result.confidence < 1.0
    assert result.warnings == ["omitted_forbidden_context: full_catalog"]


# ---------------------------------------------------------------------------
# 2. ContextPreviewHandler
# ---------------------------------------------------------------------------


async def test_context_preview_handler_includes_context_preview_only() -> None:
    handler = ContextPreviewHandler()
    compiled = _compiled_context(
        included_sections=["user_message", "profile_summary"],
        omitted_sections=["wiki_snippets"],
        estimated_items=3,
    )

    result = await handler.run(
        subtask=_subtask(), compiled_context=compiled, blackboard=_blackboard(), dry_run=True
    )

    assert result.status == "completed"
    assert result.output_summary == {
        "dryRun": True,
        "includedSections": ["user_message", "profile_summary"],
        "omittedSections": ["wiki_snippets"],
        "estimatedItems": 3,
    }
    # No capability-specific "work" performed -- content is context metadata only.
    assert "message" not in result.output_summary


# ---------------------------------------------------------------------------
# 3. UnsupportedCapabilityHandler
# ---------------------------------------------------------------------------


async def test_unsupported_capability_handler_returns_skipped_safely() -> None:
    handler = UnsupportedCapabilityHandler()

    result = await handler.run(
        subtask=_subtask(capability_name="does_not_exist"),
        compiled_context=None,
        blackboard=_blackboard(),
        dry_run=True,
    )

    assert result.status == "skipped"
    assert result.confidence == 0.0
    assert any("unsupported_capability" in warning for warning in result.warnings)


# ---------------------------------------------------------------------------
# 4/5. Handler registry resolution.
# ---------------------------------------------------------------------------


def test_handler_registry_resolves_by_capability_name() -> None:
    custom_handler = ContextPreviewHandler()
    registry = SubtaskHandlerRegistry(default_handler=DryRunCapabilityHandler())
    registry.register_for_capability_name("wiki_hybrid_retrieval", custom_handler)

    resolved = registry.resolve(capability_name="wiki_hybrid_retrieval", capability_type="retrieval")
    assert resolved is custom_handler


def test_handler_registry_resolves_by_capability_type_when_no_name_match() -> None:
    type_handler = ContextPreviewHandler()
    registry = SubtaskHandlerRegistry(default_handler=DryRunCapabilityHandler())
    registry.register_for_capability_type("retrieval", type_handler)

    resolved = registry.resolve(capability_name="some_retrieval_tool", capability_type="retrieval")
    assert resolved is type_handler


def test_handler_registry_falls_back_safely_for_unknown_handler() -> None:
    default_handler = DryRunCapabilityHandler()
    registry = SubtaskHandlerRegistry(default_handler=default_handler)

    resolved = registry.resolve(capability_name="totally_unknown", capability_type=None)
    assert resolved is default_handler


def test_default_handler_registry_routes_retrieval_validator_composer_to_context_preview() -> None:
    registry = build_default_handler_registry()

    for capability_type in ("retrieval", "validator", "composer"):
        handler = registry.resolve(capability_name="anything", capability_type=capability_type)
        assert isinstance(handler, ContextPreviewHandler)


def test_default_handler_registry_uses_dry_run_handler_for_workflow_type() -> None:
    registry = build_default_handler_registry()
    handler = registry.resolve(capability_name="graduation_progress_workflow", capability_type="workflow")
    assert isinstance(handler, DryRunCapabilityHandler)
