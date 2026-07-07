"""Unit tests for `app.agent.specialists.registry`."""

from __future__ import annotations

import pytest

from app.agent.specialists.registry import (
    SpecialistAgentNotFoundError,
    SpecialistAgentRegistry,
    build_default_specialist_agent_registry,
)


# ---------------------------------------------------------------------------
# 1. Default registry contains exactly the 3 read-only specialists.
# ---------------------------------------------------------------------------


def test_default_registry_contains_exactly_three_read_only_specialists() -> None:
    registry = build_default_specialist_agent_registry()

    assert registry.list_agents() == [
        "course_catalog_agent",
        "graduation_progress_agent",
        "requirement_explanation_agent",
    ]


def test_default_registry_excludes_write_or_proposal_agents() -> None:
    registry = build_default_specialist_agent_registry()

    for name in ("transcript_import_agent", "semester_planning_agent", "action_proposal_agent", "profile_update_agent"):
        assert not registry.has(name)


# ---------------------------------------------------------------------------
# 2. require() works.
# ---------------------------------------------------------------------------


def test_require_returns_registered_agent_function() -> None:
    registry = build_default_specialist_agent_registry()

    fn = registry.require("graduation_progress_agent")

    assert callable(fn)
    assert fn is registry.get("graduation_progress_agent")


# ---------------------------------------------------------------------------
# 3. Unknown specialist raises a clear error.
# ---------------------------------------------------------------------------


def test_require_unknown_agent_raises_clear_error() -> None:
    registry = build_default_specialist_agent_registry()

    with pytest.raises(SpecialistAgentNotFoundError):
        registry.require("not_a_real_agent")


def test_get_unknown_agent_returns_none() -> None:
    registry = build_default_specialist_agent_registry()

    assert registry.get("not_a_real_agent") is None


# ---------------------------------------------------------------------------
# 4. list_agents() is deterministic (sorted).
# ---------------------------------------------------------------------------


def test_list_agents_is_deterministically_sorted() -> None:
    registry = build_default_specialist_agent_registry()

    assert registry.list_agents() == sorted(registry.list_agents())


# ---------------------------------------------------------------------------
# Extra registry behavior.
# ---------------------------------------------------------------------------


def test_registering_duplicate_agent_name_raises_without_overwrite() -> None:
    registry = SpecialistAgentRegistry()

    async def _fake_agent(*_args, **_kwargs):
        return None

    registry.register("fake_agent", _fake_agent)
    with pytest.raises(ValueError):
        registry.register("fake_agent", _fake_agent)


def test_registering_duplicate_agent_name_with_overwrite_succeeds() -> None:
    registry = SpecialistAgentRegistry()

    async def _fake_agent_a(*_args, **_kwargs):
        return "a"

    async def _fake_agent_b(*_args, **_kwargs):
        return "b"

    registry.register("fake_agent", _fake_agent_a)
    registry.register("fake_agent", _fake_agent_b, overwrite=True)

    assert registry.get("fake_agent") is _fake_agent_b


def test_has_returns_true_only_for_registered_agents() -> None:
    registry = build_default_specialist_agent_registry()

    assert registry.has("graduation_progress_agent") is True
    assert registry.has("nonexistent_agent") is False
