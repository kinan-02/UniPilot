"""Unit tests for planner repair safety (Phase 19)."""

from __future__ import annotations

from pathlib import Path

from app.agent.planner.repair_safety import scan_planner_repair_package_for_forbidden_tokens


def test_static_scan_finds_no_forbidden_tokens() -> None:
    root = Path(__file__).resolve().parents[2] / "app" / "agent" / "planner"
    assert scan_planner_repair_package_for_forbidden_tokens(package_root=root) == []
