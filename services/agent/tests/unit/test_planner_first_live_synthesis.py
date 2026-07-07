"""Unit tests for Phase 5 (post-Phase-9) live Synthesis composition/promotion.

Covers `app.agent.planner_first_live.attempt_live_synthesis_promotion`, which
reuses the exact same `run_synthesis_diagnostics`/`evaluate_synthesis_text_promotion`
entry points already wired into the deterministic live path -- this module
adds no new synthesis mechanism, only a new caller for Planner-first-live turns.
"""

from __future__ import annotations

import pytest

from app.agent.planner_first_live import attempt_live_synthesis_promotion
from app.agent.schemas import AgentResponse, ProposedAction, StructuredBlock
from app.config import Settings


def _response(**overrides) -> AgentResponse:
    defaults = dict(
        conversation_id="c1",
        message_id="",
        run_id="r1",
        text="You need 3 more credits to graduate.",
        blocks=[StructuredBlock(type="GraduationStatusBlock", data={"creditsRemaining": 3})],
        warnings=[],
        proposed_actions=[],
        used_sources=["mongodb:completed_courses"],
    )
    defaults.update(overrides)
    return AgentResponse(**defaults)


_PROMOTABLE_SETTINGS_KWARGS = {
    "AGENT_SYNTHESIS_ENABLED": True,
    "AGENT_SYNTHESIS_TEXT_PROMOTION_ENABLED": True,
    "AGENT_SYNTHESIS_TEXT_PROMOTION_MODE": "promote_validated",
    "AGENT_SYNTHESIS_TEXT_PROMOTION_WORKFLOWS": "graduation_progress_workflow",
}


@pytest.mark.asyncio
async def test_synthesis_disabled_by_default_does_nothing() -> None:
    promoted, synthesis_metadata, promotion_metadata = await attempt_live_synthesis_promotion(
        workflow_name="graduation_progress_workflow",
        user_message="What am I missing to graduate?",
        live_response=_response(),
        monitor_metadata=None,
        plan_repair_metadata=None,
        # Explicit, not relied-on-default: an operator's real `.env` may have
        # both of these on (as this repo's own root `.env` does, post-Phase-9).
        settings=Settings(AGENT_SYNTHESIS_ENABLED=False, AGENT_SYNTHESIS_TEXT_PROMOTION_ENABLED=False),
    )
    assert promoted is None
    assert synthesis_metadata is None
    assert promotion_metadata is None


@pytest.mark.asyncio
async def test_synthesis_runs_but_promotion_stays_off_without_its_own_flag() -> None:
    settings = Settings(AGENT_SYNTHESIS_ENABLED=True, AGENT_SYNTHESIS_TEXT_PROMOTION_ENABLED=False)
    promoted, synthesis_metadata, promotion_metadata = await attempt_live_synthesis_promotion(
        workflow_name="graduation_progress_workflow",
        user_message="What am I missing to graduate?",
        live_response=_response(),
        monitor_metadata=None,
        plan_repair_metadata=None,
        settings=settings,
    )
    assert promoted is None
    assert synthesis_metadata is not None
    assert promotion_metadata is None


@pytest.mark.asyncio
async def test_promotes_when_every_gate_passes() -> None:
    settings = Settings(**_PROMOTABLE_SETTINGS_KWARGS)
    response = _response()
    promoted, synthesis_metadata, promotion_metadata = await attempt_live_synthesis_promotion(
        workflow_name="graduation_progress_workflow",
        user_message="What am I missing to graduate?",
        live_response=response,
        monitor_metadata=None,
        plan_repair_metadata=None,
        settings=settings,
    )
    assert promoted is not None
    assert promoted.text == response.text
    assert promoted.blocks == response.blocks
    assert promoted.used_sources == response.used_sources
    assert synthesis_metadata is not None
    assert synthesis_metadata["status"] == "candidate_ready"
    assert promotion_metadata is not None
    assert promotion_metadata["promoted"] is True


@pytest.mark.asyncio
async def test_never_promotes_for_workflow_outside_hard_allowed_set() -> None:
    """general_academic_workflow is not in `promotion_policy`'s hard-allowed
    set -- confirms this caller doesn't bypass that gate either."""
    settings = Settings(
        **{**_PROMOTABLE_SETTINGS_KWARGS, "AGENT_SYNTHESIS_TEXT_PROMOTION_WORKFLOWS": "general_academic_workflow"}
    )
    promoted, _synthesis_metadata, promotion_metadata = await attempt_live_synthesis_promotion(
        workflow_name="general_academic_workflow",
        user_message="test",
        live_response=_response(),
        monitor_metadata=None,
        plan_repair_metadata=None,
        settings=settings,
    )
    assert promoted is None
    assert promotion_metadata is not None
    assert promotion_metadata["promoted"] is False


@pytest.mark.asyncio
async def test_never_promotes_when_live_response_has_proposed_actions() -> None:
    """Automatic for the proposal-capable (write-workflow) Planner-first-live
    path: `evaluate_synthesis_text_promotion` already blocks whenever the
    live response carries a proposed action, with zero extra logic needed
    here."""
    settings = Settings(
        **{**_PROMOTABLE_SETTINGS_KWARGS, "AGENT_SYNTHESIS_TEXT_PROMOTION_WORKFLOWS": "transcript_import_workflow"}
    )
    response = _response(
        proposed_actions=[
            ProposedAction(id="a1", action_type="import_completed_courses", label="Import", title="Import")
        ]
    )
    promoted, _synthesis_metadata, promotion_metadata = await attempt_live_synthesis_promotion(
        workflow_name="transcript_import_workflow",
        user_message="Import my transcript",
        live_response=response,
        monitor_metadata=None,
        plan_repair_metadata=None,
        settings=settings,
    )
    assert promoted is None
    assert promotion_metadata is not None
    assert promotion_metadata["promoted"] is False


@pytest.mark.asyncio
async def test_never_promotes_when_monitor_signals_unsafe() -> None:
    settings = Settings(**_PROMOTABLE_SETTINGS_KWARGS)
    monitor_metadata = {"decision": {"action": "abort_safely"}}
    promoted, _synthesis_metadata, promotion_metadata = await attempt_live_synthesis_promotion(
        workflow_name="graduation_progress_workflow",
        user_message="What am I missing to graduate?",
        live_response=_response(),
        monitor_metadata=monitor_metadata,
        plan_repair_metadata=None,
        settings=settings,
    )
    assert promoted is None
    assert promotion_metadata is not None
    assert promotion_metadata["promoted"] is False


@pytest.mark.asyncio
async def test_only_replaces_text_never_blocks_warnings_or_sources() -> None:
    # Deliberately no `warnings` here -- the deterministic synthesis
    # composer factors uncertainty/warning signals into its confidence
    # score, and this test's job is to verify *field preservation* on
    # promotion, not the confidence formula itself (covered elsewhere).
    settings = Settings(**_PROMOTABLE_SETTINGS_KWARGS)
    response = _response(used_sources=["source_a", "source_b"])
    promoted, _synthesis_metadata, _promotion_metadata = await attempt_live_synthesis_promotion(
        workflow_name="graduation_progress_workflow",
        user_message="What am I missing to graduate?",
        live_response=response,
        monitor_metadata=None,
        plan_repair_metadata=None,
        settings=settings,
    )
    assert promoted is not None
    assert promoted.warnings == response.warnings
    assert promoted.used_sources == response.used_sources
    assert promoted.blocks == response.blocks
    assert promoted.proposed_actions == response.proposed_actions
