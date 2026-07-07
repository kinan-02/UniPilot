"""Unit tests for planner dynamic spec safety (Phase 20)."""

from __future__ import annotations

from pathlib import Path

from app.agent.planner.dynamic_spec_safety import scan_planner_dynamic_spec_package_for_forbidden_tokens


def test_static_scan_finds_no_forbidden_tokens() -> None:
    root = Path(__file__).resolve().parents[2] / "app" / "agent" / "planner"
    assert scan_planner_dynamic_spec_package_for_forbidden_tokens(package_root=root) == []
