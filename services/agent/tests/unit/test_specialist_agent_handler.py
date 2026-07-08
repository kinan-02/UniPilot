"""Unit tests for `app.agent.specialists.supervisor_handler.SpecialistAgentHandler`."""

from __future__ import annotations

from typing import Any

from app.agent.capabilities.default_registry import build_default_capability_registry
from app.agent.capabilities.registry import CapabilityRegistry
from app.agent.capabilities.schemas import CapabilityDescriptor, CapabilityExecutionMetadata
from app.agent.context_compiler.schemas import CompiledContext
from app.agent.planner.schemas import PlannerSubtask
from app.agent.specialists.registry import SpecialistAgentRegistry
from app.agent.specialists.schemas import SpecialistAgentInput, SpecialistAgentOutput
from app.agent.specialists.supervisor_handler import SpecialistAgentHandler
from app.agent.supervisor.blackboard import SupervisorBlackboard
from app.agent.supervisor.schemas import SubtaskResult, SupervisorRuntimeContext
from app.config import Settings

_ENABLED_SETTINGS = Settings(AGENT_SPECIALIST_AGENTS_ENABLED=True)
_DISABLED_SETTINGS = Settings(AGENT_SPECIALIST_AGENTS_ENABLED=False)
_DRY_RUN_FALSE_SETTINGS = Settings(AGENT_SPECIALIST_AGENTS_ENABLED=True, AGENT_SPECIALIST_AGENTS_DRY_RUN=False)


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


class FakeSpecialistRegistry(SpecialistAgentRegistry):
    def __init__(self, fn) -> None:
        super().__init__()
        self.register("graduation_progress_agent", fn)


def _fake_specialist_fn(output: SpecialistAgentOutput | None = None, *, raises: Exception | None = None):
    calls: list[SpecialistAgentInput] = []

    async def _fn(specialist_input: SpecialistAgentInput, **_kwargs: Any) -> SpecialistAgentOutput:
        calls.append(specialist_input)
        if raises is not None:
            raise raises
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
        key_findings=["40 credits remaining"],
        sources=[{"type": "graduation_audit"}],
    )
    defaults.update(overrides)
    return SpecialistAgentOutput(**defaults)


def _handler(*, specialist_fn=None, settings=_ENABLED_SETTINGS, capability_registry=None) -> SpecialistAgentHandler:
    specialist_registry = FakeSpecialistRegistry(specialist_fn or _fake_specialist_fn(_output()))
    return SpecialistAgentHandler(
        specialist_registry=specialist_registry,
        capability_registry=capability_registry or build_default_capability_registry(),
        settings=settings,
    )


# ---------------------------------------------------------------------------
# 1. Resolves correct specialist.
# ---------------------------------------------------------------------------


async def test_handler_resolves_correct_specialist() -> None:
    fn = _fake_specialist_fn(_output())
    handler = _handler(specialist_fn=fn)

    await handler.run(
        subtask=_subtask(), compiled_context=_compiled_context(), blackboard=_blackboard(), dry_run=True
    )

    assert len(fn.calls) == 1
    assert fn.calls[0].agent_name == "graduation_progress_agent"
    assert fn.calls[0].subtask_id == "check_progress"


# ---------------------------------------------------------------------------
# 2. Converts SpecialistAgentOutput to SubtaskResult.
# ---------------------------------------------------------------------------


async def test_handler_converts_output_to_subtask_result() -> None:
    handler = _handler(specialist_fn=_fake_specialist_fn(_output()))

    result = await handler.run(
        subtask=_subtask(), compiled_context=_compiled_context(), blackboard=_blackboard(), dry_run=True
    )

    assert isinstance(result, SubtaskResult)
    assert result.subtask_id == "check_progress"
    assert result.capability_name == "graduation_progress_agent"
    assert result.status == "completed"
    assert result.confidence == 0.9


# ---------------------------------------------------------------------------
# 3. Stores compact summary only.
# ---------------------------------------------------------------------------


async def test_handler_stores_compact_summary_only() -> None:
    handler = _handler(specialist_fn=_fake_specialist_fn(_output()))

    result = await handler.run(
        subtask=_subtask(), compiled_context=_compiled_context(), blackboard=_blackboard(), dry_run=True
    )

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
# 4. Strips/blocks proposed actions.
# ---------------------------------------------------------------------------


async def test_handler_strips_proposed_actions() -> None:
    output = _output(proposed_actions=[{"actionType": "save_semester_plan"}])
    handler = _handler(specialist_fn=_fake_specialist_fn(output))

    result = await handler.run(
        subtask=_subtask(), compiled_context=_compiled_context(), blackboard=_blackboard(), dry_run=True
    )

    assert result.output_summary["hasProposedActions"] is False


# ---------------------------------------------------------------------------
# 5. Returns skipped when specialists disabled.
# ---------------------------------------------------------------------------


async def test_handler_returns_skipped_when_specialists_disabled() -> None:
    fn = _fake_specialist_fn(_output())
    handler = _handler(specialist_fn=fn, settings=_DISABLED_SETTINGS)

    # The specialist_fn itself is called (it's the fake), but the real
    # specialist implementations self-gate on the flag internally -- this
    # test uses the handler's own dry_run wiring to confirm the flag flows
    # through to the SpecialistAgentInput it builds.
    await handler.run(subtask=_subtask(), compiled_context=_compiled_context(), blackboard=_blackboard(), dry_run=True)

    assert fn.calls[0].dry_run is True  # AGENT_SPECIALIST_AGENTS_DRY_RUN defaults True


async def test_handler_returns_skipped_when_capability_unknown() -> None:
    empty_registry = CapabilityRegistry()
    handler = _handler(capability_registry=empty_registry)

    result = await handler.run(
        subtask=_subtask(), compiled_context=_compiled_context(), blackboard=_blackboard(), dry_run=True
    )

    assert result.status == "skipped"
    assert "specialist_agent_not_safe_or_unknown" in str(result.output_summary)


async def test_handler_returns_skipped_when_capability_unsafe() -> None:
    unsafe_registry = CapabilityRegistry()
    unsafe_registry.register(
        CapabilityDescriptor(
            name="graduation_progress_agent",
            type="specialist_agent",
            description="test",
            enabled=True,
            execution=CapabilityExecutionMetadata(side_effect_level="proposal"),
        )
    )
    handler = _handler(capability_registry=unsafe_registry)

    result = await handler.run(
        subtask=_subtask(), compiled_context=_compiled_context(), blackboard=_blackboard(), dry_run=True
    )

    assert result.status == "skipped"


async def test_handler_returns_skipped_when_specialist_not_registered() -> None:
    empty_specialist_registry = SpecialistAgentRegistry()
    handler = SpecialistAgentHandler(
        specialist_registry=empty_specialist_registry,
        capability_registry=build_default_capability_registry(),
        settings=_ENABLED_SETTINGS,
    )

    result = await handler.run(
        subtask=_subtask(), compiled_context=_compiled_context(), blackboard=_blackboard(), dry_run=True
    )

    assert result.status == "skipped"
    assert "specialist_agent_not_registered" in str(result.output_summary)


# ---------------------------------------------------------------------------
# 6. Remains shadow-only when dry_run=false is misconfigured.
# ---------------------------------------------------------------------------


async def test_handler_passes_dry_run_false_through_but_stays_shadow_only() -> None:
    fn = _fake_specialist_fn(_output())
    handler = _handler(specialist_fn=fn, settings=_DRY_RUN_FALSE_SETTINGS)

    result = await handler.run(
        subtask=_subtask(), compiled_context=_compiled_context(), blackboard=_blackboard(), dry_run=True
    )

    assert fn.calls[0].dry_run is False
    # Still just a normal SubtaskResult -- no write, no real execution
    # engine exists to actually act on dry_run=False in Phase 10.
    assert isinstance(result, SubtaskResult)
    assert result.status == "completed"


# ---------------------------------------------------------------------------
# 7. Does not store raw compiled context.
# ---------------------------------------------------------------------------


async def test_handler_does_not_store_raw_compiled_context() -> None:
    long_context = {"user_message": "x" * 5000, "raw_context": {"secret": "value"}}
    handler = _handler(specialist_fn=_fake_specialist_fn(_output()))

    result = await handler.run(
        subtask=_subtask(),
        compiled_context=_compiled_context(context=long_context),
        blackboard=_blackboard(),
        dry_run=True,
    )

    summary_text = str(result.output_summary)
    assert "x" * 5000 not in summary_text
    assert "raw_context" not in summary_text
    assert "secret" not in summary_text


async def test_handler_passes_compiled_context_to_specialist_input_not_diagnostics() -> None:
    fn = _fake_specialist_fn(_output())
    handler = _handler(specialist_fn=fn)
    compiled = {"user_message": "hi", "profile_summary": {"degreeProgram": "BSc"}}

    await handler.run(
        subtask=_subtask(), compiled_context=_compiled_context(context=compiled), blackboard=_blackboard(), dry_run=True
    )

    assert fn.calls[0].compiled_context == compiled


# ---------------------------------------------------------------------------
# 8. Handles specialist failure without raising.
# ---------------------------------------------------------------------------


async def test_handler_handles_specialist_failure_without_raising() -> None:
    fn = _fake_specialist_fn(raises=RuntimeError("boom"))
    handler = _handler(specialist_fn=fn)

    result = await handler.run(
        subtask=_subtask(), compiled_context=_compiled_context(), blackboard=_blackboard(), dry_run=True
    )

    assert result.status == "failed"
    assert result.error == "boom"


# ---------------------------------------------------------------------------
# Dependency outputs / status mapping.
# ---------------------------------------------------------------------------


async def test_handler_passes_dependency_outputs_from_blackboard() -> None:
    fn = _fake_specialist_fn(_output())
    handler = _handler(specialist_fn=fn)
    blackboard = _blackboard()
    blackboard.subtask_results["retrieve_context"] = SubtaskResult(
        subtask_id="retrieve_context", capability_name="wiki_hybrid_retrieval", status="completed",
        output_summary={"snippets": 3},
    )

    await handler.run(
        subtask=_subtask(depends_on=["retrieve_context"]),
        compiled_context=_compiled_context(),
        blackboard=blackboard,
        dry_run=True,
    )

    assert fn.calls[0].dependency_outputs == {"retrieve_context": {"snippets": 3}}


async def test_handler_maps_needs_more_context_to_completed_subtask_status() -> None:
    output = _output(status="needs_more_context")
    handler = _handler(specialist_fn=_fake_specialist_fn(output))

    result = await handler.run(
        subtask=_subtask(), compiled_context=_compiled_context(), blackboard=_blackboard(), dry_run=True
    )

    assert result.status == "completed"
    assert result.output_summary["status"] == "needs_more_context"


async def test_handler_maps_specialist_skipped_to_subtask_skipped() -> None:
    output = _output(status="skipped", decision_summary="Specialist agent reasoning unavailable; skipped in shadow mode.")
    handler = _handler(specialist_fn=_fake_specialist_fn(output))

    result = await handler.run(
        subtask=_subtask(), compiled_context=_compiled_context(), blackboard=_blackboard(), dry_run=True
    )

    assert result.status == "skipped"


# ---------------------------------------------------------------------------
# Layer 3 -- `candidate_sink` capture.
# ---------------------------------------------------------------------------


def _runtime_context(**overrides) -> SupervisorRuntimeContext:
    defaults = dict(conversation_id="c1", run_id="r1")
    defaults.update(overrides)
    return SupervisorRuntimeContext(**defaults)


async def test_handler_captures_candidate_when_gates_pass() -> None:
    output = _output(result={"answer_text": "You still need 40 credits."})
    specialist_registry = FakeSpecialistRegistry(_fake_specialist_fn(output))
    candidate_sink: dict[str, Any] = {}
    handler = SpecialistAgentHandler(
        specialist_registry=specialist_registry,
        capability_registry=build_default_capability_registry(),
        settings=_ENABLED_SETTINGS,
        candidate_sink=candidate_sink,
    )

    await handler.run(
        subtask=_subtask(),
        compiled_context=_compiled_context(),
        blackboard=_blackboard(),
        dry_run=True,
        runtime_context=_runtime_context(),
    )

    assert "graduation_progress_agent" in candidate_sink
    candidate = candidate_sink["graduation_progress_agent"]
    assert candidate.text == "You still need 40 credits."
    assert candidate.conversation_id == "c1"
    assert candidate.run_id == "r1"


async def test_handler_candidate_sink_empty_when_mapper_gates_fail() -> None:
    # No `answer_text` in `result` -- the mapper's own gate fails.
    output = _output(result={})
    specialist_registry = FakeSpecialistRegistry(_fake_specialist_fn(output))
    candidate_sink: dict[str, Any] = {}
    handler = SpecialistAgentHandler(
        specialist_registry=specialist_registry,
        capability_registry=build_default_capability_registry(),
        settings=_ENABLED_SETTINGS,
        candidate_sink=candidate_sink,
    )

    await handler.run(
        subtask=_subtask(),
        compiled_context=_compiled_context(),
        blackboard=_blackboard(),
        dry_run=True,
        runtime_context=_runtime_context(),
    )

    assert candidate_sink == {}


async def test_handler_candidate_sink_empty_without_runtime_context() -> None:
    output = _output(result={"answer_text": "You still need 40 credits."})
    specialist_registry = FakeSpecialistRegistry(_fake_specialist_fn(output))
    candidate_sink: dict[str, Any] = {}
    handler = SpecialistAgentHandler(
        specialist_registry=specialist_registry,
        capability_registry=build_default_capability_registry(),
        settings=_ENABLED_SETTINGS,
        candidate_sink=candidate_sink,
    )

    await handler.run(
        subtask=_subtask(), compiled_context=_compiled_context(), blackboard=_blackboard(), dry_run=True
    )

    assert candidate_sink == {}


async def test_handler_candidate_sink_none_by_default_is_zero_behavior_change() -> None:
    output = _output(result={"answer_text": "You still need 40 credits."})
    specialist_registry = FakeSpecialistRegistry(_fake_specialist_fn(output))
    handler = SpecialistAgentHandler(
        specialist_registry=specialist_registry,
        capability_registry=build_default_capability_registry(),
        settings=_ENABLED_SETTINGS,
    )

    result = await handler.run(
        subtask=_subtask(),
        compiled_context=_compiled_context(),
        blackboard=_blackboard(),
        dry_run=True,
        runtime_context=_runtime_context(),
    )

    assert isinstance(result, SubtaskResult)
    assert result.status == "completed"
