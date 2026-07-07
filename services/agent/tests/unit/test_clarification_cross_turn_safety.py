"""Static safety checks for Phase 18 clarification cross-turn code."""

from __future__ import annotations

from pathlib import Path

from app.agent.clarification.safety import scan_clarification_package_for_forbidden_tokens


def test_static_scan_finds_no_forbidden_tokens_in_clarification_package() -> None:
    root = Path(__file__).resolve().parents[2] / "app" / "agent" / "clarification"
    assert scan_clarification_package_for_forbidden_tokens(package_root=root) == []


def test_repository_writes_only_clarification_collection() -> None:
    repo_path = (
        Path(__file__).resolve().parents[2] / "app" / "repositories" / "clarification_state_repository.py"
    )
    text = repo_path.read_text(encoding="utf-8")
    assert "agent_clarification_states" in text
    assert "completed_courses" not in text
    assert "create_agent_action_proposal(" not in text
