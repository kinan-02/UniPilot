"""Unit tests for Phase 4 (post-Phase-9) live repair-and-redispatch.

Covers `app.agent.planner_first_live.attempt_live_plan_repair`,
`_is_repaired_plan_safe_to_redispatch`, and `_repaired_planner_output_for_redispatch`.
"""

from __future__ import annotations

import pytest

from app.agent.planner_first_live import (
    _is_repaired_plan_safe_to_redispatch,
    _repaired_planner_output_for_redispatch,
    attempt_live_plan_repair,
)
from app.agent.planner.repair_schemas import PlanRepairOutput
from app.agent.schemas import AgentResponse, StructuredBlock
from app.config import Settings


def _plan(*, capability_name: str = "graduation_progress_workflow", subtask_id: str = "run_it") -> dict:
    return {
        "status": "completed",
        "plan_id": "plan-live-1",
        "user_goal": "What am I missing to graduate?",
        "execution_mode": "single_capability",
        "recommended_autonomy_level": 3,
        "primary_intent": "graduation_progress_check",
        "subtasks": [
            {
                "id": subtask_id,
                "title": "Run existing deterministic workflow",
                "kind": "analyze",
                "capability_name": capability_name,
                "objective": "test",
                "depends_on": [],
                "required_context_sections": ["user_message"],
            }
        ],
        "decision_summary": "test",
        "confidence": 0.85,
    }


def _monitor_metadata(*, action: str = "request_plan_repair", subtask_id: str = "run_it") -> dict:
    return {
        "decision": {"action": action, "reason": "assumption_violation_detected"},
        "signals": [
            {
                "kind": "assumption_violation",
                "severity": "warning",
                "relatedSubtaskIds": [subtask_id],
            }
        ],
    }


def _response(**overrides) -> AgentResponse:
    defaults = dict(
        conversation_id="c1",
        message_id="",
        run_id="r1",
        text="Updated answer after repair.",
        blocks=[StructuredBlock(type="RequirementSummaryBlock", data={"ok": True})],
        warnings=[],
        proposed_actions=[],
        used_sources=[],
    )
    defaults.update(overrides)
    return AgentResponse(**defaults)


class _FakeWorkflow:
    name = "graduation_progress_workflow"

    def __init__(self, response: AgentResponse) -> None:
        self._response = response

    async def run(self, database, *, context, user_message):
        yield self._response


# ---------------------------------------------------------------------------
# _is_repaired_plan_safe_to_redispatch
# ---------------------------------------------------------------------------


def _repair_output(**overrides) -> PlanRepairOutput:
    defaults = dict(
        status="repaired",
        mode_used="repair",
        plan_id="plan-live-1",
        repaired_plan={
            "plan_id": "plan-live-1",
            "subtasks": [{"id": "run_it", "capability_name": "graduation_progress_workflow", "status": "revised"}],
        },
        preserved_subtask_ids=[],
        revised_subtask_ids=["run_it"],
        added_subtask_ids=[],
        removed_subtask_ids=[],
        decision_summary="test",
        safe_to_use=False,
    )
    defaults.update(overrides)
    return PlanRepairOutput(**defaults)


def test_repair_mode_with_matching_capability_is_safe() -> None:
    output = _repair_output()
    assert _is_repaired_plan_safe_to_redispatch(output, workflow_name="graduation_progress_workflow") is True


def test_regenerate_mode_is_never_safe() -> None:
    output = _repair_output(mode_used="regenerate", repaired_plan={"plan_id": "x", "subtasks": []})
    assert _is_repaired_plan_safe_to_redispatch(output, workflow_name="graduation_progress_workflow") is False


def test_continue_mode_is_never_safe() -> None:
    output = _repair_output(mode_used="continue", repaired_plan=None)
    assert _is_repaired_plan_safe_to_redispatch(output, workflow_name="graduation_progress_workflow") is False


def test_empty_subtasks_is_never_safe() -> None:
    output = _repair_output(repaired_plan={"plan_id": "x", "subtasks": []})
    assert _is_repaired_plan_safe_to_redispatch(output, workflow_name="graduation_progress_workflow") is False


def test_added_subtask_ids_blocks_redispatch() -> None:
    output = _repair_output(added_subtask_ids=["new_one"])
    assert _is_repaired_plan_safe_to_redispatch(output, workflow_name="graduation_progress_workflow") is False


def test_removed_subtask_ids_blocks_redispatch() -> None:
    output = _repair_output(removed_subtask_ids=["run_it"])
    assert _is_repaired_plan_safe_to_redispatch(output, workflow_name="graduation_progress_workflow") is False


def test_mismatched_capability_name_blocks_redispatch() -> None:
    """Defense in depth: even if repair somehow revised a subtask to target
    a different capability, re-dispatch must refuse -- only the exact
    workflow already vetted eligible this turn is ever safe."""
    output = _repair_output(
        repaired_plan={
            "plan_id": "plan-live-1",
            "subtasks": [{"id": "run_it", "capability_name": "semester_planning_workflow", "status": "revised"}],
        }
    )
    assert _is_repaired_plan_safe_to_redispatch(output, workflow_name="graduation_progress_workflow") is False


def test_missing_repaired_plan_blocks_redispatch() -> None:
    output = _repair_output(repaired_plan=None)
    assert _is_repaired_plan_safe_to_redispatch(output, workflow_name="graduation_progress_workflow") is False


def test_safe_to_use_field_is_irrelevant() -> None:
    """The permanently-`False` `safe_to_use` field must never gate this --
    the function must return `True` here despite `safe_to_use=False`."""
    output = _repair_output(safe_to_use=False)
    assert output.safe_to_use is False
    assert _is_repaired_plan_safe_to_redispatch(output, workflow_name="graduation_progress_workflow") is True


# ---------------------------------------------------------------------------
# _repaired_planner_output_for_redispatch
# ---------------------------------------------------------------------------


def test_merge_fills_in_missing_required_fields() -> None:
    original = _plan()
    repaired_plan = {
        "plan_id": "plan-live-1",
        "execution_mode": "diagnostic_repair",
        "subtasks": [
            {
                "id": "run_it",
                "title": "Run existing deterministic workflow",
                "kind": "analyze",
                "capability_name": "graduation_progress_workflow",
                "objective": "test",
                "status": "revised",
            }
        ],
    }
    merged = _repaired_planner_output_for_redispatch(repaired_plan, original_planner_output=original)
    assert merged["status"] == "completed"
    assert merged["recommended_autonomy_level"] == original["recommended_autonomy_level"]
    assert merged["primary_intent"] == original["primary_intent"]
    assert merged["subtasks"] == repaired_plan["subtasks"]
    # `deterministic_plan_repair`'s "diagnostic_repair" sentinel is not a
    # valid `PlannerOutput.execution_mode` -- must be replaced, not passed through.
    assert merged["execution_mode"] == original["execution_mode"]

    from app.agent.planner.schemas import PlannerOutput

    PlannerOutput.model_validate(merged)


# ---------------------------------------------------------------------------
# attempt_live_plan_repair
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_repair_disabled_by_default_returns_none() -> None:
    candidate, metadata = await attempt_live_plan_repair(
        database=object(),
        agent_context_pack=object(),
        user_message="What am I missing to graduate?",
        user_id="u1",
        conversation_id="c1",
        run_id="r1",
        workflow_name="graduation_progress_workflow",
        planner_output=_plan(),
        monitor_metadata=_monitor_metadata(),
        # Explicit, not relied-on-default: an operator's real `.env` may have
        # this on (as this repo's own root `.env` does, post-Phase-9).
        settings=Settings(AGENT_PLANNER_FIRST_LIVE_REPAIR_ENABLED=False),
    )
    assert candidate is None
    assert metadata is None


@pytest.mark.asyncio
async def test_repair_not_attempted_when_monitor_decision_is_continue() -> None:
    settings = Settings(
        **{
            "AGENT_PLANNER_FIRST_LIVE_REPAIR_ENABLED": True,
            "AGENT_PLAN_REPAIR_ENABLED": True,
        }
    )
    candidate, metadata = await attempt_live_plan_repair(
        database=object(),
        agent_context_pack=object(),
        user_message="What am I missing to graduate?",
        user_id="u1",
        conversation_id="c1",
        run_id="r1",
        workflow_name="graduation_progress_workflow",
        planner_output=_plan(),
        monitor_metadata=_monitor_metadata(action="continue"),
        settings=settings,
    )
    assert candidate is None
    assert metadata is None


@pytest.mark.asyncio
async def test_repair_and_redispatch_succeeds_when_every_gate_passes() -> None:
    settings = Settings(
        **{
            "AGENT_PLANNER_FIRST_LIVE_REPAIR_ENABLED": True,
            "AGENT_PLAN_REPAIR_ENABLED": True,
            "AGENT_PLAN_REPAIR_USE_LLM": False,
            "AGENT_SUPERVISOR_REAL_HANDLERS_ENABLED": True,
        }
    )
    response = _response()
    candidate, metadata = await attempt_live_plan_repair(
        database=object(),
        agent_context_pack=object(),
        user_message="What am I missing to graduate?",
        user_id="u1",
        conversation_id="c1",
        run_id="r1",
        workflow_name="graduation_progress_workflow",
        planner_output=_plan(),
        monitor_metadata=_monitor_metadata(),
        settings=settings,
        workflow_lookup=lambda name: _FakeWorkflow(response),
    )
    assert candidate is response
    assert metadata is not None
    assert metadata["modeUsed"] == "repair"


@pytest.mark.asyncio
async def test_repair_metadata_still_returned_when_redispatch_not_attempted(monkeypatch) -> None:
    """`plan_repair_metadata` should still be populated for diagnostics even
    when the repair mode itself doesn't qualify for live re-dispatch."""
    import app.agent.planner.repair_diagnostics as repair_diagnostics_module

    monkeypatch.setattr(repair_diagnostics_module, "choose_repair_mode", lambda request: "clarify_first")

    settings = Settings(
        **{
            "AGENT_PLANNER_FIRST_LIVE_REPAIR_ENABLED": True,
            "AGENT_PLAN_REPAIR_ENABLED": True,
        }
    )
    candidate, metadata = await attempt_live_plan_repair(
        database=object(),
        agent_context_pack=object(),
        user_message="What am I missing to graduate?",
        user_id="u1",
        conversation_id="c1",
        run_id="r1",
        workflow_name="graduation_progress_workflow",
        planner_output=_plan(),
        monitor_metadata=_monitor_metadata(),
        settings=settings,
    )
    assert candidate is None
    assert metadata is not None
