"""Unit tests for `app.agent_core.orchestrator.monitor` (docs/agent/AGENT_VISION.md §9)."""

from __future__ import annotations

from datetime import datetime, timezone

from app.agent_core.orchestrator.monitor import evaluate_step_result
from app.agent_core.planning.schemas import PlanStep
from app.agent_core.planning.state import CertaintyTag, StateEntry


def _step(**overrides) -> PlanStep:
    defaults = dict(step_id="s1", title="t", objective="o", role="retrieval")
    defaults.update(overrides)
    return PlanStep(**defaults)


def _entry(status: str) -> StateEntry:
    return StateEntry(
        entry_id="s1-0",
        step_id="s1",
        role="retrieval",
        status=status,
        output_schema_name="generic_step_output_v1",
        data={},
        certainty=CertaintyTag(basis="wiki_derived", confidence=0.9),
        produced_at=datetime.now(timezone.utc),
    )


def test_failed_status_triggers_replan():
    assert evaluate_step_result(_step(), _entry("failed")) == "replan"


def test_partial_status_triggers_clarify():
    assert evaluate_step_result(_step(), _entry("partial")) == "clarify"


def test_succeeded_status_continues():
    assert evaluate_step_result(_step(), _entry("succeeded")) == "continue"
