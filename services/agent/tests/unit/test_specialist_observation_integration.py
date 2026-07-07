"""Unit tests for the Phase 12 specialist-agent <-> observation-layer wiring.

Uses a fake `SpecialistAgentRegistry` entry (no real `ReasoningBlock`/LLM
call) exercised through the real `SpecialistAgentHandler`, exactly like
`tests/unit/test_specialist_agent_handler.py`.
"""

from __future__ import annotations

from typing import Any

import pytest

from app.agent.capabilities.default_registry import build_default_capability_registry
from app.agent.context_compiler.schemas import CompiledContext
from app.agent.planner.schemas import PlannerSubtask
from app.agent.reasoning.prompt_registry import (
    SPECIALIST_COURSE_CATALOG_V1,
    SPECIALIST_GRADUATION_PROGRESS_V1,
    SPECIALIST_REQUIREMENT_EXPLANATION_V1,
    build_default_prompt_registry,
)
from app.agent.schemas import AgentContextPack
from app.agent.specialists.registry import SpecialistAgentRegistry
from app.agent.specialists.schemas import SpecialistAgentInput, SpecialistAgentOutput
from app.agent.specialists.supervisor_handler import SpecialistAgentHandler
from app.agent.supervisor.blackboard import SupervisorBlackboard
from app.agent.supervisor.schemas import SubtaskResult, SupervisorRuntimeContext
from app.config import Settings

_ENABLED_NO_OBSERVATIONS = Settings(AGENT_SPECIALIST_AGENTS_ENABLED=True, AGENT_SPECIALIST_OBSERVATIONS_ENABLED=False)
_ENABLED_WITH_OBSERVATIONS = Settings(AGENT_SPECIALIST_AGENTS_ENABLED=True, AGENT_SPECIALIST_OBSERVATIONS_ENABLED=True)


def _subtask(**overrides) -> PlannerSubtask:
    defaults = dict(
        id="check_progress",
        title="Check graduation progress",
        kind="analyze",
        capability_name="graduation_progress_agent",
        objective="Determine remaining requirements toward graduation.",
        depends_on=[],
        success_criteria=["Summarize progress"],
        validation_requirements=["Use only compiled context"],
    )
    defaults.update(overrides)
    return PlannerSubtask(**defaults)


def _compiled_context(**overrides) -> CompiledContext:
    defaults = dict(
        capability_name="graduation_progress_agent",
        objective="Determine remaining requirements toward graduation.",
        context={"user_message": "What am I missing to graduate?"},
        included_sections=["user_message"],
    )
    defaults.update(overrides)
    return CompiledContext(**defaults)


def _blackboard() -> SupervisorBlackboard:
    return SupervisorBlackboard(original_user_message="What am I missing to graduate?")


def _pack(**overrides) -> AgentContextPack:
    defaults = dict(conversation_id="c1", run_id="r1", user_id="u1", intent="graduation_progress_check")
    defaults.update(overrides)
    return AgentContextPack(**defaults)


class FakeSpecialistRegistry(SpecialistAgentRegistry):
    def __init__(self, fn) -> None:
        super().__init__()
        self.register("graduation_progress_agent", fn)


def _fake_specialist_fn(output: SpecialistAgentOutput | None = None):
    calls: list[SpecialistAgentInput] = []

    async def _fn(specialist_input: SpecialistAgentInput, **_kwargs: Any) -> SpecialistAgentOutput:
        calls.append(specialist_input)
        assert output is not None
        return output

    _fn.calls = calls  # type: ignore[attr-defined]
    return _fn


def _output(**overrides) -> SpecialistAgentOutput:
    defaults = dict(
        status="completed",
        agent_name="graduation_progress_agent",
        subtask_id="check_progress",
        decision_summary="You still need 40 credits.",
        confidence=0.9,
    )
    defaults.update(overrides)
    return SpecialistAgentOutput(**defaults)


def _handler(*, specialist_fn=None, settings: Settings) -> SpecialistAgentHandler:
    specialist_registry = FakeSpecialistRegistry(specialist_fn or _fake_specialist_fn(_output()))
    return SpecialistAgentHandler(
        specialist_registry=specialist_registry,
        capability_registry=build_default_capability_registry(),
        settings=settings,
    )


# ---------------------------------------------------------------------------
# 1. Observations disabled preserves Phase 10 input shape.
# ---------------------------------------------------------------------------


async def test_observations_disabled_preserves_phase10_input_shape() -> None:
    fn = _fake_specialist_fn(_output())
    handler = _handler(specialist_fn=fn, settings=_ENABLED_NO_OBSERVATIONS)

    result = await handler.run(
        subtask=_subtask(), compiled_context=_compiled_context(), blackboard=_blackboard(), dry_run=True
    )

    assert fn.calls[0].deterministic_observations == []
    assert set(result.output_summary) == {
        "agentName",
        "status",
        "confidence",
        "keyFindingCount",
        "warningCount",
        "sourceCount",
        "missingContextCount",
        "hasProposedActions",
        "resultKeys",
        "decisionSummaryPreview",
    }


# ---------------------------------------------------------------------------
# 2. Observations enabled passes deterministic_observations to specialist.
# ---------------------------------------------------------------------------


async def test_observations_enabled_passes_deterministic_observations_to_specialist() -> None:
    fn = _fake_specialist_fn(_output())
    handler = _handler(specialist_fn=fn, settings=_ENABLED_WITH_OBSERVATIONS)
    pack = _pack(user_context={"profile": {"degreeProgram": "BSc"}})
    runtime_context = SupervisorRuntimeContext(agent_context_pack=pack)

    await handler.run(
        subtask=_subtask(),
        compiled_context=_compiled_context(),
        blackboard=_blackboard(),
        dry_run=True,
        runtime_context=runtime_context,
    )

    observations = fn.calls[0].deterministic_observations
    assert observations != []
    names = {obs.name for obs in observations}
    assert "profile_summary" in names
    profile_obs = next(obs for obs in observations if obs.name == "profile_summary")
    assert profile_obs.status == "available"
    assert profile_obs.summary["degreeProgram"] == "BSc"


async def test_observations_enabled_without_pack_still_returns_missing_observations() -> None:
    fn = _fake_specialist_fn(_output())
    handler = _handler(specialist_fn=fn, settings=_ENABLED_WITH_OBSERVATIONS)

    await handler.run(
        subtask=_subtask(), compiled_context=_compiled_context(), blackboard=_blackboard(), dry_run=True
    )

    observations = fn.calls[0].deterministic_observations
    assert observations != []
    assert all(obs.status in ("missing", "available") for obs in observations)


# ---------------------------------------------------------------------------
# 3. Specialist prompt contract includes observation instructions.
# ---------------------------------------------------------------------------


@pytest.mark.parametrize(
    "contract_name",
    [SPECIALIST_GRADUATION_PROGRESS_V1, SPECIALIST_COURSE_CATALOG_V1, SPECIALIST_REQUIREMENT_EXPLANATION_V1],
)
def test_specialist_prompt_contract_includes_observation_instructions(contract_name: str) -> None:
    contract = build_default_prompt_registry().get(contract_name)
    combined = " ".join(contract.instructions).lower()

    assert "deterministic_observations as trusted read-only observations" in combined
    assert "prefer the deterministic" in combined
    assert "do not invent observations" in combined
    assert "do not request unavailable tools" in combined


# ---------------------------------------------------------------------------
# 4. Observation names appear in compact result summary.
# ---------------------------------------------------------------------------


async def test_observation_names_appear_in_compact_result_summary() -> None:
    fn = _fake_specialist_fn(_output())
    handler = _handler(specialist_fn=fn, settings=_ENABLED_WITH_OBSERVATIONS)
    pack = _pack(user_context={"profile": {"degreeProgram": "BSc"}})
    runtime_context = SupervisorRuntimeContext(agent_context_pack=pack)

    result = await handler.run(
        subtask=_subtask(),
        compiled_context=_compiled_context(),
        blackboard=_blackboard(),
        dry_run=True,
        runtime_context=runtime_context,
    )

    assert "observationCount" in result.output_summary
    assert "observationNames" in result.output_summary
    assert "profile_summary" in result.output_summary["observationNames"]
    assert result.output_summary["observationCount"] >= 1
    assert "observationWarningCount" in result.output_summary
    assert "missingObservationCount" in result.output_summary


# ---------------------------------------------------------------------------
# 5. Raw observation content is not stored in SubtaskResult.
# ---------------------------------------------------------------------------


async def test_raw_observation_content_not_stored_in_subtask_result() -> None:
    fn = _fake_specialist_fn(_output())
    handler = _handler(specialist_fn=fn, settings=_ENABLED_WITH_OBSERVATIONS)
    pack = _pack(user_context={"profile": {"degreeProgram": "BSc", "track": "very-specific-secret-track"}})
    runtime_context = SupervisorRuntimeContext(agent_context_pack=pack)

    result = await handler.run(
        subtask=_subtask(),
        compiled_context=_compiled_context(),
        blackboard=_blackboard(),
        dry_run=True,
        runtime_context=runtime_context,
    )

    summary_text = str(result.output_summary)
    assert "very-specific-secret-track" not in summary_text
    assert "summary" not in result.output_summary  # no raw per-observation summary dict


# ---------------------------------------------------------------------------
# 6. Observation builder failure does not break specialist handler.
# ---------------------------------------------------------------------------


async def test_observation_builder_failure_does_not_break_specialist_handler(monkeypatch) -> None:
    from app.agent.specialists import supervisor_handler as supervisor_handler_module

    def _boom(*_args, **_kwargs):
        raise RuntimeError("boom")

    monkeypatch.setattr(supervisor_handler_module, "build_specialist_observations", _boom)

    fn = _fake_specialist_fn(_output())
    handler = _handler(specialist_fn=fn, settings=_ENABLED_WITH_OBSERVATIONS)

    result = await handler.run(
        subtask=_subtask(), compiled_context=_compiled_context(), blackboard=_blackboard(), dry_run=True
    )

    assert isinstance(result, SubtaskResult)
    assert result.status == "completed"
    assert fn.calls[0].deterministic_observations == []


# ---------------------------------------------------------------------------
# 7. Specialist still strips proposed_actions.
# ---------------------------------------------------------------------------


async def test_specialist_still_strips_proposed_actions_with_observations_enabled() -> None:
    output = _output(proposed_actions=[{"actionType": "save_semester_plan"}])
    handler = _handler(specialist_fn=_fake_specialist_fn(output), settings=_ENABLED_WITH_OBSERVATIONS)

    result = await handler.run(
        subtask=_subtask(), compiled_context=_compiled_context(), blackboard=_blackboard(), dry_run=True
    )

    assert result.output_summary["hasProposedActions"] is False


# ---------------------------------------------------------------------------
# 8. Specialist output still not promotable.
# ---------------------------------------------------------------------------


def test_specialist_output_still_not_promotable_with_observations_enabled() -> None:
    from app.agent.supervisor.promotion import eligible_promotion_workflows

    settings = Settings(
        AGENT_SPECIALIST_AGENTS_ENABLED=True,
        AGENT_SPECIALIST_OBSERVATIONS_ENABLED=True,
        AGENT_SUPERVISOR_PROMOTION_ENABLED=True,
        AGENT_SUPERVISOR_PROMOTION_MODE="promote_validated",
        AGENT_SUPERVISOR_PROMOTION_WORKFLOWS=(
            "graduation_progress_workflow,graduation_progress_agent,course_catalog_agent"
        ),
    )

    eligible = eligible_promotion_workflows(settings)

    assert eligible == {"graduation_progress_workflow"}
    assert "graduation_progress_agent" not in eligible
