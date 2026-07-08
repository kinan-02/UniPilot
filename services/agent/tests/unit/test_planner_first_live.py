"""Unit tests for Controlled Planner-first live execution (post-Phase-9)."""

from __future__ import annotations

import json
from pathlib import Path

import pytest

from app.agent.planner_first_live import (
    eligible_planner_first_live_proposal_workflows,
    eligible_planner_first_live_specialist_agents,
    eligible_planner_first_live_workflows,
    is_capability_planner_first_live_eligible,
    is_capability_planner_first_live_proposal_eligible,
    is_specialist_planner_first_live_eligible,
    run_planner_first_live_turn,
)
from app.agent.schemas import AgentResponse, ProposedAction, StructuredBlock
from app.agent.specialists.registry import SpecialistAgentRegistry
from app.agent.specialists.schemas import SpecialistAgentOutput
from app.config import Settings


def _plan(*, capability_name: str = "graduation_progress_workflow") -> dict:
    return {
        "status": "completed",
        "plan_id": "plan-live-1",
        "user_goal": "test",
        "execution_mode": "single_capability",
        "recommended_autonomy_level": 3,
        "primary_intent": "graduation_progress_check",
        "subtasks": [
            {
                "id": "run_it",
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


def _response(**overrides) -> AgentResponse:
    defaults = dict(
        conversation_id="c1",
        message_id="",
        run_id="r1",
        text="You need 3 credits.",
        blocks=[StructuredBlock(type="RequirementSummaryBlock", data={"ok": True})],
        warnings=[],
        proposed_actions=[],
        used_sources=["mongodb:completed_courses"],
    )
    defaults.update(overrides)
    return AgentResponse(**defaults)


class _FakeReadOnlyWorkflow:
    name = "graduation_progress_workflow"

    def __init__(self, response: AgentResponse) -> None:
        self._response = response

    async def run(self, database, *, context, user_message):
        yield self._response


class _FailingSubtaskWorkflow:
    name = "graduation_progress_workflow"

    async def run(self, database, *, context, user_message):
        raise RuntimeError("boom")
        yield  # pragma: no cover - unreachable, keeps this an async generator


# ---------------------------------------------------------------------------
# Eligibility gating.
# ---------------------------------------------------------------------------


def test_default_settings_never_eligible() -> None:
    # Explicit, not relied-on-default: an operator's real `.env` may have
    # Planner-first-live turned on (as this repo's own root `.env` does,
    # post-Phase-9) -- this test's actual intent is "when the flag is off,
    # eligibility is empty," which an explicit override proves regardless.
    settings = Settings(AGENT_PLANNER_FIRST_LIVE_ENABLED=False, AGENT_PLANNER_FIRST_LIVE_WORKFLOWS="")
    assert eligible_planner_first_live_workflows(settings) == frozenset()
    assert is_capability_planner_first_live_eligible("graduation_progress_workflow", settings=settings) is False


def test_flag_off_is_not_eligible_even_if_configured() -> None:
    settings = Settings(
        **{
            "AGENT_PLANNER_FIRST_LIVE_ENABLED": False,
            "AGENT_PLANNER_FIRST_LIVE_WORKFLOWS": "graduation_progress_workflow",
            "AGENT_RUNTIME_READINESS_GATE_ENABLED": True,
            "AGENT_SUPERVISOR_REAL_HANDLERS_ENABLED": True,
        }
    )
    assert is_capability_planner_first_live_eligible("graduation_progress_workflow", settings=settings) is False


def test_workflow_outside_hard_allowed_set_is_never_eligible() -> None:
    settings = Settings(
        **{
            "AGENT_PLANNER_FIRST_LIVE_ENABLED": True,
            "AGENT_PLANNER_FIRST_LIVE_WORKFLOWS": "semester_planning_workflow",
            "AGENT_RUNTIME_READINESS_GATE_ENABLED": True,
            "AGENT_SUPERVISOR_REAL_HANDLERS_ENABLED": True,
        }
    )
    assert is_capability_planner_first_live_eligible("semester_planning_workflow", settings=settings) is False


def test_readiness_gate_disabled_fails_closed_unlike_promotion() -> None:
    """Unlike `supervisor.promotion`, this never bypasses to `allowed=True`
    just because the gate is off -- the blast radius here is much larger."""
    settings = Settings(
        **{
            "AGENT_PLANNER_FIRST_LIVE_ENABLED": True,
            "AGENT_PLANNER_FIRST_LIVE_WORKFLOWS": "graduation_progress_workflow",
            "AGENT_RUNTIME_READINESS_GATE_ENABLED": False,
            "AGENT_SUPERVISOR_REAL_HANDLERS_ENABLED": True,
        }
    )
    assert is_capability_planner_first_live_eligible("graduation_progress_workflow", settings=settings) is False


def _manifest_path(tmp_path: Path, *, level: str = "ready_for_broader_promotion") -> str:
    manifest = {
        "schemaVersion": "1",
        "reviewedAt": "2026-07-06T00:00:00Z",
        "reviewedBy": "human",
        "candidates": [
            {
                "candidateId": "planner_first_live.graduation_progress_workflow",
                "level": level,
                "approved": True,
                "scope": ["graduation_progress_workflow"],
                "expiresAt": "2099-01-01T00:00:00Z",
            }
        ],
    }
    path = tmp_path / "manifest.json"
    path.write_text(json.dumps(manifest), encoding="utf-8")
    return str(path)


def test_approved_manifest_at_top_rung_is_eligible(tmp_path: Path) -> None:
    settings = Settings(
        **{
            "AGENT_PLANNER_FIRST_LIVE_ENABLED": True,
            "AGENT_PLANNER_FIRST_LIVE_WORKFLOWS": "graduation_progress_workflow",
            "AGENT_RUNTIME_READINESS_GATE_ENABLED": True,
            "AGENT_RUNTIME_READINESS_MANIFEST_PATH": _manifest_path(tmp_path),
            "AGENT_SUPERVISOR_REAL_HANDLERS_ENABLED": True,
        }
    )
    assert is_capability_planner_first_live_eligible("graduation_progress_workflow", settings=settings) is True


def test_manifest_approved_only_at_lower_rung_is_not_eligible(tmp_path: Path) -> None:
    """Requires `ready_for_broader_promotion` specifically -- the top rung,
    stricter than whatever `AGENT_RUNTIME_READINESS_MIN_LEVEL` says for
    other, lower-stakes candidate types."""
    settings = Settings(
        **{
            "AGENT_PLANNER_FIRST_LIVE_ENABLED": True,
            "AGENT_PLANNER_FIRST_LIVE_WORKFLOWS": "graduation_progress_workflow",
            "AGENT_RUNTIME_READINESS_GATE_ENABLED": True,
            "AGENT_RUNTIME_READINESS_MANIFEST_PATH": _manifest_path(tmp_path, level="ready_for_limited_promotion"),
            "AGENT_SUPERVISOR_REAL_HANDLERS_ENABLED": True,
        }
    )
    assert is_capability_planner_first_live_eligible("graduation_progress_workflow", settings=settings) is False


def test_no_manifest_file_fails_closed(tmp_path: Path) -> None:
    settings = Settings(
        **{
            "AGENT_PLANNER_FIRST_LIVE_ENABLED": True,
            "AGENT_PLANNER_FIRST_LIVE_WORKFLOWS": "graduation_progress_workflow",
            "AGENT_RUNTIME_READINESS_GATE_ENABLED": True,
            "AGENT_RUNTIME_READINESS_MANIFEST_PATH": str(tmp_path / "does_not_exist.json"),
            "AGENT_SUPERVISOR_REAL_HANDLERS_ENABLED": True,
        }
    )
    assert is_capability_planner_first_live_eligible("graduation_progress_workflow", settings=settings) is False


# ---------------------------------------------------------------------------
# Proposal-capable eligibility -- independent flag/allowlist/candidate-id
# from the read-only case above.
# ---------------------------------------------------------------------------


def test_proposal_eligibility_default_settings_never_eligible() -> None:
    # Explicit, not relied-on-default -- see test_default_settings_never_eligible above.
    settings = Settings(
        AGENT_PLANNER_FIRST_LIVE_PROPOSAL_ENABLED=False, AGENT_PLANNER_FIRST_LIVE_PROPOSAL_WORKFLOWS=""
    )
    assert eligible_planner_first_live_proposal_workflows(settings) == frozenset()
    assert is_capability_planner_first_live_proposal_eligible("transcript_import_workflow", settings=settings) is False


def test_read_only_flag_does_not_enable_proposal_eligibility() -> None:
    """Enabling read-only Planner-first-live must never silently also opt a
    deployment into proposal-creating execution."""
    settings = Settings(
        **{
            "AGENT_PLANNER_FIRST_LIVE_ENABLED": True,
            "AGENT_PLANNER_FIRST_LIVE_WORKFLOWS": "graduation_progress_workflow",
            "AGENT_SUPERVISOR_REAL_HANDLERS_ENABLED": True,
            "AGENT_RUNTIME_READINESS_GATE_ENABLED": True,
            # Explicit: proves the read-only flag above doesn't cross-contaminate
            # into proposal eligibility -- an operator's real `.env` may have
            # its own, independent proposal flag on (as this repo's does,
            # post-Phase-9), which would make this assertion pass for the
            # wrong reason (or fail) if left ambient.
            "AGENT_PLANNER_FIRST_LIVE_PROPOSAL_ENABLED": False,
        }
    )
    assert is_capability_planner_first_live_proposal_eligible("transcript_import_workflow", settings=settings) is False


def test_proposal_workflow_outside_hard_allowed_set_is_never_eligible() -> None:
    settings = Settings(
        **{
            "AGENT_PLANNER_FIRST_LIVE_PROPOSAL_ENABLED": True,
            "AGENT_PLANNER_FIRST_LIVE_PROPOSAL_WORKFLOWS": "graduation_progress_workflow",
            "AGENT_SUPERVISOR_REAL_HANDLERS_ENABLED": True,
            "AGENT_RUNTIME_READINESS_GATE_ENABLED": True,
        }
    )
    assert is_capability_planner_first_live_proposal_eligible("graduation_progress_workflow", settings=settings) is False


def test_proposal_readiness_gate_disabled_fails_closed() -> None:
    settings = Settings(
        **{
            "AGENT_PLANNER_FIRST_LIVE_PROPOSAL_ENABLED": True,
            "AGENT_PLANNER_FIRST_LIVE_PROPOSAL_WORKFLOWS": "transcript_import_workflow",
            "AGENT_SUPERVISOR_REAL_HANDLERS_ENABLED": True,
            "AGENT_RUNTIME_READINESS_GATE_ENABLED": False,
        }
    )
    assert is_capability_planner_first_live_proposal_eligible("transcript_import_workflow", settings=settings) is False


def _proposal_manifest_path(tmp_path: Path, *, level: str = "ready_for_broader_promotion") -> str:
    manifest = {
        "schemaVersion": "1",
        "reviewedAt": "2026-07-06T00:00:00Z",
        "reviewedBy": "human",
        "candidates": [
            {
                "candidateId": "planner_first_live_proposal.transcript_import_workflow",
                "level": level,
                "approved": True,
                "scope": ["transcript_import_workflow"],
                "expiresAt": "2099-01-01T00:00:00Z",
            }
        ],
    }
    path = tmp_path / "proposal_manifest.json"
    path.write_text(json.dumps(manifest), encoding="utf-8")
    return str(path)


def test_proposal_approved_manifest_at_top_rung_is_eligible(tmp_path: Path) -> None:
    settings = Settings(
        **{
            "AGENT_PLANNER_FIRST_LIVE_PROPOSAL_ENABLED": True,
            "AGENT_PLANNER_FIRST_LIVE_PROPOSAL_WORKFLOWS": "transcript_import_workflow",
            "AGENT_SUPERVISOR_REAL_HANDLERS_ENABLED": True,
            "AGENT_RUNTIME_READINESS_GATE_ENABLED": True,
            "AGENT_RUNTIME_READINESS_MANIFEST_PATH": _proposal_manifest_path(tmp_path),
        }
    )
    assert is_capability_planner_first_live_proposal_eligible("transcript_import_workflow", settings=settings) is True


def test_proposal_manifest_approved_only_at_lower_rung_is_not_eligible(tmp_path: Path) -> None:
    settings = Settings(
        **{
            "AGENT_PLANNER_FIRST_LIVE_PROPOSAL_ENABLED": True,
            "AGENT_PLANNER_FIRST_LIVE_PROPOSAL_WORKFLOWS": "transcript_import_workflow",
            "AGENT_SUPERVISOR_REAL_HANDLERS_ENABLED": True,
            "AGENT_RUNTIME_READINESS_GATE_ENABLED": True,
            "AGENT_RUNTIME_READINESS_MANIFEST_PATH": _proposal_manifest_path(
                tmp_path, level="ready_for_limited_promotion"
            ),
        }
    )
    assert is_capability_planner_first_live_proposal_eligible("transcript_import_workflow", settings=settings) is False


# ---------------------------------------------------------------------------
# Layer 3 -- specialist-agent eligibility -- independent flag/allowlist/
# candidate-id from both workflow cases above.
# ---------------------------------------------------------------------------


def test_specialist_eligibility_default_settings_never_eligible() -> None:
    settings = Settings(
        AGENT_PLANNER_FIRST_LIVE_SPECIALIST_AGENTS_ENABLED=False, AGENT_PLANNER_FIRST_LIVE_SPECIALIST_AGENTS=""
    )
    assert eligible_planner_first_live_specialist_agents(settings) == frozenset()
    assert is_specialist_planner_first_live_eligible("graduation_progress_agent", settings=settings) is False


def test_specialist_eligibility_flag_off_even_if_configured() -> None:
    settings = Settings(
        **{
            "AGENT_PLANNER_FIRST_LIVE_SPECIALIST_AGENTS_ENABLED": False,
            "AGENT_PLANNER_FIRST_LIVE_SPECIALIST_AGENTS": "graduation_progress_agent",
            "AGENT_RUNTIME_READINESS_GATE_ENABLED": True,
            "AGENT_SUPERVISOR_REAL_HANDLERS_ENABLED": True,
        }
    )
    assert is_specialist_planner_first_live_eligible("graduation_progress_agent", settings=settings) is False


def test_specialist_outside_hard_allowed_set_is_never_eligible() -> None:
    """Only `graduation_progress_agent` is in the hard ceiling -- the other
    two specialists never populate `answer_text` today (see module
    docstring), and configuring one wider can never widen the ceiling."""
    settings = Settings(
        **{
            "AGENT_PLANNER_FIRST_LIVE_SPECIALIST_AGENTS_ENABLED": True,
            "AGENT_PLANNER_FIRST_LIVE_SPECIALIST_AGENTS": "course_catalog_agent",
            "AGENT_RUNTIME_READINESS_GATE_ENABLED": True,
            "AGENT_SUPERVISOR_REAL_HANDLERS_ENABLED": True,
        }
    )
    assert is_specialist_planner_first_live_eligible("course_catalog_agent", settings=settings) is False


def test_specialist_readiness_gate_disabled_fails_closed() -> None:
    settings = Settings(
        **{
            "AGENT_PLANNER_FIRST_LIVE_SPECIALIST_AGENTS_ENABLED": True,
            "AGENT_PLANNER_FIRST_LIVE_SPECIALIST_AGENTS": "graduation_progress_agent",
            "AGENT_RUNTIME_READINESS_GATE_ENABLED": False,
            "AGENT_SUPERVISOR_REAL_HANDLERS_ENABLED": True,
        }
    )
    assert is_specialist_planner_first_live_eligible("graduation_progress_agent", settings=settings) is False


def _specialist_manifest_path(tmp_path: Path, *, level: str = "ready_for_broader_promotion") -> str:
    manifest = {
        "schemaVersion": "1",
        "reviewedAt": "2026-07-06T00:00:00Z",
        "reviewedBy": "human",
        "candidates": [
            {
                "candidateId": "planner_first_live_specialist.graduation_progress_agent",
                "level": level,
                "approved": True,
                "scope": ["graduation_progress_agent"],
                "expiresAt": "2099-01-01T00:00:00Z",
            }
        ],
    }
    path = tmp_path / "specialist_manifest.json"
    path.write_text(json.dumps(manifest), encoding="utf-8")
    return str(path)


def test_specialist_approved_manifest_at_top_rung_is_eligible(tmp_path: Path) -> None:
    settings = Settings(
        **{
            "AGENT_PLANNER_FIRST_LIVE_SPECIALIST_AGENTS_ENABLED": True,
            "AGENT_PLANNER_FIRST_LIVE_SPECIALIST_AGENTS": "graduation_progress_agent",
            "AGENT_RUNTIME_READINESS_GATE_ENABLED": True,
            "AGENT_RUNTIME_READINESS_MANIFEST_PATH": _specialist_manifest_path(tmp_path),
            "AGENT_SUPERVISOR_REAL_HANDLERS_ENABLED": True,
        }
    )
    assert is_specialist_planner_first_live_eligible("graduation_progress_agent", settings=settings) is True


def test_specialist_manifest_approved_only_at_lower_rung_is_not_eligible(tmp_path: Path) -> None:
    settings = Settings(
        **{
            "AGENT_PLANNER_FIRST_LIVE_SPECIALIST_AGENTS_ENABLED": True,
            "AGENT_PLANNER_FIRST_LIVE_SPECIALIST_AGENTS": "graduation_progress_agent",
            "AGENT_RUNTIME_READINESS_GATE_ENABLED": True,
            "AGENT_RUNTIME_READINESS_MANIFEST_PATH": _specialist_manifest_path(
                tmp_path, level="ready_for_limited_promotion"
            ),
            "AGENT_SUPERVISOR_REAL_HANDLERS_ENABLED": True,
        }
    )
    assert is_specialist_planner_first_live_eligible("graduation_progress_agent", settings=settings) is False


# ---------------------------------------------------------------------------
# run_planner_first_live_turn execution.
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_run_returns_candidate_on_clean_completion() -> None:
    response = _response()
    candidate, run_output = await run_planner_first_live_turn(
        database=object(),
        agent_context_pack=object(),
        user_message="What am I missing to graduate?",
        user_id="u1",
        conversation_id="c1",
        run_id="r1",
        workflow_name="graduation_progress_workflow",
        planner_output=_plan(),
        settings=Settings(AGENT_SUPERVISOR_REAL_HANDLERS_ENABLED=True),
        workflow_lookup=lambda name: _FakeReadOnlyWorkflow(response),
    )
    assert candidate is response
    assert run_output is not None
    assert run_output.status in {"completed", "completed_with_warnings"}


@pytest.mark.asyncio
async def test_run_falls_back_to_none_when_subtask_fails() -> None:
    candidate, run_output = await run_planner_first_live_turn(
        database=object(),
        agent_context_pack=object(),
        user_message="What am I missing to graduate?",
        user_id="u1",
        conversation_id="c1",
        run_id="r1",
        workflow_name="graduation_progress_workflow",
        planner_output=_plan(),
        settings=Settings(AGENT_SUPERVISOR_REAL_HANDLERS_ENABLED=True),
        workflow_lookup=lambda name: _FailingSubtaskWorkflow(),
    )
    assert candidate is None
    assert run_output is not None
    assert run_output.failed_subtasks


@pytest.mark.asyncio
async def test_run_falls_back_to_none_when_candidate_has_proposed_actions() -> None:
    response = _response(
        proposed_actions=[ProposedAction(id="a1", action_type="save_semester_plan", label="Save", title="Save")]
    )
    candidate, run_output = await run_planner_first_live_turn(
        database=object(),
        agent_context_pack=object(),
        user_message="What am I missing to graduate?",
        user_id="u1",
        conversation_id="c1",
        run_id="r1",
        workflow_name="graduation_progress_workflow",
        planner_output=_plan(),
        settings=Settings(AGENT_SUPERVISOR_REAL_HANDLERS_ENABLED=True),
        workflow_lookup=lambda name: _FakeReadOnlyWorkflow(response),
    )
    assert candidate is None
    # The defense-in-depth "unexpected proposed actions" check inside the
    # adapter itself already turns this into a failed subtask.
    assert run_output is not None


@pytest.mark.asyncio
async def test_run_falls_back_to_none_when_missing_runtime_context() -> None:
    """`database`/`agent_context_pack` missing -- `_select_handler` falls back
    to the safe dry-run stand-in (with a warning), which never populates the
    candidate sink, so no candidate is ever produced."""
    candidate, run_output = await run_planner_first_live_turn(
        database=None,
        agent_context_pack=None,
        user_message="What am I missing to graduate?",
        user_id="u1",
        conversation_id="c1",
        run_id="r1",
        workflow_name="graduation_progress_workflow",
        planner_output=_plan(),
        settings=Settings(AGENT_SUPERVISOR_REAL_HANDLERS_ENABLED=True),
        workflow_lookup=lambda name: _FakeReadOnlyWorkflow(_response()),
    )
    assert candidate is None
    assert run_output is not None
    assert not run_output.failed_subtasks
    assert not run_output.skipped_subtasks


@pytest.mark.asyncio
async def test_run_falls_back_to_none_when_no_workflow_found() -> None:
    candidate, run_output = await run_planner_first_live_turn(
        database=object(),
        agent_context_pack=object(),
        user_message="test",
        user_id="u1",
        conversation_id="c1",
        run_id="r1",
        workflow_name="graduation_progress_workflow",
        planner_output=_plan(),
        settings=Settings(AGENT_SUPERVISOR_REAL_HANDLERS_ENABLED=True),
        workflow_lookup=lambda name: None,
    )
    assert candidate is None
    assert run_output is not None
    assert run_output.skipped_subtasks


# ---------------------------------------------------------------------------
# run_planner_first_live_turn: allow_single_proposed_action (post-Phase-9).
# ---------------------------------------------------------------------------


def _proposal_response(**overrides) -> AgentResponse:
    defaults = dict(
        conversation_id="c1",
        message_id="",
        run_id="r1",
        text="Here is a draft transcript import for you to review.",
        blocks=[StructuredBlock(type="TranscriptImportBlock", data={"ok": True})],
        warnings=[],
        proposed_actions=[
            ProposedAction(
                id="a1", action_type="import_completed_courses", label="Import", title="Import transcript"
            )
        ],
        used_sources=[],
    )
    defaults.update(overrides)
    return AgentResponse(**defaults)


@pytest.mark.asyncio
async def test_run_rejects_proposed_action_when_not_opted_in() -> None:
    """Default `allow_single_proposed_action=False` forces `transcript_import_workflow`
    out of consideration entirely (it is never read-only-eligible, and proposal
    eligibility is force-disabled by `allow_single_proposed_action=False`
    regardless of ambient readiness-manifest state) -- Layer 2's plan-level
    eligibility computation short-circuits before ever attempting dispatch,
    so unlike the pre-Layer-2 behavior this never even reaches the Supervisor."""
    response = _proposal_response()
    candidate, run_output = await run_planner_first_live_turn(
        database=object(),
        agent_context_pack=object(),
        user_message="Import my transcript",
        user_id="u1",
        conversation_id="c1",
        run_id="r1",
        workflow_name="transcript_import_workflow",
        planner_output=_plan(capability_name="transcript_import_workflow"),
        settings=Settings(AGENT_SUPERVISOR_REAL_HANDLERS_ENABLED=True),
        workflow_lookup=lambda name: _FakeReadOnlyWorkflow(response),
    )
    assert candidate is None
    assert run_output is None


@pytest.mark.asyncio
async def test_run_returns_candidate_with_single_proposed_action_when_opted_in() -> None:
    response = _proposal_response()
    candidate, run_output = await run_planner_first_live_turn(
        database=object(),
        agent_context_pack=object(),
        user_message="Import my transcript",
        user_id="u1",
        conversation_id="c1",
        run_id="r1",
        workflow_name="transcript_import_workflow",
        planner_output=_plan(capability_name="transcript_import_workflow"),
        settings=Settings(AGENT_SUPERVISOR_REAL_HANDLERS_ENABLED=True),
        workflow_lookup=lambda name: _FakeReadOnlyWorkflow(response),
        allow_single_proposed_action=True,
    )
    assert candidate is response
    assert candidate.proposed_actions
    assert run_output is not None
    assert run_output.status in {"completed", "completed_with_warnings"}


@pytest.mark.asyncio
async def test_run_still_rejects_two_proposed_actions_even_when_opted_in() -> None:
    response = _proposal_response(
        proposed_actions=[
            ProposedAction(id="a1", action_type="import_completed_courses", label="Import", title="Import 1"),
            ProposedAction(id="a2", action_type="import_completed_courses", label="Import 2", title="Import 2"),
        ]
    )
    candidate, run_output = await run_planner_first_live_turn(
        database=object(),
        agent_context_pack=object(),
        user_message="Import my transcript",
        user_id="u1",
        conversation_id="c1",
        run_id="r1",
        workflow_name="transcript_import_workflow",
        planner_output=_plan(capability_name="transcript_import_workflow"),
        settings=Settings(AGENT_SUPERVISOR_REAL_HANDLERS_ENABLED=True),
        workflow_lookup=lambda name: _FakeReadOnlyWorkflow(response),
        allow_single_proposed_action=True,
    )
    assert candidate is None
    assert run_output is not None


# ---------------------------------------------------------------------------
# Layer 2 -- genuine multi-subtask live dispatch.
# ---------------------------------------------------------------------------


def _multi_plan(*, capability_names: list[str]) -> dict:
    return {
        "status": "completed",
        "plan_id": "plan-live-multi",
        "user_goal": "test",
        "execution_mode": "multi_capability_graph",
        "recommended_autonomy_level": 3,
        "primary_intent": "graduation_progress_check",
        "subtasks": [
            {
                "id": f"run_{name}",
                "title": f"Run {name}",
                "kind": "analyze",
                "capability_name": name,
                "objective": "test",
                "depends_on": [],
                "required_context_sections": ["user_message"],
            }
            for name in capability_names
        ],
        "decision_summary": "test",
        "confidence": 0.85,
    }


def _dispatching_workflow_lookup(responses: dict[str, AgentResponse]):
    def _lookup(name: str):
        return _FakeReadOnlyWorkflow(responses[name])

    return _lookup


_MULTI_CAPABILITY_SETTINGS = Settings(
    AGENT_SUPERVISOR_REAL_HANDLERS_ENABLED=True,
    AGENT_PLANNER_FIRST_LIVE_MULTI_CAPABILITY_ENABLED=True,
)


@pytest.mark.asyncio
async def test_multi_capability_plan_dispatches_both_for_real_and_combines_response() -> None:
    responses = {
        "graduation_progress_workflow": _response(text="You need 3 more credits."),
        "course_question_workflow": _response(text="Yes, you can take 234218 next semester."),
    }
    candidate, run_output = await run_planner_first_live_turn(
        database=object(),
        agent_context_pack=object(),
        user_message="What am I missing, and can I take 234218?",
        user_id="u1",
        conversation_id="c1",
        run_id="r1",
        workflow_name="graduation_progress_workflow",
        planner_output=_multi_plan(
            capability_names=["graduation_progress_workflow", "course_question_workflow"]
        ),
        settings=_MULTI_CAPABILITY_SETTINGS,
        workflow_lookup=_dispatching_workflow_lookup(responses),
    )
    assert candidate is not None
    assert "You need 3 more credits." in candidate.text
    assert "Yes, you can take 234218 next semester." in candidate.text
    assert run_output is not None
    assert sorted(run_output.diagnostics.get("realCapabilityNames") or []) == [
        "course_question_workflow",
        "graduation_progress_workflow",
    ]


@pytest.mark.asyncio
async def test_multi_capability_plan_degrades_gracefully_for_unapproved_capability() -> None:
    """`general_academic_workflow` is never eligible for Planner-first-live
    (hard-excluded, see module docstring) -- alongside an eligible capability
    in the same plan, the run must still complete and surface the eligible
    one's real response, not abort the whole turn."""
    responses = {
        "graduation_progress_workflow": _response(text="You need 3 more credits."),
    }
    candidate, run_output = await run_planner_first_live_turn(
        database=object(),
        agent_context_pack=object(),
        user_message="What am I missing to graduate?",
        user_id="u1",
        conversation_id="c1",
        run_id="r1",
        workflow_name="graduation_progress_workflow",
        planner_output=_multi_plan(
            capability_names=["graduation_progress_workflow", "general_academic_workflow"]
        ),
        settings=_MULTI_CAPABILITY_SETTINGS,
        workflow_lookup=_dispatching_workflow_lookup(responses),
    )
    assert candidate is not None
    assert candidate.text == "You need 3 more credits."
    assert run_output is not None
    assert not run_output.failed_subtasks
    assert not run_output.skipped_subtasks
    assert run_output.diagnostics.get("realCapabilityNames") == ["graduation_progress_workflow"]


@pytest.mark.asyncio
async def test_multi_capability_plan_aborts_when_total_proposed_actions_exceed_one() -> None:
    """Two different proposal-eligible capabilities each producing exactly
    one proposed action -- 2 total, plan-wide -- must still be rejected."""
    responses = {
        "transcript_import_workflow": _proposal_response(
            text="Draft transcript import.",
            proposed_actions=[
                ProposedAction(
                    id="a1", action_type="import_completed_courses", label="Import", title="Import transcript"
                )
            ],
        ),
        "semester_planning_workflow": _proposal_response(
            text="Draft semester plan.",
            proposed_actions=[
                ProposedAction(id="a2", action_type="save_semester_plan", label="Save", title="Save plan")
            ],
        ),
    }
    candidate, run_output = await run_planner_first_live_turn(
        database=object(),
        agent_context_pack=object(),
        user_message="Import my transcript and plan next semester",
        user_id="u1",
        conversation_id="c1",
        run_id="r1",
        workflow_name="transcript_import_workflow",
        planner_output=_multi_plan(
            capability_names=["transcript_import_workflow", "semester_planning_workflow"]
        ),
        settings=_MULTI_CAPABILITY_SETTINGS,
        workflow_lookup=_dispatching_workflow_lookup(responses),
        allow_single_proposed_action=True,
    )
    assert candidate is None
    assert run_output is not None


@pytest.mark.asyncio
async def test_multi_capability_plan_aborts_whole_turn_on_mid_plan_failure() -> None:
    """One real subtask failing alongside one that would have succeeded --
    conservative choice: abort the whole turn, never compose a partial
    response from whichever subtasks did succeed."""

    def _lookup(name: str):
        if name == "course_question_workflow":
            return _FailingSubtaskWorkflow()
        return _FakeReadOnlyWorkflow(_response(text="You need 3 more credits."))

    candidate, run_output = await run_planner_first_live_turn(
        database=object(),
        agent_context_pack=object(),
        user_message="What am I missing, and can I take 234218?",
        user_id="u1",
        conversation_id="c1",
        run_id="r1",
        workflow_name="graduation_progress_workflow",
        planner_output=_multi_plan(
            capability_names=["graduation_progress_workflow", "course_question_workflow"]
        ),
        settings=_MULTI_CAPABILITY_SETTINGS,
        workflow_lookup=_lookup,
    )
    assert candidate is None
    assert run_output is not None
    assert run_output.failed_subtasks


@pytest.mark.asyncio
async def test_multi_capability_disabled_by_default_dispatches_only_primary_workflow() -> None:
    """`AGENT_PLANNER_FIRST_LIVE_MULTI_CAPABILITY_ENABLED` defaults `False` --
    a genuinely 2-eligible-capability plan still only dispatches the primary
    `workflow_name`, byte-for-byte pre-Layer-2 behavior."""
    responses = {
        "graduation_progress_workflow": _response(text="You need 3 more credits."),
        "course_question_workflow": _response(text="Yes, you can take 234218 next semester."),
    }
    candidate, run_output = await run_planner_first_live_turn(
        database=object(),
        agent_context_pack=object(),
        user_message="What am I missing, and can I take 234218?",
        user_id="u1",
        conversation_id="c1",
        run_id="r1",
        workflow_name="graduation_progress_workflow",
        planner_output=_multi_plan(
            capability_names=["graduation_progress_workflow", "course_question_workflow"]
        ),
        settings=Settings(AGENT_SUPERVISOR_REAL_HANDLERS_ENABLED=True),
        workflow_lookup=_dispatching_workflow_lookup(responses),
    )
    assert candidate is not None
    assert candidate.text == "You need 3 more credits."
    assert "Yes, you can take 234218 next semester." not in candidate.text
    assert run_output is not None
    assert run_output.diagnostics.get("realCapabilityNames") == ["graduation_progress_workflow"]


# ---------------------------------------------------------------------------
# Layer 3 -- specialist agents as first-class live dispatch targets.
# ---------------------------------------------------------------------------


def _specialist_output(**overrides) -> SpecialistAgentOutput:
    defaults = dict(
        status="completed",
        agent_name="graduation_progress_agent",
        subtask_id="run_graduation_progress_agent",
        decision_summary="You still need 40 credits.",
        confidence=0.9,
        result={"answer_text": "You still need 40 credits."},
    )
    defaults.update(overrides)
    return SpecialistAgentOutput(**defaults)


def _fake_specialist_registry(outputs: dict[str, SpecialistAgentOutput]) -> SpecialistAgentRegistry:
    registry = SpecialistAgentRegistry()

    def _make_fn(output: SpecialistAgentOutput):
        async def _fn(specialist_input, **_kwargs):
            return output

        return _fn

    for name, output in outputs.items():
        registry.register(name, _make_fn(output))
    return registry


def _combined_manifest_path(tmp_path: Path) -> str:
    manifest = {
        "schemaVersion": "1",
        "reviewedAt": "2026-07-06T00:00:00Z",
        "reviewedBy": "human",
        "candidates": [
            {
                "candidateId": "planner_first_live.course_question_workflow",
                "level": "ready_for_broader_promotion",
                "approved": True,
                "scope": ["course_question_workflow"],
                "expiresAt": "2099-01-01T00:00:00Z",
            },
            {
                "candidateId": "planner_first_live_specialist.graduation_progress_agent",
                "level": "ready_for_broader_promotion",
                "approved": True,
                "scope": ["graduation_progress_agent"],
                "expiresAt": "2099-01-01T00:00:00Z",
            },
        ],
    }
    path = tmp_path / "combined_manifest.json"
    path.write_text(json.dumps(manifest), encoding="utf-8")
    return str(path)


def _specialist_settings(tmp_path: Path) -> Settings:
    return Settings(
        **{
            "AGENT_SUPERVISOR_REAL_HANDLERS_ENABLED": True,
            "AGENT_PLANNER_FIRST_LIVE_MULTI_CAPABILITY_ENABLED": True,
            "AGENT_PLANNER_FIRST_LIVE_ENABLED": True,
            "AGENT_PLANNER_FIRST_LIVE_WORKFLOWS": "course_question_workflow",
            "AGENT_PLANNER_FIRST_LIVE_SPECIALIST_AGENTS_ENABLED": True,
            "AGENT_PLANNER_FIRST_LIVE_SPECIALIST_AGENTS": "graduation_progress_agent",
            "AGENT_RUNTIME_READINESS_GATE_ENABLED": True,
            "AGENT_RUNTIME_READINESS_MANIFEST_PATH": _combined_manifest_path(tmp_path),
        }
    )


@pytest.mark.asyncio
async def test_specialist_agent_dispatches_alongside_workflow_and_combines_response(tmp_path: Path) -> None:
    workflow_responses = {"course_question_workflow": _response(text="Yes, you can take 234218 next semester.")}
    specialist_outputs = {"graduation_progress_agent": _specialist_output()}

    candidate, run_output = await run_planner_first_live_turn(
        database=object(),
        agent_context_pack=object(),
        user_message="What am I missing, and can I take 234218?",
        user_id="u1",
        conversation_id="c1",
        run_id="r1",
        workflow_name="course_question_workflow",
        planner_output=_multi_plan(
            capability_names=["course_question_workflow", "graduation_progress_agent"]
        ),
        settings=_specialist_settings(tmp_path),
        workflow_lookup=_dispatching_workflow_lookup(workflow_responses),
        specialist_registry=_fake_specialist_registry(specialist_outputs),
    )

    assert candidate is not None
    assert "Yes, you can take 234218 next semester." in candidate.text
    assert "You still need 40 credits." in candidate.text
    assert run_output is not None
    assert sorted(run_output.diagnostics.get("realCapabilityNames") or []) == [
        "course_question_workflow",
        "graduation_progress_agent",
    ]


@pytest.mark.asyncio
async def test_specialist_agent_output_failing_mapper_gates_degrades_gracefully(tmp_path: Path) -> None:
    """A specialist subtask whose output never populates `answer_text` must
    not be captured -- but the subtask itself still completes normally, so
    the plan still surfaces the workflow's real response rather than
    aborting the whole turn."""
    workflow_responses = {"course_question_workflow": _response(text="Yes, you can take 234218 next semester.")}
    specialist_outputs = {"graduation_progress_agent": _specialist_output(result={})}

    candidate, run_output = await run_planner_first_live_turn(
        database=object(),
        agent_context_pack=object(),
        user_message="What am I missing, and can I take 234218?",
        user_id="u1",
        conversation_id="c1",
        run_id="r1",
        workflow_name="course_question_workflow",
        planner_output=_multi_plan(
            capability_names=["course_question_workflow", "graduation_progress_agent"]
        ),
        settings=_specialist_settings(tmp_path),
        workflow_lookup=_dispatching_workflow_lookup(workflow_responses),
        specialist_registry=_fake_specialist_registry(specialist_outputs),
    )

    assert candidate is not None
    assert candidate.text == "Yes, you can take 234218 next semester."
    assert run_output is not None
    assert not run_output.failed_subtasks
    assert not run_output.skipped_subtasks
    assert run_output.diagnostics.get("realCapabilityNames") == ["course_question_workflow"]


@pytest.mark.asyncio
async def test_specialist_only_plan_dispatches_nothing_when_multi_capability_disabled(tmp_path: Path) -> None:
    """No legacy notion of a specialist being "the" primary capability the
    way a workflow is -- a specialist-only-eligible plan must dispatch
    nothing extra (and here, nothing at all) when multi-capability mode is
    off, regardless of how eligible the specialist itself is."""
    settings_dict = {
        "AGENT_SUPERVISOR_REAL_HANDLERS_ENABLED": True,
        "AGENT_PLANNER_FIRST_LIVE_MULTI_CAPABILITY_ENABLED": False,
        "AGENT_PLANNER_FIRST_LIVE_SPECIALIST_AGENTS_ENABLED": True,
        "AGENT_PLANNER_FIRST_LIVE_SPECIALIST_AGENTS": "graduation_progress_agent",
        "AGENT_RUNTIME_READINESS_GATE_ENABLED": True,
        "AGENT_RUNTIME_READINESS_MANIFEST_PATH": _combined_manifest_path(tmp_path),
    }
    specialist_outputs = {"graduation_progress_agent": _specialist_output()}

    candidate, run_output = await run_planner_first_live_turn(
        database=object(),
        agent_context_pack=object(),
        user_message="What am I missing to graduate?",
        user_id="u1",
        conversation_id="c1",
        run_id="r1",
        workflow_name="graduation_progress_workflow",
        planner_output=_multi_plan(capability_names=["graduation_progress_agent"]),
        settings=Settings(**settings_dict),
        specialist_registry=_fake_specialist_registry(specialist_outputs),
    )

    assert candidate is None
    assert run_output is None
