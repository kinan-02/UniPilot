"""Unit tests for `app.agent.specialists.safety` and the Phase 10 static safety scan.

Includes the dedicated static source scan for the whole `specialists`
package (no Mongo writes, no proposal creation, no confirm/reject calls, no
direct LLM calls) mirroring the equivalent Phase 6/7/8/9 supervisor scans.
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
from app.agent.specialists.safety import is_specialist_agent_safe, specialist_agent_unsafe_warning


def _capability(**overrides) -> CapabilityDescriptor:
    defaults = dict(
        name="test_specialist",
        type="specialist_agent",
        description="test",
        execution=CapabilityExecutionMetadata(
            execution_supported=True,
            shadow_execution_supported=True,
            handler_name="specialist_agent_handler",
            side_effect_level="none",
            safe_for_shadow_execution=True,
        ),
        permissions=CapabilityPermissionScope(),
    )
    defaults.update(overrides)
    return CapabilityDescriptor(**defaults)


# ---------------------------------------------------------------------------
# 1. Specialist agent must be read-only.
# ---------------------------------------------------------------------------


def test_read_only_specialist_agent_is_safe() -> None:
    assert is_specialist_agent_safe(_capability()) is True


def test_real_default_registry_specialists_are_safe() -> None:
    registry = build_default_capability_registry()
    for name in ("graduation_progress_agent", "course_catalog_agent", "requirement_explanation_agent"):
        assert is_specialist_agent_safe(registry.require(name)) is True, name


def test_real_default_registry_write_or_proposal_specialists_are_unsafe() -> None:
    registry = build_default_capability_registry()
    for name in ("transcript_import_agent", "semester_planning_agent"):
        assert is_specialist_agent_safe(registry.require(name)) is False, name


def test_non_specialist_agent_capability_type_is_unsafe() -> None:
    capability = _capability(type="workflow")
    assert is_specialist_agent_safe(capability) is False


# ---------------------------------------------------------------------------
# 2. dry_run/write-scope-derived checks.
# ---------------------------------------------------------------------------


def test_write_scope_proposal_only_blocks_specialist_safety() -> None:
    capability = _capability(permissions=CapabilityPermissionScope(write_scope="proposal_only"))
    assert is_specialist_agent_safe(capability) is False


def test_can_create_action_proposals_blocks_specialist_safety() -> None:
    capability = _capability(permissions=CapabilityPermissionScope(can_create_action_proposals=True))
    assert is_specialist_agent_safe(capability) is False


def test_can_execute_writes_blocks_specialist_safety() -> None:
    capability = _capability(permissions=CapabilityPermissionScope(can_execute_writes=True))
    assert is_specialist_agent_safe(capability) is False


# ---------------------------------------------------------------------------
# 3. proposed_actions must be empty -- covered by side_effect_level checks.
# ---------------------------------------------------------------------------


@pytest.mark.parametrize("side_effect_level", ["unknown", "proposal", "write"])
def test_non_none_side_effect_level_blocks_specialist_safety(side_effect_level: str) -> None:
    capability = _capability(
        execution=CapabilityExecutionMetadata(
            execution_supported=True,
            shadow_execution_supported=True,
            side_effect_level=side_effect_level,
            safe_for_shadow_execution=True,
        )
    )
    assert is_specialist_agent_safe(capability) is False


def test_default_execution_metadata_is_conservative_and_blocks_specialist_safety() -> None:
    capability = _capability(execution=CapabilityExecutionMetadata())
    assert capability.execution.side_effect_level == "unknown"
    assert is_specialist_agent_safe(capability) is False


def test_disabled_specialist_capability_blocks_safety() -> None:
    capability = _capability(enabled=False)
    assert is_specialist_agent_safe(capability) is False


def test_shadow_execution_not_supported_blocks_specialist_safety() -> None:
    capability = _capability(
        execution=CapabilityExecutionMetadata(
            execution_supported=True,
            shadow_execution_supported=False,
            side_effect_level="none",
            safe_for_shadow_execution=True,
        )
    )
    assert is_specialist_agent_safe(capability) is False


def test_not_safe_for_shadow_execution_blocks_specialist_safety() -> None:
    capability = _capability(
        execution=CapabilityExecutionMetadata(
            execution_supported=True,
            shadow_execution_supported=True,
            side_effect_level="none",
            safe_for_shadow_execution=False,
        )
    )
    assert is_specialist_agent_safe(capability) is False


def test_specialist_agent_unsafe_warning_format() -> None:
    assert specialist_agent_unsafe_warning("foo_agent") == "specialist_agent_not_safe_for_execution: foo_agent"


# ---------------------------------------------------------------------------
# Static safety scan: no Mongo writes, no proposal creation, no
# confirm/reject calls, no direct LLM calls anywhere in the `specialists`
# package.
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
    "OpenAI(",
    "chat.completions",
    "llm.ainvoke",
    "llm.invoke",
    "build_chat_llm(",
)


def test_static_scan_no_writes_proposals_confirm_reject_or_direct_llm_calls() -> None:
    """Recursive (`rglob`) since Phase 12 -- covers `specialists/tools/` too."""
    specialists_dir = Path(__file__).resolve().parents[2] / "app" / "agent" / "specialists"
    assert specialists_dir.is_dir()

    violations: dict[str, list[str]] = {}
    for path in specialists_dir.rglob("*.py"):
        text = path.read_text(encoding="utf-8")
        hits = [token for token in _FORBIDDEN_TOKENS if token in text]
        if hits:
            violations[str(path.relative_to(specialists_dir))] = hits

    assert not violations, (
        "Forbidden write/proposal/confirm-reject/direct-LLM patterns found in "
        f"the specialists package: {violations}"
    )


def test_phase11_validation_compare_diagnostics_files_contain_no_forbidden_patterns() -> None:
    """Extended static scan specifically for the Phase 11 files, matching
    the token list from the Phase 11 spec's own 'Static safety tests'
    section (a superset is already covered by the whole-package scan above,
    but this keeps the exact spec wording independently verifiable)."""
    specialists_dir = Path(__file__).resolve().parents[2] / "app" / "agent" / "specialists"
    phase11_files = ("validation_schemas.py", "validation.py", "compare.py", "diagnostics.py")

    forbidden_tokens = (
        ".insert_one(",
        ".update_one(",
        ".delete_one(",
        "create_agent_action_proposal(",
        "confirm",
        "reject",
        "chat.completions",
        "ChatOpenAI",
        "OpenAI(",
        "llm.invoke",
        "llm.ainvoke",
    )

    violations: dict[str, list[str]] = {}
    for filename in phase11_files:
        path = specialists_dir / filename
        assert path.is_file(), f"expected Phase 11 file missing: {filename}"
        text = path.read_text(encoding="utf-8")
        hits = [token for token in forbidden_tokens if token in text]
        if hits:
            violations[filename] = hits

    assert not violations, f"Forbidden patterns found in Phase 11 files: {violations}"


def test_specialists_package_only_calls_reasoning_block_run() -> None:
    """Specialists may call `ReasoningBlock.run(...)` only -- confirm no file
    references a lower-level LLM adapter method directly."""
    specialists_dir = Path(__file__).resolve().parents[2] / "app" / "agent" / "specialists"
    for path in specialists_dir.glob("*.py"):
        text = path.read_text(encoding="utf-8")
        assert "complete_json(" not in text, f"{path.name} must not call the LLM adapter directly"
        assert ".complete(" not in text, f"{path.name} must not call the LLM adapter directly"
