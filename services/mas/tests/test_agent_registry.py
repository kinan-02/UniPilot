"""Unit tests for MAS agent registry."""

from __future__ import annotations

from app.agents.registry import AgentRegistry, get_default_registry


def test_default_registry_exposes_mas_15_agents() -> None:
    registry = get_default_registry()

    assert registry.goal_analyst.role == "goal_analyst"
    assert registry.planner.role == "planner"
    assert registry.catalog_scout.role == "catalog_scout"
    assert registry.risk_sentinel.role == "risk_sentinel"
    assert registry.progress_scout.role == "progress_scout"
    assert registry.student_advocate.role == "student_advocate"
    assert registry.arbiter.role == "arbiter"
    assert registry.explainer.role == "explainer"
    assert registry.red_team.role == "red_team"
    assert len(registry.hard_critics()) == 2
    assert len(registry.soft_advocates()) == 2
    assert len(registry.critics()) == 4
    assert len(registry.all_agents()) == 9


def test_custom_registry_can_be_injected() -> None:
    custom = AgentRegistry()
    assert custom.all_agents()[0].role == "goal_analyst"
