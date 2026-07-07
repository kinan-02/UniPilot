"""Unit tests for monitoring package safety (Phase 16)."""

from __future__ import annotations

from pathlib import Path

from app.agent.monitoring.monitor import monitor_plan_execution
from app.agent.monitoring.schemas import MonitorInput
from app.agent.monitoring.safety import scan_monitoring_package_for_forbidden_tokens


def test_static_scan_finds_no_forbidden_tokens() -> None:
    root = Path(__file__).resolve().parents[2] / "app" / "agent" / "monitoring"
    assert scan_monitoring_package_for_forbidden_tokens(package_root=root) == []


def test_monitor_never_calls_llm_or_reasoning_block() -> None:
    root = Path(__file__).resolve().parents[2] / "app" / "agent" / "monitoring"
    text = "\n".join(path.read_text(encoding="utf-8") for path in root.rglob("*.py") if path.name != "safety.py")
    assert "ReasoningBlock" not in text
    assert "build_chat_llm(" not in text


def test_monitor_disabled_is_safe_noop() -> None:
    output = monitor_plan_execution(MonitorInput(), enabled=False)
    assert output.status == "skipped"
    assert output.decision.action == "continue"
